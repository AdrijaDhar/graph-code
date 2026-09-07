"""Natural-language front door over the graph: "I just indexed a repo, now what do I
query, and how?" is a real, repeatedly-reported gap — autocomplete and starting-point
suggestions (graph_overview/suggest_starting_points) help once you know roughly what
you want, but not a user staring at five query types with no idea which one answers
their actual question.

This module answers a free-text question directly. It does NOT call an external LLM
API (no key to configure, no per-query cost, no network dependency, no rate limit) —
it reuses the same real, pretrained Hugging Face sentence-transformer already loaded
for semantic code search (`sentence-transformers/all-MiniLM-L6-v2`, run locally via
fastembed/ONNX — see embed/encoder.py) to do genuine semantic intent matching: a
question is embedded and compared against a handful of example phrasings per intent,
so "what will I break" and "who relies on this" land on the same intent even though
they share no words. That's the actual difference from a keyword/regex router — this
one generalizes to paraphrases the way a trained model does, not just to string
overlap.
"""

from __future__ import annotations

import re

from graphcode.embed.encoder import cosine, embed_text
from graphcode.indexer import IndexService
from graphcode.loader.memory import MemoryStore
from graphcode.queries.call_chain import call_chain
from graphcode.queries.hybrid import semantic_search
from graphcode.queries.paths import blast_radius, shortest_path
from graphcode.queries.test_impact import find_affected_tests

# A handful of example phrasings per intent, not an exhaustive list — the embedding
# model generalizes from these to paraphrases at query time, so this doesn't need to
# (and shouldn't try to) enumerate every way someone might ask.
_INTENT_EXAMPLES: dict[str, list[str]] = {
    "impact": [
        "what depends on this function",
        "what breaks if I change this",
        "who calls this",
        "what will be affected if I edit this code",
        "show me everything that relies on this symbol",
        "is it safe to modify this",
        "what uses this class",
    ],
    "tests": [
        "what tests cover this function",
        "which tests should I run after changing this",
        "is this code tested",
        "find the tests for this",
        "what test suite exercises this",
    ],
    "path": [
        "how are these two things connected",
        "what is the path between these two functions",
        "how does this function reach that one",
        "are these two classes related",
        "connection between these symbols",
    ],
    "chain": [
        "what happens when this function runs",
        "trace the call chain from this function",
        "show me everything this function eventually calls",
        "what is the execution flow starting here",
        "what does this call downstream",
    ],
    "semantic": [
        "find code that sends an email",
        "where is authentication handled",
        "search for retry logic",
        "find the code that parses configuration files",
        "show me code related to this idea",
    ],
}

# Matches code-identifier-shaped tokens: quoted/backticked, dotted (a.b.c), snake_case,
# or camelCase. Masked out to "this" before intent classification — otherwise a
# question like "what breaks if I change parse_config?" gets pulled toward the
# semantic-search intent just because "parse_config" is lexically close to an example
# like "find code that parses configuration files", drowning out the actual phrasing
# ("what breaks if I change X") that should decide the intent. Entity extraction and
# intent classification need to look at different things, so they're kept separate.
_IDENTIFIER_RE = re.compile(
    r"[`'\"][\w.]+[`'\"]"
    r"|\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z0-9_.]+\b"
    r"|\b[A-Za-z]+_[A-Za-z0-9_]+\b"
    r"|\b[a-z]+[A-Z][A-Za-z0-9]*\b"
)


def _mask_identifiers(text: str) -> str:
    return _IDENTIFIER_RE.sub("this", text)


_anchor_vecs: dict[str, list[list[float]]] | None = None


def _anchors() -> dict[str, list[list[float]]]:
    global _anchor_vecs
    if _anchor_vecs is None:
        _anchor_vecs = {intent: [embed_text(ex) for ex in exs] for intent, exs in _INTENT_EXAMPLES.items()}
    return _anchor_vecs


def classify_intent(text: str) -> tuple[str, float]:
    """Embeds `text` and returns the (intent, similarity) of whichever single anchor
    example it's closest to, across all intents — the best individual match, not an
    averaged centroid per intent, since one good paraphrase match is a stronger signal
    than a mediocre match against every example in a set."""
    qv = embed_text(_mask_identifiers(text))
    best_intent, best_score = "semantic", -1.0
    for intent, vecs in _anchors().items():
        for v in vecs:
            s = cosine(qv, v)
            if s > best_score:
                best_intent, best_score = intent, s
    return best_intent, best_score


# Plain English words that are common enough in real questions to risk a false-
# positive substring match against an unrelated real path/name in a large repo (e.g.
# the verb "change" is a literal substring of a file named "changed-files.ts") — only
# applied to the generic word-splitting fallback below, never to identifier-shaped
# candidates, which are already high-confidence on their own.
_ASK_STOPWORDS = {
    "what", "if", "change", "changed", "changes", "the", "does", "do", "this", "that", "breaks", "break", "who",
    "calls", "call", "depends", "depend", "dependent", "dependents", "on", "is", "are", "related", "relate", "and",
    "between", "path", "connects", "connect", "connection", "how", "tests", "test", "cover", "covers", "for", "of",
    "in", "from", "when", "runs", "run", "trace", "flow", "use", "uses", "used", "by", "with", "affects", "affect",
    "impact", "impacted", "will", "would", "happens", "happen", "function", "class", "file", "code", "find",
    "search", "show", "get", "list", "all", "chain", "deep", "hops", "step", "steps", "its", "there", "here",
    "please", "can", "you", "modify", "editing", "edit", "about", "into", "does", "cover",
}


