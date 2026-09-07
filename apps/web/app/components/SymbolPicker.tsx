"use client";
import { useEffect, useRef, useState } from "react";

interface SymbolHit {
  id: string;
  label: string;
  path?: string;
  name?: string;
  qualified_name?: string;
}

/** Replaces a blind "type an exact symbol name and hope" text box with a real,
 * live-searched picker — the actual fix for "querying is weird": before this, a
 * typo or an ambiguous short name (the exact failure mode find()'s own ranking bug
 * used to hit) only surfaced as a wrong or empty result *after* running the query,
 * with no way to see what you were actually about to ask for. Debounced so it
 * doesn't fire a search request on every keystroke. */
export function SymbolPicker({
  apiBase,
  value,
  onChange,
  placeholder = "symbol or file",
  className = "",
}: {
  apiBase: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}) {
  const [text, setText] = useState(value);
  const [hits, setHits] = useState<SymbolHit[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => setText(value), [value]);

  useEffect(() => {
    if (!text || text.length < 2) {
      setHits([]);
      return;
    }
    const handle = setTimeout(() => {
      fetch(`${apiBase}/v1/symbols/search?q=${encodeURIComponent(text)}`, { credentials: "include" })
        .then((r) => r.json())
        .then((d) => setHits(d.results || []))
        .catch(() => setHits([]));
    }, 200);
    return () => clearTimeout(handle);
  }, [text, apiBase]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function pick(hit: SymbolHit) {
    const picked = hit.qualified_name || hit.path || hit.id;
    setText(picked);
    onChange(picked);
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        className={
          "bg-black/25 border border-white/10 rounded-lg text-[#e8eefc] px-3 py-2 mr-2 text-sm " +
          "placeholder:text-[#e8eefc]/35 focus:outline-none focus:ring-2 focus:ring-[#3b7bf6]/40 focus:border-[#3b7bf6]/70 " +
          "transition-shadow duration-150 " +
          className
        }
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          setText(e.target.value);
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
      />
      {open && hits.length > 0 && (
        <div className="absolute z-20 mt-1 w-72 max-h-64 overflow-y-auto bg-[#151b30] border border-white/10 rounded-lg shadow-xl py-1">
          {hits.map((h) => (
            <button
              key={h.id}
              type="button"
              onClick={() => pick(h)}
              className="w-full text-left px-3 py-2 hover:bg-white/[0.06] transition-colors"
            >
              <div className="text-sm text-white truncate">{h.qualified_name || h.name || h.path}</div>
              <div className="text-xs text-[#e8eefc]/40 truncate">
                {h.label}
                {h.path ? ` · ${h.path}` : ""}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
