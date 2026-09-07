"use client";
import { useEffect, useState } from "react";
import { Card, PageHeading, Skeleton, StatTile } from "../components/ui";
import { ChartIcon, ShieldIcon, UsersIcon } from "../components/Icon";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
        <PageHeading icon={<ShieldIcon className="w-5 h-5" />}>Admin</PageHeading>
        <Card>{error}</Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeading icon={<ShieldIcon className="w-5 h-5" />}>Admin</PageHeading>
      <Card>
        {data === null ? (
          <Skeleton className="h-12 w-full" />
        ) : (
          <div className="grid grid-cols-3 gap-6">
            <StatTile value={data.users} label="Users" icon={<UsersIcon />} />
            <StatTile value={data.orgs} label="Orgs" icon={<UsersIcon />} />
            <StatTile value={data.usage_events} label="Usage events" icon={<ChartIcon />} />
          </div>
        )}
      </Card>

      <Card>
        <h2 className="text-[0.95rem] font-semibold text-white mt-0 mb-3">Recent users</h2>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-[#e8eefc]/40 text-xs uppercase tracking-wide">
              <th className="px-3 py-2 font-medium">ID</th>
              <th className="px-3 py-2 font-medium">Login</th>
              <th className="px-3 py-2 font-medium">GitHub ID</th>
            </tr>
          </thead>
          <tbody>
            {(data?.recent_users || []).map((u: any) => (
              <tr key={u.id} className="border-t border-white/[0.05] hover:bg-white/[0.02]">
                <td className="px-3 py-2 text-[#e8eefc]/60">{u.id}</td>
                <td className="px-3 py-2 text-white">{u.login}</td>
                <td className="px-3 py-2 text-[#e8eefc]/60">{u.github_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
