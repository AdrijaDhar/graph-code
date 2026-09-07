"use client";
import { useEffect, useState } from "react";
import { Card, Muted, PageHeading, Skeleton, StatTile } from "../components/ui";
import { ChartIcon, FolderIcon, SearchIcon, UsersIcon } from "../components/Icon";

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
      <PageHeading icon={<ChartIcon className="w-5 h-5" />}>Impact</PageHeading>
      <Muted>Public counts for users, orgs, repos indexed, and queries served.</Muted>

      <Card>
        {data === null ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-6">
            <StatTile value={data.users} label="Users" icon={<UsersIcon />} />
            <StatTile value={data.orgs} label="Orgs" icon={<UsersIcon />} />
            <StatTile value={data.repos_indexed} label="Repos indexed" icon={<FolderIcon />} />
            <StatTile value={data.queries_served} label="Queries served" icon={<SearchIcon />} />
          </div>
        )}
      </Card>

      {data?.story && (
        <Card className="border-l-2 border-l-[#3b7bf6]">
          <p className="text-[#e8eefc]/85 italic">"{data.story}"</p>
        </Card>
      )}
    </div>
  );
}
