from __future__ import annotations

from pathlib import Path

from graphcode.loader.memory import MemoryStore
from graphcode.queries.call_chain import call_chain
from graphcode.queries.paths import blast_radius, shortest_path


def _tokens(text: str) -> int:
    return max(1, len(text.split()))


def slice_source(root: Path, path: str, start: int, end: int, budget_lines: int = 40) -> str:
    fp = root / path
    if not fp.is_file():
        return ""
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    s = max(start - 1, 0)
    e = min(end, s + budget_lines)
    body = "\n".join(lines[s:e])
    return f"--- {path} (lines {s + 1}–{e}) ---\n{body}\n"


def compile_context(
    store: MemoryStore,
    *,
    root: Path | str | None,
    files: list[str] | None = None,
    symbols: list[str] | None = None,
    prompt: str = "",
    max_tokens: int = 8000,
) -> str:
    root_p = Path(root) if root else None
    keys = list(symbols or []) + list(files or [])
    if not keys and prompt:
        for tok in prompt.replace(",", " ").split():
            if "/" in tok or "." in tok:
                keys.append(tok.strip("`"))
    if not keys:
        return "## Structural Context\nNo files or symbols provided.\n"

    sections: list[str] = []
    used = 0
    primary = keys[0]
    br = blast_radius(store, primary, direction="upstream", max_hops=3)
    sections.append(f"## Structural Context for: {primary}\n")
    up = br.get("nodes") or []
    sections.append(f"### Blast radius (upstream of {primary})\n")
    for n in up[:20]:
        line = f"- [{n.get('label')}] {n.get('qualified_name') or n.get('path')} via {n.get('via', 'origin')}\n"
        sections.append(line)
    if len(keys) >= 2:
        sp = shortest_path(store, keys[0], keys[1])
        sections.append("\n### Dependency path\n")
        for n in sp.get("path") or []:
            via = n.get("via")
            qn = n.get("qualified_name") or n.get("path")
            sections.append(f"{qn}" + (f"  --{via}-->" if via else "") + "\n")
    cc = call_chain(store, primary, max_depth=5)
    sections.append("\n### Call chains\n")
    for path in (cc.get("paths") or [])[:5]:
        names = " → ".join(p.get("name") or p.get("qualified_name", "") for p in path)
        sections.append(f"- {names}\n")

    if root_p:
        sections.append("\n### Relevant signatures and bodies\n")
        seen_paths = set()
        for n in up:
            pth = n.get("path")
            if not pth or pth in seen_paths:
                continue
            seen_paths.add(pth)
            start = int(n.get("start_line") or 1)
            end = int(n.get("end_line") or start + 20)
            chunk = slice_source(root_p, pth, start, end)
            if _tokens("".join(sections) + chunk) > max_tokens:
                qn = n.get("qualified_name") or pth
                sections.append(f"- stub: {qn}\n")
                continue
            sections.append(chunk)

    text = "".join(sections)
    summary = f"\n### Graph summary\n- {len(up) - 1} related nodes within 3 hops\n"
    return text + summary
