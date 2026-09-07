import Script from "next/script";
import { AuthStatus } from "./components/AuthStatus";
import { NetworkIcon } from "./components/Icon";

export const metadata = {
  title: "Graph-Code",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
      </head>
      {/* inline style on body avoids a flash-of-white before the Tailwind CDN script
          finishes parsing classes and injecting its <style> tag */}
      <body
        style={{
          background: "radial-gradient(ellipse 80% 50% at 50% -20%, rgba(59,123,246,0.12), transparent), #090d1a",
          color: "#e8eefc",
          fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif",
        }}
        className="m-0 min-h-screen antialiased"
      >
        {/* CDN libraries — no npm dependency, works under this app's static export.
            beforeInteractive: guaranteed loaded before hydration, so client
            components' first effect (D3 graph, highlight.js) never races the script.
            Next.js hoists these into <head> itself regardless of where they're
            written — placing them as a direct child of <html> (outside <body>) is
            invalid HTML and causes a hydration mismatch, confirmed live. */}
        <Script src="https://cdn.tailwindcss.com" strategy="beforeInteractive" />
        <Script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js" strategy="beforeInteractive" />
        <Script
          src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"
          strategy="beforeInteractive"
        />
        <link
          rel="stylesheet"
          href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css"
        />
        <header className="sticky top-0 z-20 px-6 py-3.5 border-b border-white/[0.06] bg-[#090d1a]/80 backdrop-blur-md flex items-center">
          <a href="/" className="flex items-center gap-2 no-underline">
            <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#3b7bf6] to-[#7b3bf6] flex items-center justify-center text-white shrink-0">
              <NetworkIcon className="w-4 h-4" />
            </span>
            <span className="text-white font-semibold text-[0.95rem] tracking-tight">Graph-Code</span>
          </a>
          <nav className="ml-8 flex gap-1 text-sm">
            <a href="/impact" className="px-3 py-1.5 rounded-md text-[#e8eefc]/60 hover:text-white hover:bg-white/[0.06] transition-colors">
              Impact
            </a>
            <a href="/app" className="px-3 py-1.5 rounded-md text-[#e8eefc]/60 hover:text-white hover:bg-white/[0.06] transition-colors">
              Dashboard
            </a>
            <a href="/admin" className="px-3 py-1.5 rounded-md text-[#e8eefc]/60 hover:text-white hover:bg-white/[0.06] transition-colors">
              Admin
            </a>
          </nav>
          {/* There was previously no way to end a session at all short of manually
              clearing cookies — confirmed live. AuthStatus shows a real, working Sign
              out link once actually authenticated via GitHub OAuth, or an honest
              "Demo mode" label instead of a Sign out link that would look broken on a
              deployment with no OAuth configured (every request there shares one demo
              account regardless of cookies — see /v1/me's `demo` flag). */}
          <AuthStatus />
        </header>
        {/* max-w-5xl (1024px) made every page look like a narrow box floating in the
            middle of the screen on any real monitor — confirmed live, this was the
            actual "boxed" complaint. 1600px gives the graph visualization real room
            without going full-bleed (unconstrained width on an ultrawide would make
            the text-heavy pages uncomfortably wide to read). */}
        <main className="px-6 py-8 max-w-[1600px] mx-auto">{children}</main>
      </body>
    </html>
  );
}