def _resolve_symbols(store: MemoryStore, text: str, org_id: str | None, limit: int = 2) -> list[dict]:
    """Pulls real, indexed symbols out of free text. Identifier-shaped tokens
    (quoted/backticked, dotted, snake_case, camelCase — see `_IDENTIFIER_RE`) are
    tried first and are near-certain: a plain-English question rarely contains a
    `snake_case` token by accident. Only if none of those resolve does this fall back
    to generic word tokens, filtered against a stopword list — otherwise an ordinary
    verb like "change" can accidentally substring-match an unrelated real path (e.g.
    "changed-files.ts") before the actual symbol later in the sentence is even tried.
    Stops as soon as `limit` distinct symbols are found."""
    identifier_like = [tok.strip("`'\"") for tok in _IDENTIFIER_RE.findall(text)]
    generic = [w for w in re.split(r"[^\w.]+", text) if len(w) > 2 and w.lower() not in _ASK_STOPWORDS]
    seen_cand: set[str] = set()
    candidates: list[str] = []
    for cand in identifier_like + generic:
        if cand.lower() not in seen_cand:
            seen_cand.add(cand.lower())
            candidates.append(cand)

    seen_ids: set[str] = set()
    hits: list[dict] = []
    for cand in candidates:
        for n in store.search(cand, org_id=org_id, limit=3):
            if n.id in seen_ids:
                continue
            seen_ids.add(n.id)
            hits.append({"id": n.id, "label": n.label, **n.props})
            break  # keep only the best match for each candidate word
        if len(hits) >= limit:
            break
    return hits


def _name(rec: dict) -> str:
    return rec.get("qualified_name") or rec.get("name") or rec.get("path") or rec.get("id", "")


def ask(svc: IndexService, text: str, org_id: str | None = None) -> dict:
    """Classifies what's being asked, resolves the real symbol(s) it's about, runs the
    one underlying graph query that actually answers it, and phrases the result back
    as a sentence — the raw result is still returned under `data` so the UI can render
    its existing detailed view (graph, list, etc.) underneath the sentence."""
    intent, score = classify_intent(text)
    symbols = _resolve_symbols(svc.memory, text, org_id)
    names = [_name(s) for s in symbols]

    if intent == "path" and len(names) >= 2:
        data = shortest_path(svc.memory, names[0], names[1], org_id=org_id)
        if data.get("path"):
            steps = " → ".join(_name(n) for n in data["path"])
            hops = data["hops"]
            answer = f"Yes — {hops} hop{'s' if hops != 1 else ''} apart: {steps}"
        else:
            answer = f'No connection found between "{names[0]}" and "{names[1]}" within the search depth.'
        return {"intent": "path", "symbols": names[:2], "confidence": score, "answer": answer, "data": data}

    if intent == "chain" and names:
        data = call_chain(svc.memory, names[0], org_id=org_id)
        n = len(data.get("paths") or [])
        answer = (
            f'"{names[0]}" leads to {n} distinct call chain{"s" if n != 1 else ""}.'
            if n
            else f"\"{names[0]}\" doesn't call anything else that's indexed."
        )
        return {"intent": "chain", "symbols": names[:1], "confidence": score, "answer": answer, "data": data}

    if intent == "tests" and names:
        data = find_affected_tests(svc.memory, names[0], org_id=org_id)
        n = len(data.get("tests") or [])
        answer = (
            f'{n} test{"s" if n != 1 else ""} cover{"s" if n == 1 else ""} "{names[0]}".'
            if n
            else f'No indexed test covers "{names[0]}", even transitively.'
        )
        return {"intent": "tests", "symbols": names[:1], "confidence": score, "answer": answer, "data": data}

    if intent == "impact" and names:
        blast = blast_radius(svc.memory, names[0], direction="upstream", org_id=org_id)
        tests = find_affected_tests(svc.memory, names[0], org_id=org_id)
        dep_count = max(len(blast.get("nodes") or []) - 1, 0)
        test_count = len(tests.get("tests") or [])
        answer = f'"{names[0]}" — {dep_count} thing{"s" if dep_count != 1 else ""} depend on it' + (
            f', covered by {test_count} test{"s" if test_count != 1 else ""}.'
            if test_count
            else ", and no indexed test covers it."
        )
        return {
            "intent": "impact",
            "symbols": names[:1],
            "confidence": score,
            "answer": answer,
            "data": {"blast": blast, "tests": tests},
        }

    # Semantic fallback — either the question was genuinely descriptive ("find code
    # that sends an email"), or nothing in it resolved to a real indexed symbol so
    # there's nothing else left to run.
    data = semantic_search(svc, text, k=8, org_id=org_id or "local")
    hits = data.get("hits") or []
    if hits:
        top = hits[0]
        answer = f'Closest match: "{_name(top)}" (score {top["score"]:.2f}) — {len(hits)} result{"s" if len(hits) != 1 else ""} total.'
    else:
        answer = "Couldn't match that to anything in this repo — try a symbol name, or rephrase what the code does."
    return {"intent": "semantic", "symbols": names, "confidence": score, "answer": answer, "data": data}
