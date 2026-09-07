"use client";
import { useEffect, useState } from "react";
import { Button, Card, EmptyState, Input, Muted, PageHeading, SectionHeading, Skeleton, Spinner } from "../../components/ui";
import { UsersIcon } from "../../components/Icon";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Team() {
  const [org, setOrg] = useState<any>(null);
  const [login, setLogin] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    fetch(`${API}/v1/org`, { credentials: "include" })
      .then((r) => r.json())
      .then(setOrg);
  }

  useEffect(load, []);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    if (!login.trim()) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/v1/org/invite?login=${encodeURIComponent(login.trim())}`, {
        method: "POST",
        credentials: "include",
      });
      setStatus(res.ok ? `Invited ${login.trim()}` : `Failed: ${res.status}`);
      setLogin("");
      load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeading icon={<UsersIcon className="w-5 h-5" />}>Team</PageHeading>
      <Card>
        {org === null ? (
          <Skeleton className="h-6 w-1/2" />
        ) : (
          <>
            <SectionHeading>{org?.org || "Your org"}</SectionHeading>
            <Muted className="mb-4">Plan: {org?.plan}</Muted>
          </>
        )}
        {org?.members?.length > 0 ? (
          <ul className="list-none p-0 divide-y divide-white/[0.06]">
            {org.members.map((m: any, i: number) => (
              <li key={i} className="py-2.5 text-sm flex items-center justify-between">
                <span className="text-white">{m.login || m.name || m.user_id}</span>
                <span className="text-[#e8eefc]/40 text-xs">{m.role}</span>
              </li>
            ))}
          </ul>
        ) : org ? (
          <EmptyState icon={<UsersIcon className="w-6 h-6" />} title="No members yet" />
        ) : null}
      </Card>

      <Card>
        <SectionHeading>Invite a member</SectionHeading>
        <Muted className="mb-3 text-xs">
          Note: this creates a placeholder membership immediately — it does not send a
          real invite, and isn't linked to that person's actual GitHub account until
          they separately sign in with GitHub themselves (which creates a
          <em> different</em>, unconnected member row today, not a merge into this
          one). Treat this as a roster placeholder, not a working invite flow yet.
        </Muted>
        <form onSubmit={invite} className="flex items-center gap-2">
          <Input className="mr-0" value={login} onChange={(e) => setLogin(e.target.value)} placeholder="GitHub username" disabled={busy} />
          <Button type="submit" disabled={busy} className="flex items-center gap-2">
            {busy && <Spinner />}
            Invite
          </Button>
        </form>
        {status && <Muted className="mt-3">{status}</Muted>}
      </Card>
    </div>
  );
}
