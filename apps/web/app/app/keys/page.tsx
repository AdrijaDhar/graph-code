"use client";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Keys() {
  const [out, setOut] = useState<any>(null);
  return (
    <div>
      <h1>MCP API keys</h1>
      <button
        onClick={() =>
          fetch(`${API}/v1/keys`, { method: "POST", credentials: "include" })
            .then((r) => r.json())
            .then(setOut)
        }
      >
        Create key
      </button>
      <pre>{JSON.stringify(out, null, 2)}</pre>
    </div>
  );
}
