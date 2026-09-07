"use client";
import { useEffect, useState } from "react";
import { Badge, Button, Card, ElapsedTimer, EmptyState, Input, Muted, PageHeading, SectionHeading, Skeleton, Spinner } from "../components/ui";
import { ClockIcon, FolderIcon, GitBranchIcon, NetworkIcon } from "../components/Icon";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AppHome() {
  const [me, setMe] = useState<any>(null);
  const [repos, setRepos] = useState<any[] | null>(null);
  const [githubUrl, setGithubUrl] = useState("");
  const [name, setName] = useState("");
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);

  function loadRepos() {
    fetch(`${API}/v1/repos`, { credentials: "include" })
      .then((r) => r.json())
      .then((d) => setRepos(Array.isArray(d) ? d : []))
      .catch(() => setRepos([]));
  }

  useEffect(() => {
    fetch(`${API}/v1/me`, { credentials: "include" })
      .then((r) => r.json())
      .then(setMe)
      .catch(() => setMe({ error: "API offline — is uvicorn running on :8000?" }));
    loadRepos();
  }, []);

  function deriveName(url: string): string {
    const parts = url.replace(/\/$/, "").split("/");
    return (parts[parts.length - 1] || "repo").replace(/\.git$/, "");
  }

  async function addAndIndex(e: React.FormEvent) {
    e.preventDefault();
    if (!githubUrl.trim()) return;
    setBusy(true);
    setStatus("Registering repo…");
    try {
      const createRes = await fetch(`${API}/v1/repos`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() || deriveName(githubUrl), github_url: githubUrl.trim() }),
      });
      if (!createRes.ok) {
        setStatus(`Failed to register: ${createRes.status} ${await createRes.text()}`);
        setBusy(false);
        return;
      }
      const created = await createRes.json();
      setStatus(`Cloning and indexing "${created.name}" — this can take a moment for larger repos…`);
      const indexRes = await fetch(`${API}/v1/repos/${created.id}/index`, {
        method: "POST",
        credentials: "include",
      });
      if (!indexRes.ok) {
        setStatus(`Registered but indexing failed: ${indexRes.status} ${await indexRes.text()}`);
      } else {
        const result = await indexRes.json();
        setStatus(`Indexed: ${JSON.stringify(result.counts || result)}`);
      }
      setGithubUrl("");
      setName("");
      loadRepos();
    } catch (err: any) {
      setStatus(`Error: ${err?.message || err}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeading icon={<NetworkIcon className="w-5 h-5" />}>Dashboard</PageHeading>
      <Muted>Signed in as {me?.login || me?.error || "…"}</Muted>

      <Card>
        <SectionHeading icon={<GitBranchIcon />}>Index a repo</SectionHeading>
        <Muted className="mb-4">Paste any public GitHub URL. It's shallow-cloned locally and parsed with Tree-sitter.</Muted>
        <form onSubmit={addAndIndex} className="flex flex-wrap items-center gap-2">
          <Input
            className="min-w-[280px] flex-1 mr-0"
            placeholder="https://github.com/owner/repo"
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            disabled={busy}
          />
          <Input className="mr-0 w-40" placeholder="name (optional)" value={name} onChange={(e) => setName(e.target.value)} disabled={busy} />
          <Button type="submit" disabled={busy || !githubUrl.trim()} className="flex items-center gap-2 whitespace-nowrap">
            {busy && <Spinner />}
            {busy ? "Working…" : "Add + Index"}
          </Button>
          <ElapsedTimer running={busy} />
        </form>
        {status && <p className="text-[#e8eefc]/70 text-sm whitespace-pre-wrap mt-3 font-mono bg-black/20 rounded-lg px-3 py-2">{status}</p>}
      </Card>

      <Card>
        <SectionHeading icon={<FolderIcon />}>Repos</SectionHeading>
        {repos === null && (
          <div className="space-y-2.5">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        )}
        {repos !== null && repos.length === 0 && (
          <EmptyState
            icon={<FolderIcon className="w-8 h-8" />}
            title="No repos indexed yet"
            description="Paste a GitHub URL above to get started."
          />
        )}
        {repos !== null && repos.length > 0 && (
          <ul className="list-none p-0 space-y-2">
            {repos.map((r) => (
              <li key={r.id}>
                <a
                  href={`/app/repo?id=${r.id}`}
                  className="flex items-center justify-between gap-3 rounded-xl px-4 py-3 bg-white/[0.02] border border-white/[0.05] hover:bg-white/[0.05] hover:border-white/10 transition-colors group"
                >
                  <span className="flex items-center gap-2.5 min-w-0">
                    <FolderIcon className="w-4 h-4 text-[#e8eefc]/30 shrink-0" />
                    <span className="text-white font-medium text-sm truncate group-hover:text-[#8ab4ff] transition-colors">{r.name}</span>
                  </span>
                  <span className="flex items-center gap-2 text-xs text-[#e8eefc]/50 shrink-0">
                    {r.node_count ? <Badge tone="success">{r.node_count} nodes</Badge> : <Badge tone="warn">not indexed</Badge>}
                    {r.last_indexed_at && (
                      <span className="hidden sm:flex items-center gap-1">
                        <ClockIcon className="w-3 h-3" />
                        {new Date(r.last_indexed_at).toLocaleDateString()}
                      </span>
                    )}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <p className="mt-5 text-sm text-[#e8eefc]/40 flex gap-4">
        <a href="/app/team" className="hover:text-white transition-colors">Team</a>
        <a href="/app/usage" className="hover:text-white transition-colors">Usage</a>
        <a href="/app/keys" className="hover:text-white transition-colors">API keys</a>
      </p>
    </div>
  );
}
