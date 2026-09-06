"use client";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const card: React.CSSProperties = {
  border: "1px solid #243",
  borderRadius: 8,
  padding: 16,
  marginTop: 16,
  background: "#0f1830",
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
};

export default function Keys() {
  const [out, setOut] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  async function createKey() {
    setBusy(true);
    try {
      const res = await fetch(`${API}/v1/keys`, { method: "POST", credentials: "include" });
      setOut(await res.json());
      setCopied(false);
    } finally {
      setBusy(false);
    }
  }

  function copySnippet() {
    if (out?.mcp_json) {
      navigator.clipboard.writeText(JSON.stringify(out.mcp_json, null, 2));
      setCopied(true);
    }
  }

  return (
    <div>
      <h1>MCP API keys</h1>
      <div style={card}>
        <p style={{ marginTop: 0, opacity: 0.8 }}>
          Org-scoped keys for the REST API (Bearer auth, quota-enforced). A new key is
          shown once; copy it now.
        </p>
        <p style={{ marginTop: 0, opacity: 0.6, fontSize: 13 }}>
          Note: the local <code>graphcode chat</code> / MCP stdio server doesn't check
          this key yet — it always runs as a single local session, not scoped to your
          org. The config below is for a future remote-MCP setup; today it's REST-API-only.
        </p>
        <button style={button} onClick={createKey} disabled={busy}>
          {busy ? "Creating…" : "Create key"}
        </button>
      </div>

      {out?.key && (
        <div style={card}>
          <h2 style={{ marginTop: 0 }}>New key</h2>
          <pre style={pre}>{out.key}</pre>
          <h3>Cursor / MCP client config</h3>
          <pre style={pre}>{JSON.stringify(out.mcp_json, null, 2)}</pre>
          <button style={button} onClick={copySnippet}>
            {copied ? "Copied!" : "Copy config"}
          </button>
        </div>
      )}
    </div>
  );
}
