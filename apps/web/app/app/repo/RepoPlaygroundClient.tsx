"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Badge,
  Button,
  Card,
  ElapsedTimer,
  EmptyState,
  Input,
  Muted,
  PageHeading,
  SecondaryButton,
  SectionHeading,
  Select,
  Spinner,
  Tabs,
} from "../../components/ui";
import { CodeBlock } from "../../components/CodeBlock";
import { DependencyGraph, type GraphNode } from "../../components/DependencyGraph";
import { GraphOverview, type OverviewNode } from "../../components/GraphOverview";
import { SymbolPicker } from "../../components/SymbolPicker";
import { ExternalLinkIcon, GitBranchIcon, NetworkIcon, RouteIcon, SearchIcon, SparkleIcon, XIcon } from "../../components/Icon";
import { apiFetch } from "../../lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SourceView {
  path: string;
  start: number;
  end: number;
  text: string;
  loading?: boolean;
}

// Blast radius and affected tests both answer the same real question — "tell me
// about this symbol" — so they're one always-visible panel below, not tabs. These
// three are genuinely different questions (compare two symbols, search by meaning,
// trace calls several hops deep), which is why they stay as secondary tabs instead —
// but five equal-weight tabs with no hierarchy was the actual source of "what do I do
// here", confirmed live: it wasn't the labels, it was that nothing said which one
// mattered first.
const SECONDARY_TABS = [
  { id: "path", label: "Shortest path", icon: <RouteIcon className="w-4 h-4" /> },
  { id: "semantic", label: "Semantic search", icon: <SearchIcon className="w-4 h-4" /> },
  { id: "chain", label: "Call chain", icon: <RouteIcon className="w-4 h-4" /> },
];

