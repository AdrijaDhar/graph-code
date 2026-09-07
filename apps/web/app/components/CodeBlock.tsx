"use client";
import { useEffect, useRef } from "react";

const EXT_LANG: Record<string, string> = {
  py: "python",
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  ts: "typescript",
  tsx: "typescript",
  go: "go",
  java: "java",
  rs: "rust",
  c: "c",
  h: "c",
  cpp: "cpp",
  cc: "cpp",
  cxx: "cpp",
  hpp: "cpp",
  hh: "cpp",
};

function langFromPath(path?: string): string | undefined {
  if (!path) return undefined;
  const ext = path.split(".").pop()?.toLowerCase();
  return ext ? EXT_LANG[ext] : undefined;
}

/** highlight.js is loaded globally via a <Script> tag in layout.tsx (CDN, no npm
 * dependency) — this just calls it imperatively on the <code> element. */
export function CodeBlock({ code, path, language }: { code: string; path?: string; language?: string }) {
  const ref = useRef<HTMLElement>(null);
  const lang = language || langFromPath(path);

  useEffect(() => {
    const hljs = (window as any).hljs;
    if (hljs && ref.current) {
      ref.current.removeAttribute("data-highlighted");
      try {
        hljs.highlightElement(ref.current);
      } catch {
        // unsupported/undetected language — leave as plain text, not worth surfacing
      }
    }
  }, [code, lang]);

  return (
    <pre className="bg-black/30 border border-white/[0.06] rounded-xl p-4 overflow-x-auto text-[13px] leading-relaxed shadow-inner">
      <code ref={ref} className={lang ? `language-${lang}` : undefined}>
        {code}
      </code>
    </pre>
  );
}
