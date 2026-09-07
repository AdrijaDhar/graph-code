import { Suspense } from "react";
import RepoPlaygroundClient from "./RepoPlaygroundClient";

// useSearchParams() (used in RepoPlaygroundClient to read ?id=) requires a Suspense
// boundary in the App Router — without it, `next build` fails under output: "export".
export default function Page() {
  return (
    <Suspense fallback={<div className="text-[#e8eefc]/50 text-sm">Loading…</div>}>
      <RepoPlaygroundClient />
    </Suspense>
  );
}
