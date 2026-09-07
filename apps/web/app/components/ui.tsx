"use client";
import { useEffect, useState } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { ChevronDownIcon } from "./Icon";

// Shared design-system primitives (Tailwind, loaded via the CDN <Script> in
// layout.tsx — no build step). Real depth (shadows, layered surfaces), gradient
// primary actions, and proper focus rings instead of flat borders — the things
// that separate a considered UI from a default-utility-classes demo.

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={
        "border border-white/[0.06] rounded-2xl p-5 mt-4 bg-[#10182c] shadow-[0_1px_0_rgba(255,255,255,0.04)_inset,0_8px_24px_-8px_rgba(0,0,0,0.5)] " +
        className
      }
    >
      {children}
    </div>
  );
}

export function Button({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={
        "bg-gradient-to-b from-[#3b7bf6] to-[#2d63dc] hover:from-[#4a86f8] hover:to-[#3670e0] " +
        "active:scale-[0.98] disabled:from-[#2d63dc]/40 disabled:to-[#2d63dc]/40 disabled:cursor-not-allowed " +
        "disabled:active:scale-100 border-none rounded-lg text-white px-4 py-2 cursor-pointer " +
        "transition-all duration-150 text-sm font-medium shadow-[0_1px_0_rgba(255,255,255,0.15)_inset,0_4px_12px_-2px_rgba(45,99,220,0.5)] " +
        className
      }
      {...props}
    />
  );
}

export function SecondaryButton({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={
        "bg-white/[0.04] hover:bg-white/[0.08] active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed " +
        "disabled:active:scale-100 border border-white/10 rounded-lg text-[#e8eefc] px-4 py-2 cursor-pointer " +
        "transition-all duration-150 text-sm font-medium " +
        className
      }
      {...props}
    />
  );
}

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={
        "bg-black/25 border border-white/10 rounded-lg text-[#e8eefc] px-3 py-2 mr-2 text-sm " +
        "placeholder:text-[#e8eefc]/35 focus:outline-none focus:ring-2 focus:ring-[#3b7bf6]/40 focus:border-[#3b7bf6]/70 " +
        "transition-shadow duration-150 " +
        className
      }
      {...props}
    />
  );
}

export function Select({ className = "", children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative inline-block mr-2">
      <select
        className={
          "appearance-none bg-black/25 border border-white/10 rounded-lg text-[#e8eefc] pl-3 pr-8 py-2 text-sm " +
          "focus:outline-none focus:ring-2 focus:ring-[#3b7bf6]/40 focus:border-[#3b7bf6]/70 cursor-pointer " +
          className
        }
        {...props}
      >
        {children}
      </select>
      <ChevronDownIcon className="w-3.5 h-3.5 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-[#e8eefc]/50" />
    </div>
  );
}

const BADGE_TONES: Record<string, string> = {
  default: "bg-white/[0.06] text-[#9cc4ff] border border-white/10",
  success: "bg-emerald-500/10 text-emerald-300 border border-emerald-500/20",
  warn: "bg-amber-500/10 text-amber-300 border border-amber-500/20",
  danger: "bg-red-500/10 text-red-300 border border-red-500/20",
};

export function Badge({
  children,
  tone = "default",
  icon,
}: {
  children: ReactNode;
  tone?: keyof typeof BADGE_TONES;
  icon?: ReactNode;
}) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${BADGE_TONES[tone]}`}>
      {icon}
      {children}
    </span>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="loading"
      className={`inline-block w-4 h-4 border-[1.5px] border-white/20 border-t-white rounded-full animate-spin ${className}`}
    />
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`bg-white/[0.06] rounded-lg animate-pulse ${className}`} />;
}

/** Ticking "Ns" label while `running` is true — for long clone/index waits where we
 * can't report real backend progress, at least show it's alive and how long it's been. */
export function ElapsedTimer({ running }: { running: boolean }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!running) {
      setSeconds(0);
      return;
    }
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [running]);
  if (!running) return null;
  return <span className="text-[#e8eefc]/40 text-xs ml-2 tabular-nums">{seconds}s</span>;
}

export function PageHeading({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return (
    <h1 className="flex items-center gap-2.5 text-[1.6rem] font-semibold tracking-tight text-white mb-1">
      {icon && <span className="text-[#3b7bf6]">{icon}</span>}
      {children}
    </h1>
  );
}

export function SectionHeading({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return (
    <h2 className="flex items-center gap-2 text-[0.95rem] font-semibold text-white mt-0 mb-3">
      {icon && <span className="text-[#e8eefc]/40">{icon}</span>}
      {children}
    </h2>
  );
}

export function Muted({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <p className={`text-[#e8eefc]/50 text-sm leading-relaxed ${className}`}>{children}</p>;
}

export function StatTile({ value, label, icon }: { value: ReactNode; label: string; icon?: ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      {icon && (
        <div className="w-9 h-9 rounded-lg bg-[#3b7bf6]/10 border border-[#3b7bf6]/20 flex items-center justify-center text-[#3b7bf6] shrink-0">
          {icon}
        </div>
      )}
      <div>
        <div className="text-2xl font-semibold text-white tabular-nums leading-none">{value}</div>
        <div className="text-[#e8eefc]/45 text-xs mt-1">{label}</div>
      </div>
    </div>
  );
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string; icon?: ReactNode }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex gap-1 border-b border-white/[0.06] mb-4 -mt-1">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={
            "flex items-center gap-1.5 px-3.5 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors " +
            (active === t.id
              ? "border-[#3b7bf6] text-white"
              : "border-transparent text-[#e8eefc]/45 hover:text-[#e8eefc]/80")
          }
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function EmptyState({ icon, title, description }: { icon?: ReactNode; title: string; description?: string }) {
  return (
    <div className="text-center py-10 px-4">
      {icon && <div className="inline-flex text-[#e8eefc]/20 mb-3">{icon}</div>}
      <div className="text-[#e8eefc]/70 text-sm font-medium">{title}</div>
      {description && <div className="text-[#e8eefc]/40 text-xs mt-1 max-w-sm mx-auto">{description}</div>}
    </div>
  );
}
