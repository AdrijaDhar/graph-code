"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Admin() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    fetch(`${API}/v1/admin`, { credentials: "include" })
      .then((r) => r.json())
      .then(setData);
  }, []);
  return (
    <div>
      <h1>Admin</h1>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
