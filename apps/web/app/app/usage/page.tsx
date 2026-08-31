"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Usage() {
  const [u, setU] = useState<any>(null);
  useEffect(() => {
    fetch(`${API}/v1/usage`, { credentials: "include" })
      .then((r) => r.json())
      .then(setU);
  }, []);
  return (
    <div>
      <h1>Usage</h1>
      <pre>{JSON.stringify(u, null, 2)}</pre>
      <button
        onClick={() =>
          fetch(`${API}/v1/billing/checkout?plan=pro`, { method: "POST", credentials: "include" }).then((r) =>
            r.json().then(alert)
          )
        }
      >
        Upgrade (Stripe test)
      </button>
    </div>
  );
}
