"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const card: React.CSSProperties = {
  border: "1px solid #243",
  borderRadius: 8,
  padding: 16,
  marginTop: 16,
  background: "#0f1830",
};
const input: React.CSSProperties = {
  background: "#0b1020",
  border: "1px solid #345",
  borderRadius: 6,
  color: "#e8eefc",
  padding: "8px 10px",
  marginRight: 8,
  minWidth: 260,
};
const button: React.CSSProperties = {
  background: "#2d6cdf",
  border: "none",
  borderRadius: 6,
  color: "white",
  padding: "8px 14px",
  cursor: "pointer",
};

export default function AppHome() {
  const [me, setMe] = useState<any>(null);
  const [repos, setRepos] = useState<any[]>([]);
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
      <h1>Dashboard</h1>
      <p style={{ opacity: 0.7 }}>Signed in as {me?.login || me?.error || "…"}</p>

      <div style={card}>
        <h2 style={{ marginTop: 0 }}>Index a repo</h2>
        <p style={{ opacity: 0.7, marginTop: 0 }}>
          Paste any public GitHub URL. It's shallow-cloned locally and parsed with Tree-sitter.
        </p>
        <form onSubmit={addAndIndex}>
          <input
            style={input}
            placeholder="https://github.com/owner/repo"
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            disabled={busy}
          />
          <input
            style={input}
            placeholder="name (optional)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
          />
          <button style={button} type="submit" disabled={busy || !githubUrl.trim()}>
            {busy ? "Working…" : "Add + Index"}
          </button>
        </form>
        {status && <p style={{ opacity: 0.85, whiteSpace: "pre-wrap" }}>{status}</p>}
      </div>

      <div style={card}>
        <h2 style={{ marginTop: 0 }}>Repos</h2>
        {repos.length === 0 && <p style={{ opacity: 0.7 }}>No repos indexed yet — add one above.</p>}
        <ul style={{ listStyle: "none", padding: 0 }}>
          {repos.map((r) => (
            <li key={r.id} style={{ padding: "8px 0", borderBottom: "1px solid #243" }}>
              <a href={`/app/repos/${r.id}`} style={{ color: "#9cf", fontWeight: 600 }}>
                {r.name}
              </a>
              <span style={{ opacity: 0.6, marginLeft: 12, fontSize: 13 }}>
                {r.node_count ? `${r.node_count} nodes` : "not indexed yet"} ·{" "}
                {r.last_indexed_at ? `indexed ${new Date(r.last_indexed_at).toLocaleString()}` : "never indexed"}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <p style={{ marginTop: 16 }}>
        <a href="/app/team" style={{ color: "#9cf" }}>Team</a> ·{" "}
        <a href="/app/usage" style={{ color: "#9cf" }}>Usage</a> ·{" "}
        <a href="/app/keys" style={{ color: "#9cf" }}>API keys</a>
      </p>
    </div>
  );
}
