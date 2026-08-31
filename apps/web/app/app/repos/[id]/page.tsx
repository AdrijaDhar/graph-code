"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function generateStaticParams() {
  return [{ id: "demo" }, { id: "1" }];
}

export default function RepoPlayground({ params }: { params: { id: string } }) {
  const [symbol, setSymbol] = useState("parse_config");
  const [result, setResult] = useState<any>(null);
  return (
    <div>
      <h1>Repo {params.id}</h1>
      <p>Blast radius playground</p>
      <input value={symbol} onChange={(e) => setSymbol(e.target.value)} />
      <button
        onClick={() => {
          fetch(`${API}/v1/queries/blast-radius?symbol=${encodeURIComponent(symbol)}`, {
            credentials: "include",
          })
            .then((r) => r.json())
            .then(setResult);
        }}
      >
        Who breaks?
      </button>
      <pre>{JSON.stringify(result, null, 2)}</pre>
    </div>
  );
}