export default function RepoPlaygroundClient() {
  // Read the repo id from a query param (?id=2) rather than a Next.js dynamic route
  // segment ([id]) — this app builds with `output: "export"`, which requires every
  // dynamic route param to be known at build time via generateStaticParams(). Repo
  // ids are created at runtime as you add repos, so no fixed list could ever cover
  // them (confirmed live: navigating to a real repo id threw exactly this error).
  // A query param on one static page has no such restriction — the id is just read
  // client-side, which is what this page already does for all its data anyway.
  const searchParams = useSearchParams();
  const id = searchParams.get("id") || "";

  const [repo, setRepo] = useState<any>(null);
  const [loadStatus, setLoadStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const [tab, setTab] = useState("path");

  const [symbol, setSymbol] = useState("");
  const [direction, setDirection] = useState("upstream");
  const [blastResult, setBlastResult] = useState<any>(null);
  const [testsResult, setTestsResult] = useState<any>(null);
  const [exploreBusy, setExploreBusy] = useState(false);

  const [fromSymbol, setFromSymbol] = useState("");
  const [toSymbol, setToSymbol] = useState("");
  const [pathResult, setPathResult] = useState<any>(null);
  const [pathBusy, setPathBusy] = useState(false);

  const [query, setQuery] = useState("");
  const [semanticResult, setSemanticResult] = useState<any>(null);
  const [semanticBusy, setSemanticBusy] = useState(false);

  const [chainSymbol, setChainSymbol] = useState("");
  const [chainResult, setChainResult] = useState<any>(null);
  const [chainBusy, setChainBusy] = useState(false);

  const [sourceView, setSourceView] = useState<SourceView | null>(null);

  const [overview, setOverview] = useState<{ nodes: OverviewNode[]; edges: any[] } | null>(null);
  const [overviewBusy, setOverviewBusy] = useState(false);

  const [suggestions, setSuggestions] = useState<any[] | null>(null);
  const [suggestionsBusy, setSuggestionsBusy] = useState(false);

  const [askText, setAskText] = useState("");
  const [askBusy, setAskBusy] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);

  // Clicking a suggestion chip, a codebase-map node, or an Ask example updates a card
  // further down the page — with no visual link between "I clicked something" and
  // "something changed," that update is easy to miss entirely (confirmed live: "does
  // nothing... graph moves a lil but nothing... comes"). Scrolling the relevant card
  // into view on every one of those triggers makes the result impossible to miss.
  const exploreRef = useRef<HTMLDivElement>(null);
  const secondaryRef = useRef<HTMLDivElement>(null);
  function scrollTo(ref: React.RefObject<HTMLDivElement>) {
    setTimeout(() => ref.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  useEffect(() => {
    // Reset all per-repo state on navigation to a different id — this component
    // instance is reused across repos (the route is `/app/repo?id=`, not a fresh
    // page load), so without this, query results, active-graph status, and the
    // source-view panel from a previously-viewed repo would keep showing here.
    setRepo(null);
    setLoadStatus("");
    setIsActive(false);
    setBlastResult(null);
    setTestsResult(null);
    setPathResult(null);
    setSemanticResult(null);
    setChainResult(null);
    setSourceView(null);
    setOverview(null);
    setSuggestions(null);
    if (!id) return;
    apiFetch(`${API}/v1/repos`)
      .then((r) => r.json())
      .then((list) => setRepo((Array.isArray(list) ? list : []).find((r: any) => String(r.id) === id)));
  }, [id]);

  async function loadRepo() {
    setBusy(true);
    setLoadStatus("Cloning/indexing — makes this repo the active graph…");
    setBlastResult(null);
    setTestsResult(null);
    setPathResult(null);
    setSemanticResult(null);
    setChainResult(null);
    setSourceView(null);
    setOverview(null);
    setSuggestions(null);
    try {
      const res = await apiFetch(`${API}/v1/repos/${id}/index`, { method: "POST" });
      if (!res.ok) {
        setLoadStatus(`Failed: ${res.status} ${await res.text()}`);
        setIsActive(false);
      } else {
        const result = await res.json();
        setLoadStatus(`Active — ${result.counts?.Function ?? "?"} functions, ${result.counts?.edges ?? "?"} edges`);
        setIsActive(true);
        loadOverview();
        loadSuggestions();
      }
    } catch (err: any) {
      setLoadStatus(`Error: ${err?.message || err}`);
    } finally {
      setBusy(false);
    }
  }

  async function loadOverview() {
    setOverviewBusy(true);
    try {
      const res = await apiFetch(`${API}/v1/graph/overview`);
      if (res.ok) setOverview(await res.json());
    } finally {
      setOverviewBusy(false);
    }
  }

  async function loadSuggestions() {
    setSuggestionsBusy(true);
    try {
      const res = await apiFetch(`${API}/v1/graph/suggestions`);
      if (res.ok) setSuggestions((await res.json()).suggestions || []);
    } finally {
      setSuggestionsBusy(false);
    }
  }

  async function viewSource(path?: string, start?: number, end?: number) {
    if (!path) return;
    const s = start || 1;
    const e = Math.max(end || s + 30, s + 5);
    setSourceView({ path, start: s, end: e, text: "", loading: true });
    try {
      const res = await apiFetch(`${API}/v1/files/source?path=${encodeURIComponent(path)}&start=${s}&end=${e}`);
      if (res.ok) {
        const data = await res.json();
        setSourceView({ ...data, loading: false });
      } else {
        setSourceView({ path, start: s, end: e, text: `// failed to load (${res.status})`, loading: false });
      }
    } catch (err: any) {
      setSourceView({ path, start: s, end: e, text: `// error: ${err?.message || err}`, loading: false });
    }
  }

  /** The one primary action on this page: blast radius + affected tests, together,
   * for whatever symbol is selected — via typing, a suggestion chip, or clicking a
   * node in the codebase map. Runs both in parallel since they're always shown
   * together now, not gated behind separate tabs. Returns the fetched data (not just
   * state) so callers like ask() can build an answer immediately, without racing
   * React's async state updates. */
  async function explore(overrideSymbol?: string, overrideDirection?: string) {
    const target = overrideSymbol ?? symbol;
    if (!target) return null;
    setSymbol(target);
    setExploreBusy(true);
    setSourceView(null);
    try {
      const [blastRes, testsRes] = await Promise.all([
        apiFetch(
          `${API}/v1/queries/blast-radius?symbol=${encodeURIComponent(target)}&direction=${overrideDirection ?? direction}`
        ),
        apiFetch(`${API}/v1/queries/affected-tests?symbol=${encodeURIComponent(target)}`),
      ]);
      const blast = await blastRes.json();
      const tests = await testsRes.json();
      setBlastResult(blast);
      setTestsResult(tests);
      scrollTo(exploreRef);
      return { blast, tests };
    } finally {
      setExploreBusy(false);
    }
  }

  async function runPath(overrideFrom?: string, overrideTo?: string) {
    const from = overrideFrom ?? fromSymbol;
    const to = overrideTo ?? toSymbol;
    if (!from || !to) return null;
    setFromSymbol(from);
    setToSymbol(to);
    setPathBusy(true);
    try {
      const res = await apiFetch(
        `${API}/v1/queries/shortest-path?from_symbol=${encodeURIComponent(from)}&to_symbol=${encodeURIComponent(to)}`
      );
      const data = await res.json();
      setPathResult(data);
      setSourceView(null);
      return data;
    } finally {
      setPathBusy(false);
    }
  }

  async function runSemantic(overrideQuery?: string) {
    const q = overrideQuery ?? query;
    if (!q) return null;
    setQuery(q);
    setSemanticBusy(true);
    try {
      const res = await apiFetch(`${API}/v1/queries/semantic?query=${encodeURIComponent(q)}&k=8`);
      const data = await res.json();
      setSemanticResult(data);
      setSourceView(null);
      return data;
    } finally {
      setSemanticBusy(false);
    }
  }

  async function runChain(overrideSymbol?: string) {
    const target = overrideSymbol ?? chainSymbol;
    if (!target) return null;
    setChainSymbol(target);
    setChainBusy(true);
    try {
      const res = await apiFetch(`${API}/v1/queries/call-chain?symbol=${encodeURIComponent(target)}`);
      const data = await res.json();
      setChainResult(data);
      setSourceView(null);
      return data;
    } finally {
      setChainBusy(false);
    }
  }

  // --- "Ask" bar: a plain-English front door over the same graph-native queries
  // above, backed by a real trained model — GET /v1/ask embeds the question with the
  // same Hugging Face sentence-transformer already used for semantic code search
  // (sentence-transformers/all-MiniLM-L6-v2, run locally via fastembed, no API key
  // and no per-query cost — see queries/copilot.py), classifies which of the
  // underlying queries actually answers it via real embedding similarity (not
  // keyword rules), resolves the real symbol(s) mentioned, runs that one query
  // server-side, and returns a phrased sentence plus the raw result — which is
  // dropped straight into this page's existing state so the matching detailed panel
  // (graph, test list, path, chain, semantic hits) renders right below the sentence.
  async function ask(raw?: string) {
    const text = (raw ?? askText).trim();
    if (!text) return;
    setAskText(text);
    setAskBusy(true);
    setAnswer(null);
    setSourceView(null);
    try {
      const res = await apiFetch(`${API}/v1/ask?text=${encodeURIComponent(text)}`);
      const result = await res.json();
      if (!res.ok) {
        setAnswer(result?.detail || "Something went wrong answering that — try the tools below directly.");
        return;
      }
      setAnswer(result.answer);
      const sym = result.symbols?.[0];
      switch (result.intent) {
        case "impact":
          if (sym) setSymbol(sym);
          setBlastResult(result.data.blast);
          setTestsResult(result.data.tests);
          scrollTo(exploreRef);
          break;
        case "tests":
          if (sym) setSymbol(sym);
          setTestsResult(result.data);
          scrollTo(exploreRef);
          break;
        case "path":
          setTab("path");
          if (result.symbols?.[0]) setFromSymbol(result.symbols[0]);
          if (result.symbols?.[1]) setToSymbol(result.symbols[1]);
          setPathResult(result.data);
          scrollTo(secondaryRef);
          break;
        case "chain":
          setTab("chain");
          if (sym) setChainSymbol(sym);
          setChainResult(result.data);
          scrollTo(secondaryRef);
          break;
        default:
          setTab("semantic");
          setQuery(text);
          setSemanticResult(result.data);
          scrollTo(secondaryRef);
      }
    } catch (err: any) {
      setAnswer(`Error: ${err?.message || err}`);
    } finally {
      setAskBusy(false);
    }
  }

  if (!id) {
    return (
      <EmptyState
        icon={<GitBranchIcon className="w-8 h-8" />}
        title="No repo selected"
        description="Go back to the dashboard and pick a repo."
      />
    );
  }

  return (
    <div>
      <PageHeading icon={<GitBranchIcon className="w-5 h-5" />}>{repo?.name || `Repo ${id}`}</PageHeading>
      {repo?.github_url && (
        <a
          href={repo.github_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-[#e8eefc]/45 hover:text-[#8ab4ff] transition-colors text-sm"
        >
          {repo.github_url}
          <ExternalLinkIcon className="w-3 h-3" />
        </a>
      )}

      <Card>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Button onClick={loadRepo} disabled={busy} className="flex items-center gap-2">
              {busy && <Spinner />}
              {busy ? "Working…" : isActive ? "Reload this repo" : "Load this repo"}
            </Button>
            <ElapsedTimer running={busy} />
          </div>
          {isActive && !busy && <Badge tone="success">Active graph</Badge>}
        </div>
        <Muted className="mt-3">
          One repo's graph is active in memory at a time (v1) — Load makes this the active one before querying below.
        </Muted>
        {loadStatus && (
          <p className="text-[#e8eefc]/70 text-sm mt-3 font-mono bg-black/20 rounded-lg px-3 py-2 whitespace-pre-wrap">{loadStatus}</p>
        )}
      </Card>

      {isActive && (
        <Card className="border-[#8ab4ff]/25 bg-gradient-to-br from-[#8ab4ff]/[0.06] to-transparent">
          <SectionHeading icon={<SparkleIcon className="w-4 h-4" />}>Ask about this codebase</SectionHeading>
          <Muted className="mb-3">
            Type a plain-English question — no need to know exact names. This is the fastest way to use this page.
          </Muted>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              ask();
            }}
            className="flex flex-wrap items-center gap-2 mb-3"
          >
            <Input
              className="min-w-[320px] flex-1 mr-0"
              value={askText}
              onChange={(e) => setAskText(e.target.value)}
              placeholder='e.g. "what breaks if I change parse_config?"'
            />
            <Button type="submit" disabled={askBusy || !askText.trim()} className="flex items-center gap-2">
              {askBusy && <Spinner />}
              Ask
            </Button>
          </form>
          {/* These used to be literal template text ("what depends on this?", with
              "this" never replaced by a real name) — clicking one just filled the box
              with unanswerable text, so asking it correctly found nothing and fell
              back to a semantic search, which looked exactly like "does nothing."
              Built from this repo's own top suggested symbols instead, so every chip
              is a real, immediately-answerable question — and clicking one now runs
              it immediately (matching the suggestion chips below), not just fills
              the box. */}
          <div className="flex flex-wrap gap-2 mb-3">
            {(suggestions && suggestions.length > 0
              ? [
                  `what breaks if I change ${suggestions[0].qualified_name || suggestions[0].name}?`,
                  `what tests cover ${suggestions[0].qualified_name || suggestions[0].name}?`,
                  ...(suggestions[1]
                    ? [
                        `how are ${suggestions[0].qualified_name || suggestions[0].name} and ${
                          suggestions[1].qualified_name || suggestions[1].name
                        } connected?`,
                      ]
                    : []),
                  "find code that handles errors",
                ]
              : ["find code that handles errors", "find code that parses configuration"]
            ).map((ex) => (
              <button
                key={ex}
                type="button"
                disabled={askBusy}
                onClick={() => ask(ex)}
                className="text-xs rounded-full bg-white/[0.03] hover:bg-white/[0.07] border border-white/10 px-3 py-1.5 text-[#e8eefc]/55 transition-colors disabled:opacity-40"
              >
                {ex}
              </button>
            ))}
          </div>
          {answer && (
            <div className="rounded-xl bg-[#8ab4ff]/10 border border-[#8ab4ff]/25 px-4 py-3 text-sm text-[#e8eefc]">
              {answer}
            </div>
          )}
          <Muted className="mt-3 text-xs">
            Backed by a real pretrained model (sentence-transformers/all-MiniLM-L6-v2, via Hugging Face/fastembed,
            running locally — no API key, no per-query cost) — it understands paraphrases of a question, not just
            exact keywords, finds the real symbol you mean, and runs the matching query below. If it guesses wrong,
            the exact tools below always work directly.
          </Muted>
        </Card>
      )}

      {isActive && (
        <Card>
          <SectionHeading icon={<SparkleIcon className="w-4 h-4" />}>Not sure where to start?</SectionHeading>
          <Muted className="mb-3">
            The most relied-upon functions and classes in this codebase — ranked by how many other things call or
            inherit from them, not a guess. Click one to explore it below.
          </Muted>
          {suggestionsBusy && (
            <div className="flex items-center gap-2 text-sm text-[#e8eefc]/50 py-4">
              <Spinner /> ranking…
            </div>
          )}
          {!suggestionsBusy && suggestions && suggestions.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {suggestions.map((s: any, i: number) => (
                <button
                  key={i}
                  onClick={() => explore(s.qualified_name || s.path || s.id)}
                  className="flex items-center gap-2 rounded-full bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 px-3.5 py-2 text-sm text-[#e8eefc] transition-colors"
                >
                  <span className="font-medium">{s.qualified_name || s.name}</span>
                  <Badge>{s.dependent_count} dependent{s.dependent_count === 1 ? "" : "s"}</Badge>
                </button>
              ))}
            </div>
          )}
          {!suggestionsBusy && suggestions && suggestions.length === 0 && (
            <Muted>No clear central symbols found — this repo may be small or loosely coupled.</Muted>
          )}
        </Card>
      )}

      {isActive && (
        <Card>
          <SectionHeading icon={<NetworkIcon className="w-4 h-4" />}>Codebase map</SectionHeading>
          <Muted className="mb-3">
            Every file, sized by how much it contains, connected by real imports — click one to explore it below.
          </Muted>
          {overviewBusy && (
            <div className="flex items-center gap-2 text-sm text-[#e8eefc]/50 py-8 justify-center">
              <Spinner /> building the map…
            </div>
          )}
          {!overviewBusy && overview && overview.nodes.length > 0 && (
            <>
              <GraphOverview
                nodes={overview.nodes}
                edges={overview.edges}
                onSelectNode={(n) => explore(n.path || n.qualified_name || n.id)}
              />
              {(overview as any).truncated && (
                <Muted className="mt-2 text-xs">Showing the {overview.nodes.length} largest files — this repo has more.</Muted>
              )}
            </>
          )}
          {!overviewBusy && overview && overview.nodes.length === 0 && (
            <EmptyState icon={<NetworkIcon className="w-8 h-8" />} title="No modules found" />
          )}
        </Card>
      )}

      {/* THE primary action on this page — everything else here is either a way to
          pick a symbol for this (suggestions, the map) or a secondary, occasional
          tool (the tabs below). Blast radius and affected tests answer the same
          real question, so they show together, not as separate tabs to hunt through.
          Wrapped in a plain div (not the ref directly on Card, which doesn't forward
          refs) so clicking a suggestion/map node/Ask example can scroll this exact
          spot into view — otherwise the update happens off-screen with nothing
          visibly connecting the click to it (confirmed live). */}
      <div ref={exploreRef}>
      <Card className={isActive ? "" : "opacity-50 pointer-events-none"}>
        <SectionHeading icon={<NetworkIcon className="w-4 h-4" />}>Explore a symbol</SectionHeading>
        <Muted className="mb-3">
          "What breaks if I change this, and what do I run to check?" — pick any function, class, or file.
        </Muted>
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <SymbolPicker apiBase={API} value={symbol} onChange={setSymbol} placeholder="symbol or file" />
          <Select value={direction} onChange={(e) => setDirection(e.target.value)}>
            <option value="upstream">who depends on it</option>
            <option value="downstream">what it depends on</option>
            <option value="both">both</option>
          </Select>
          <Button onClick={() => explore()} disabled={exploreBusy || !symbol} className="flex items-center gap-2">
            {exploreBusy && <Spinner />}
            Explore
          </Button>
        </div>

        {blastResult?.origin && blastResult?.nodes && (
          <>
            <DependencyGraph
              origin={blastResult.origin}
              nodes={blastResult.nodes}
              onSelectNode={(n: GraphNode) => viewSource(n.path, n.start_line, n.end_line)}
            />
            <Muted className="mt-2">
              {blastResult.nodes.length - 1} related node{blastResult.nodes.length - 1 === 1 ? "" : "s"} · click a
              node to view its source
            </Muted>
          </>
        )}
        {blastResult?.error && <Badge tone="danger">{blastResult.error}</Badge>}

        {testsResult && !testsResult.error && (
          <div className="mt-5">
            <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-1.5">
              ✅ Tests that cover this
            </h3>
            {(testsResult.tests || []).length > 0 ? (
              <div className="space-y-2">
                {testsResult.tests.map((t: any, i: number) => (
                  <div
                    key={i}
                    className="rounded-xl bg-white/[0.02] border border-white/[0.05] px-4 py-3 flex items-center justify-between gap-3 flex-wrap"
                  >
                    <div className="min-w-0">
                      <div className="font-medium text-sm text-white truncate">{t.qualified_name || t.name}</div>
                      <div className="text-[#e8eefc]/40 text-xs mt-0.5">{t.path}</div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge>{t.depth} call{t.depth === 1 ? "" : "s"} deep</Badge>
                      <SecondaryButton className="!py-1.5 !px-2.5 text-xs" onClick={() => viewSource(t.path, t.start_line, t.end_line)}>
                        View source
                      </SecondaryButton>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Muted className="text-xs">No indexed test calls this symbol, even transitively.</Muted>
            )}
          </div>
        )}

        {!blastResult && !testsResult && (
          <EmptyState
            icon={<NetworkIcon className="w-8 h-8" />}
            title="Pick a symbol to explore"
            description="Type above, click a suggestion chip, or click a file in the codebase map — you'll see its full dependency graph and test coverage together."
          />
        )}
      </Card>
      </div>

      <div ref={secondaryRef}>
      <Card className={isActive ? "" : "opacity-50 pointer-events-none"}>
        <SectionHeading>More ways to explore</SectionHeading>
        <Muted className="mb-3 text-xs">
          Compare two symbols, search by meaning instead of name, or trace a call chain several hops deep.
        </Muted>
        <Tabs
          tabs={SECONDARY_TABS}
          active={tab}
          onChange={(t) => {
            setTab(t);
            setSourceView(null);
          }}
        />

        {tab === "path" && (
          <div>
            <Muted className="mb-1">"How are these two things connected?" — shortest chain of calls/imports between them.</Muted>
            <Muted className="mb-3 text-xs">
              Type into each box — start typing and pick from the dropdown, or use a suggestion chip above as one end.
              Example: <code className="text-[#8ab4ff]">ApiController</code> → <code className="text-[#8ab4ff]">parse_config</code>.
            </Muted>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <SymbolPicker apiBase={API} value={fromSymbol} onChange={setFromSymbol} placeholder='from — e.g. "ApiController"' />
              <SymbolPicker apiBase={API} value={toSymbol} onChange={setToSymbol} placeholder='to — e.g. "parse_config"' />
              <Button onClick={() => runPath()} disabled={pathBusy || !fromSymbol || !toSymbol} className="flex items-center gap-2">
                {pathBusy && <Spinner />}
                Run
              </Button>
            </div>
            {pathResult?.path && pathResult.path.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 bg-black/20 rounded-xl p-4">
                {pathResult.path.map((n: any, i: number) => (
                  <span key={i} className="flex items-center gap-2">
                    <Badge>{n.qualified_name || n.path || n.id}</Badge>
                    {n.via && <span className="text-[#e8eefc]/30 text-xs font-mono">→ {n.via} →</span>}
                  </span>
                ))}
              </div>
            )}
            {pathResult && (!pathResult.path || pathResult.path.length === 0) && (
              <EmptyState icon={<RouteIcon className="w-8 h-8" />} title="No path found" description="Try different symbols, or widen max_hops." />
            )}
            {!pathResult && (
              <EmptyState icon={<RouteIcon className="w-8 h-8" />} title="No query run yet" description="Enter two symbols and hit Run." />
            )}
          </div>
        )}

        {tab === "semantic" && (
          <div>
            <Muted className="mb-3">Don't remember the exact name? Describe what it does — embedding similarity over the whole repo.</Muted>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <Input
                className="min-w-[320px] flex-1 mr-0"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="natural-language or code-like query"
              />
              <Button onClick={() => runSemantic()} disabled={semanticBusy} className="flex items-center gap-2">
                {semanticBusy && <Spinner />}
                Run
              </Button>
            </div>
            {(semanticResult?.hits || []).length > 0 && (
              <div className="space-y-2">
                {semanticResult.hits.map((h: any, i: number) => (
                  <div
                    key={i}
                    className="rounded-xl bg-white/[0.02] border border-white/[0.05] px-4 py-3 flex items-center justify-between gap-3 flex-wrap"
                  >
                    <div className="min-w-0">
                      <div className="font-medium text-sm text-white truncate">{h.qualified_name || h.path}</div>
                      <div className="text-[#e8eefc]/40 text-xs mt-0.5">{h.path}</div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge>{h.score?.toFixed(3)}</Badge>
                      <SecondaryButton
                        className="!py-1.5 !px-2.5 text-xs"
                        onClick={() => explore(h.qualified_name || h.path)}
                      >
                        Explore
                      </SecondaryButton>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {semanticResult && (semanticResult?.hits || []).length === 0 && (
              <EmptyState icon={<SearchIcon className="w-8 h-8" />} title="No matches" />
            )}
            {!semanticResult && (
              <EmptyState icon={<SearchIcon className="w-8 h-8" />} title="No query run yet" description="Describe what you're looking for and hit Run." />
            )}
          </div>
        )}

        {tab === "chain" && (
          <div>
            <Muted className="mb-3">Downstream CALLS expansion — every path this function's calls lead to, several hops deep.</Muted>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <SymbolPicker apiBase={API} value={chainSymbol} onChange={setChainSymbol} placeholder="symbol or file" />
              <Button onClick={() => runChain()} disabled={chainBusy} className="flex items-center gap-2">
                {chainBusy && <Spinner />}
                Run
              </Button>
            </div>
            {(chainResult?.paths || []).length > 0 && (
              <div className="space-y-2">
                {chainResult.paths.slice(0, 15).map((path: any[], i: number) => (
                  <div key={i} className="flex flex-wrap items-center gap-1.5 bg-black/20 rounded-xl p-3 text-sm">
                    {path.map((n: any, j: number) => (
                      <span key={j} className="flex items-center gap-1.5">
                        <Badge>{n.qualified_name || n.name || n.path}</Badge>
                        {j < path.length - 1 && <span className="text-[#e8eefc]/30 text-xs">→</span>}
                      </span>
                    ))}
                  </div>
                ))}
              </div>
            )}
            {chainResult?.error && <Badge tone="danger">{chainResult.error}</Badge>}
            {chainResult && !chainResult.error && (chainResult?.paths || []).length === 0 && (
              <EmptyState icon={<RouteIcon className="w-8 h-8" />} title="No outgoing calls found" />
            )}
            {!chainResult && (
              <EmptyState icon={<RouteIcon className="w-8 h-8" />} title="No query run yet" description="Enter a symbol and hit Run." />
            )}
          </div>
        )}
      </Card>
      </div>

      {sourceView && (
        <Card>
          <div className="flex justify-between items-center mb-3">
            <SectionHeading>
              {sourceView.path}
              <span className="text-[#e8eefc]/40 font-normal text-sm ml-2">lines {sourceView.start}–{sourceView.end}</span>
            </SectionHeading>
            <SecondaryButton onClick={() => setSourceView(null)} className="!p-2">
              <XIcon className="w-4 h-4" />
            </SecondaryButton>
          </div>
          {sourceView.loading ? (
            <div className="flex items-center gap-2 text-sm text-[#e8eefc]/50 py-4">
              <Spinner /> loading…
            </div>
          ) : (
            <CodeBlock code={sourceView.text} path={sourceView.path} />
          )}
        </Card>
      )}
    </div>
  );
}
