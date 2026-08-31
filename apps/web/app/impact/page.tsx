"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Impact() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    fetch(`${API}/v1/impact`)
      .then((r) => r.json())
      .then(setData);
  }, []);
  return (
    <div>
      <h1>Impact</h1>
      <p>Public counts for users, orgs, repos indexed, and queries served.</p>
      <ul>
        <li>Users: {data?.users ?? "—"}</li>
        <li>Orgs: {data?.orgs ?? "—"}</li>
        <li>Repos indexed: {data?.repos_indexed ?? "—"}</li>
        <li>Queries served: {data?.queries_served ?? "—"}</li>
      </ul>
      <p>{data?.story}</p>
    </div>
  );
}
