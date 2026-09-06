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
const stat: React.CSSProperties = {
  display: "inline-block",
  marginRight: 32,
};

export default function Admin() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    fetch(`${API}/v1/admin`, { credentials: "include" })
      .then(async (r) => {
        if (!r.ok) {
          setError(r.status === 403 ? "Admin only — your account isn't in ADMIN_GITHUB_IDS." : `Error ${r.status}`);
          return null;
        }
        return r.json();
      })
      .then((d) => d && setData(d));
  }, []);

  if (error) {
    return (
      <div>
        <h1>Admin</h1>
        <div style={card}>{error}</div>
      </div>
    );
  }

  return (
    <div>
      <h1>Admin</h1>
      <div style={card}>
        <div style={stat}>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{data?.users ?? "…"}</div>
          <div style={{ opacity: 0.6 }}>Users</div>
        </div>
        <div style={stat}>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{data?.orgs ?? "…"}</div>
          <div style={{ opacity: 0.6 }}>Orgs</div>
        </div>
        <div style={stat}>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{data?.usage_events ?? "…"}</div>
          <div style={{ opacity: 0.6 }}>Usage events</div>
        </div>
      </div>

      <div style={card}>
        <h2 style={{ marginTop: 0 }}>Recent users</h2>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", opacity: 0.6 }}>
              <th style={{ padding: "4px 8px" }}>ID</th>
              <th style={{ padding: "4px 8px" }}>Login</th>
              <th style={{ padding: "4px 8px" }}>GitHub ID</th>
            </tr>
          </thead>
          <tbody>
            {(data?.recent_users || []).map((u: any) => (
              <tr key={u.id} style={{ borderTop: "1px solid #243" }}>
                <td style={{ padding: "4px 8px" }}>{u.id}</td>
                <td style={{ padding: "4px 8px" }}>{u.login}</td>
                <td style={{ padding: "4px 8px" }}>{u.github_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
