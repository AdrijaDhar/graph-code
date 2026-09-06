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
};
const button: React.CSSProperties = {
  background: "#2d6cdf",
  border: "none",
  borderRadius: 6,
  color: "white",
  padding: "8px 14px",
  cursor: "pointer",
};

export default function Team() {
  const [org, setOrg] = useState<any>(null);
  const [login, setLogin] = useState("");
  const [status, setStatus] = useState("");

  function load() {
    fetch(`${API}/v1/org`, { credentials: "include" })
      .then((r) => r.json())
      .then(setOrg);
  }

  useEffect(load, []);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    if (!login.trim()) return;
    const res = await fetch(`${API}/v1/org/invite?login=${encodeURIComponent(login.trim())}`, {
      method: "POST",
      credentials: "include",
    });
    setStatus(res.ok ? `Invited ${login.trim()}` : `Failed: ${res.status}`);
    setLogin("");
    load();
  }

  return (
    <div>
      <h1>Team</h1>
      <div style={card}>
        <h2 style={{ marginTop: 0 }}>{org?.org || "Your org"}</h2>
        <p style={{ opacity: 0.7 }}>Plan: {org?.plan || "…"}</p>
        <h3>Members</h3>
        <ul style={{ paddingLeft: 20 }}>
          {(org?.members || []).map((m: any, i: number) => (
            <li key={i}>
              {m.login || m.name || m.user_id} — {m.role}
            </li>
          ))}
          {!org?.members && <li style={{ opacity: 0.6, listStyle: "none", marginLeft: -20 }}>Loading…</li>}
        </ul>
      </div>

      <div style={card}>
        <h2 style={{ marginTop: 0 }}>Invite a member</h2>
        <form onSubmit={invite}>
          <input
            style={input}
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            placeholder="GitHub username"
          />
          <button style={button} type="submit">
            Invite
          </button>
        </form>
        {status && <p style={{ opacity: 0.8 }}>{status}</p>}
      </div>
    </div>
  );
}
