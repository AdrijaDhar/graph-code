"use client";
import { useEffect, useState } from "react";
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
import { ExternalLinkIcon, GitBranchIcon, NetworkIcon, RouteIcon, SearchIcon, XIcon } from "../../components/Icon";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SourceView {
  path: string;
  start: number;
  end: number;
  text: string;
  loading?: boolean;
}

const QUERY_TABS = [
  { id: "blast", label: "Blast radius", icon: <NetworkIcon className="w-4 h-4" /> },
  { id: "path", label: "Shortest path", icon: <RouteIcon className="w-4 h-4" /> },
  { id: "semantic", label: "Semantic search", icon: <SearchIcon className="w-4 h-4" /> },
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
  const [tab, setTab] = useState("blast");

  const [symbol, setSymbol] = useState("parse_config");
  const [direction, setDirection] = useState("upstream");
  const [blastResult, setBlastResult] = useState<any>(null);
  const [blastBusy, setBlastBusy] = useState(false);

  const [fromSymbol, setFromSymbol] = useState("");
  const [toSymbol, setToSymbol] = useState("");
  const [pathResult, setPathResult] = useState<any>(null);
  const [pathBusy, setPathBusy] = useState(false);

  const [query, setQuery] = useState("");
  const [semanticResult, setSemanticResult] = useState<any>(null);
  const [semanticBusy, setSemanticBusy] = useState(false);

  const [sourceView, setSourceView] = useState<SourceView | null>(null);

  useEffect(() => {
    // Reset all per-repo state on navigation to a different id — this component
    // instance is reused across repos (the route is `/app/repo?id=`, not a fresh
    // page load), so without this, query results, active-graph status, and the
    // source-view panel from a previously-viewed repo would keep showing here.
    setRepo(null);
    setLoadStatus("");
    setIsActive(false);
    setBlastResult(null);
    setPathResult(null);
    setSemanticResult(null);
    setSourceView(null);
    if (!id) return;
    fetch(`${API}/v1/repos`, { credentials: "include" })
      .then((r) => r.json())
      .then((list) => setRepo((Array.isArray(list) ? list : []).find((r: any) => String(r.id) === id)));
  }, [id]);

  async function loadRepo() {
    setBusy(true);
    setLoadStatus("Cloning/indexing — makes this repo the active graph…");
    setBlastResult(null);
    setPathResult(null);
    setSemanticResult(null);
    setSourceView(null);
    try {
      const res = await fetch(`${API}/v1/repos/${id}/index`, { method: "POST", credentials: "include" });
      if (!res.ok) {
        setLoadStatus(`Failed: ${res.status} ${await res.text()}`);
        setIsActive(false);
      } else {
        const result = await res.json();
        setLoadStatus(`Active — ${result.counts?.Function ?? "?"} functions, ${result.counts?.edges ?? "?"} edges`);
        setIsActive(true);
      }
    } catch (err: any) {
      setLoadStatus(`Error: ${err?.message || err}`);
    } finally {
      setBusy(false);
    }
  }

  async function viewSource(path?: string, start?: number, end?: number) {
    if (!path) return;
    const s = start || 1;
    const e = Math.max(end || s + 30, s + 5);
    setSourceView({ path, start: s, end: e, text: "", loading: true });
    try {
      const res = await fetch(`${API}/v1/files/source?path=${encodeURIComponent(path)}&start=${s}&end=${e}`, {
        credentials: "include",
      });
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

  async function runBlast() {
    setBlastBusy(true);
    try {
      const res = await fetch(`${API}/v1/queries/blast-radius?symbol=${encodeURIComponent(symbol)}&direction=${direction}`, {
        credentials: "include",
      });
      setBlastResult(await res.json());
      setSourceView(null);
    } finally {
      setBlastBusy(false);
    }
  }

  async function runPath() {
    setPathBusy(true);
    try {
      const res = await fetch(
        `${API}/v1/queries/shortest-path?from_symbol=${encodeURIComponent(fromSymbol)}&to_symbol=${encodeURIComponent(
          toSymbol
        )}`,
        { credentials: "include" }
      );
      setPathResult(await res.json());
      setSourceView(null);
    } finally {
      setPathBusy(false);
    }
  }

  async function runSemantic() {
    setSemanticBusy(true);
    try {
      const res = await fetch(`${API}/v1/queries/semantic?query=${encodeURIComponent(query)}&k=8`, {
        credentials: "include",
      });
      setSemanticResult(await res.json());
      setSourceView(null);
    } finally {
      setSemanticBusy(false);
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

      <Card className={isActive ? "" : "opacity-50 pointer-events-none"}>
        <Tabs
          tabs={QUERY_TABS}
          active={tab}
          onChange={(t) => {
            setTab(t);
            setSourceView(null);
          }}
        />

        {tab === "blast" && (
          <div>
            <Muted className="mb-3">"What breaks if I change this?" — trace dependencies from a symbol or file.</Muted>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <Input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="symbol or file" className="mr-0" />
              <Select value={direction} onChange={(e) => setDirection(e.target.value)}>
                <option value="upstream">upstream (who depends on it)</option>
                <option value="downstream">downstream (what it depends on)</option>
                <option value="both">both</option>
              </Select>
              <Button onClick={runBlast} disabled={blastBusy} className="flex items-center gap-2">
                {blastBusy && <Spinner />}
                Run
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
            {!blastResult && (
              <EmptyState icon={<NetworkIcon className="w-8 h-8" />} title="No query run yet" description="Enter a symbol and hit Run." />
            )}
          </div>
        )}

        {tab === "path" && (
          <div>
            <Muted className="mb-3">"What's the path from A to B?" — shortest structural connection between two symbols.</Muted>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <Input value={fromSymbol} onChange={(e) => setFromSymbol(e.target.value)} placeholder="from symbol/file" className="mr-0" />
              <Input value={toSymbol} onChange={(e) => setToSymbol(e.target.value)} placeholder="to symbol/file" className="mr-0" />
              <Button onClick={runPath} disabled={pathBusy} className="flex items-center gap-2">
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
            <Muted className="mb-3">Find functions by meaning, not name — embedding similarity over the whole repo.</Muted>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <Input
                className="min-w-[320px] flex-1 mr-0"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="natural-language or code-like query"
              />
              <Button onClick={runSemantic} disabled={semanticBusy} className="flex items-center gap-2">
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
                      <SecondaryButton className="!py-1.5 !px-2.5 text-xs" onClick={() => viewSource(h.path, h.start_line, h.end_line)}>
                        View source
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
      </Card>

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
