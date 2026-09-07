"use client";
import { useEffect, useState } from "react";
import { Button, Card, Muted, PageHeading, SectionHeading, Skeleton } from "../../components/ui";
import { ChartIcon } from "../../components/Icon";
import { apiFetch } from "../../lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function Bar({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const color = pct > 90 ? "bg-red-500" : pct > 70 ? "bg-amber-500" : "bg-gradient-to-r from-[#3b7bf6] to-[#7b3bf6]";
  return (
    <div className="bg-black/25 rounded-full h-2 overflow-hidden mt-2">
      <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function Usage() {
  const [u, setU] = useState<any>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    apiFetch(`${API}/v1/usage`)
      .then((r) => r.json())
      .then(setU);
  }, []);

  async function upgrade() {
    const res = await apiFetch(`${API}/v1/billing/checkout?plan=pro`, { method: "POST" });
    const data = await res.json();
    if (data.checkout_url && data.checkout_url.startsWith("http")) {
      window.location.href = data.checkout_url;
    } else {
      setStatus(data.message || JSON.stringify(data));
    }
  }

  return (
    <div>
      <PageHeading icon={<ChartIcon className="w-5 h-5" />}>Usage</PageHeading>
      <Card>
        {u === null ? (
          <Skeleton className="h-28 w-full" />
        ) : (
          <>
            <Muted className="mb-5">Plan: <span className="text-white font-medium">{u.plan}</span></Muted>

            <div className="mb-5">
              <div className="flex justify-between text-sm text-[#e8eefc]/80">
                <span>Queries today</span>
                <span className="tabular-nums">{u.queries_used} / {u.queries_limit}</span>
              </div>
              <Bar used={u.queries_used} limit={u.queries_limit} />
            </div>

            <div className="mb-2">
              <div className="flex justify-between text-sm text-[#e8eefc]/80">
                <span>Indexes today</span>
                <span className="tabular-nums">{u.indexes_used} / {u.indexes_limit}</span>
              </div>
              <Bar used={u.indexes_used} limit={u.indexes_limit} />
            </div>

            <Muted className="mt-4">Repo limit: {u.repos_limit}</Muted>
          </>
        )}
      </Card>

      <Card>
        <SectionHeading>Plan</SectionHeading>
        <Muted className="mb-4">Stripe test mode — no live charges possible.</Muted>
        <Button onClick={upgrade}>Upgrade to Pro</Button>
        {status && <Muted className="mt-3">{status}</Muted>}
      </Card>
    </div>
  );
}
