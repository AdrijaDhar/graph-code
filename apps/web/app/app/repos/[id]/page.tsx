"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function generateStaticParams() {
  return [{ id: "demo" }, { id: "1" }];
}

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
};
const button: React.CSSProperties = {
  background: "#2d6cdf",
  border: "none",
  borderRadius: 6,
  color: "white",
  padding: "8px 14px",
  cursor: "pointer",
};
const pre: React.CSSProperties = {
  background: "#0b1020",
  border: "1px solid #243",
  borderRadius: 6,
  padding: 12,
  overflowX: "auto",
  fontSize: 13,
  maxHeight: 400,
};

export default function RepoPlayground({ params }: { params: { id: string } }) {
  const [repo, setRepo] = useState<any>(null);
  const [loadStatus, setLoadStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [isActive, setIsActive] = useState(false);

  const [symbol, setSymbol] = useState("parse_config");
  const [direction, setDirection] = useState("upstream");
  const [blastResult, setBlastResult] = useState<any>(null);

  const [fromSymbol, setFromSymbol] = useState("");
  const [toSymbol, setToSymbol] = useState("");
  const [pathResult, setPathResult] = useState<any>(null);

  const [query, setQuery] = useState("");
  const [semanticResult, setSemanticResult] = useState<any>(null);

  useEffect(() => {
    fetch(`${API}/v1/repos`, { credentials: "include" })
      .then((r) => r.json())
      .then((list) => setRepo((Array.isArray(list) ? list : []).find((r: any) => String(r.id) === params.id)));
  }, [params.id]);

  async function loadRepo() {
    setBusy(true);
    setLoadStatus("Cloning/indexing — makes this repo the active graph…");
    try {
      const res = await fetch(`${API}/v1/repos/${params.id}/index`, { method: "POST", credentials: "include" });
      if (!res.ok) {
        setLoadStatus(`Failed: ${res.status} ${await res.text()}`);
        setIsActive(false);
      } else {
        const result = await res.json();
        setLoadStatus(`Active. ${JSON.stringify(result.counts || result)}`);
        setIsActive(true);
      }
    } catch (err: any) {
      setLoadStatus(`Error: ${err?.message || err}`);
    } finally {
      setBusy(false);
    }
  }

  function runBlast() {
    fetch(`${API}/v1/queries/blast-radius?symbol=${encodeURIComponent(symbol)}&direction=${direction}`, {
      credentials: "include",
    })
      .then((r) => r.json())
      .then(setBlastResult);
  }

  function runPath() {
    fetch(
      `${API}/v1/queries/shortest-path?from_symbol=${encodeURIComponent(fromSymbol)}&to_symbol=${encodeURIComponent(
        toSymbol
      )}`,
      { credentials: "include" }
    )
      .then((r) => r.json())
      .then(setPathResult);
  }

  function runSemantic() {
    fetch(`${API}/v1/queries/semantic?query=${encodeURIComponent(query)}&k=8`, { credentials: "include" })
      .then((r) => r.json())
      .then(setSemanticResult);
  }

  return (
    <div>
      <h1>{repo?.name || `Repo ${params.id}`}</h1>
      {repo?.github_url && (
        <p style={{ opacity: 0.7 }}>
          <a href={repo.github_url} style={{ color: "#9cf" }} target="_blank" rel="noreferrer">
            {repo.github_url}
          </a>
        </p>
      )}

      <div style={card}>
        <p style={{ marginTop: 0, opacity: 0.8 }}>
          One repo's graph is active in memory at a time (v1). Click Load to clone/index this
          repo and make it the active graph before running any query below.
        </p>
        <button style={button} onClick={loadRepo} disabled={busy}>
          {busy ? "Working…" : "Load this repo"}
        </button>
        {loadStatus && <p style={{ opacity: 0.85, whiteSpace: "pre-wrap" }}>{loadStatus}</p>}
      </div>

      <div style={{ ...card, opacity: isActive ? 1 : 0.5 }}>
        <h2 style={{ marginTop: 0 }}>Blast radius — "what breaks if I change this?"</h2>
        <input style={input} value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="symbol or file" />
        <select style={input} value={direction} onChange={(e) => setDirection(e.target.value)}>
          <option value="upstream">upstream (who depends on it)</option>
          <option value="downstream">downstream (what it depends on)</option>
          <option value="both">both</option>
        </select>
        <button style={button} onClick={runBlast} disabled={!isActive}>
          Run
        </button>
        {blastResult && <pre style={pre}>{JSON.stringify(blastResult, null, 2)}</pre>}
      </div>

      <div style={{ ...card, opacity: isActive ? 1 : 0.5 }}>
        <h2 style={{ marginTop: 0 }}>Shortest path — "what's the path from A to B?"</h2>
        <input style={input} value={fromSymbol} onChange={(e) => setFromSymbol(e.target.value)} placeholder="from symbol/file" />
        <input style={input} value={toSymbol} onChange={(e) => setToSymbol(e.target.value)} placeholder="to symbol/file" />
        <button style={button} onClick={runPath} disabled={!isActive}>
          Run
        </button>
        {pathResult && <pre style={pre}>{JSON.stringify(pathResult, null, 2)}</pre>}
      </div>

      <div style={{ ...card, opacity: isActive ? 1 : 0.5 }}>
        <h2 style={{ marginTop: 0 }}>Semantic search — "find similar functions"</h2>
        <input
          style={{ ...input, minWidth: 320 }}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="natural-language or code-like query"
        />
        <button style={button} onClick={runSemantic} disabled={!isActive}>
          Run
        </button>
        {semanticResult && <pre style={pre}>{JSON.stringify(semanticResult, null, 2)}</pre>}
      </div>
    </div>
  );
}
