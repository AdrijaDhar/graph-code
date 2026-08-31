"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AppHome() {
  const [me, setMe] = useState<any>(null);
  const [repos, setRepos] = useState<any[]>([]);
  useEffect(() => {
    fetch(`${API}/v1/me`, { credentials: "include" })
      .then((r) => r.json())
      .then(setMe)
      .catch(() => setMe({ error: "API offline" }));
    fetch(`${API}/v1/repos`, { credentials: "include" })
      .then((r) => r.json())
      .then((d) => setRepos(Array.isArray(d) ? d : []))
      .catch(() => setRepos([]));
  }, []);
  return (
    <div>
      <h1>Dashboard</h1>
      <pre>{JSON.stringify(me, null, 2)}</pre>
      <h2>Repos</h2>
      <ul>
        {repos.map((r) => (
          <li key={r.id}>
            <a href={`/app/repos/${r.id}`} style={{ color: "#9cf" }}>
              {r.name}
            </a>
          </li>
        ))}
      </ul>
      <p>
        <a href="/app/team">Team</a> · <a href="/app/usage">Usage</a> · <a href="/app/keys">API keys</a>
      </p>
    </div>
  );
}
