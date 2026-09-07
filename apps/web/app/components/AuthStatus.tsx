"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Header-right auth control. A plain "Sign out" link looked identical whether or not
 * there was a real session to end — on a deployment with no GitHub OAuth configured
 * (e.g. local dev with no GITHUB_CLIENT_ID set), every request resolves to the same
 * shared demo account regardless of cookies, so clicking it cleared a cookie that was
 * never required and the very next page load landed you right back in the same demo
 * account. Confirmed live as a real "sign out does nothing" report. This checks
 * /v1/me's `demo` flag and shows an honest, non-clickable "Demo mode" label instead of
 * a Sign out link that can't do anything, in that case — real deployments with OAuth
 * configured are unaffected and keep the functional Sign out link. */
export function AuthStatus() {
  const [demo, setDemo] = useState<boolean | null>(null);

  useEffect(() => {
    fetch(`${API}/v1/me`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setDemo(data ? !!data.demo : null))
      .catch(() => setDemo(null));
  }, []);

  if (demo === null) return null;

  if (demo) {
    return (
      <span
        title="No GitHub OAuth configured on this deployment — every visitor shares one demo account, so there's no real session to sign out of."
        className="ml-auto px-3 py-1.5 rounded-md text-[#e8eefc]/35 text-sm cursor-default select-none"
      >
        Demo mode
      </span>
    );
  }

  return (
    <a
      href={`${API}/v1/auth/logout`}
      className="ml-auto px-3 py-1.5 rounded-md text-[#e8eefc]/60 hover:text-white hover:bg-white/[0.06] transition-colors text-sm"
    >
      Sign out
    </a>
  );
}
