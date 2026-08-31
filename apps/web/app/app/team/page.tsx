"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Team() {
  const [org, setOrg] = useState<any>(null);
  const [login, setLogin] = useState("");
  useEffect(() => {
    fetch(`${API}/v1/org`, { credentials: "include" })
      .then((r) => r.json())
      .then(setOrg);
  }, []);
  return (
    <div>
      <h1>Team</h1>
      <pre>{JSON.stringify(org, null, 2)}</pre>
      <input value={login} onChange={(e) => setLogin(e.target.value)} placeholder="GitHub username" />
      <button
        onClick={() =>
          fetch(`${API}/v1/org/invite?login=${encodeURIComponent(login)}`, {
            method: "POST",
            credentials: "include",
          })
        }
      >
        Invite
      </button>
    </div>
  );
}
