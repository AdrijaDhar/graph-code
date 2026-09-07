"use client";
import { useState } from "react";
import { Button, Card, Muted, PageHeading, SectionHeading, Spinner } from "../../components/ui";
import { KeyIcon } from "../../components/Icon";
import { apiFetch } from "../../lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Keys() {
  const [out, setOut] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  async function createKey() {
    setBusy(true);
    try {
      const res = await apiFetch(`${API}/v1/keys`, { method: "POST" });
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
      <PageHeading icon={<KeyIcon className="w-5 h-5" />}>MCP API keys</PageHeading>
      <Card>
        <Muted className="mb-2">Org-scoped keys for the REST API (Bearer auth, quota-enforced). A new key is shown once; copy it now.</Muted>
        <Muted className="mb-4 text-xs">
          Note: the local <code className="bg-white/[0.06] px-1 py-0.5 rounded text-[#8ab4ff]">graphcode chat</code> / MCP
          stdio server doesn't check this key yet — it always runs as a single local session, not scoped to your org.
          The config below is for a future remote-MCP setup; today it's REST-API-only.
        </Muted>
        <Button onClick={createKey} disabled={busy} className="flex items-center gap-2">
          {busy && <Spinner />}
          {busy ? "Creating…" : "Create key"}
        </Button>
      </Card>

      {out?.key && (
        <Card>
          <SectionHeading>New key</SectionHeading>
          <pre className="bg-black/25 border border-white/10 rounded-lg p-3 overflow-x-auto text-[13px] mb-4 text-[#8ab4ff]">{out.key}</pre>
          <h3 className="text-sm font-semibold text-[#e8eefc]/70 mb-2">Cursor / MCP client config</h3>
          <pre className="bg-black/25 border border-white/10 rounded-lg p-3 overflow-x-auto text-[13px] mb-4">
            {JSON.stringify(out.mcp_json, null, 2)}
          </pre>
          <Button onClick={copySnippet}>{copied ? "Copied!" : "Copy config"}</Button>
        </Card>
      )}
    </div>
  );
}
