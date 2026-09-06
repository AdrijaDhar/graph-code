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
const button: React.CSSProperties = {
  background: "#2d6cdf",
  border: "none",
  borderRadius: 6,
  color: "white",
  padding: "8px 14px",
  cursor: "pointer",
};
const barTrack: React.CSSProperties = {
  background: "#0b1020",
  borderRadius: 6,
  height: 10,
  overflow: "hidden",
  marginTop: 6,
};

function Bar({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const color = pct > 90 ? "#e5484d" : pct > 70 ? "#f5a623" : "#2d6cdf";
  return (
    <div style={barTrack}>
      <div style={{ width: `${pct}%`, height: "100%", background: color }} />
    </div>
  );
}

export default function Usage() {
  const [u, setU] = useState<any>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetch(`${API}/v1/usage`, { credentials: "include" })
      .then((r) => r.json())
      .then(setU);
  }, []);

  async function upgrade() {
    const res = await fetch(`${API}/v1/billing/checkout?plan=pro`, { method: "POST", credentials: "include" });
    const data = await res.json();
    if (data.checkout_url && data.checkout_url.startsWith("http")) {
      window.location.href = data.checkout_url;
    } else {
      setStatus(data.message || JSON.stringify(data));
    }
  }

  return (
    <div>
      <h1>Usage</h1>
      <div style={card}>
        <p style={{ marginTop: 0, opacity: 0.7 }}>Plan: {u?.plan || "…"}</p>

        <div style={{ marginBottom: 16 }}>
          <div>
            Queries today: {u?.queries_used ?? "…"} / {u?.queries_limit ?? "…"}
          </div>
          {u && <Bar used={u.queries_used} limit={u.queries_limit} />}
        </div>

        <div style={{ marginBottom: 16 }}>
          <div>
            Indexes today: {u?.indexes_used ?? "…"} / {u?.indexes_limit ?? "…"}
          </div>
          {u && <Bar used={u.indexes_used} limit={u.indexes_limit} />}
        </div>

        <div style={{ opacity: 0.7 }}>Repo limit: {u?.repos_limit ?? "…"}</div>
      </div>

      <div style={card}>
        <h2 style={{ marginTop: 0 }}>Plan</h2>
        <p style={{ opacity: 0.7, marginTop: 0 }}>Stripe test mode — no live charges possible.</p>
        <button style={button} onClick={upgrade}>
          Upgrade to Pro
        </button>
        {status && <p style={{ opacity: 0.8 }}>{status}</p>}
      </div>
    </div>
  );
}
