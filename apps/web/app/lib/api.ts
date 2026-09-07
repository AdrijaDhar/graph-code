/** Shared fetch wrapper for every authenticated call in this app.
 *
 * Sessions are established two ways at once, deliberately:
 * 1. A `gc_session` cookie — works fine when the frontend and API are actually on the
 *    same site, e.g. local dev.
 * 2. A `Bearer` token in localStorage, sent as an `Authorization` header — this is
 *    what actually works on the real deployment, where the frontend and API live on
 *    different `onrender.com` subdomains. A cookie set only during the OAuth
 *    callback's redirect "bounce" (GitHub -> the API domain -> immediately on to the
 *    frontend domain) gets silently discarded by modern browsers' bounce-tracking
 *    mitigations before it's ever stored — confirmed live: `gc_session` never
 *    appeared in the cookie store at all, in Safari, Chrome, and Chrome Incognito
 *    alike, even though the server's Set-Cookie header was verified byte-for-byte
 *    correct. An Authorization header isn't a cookie, so no cookie policy touches it.
 *
 * captureTokenFromUrl() picks up the one-time `?token=` the backend hands back after
 * OAuth (see saas/app.py's auth_callback) and moves it into localStorage — call it
 * once, on the page the OAuth redirect actually lands on (currently `/app`).
 */

const TOKEN_KEY = "gc_token";

export function captureTokenFromUrl(): void {
  if (typeof window === "undefined") return;
  try {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (!token) return;
    localStorage.setItem(TOKEN_KEY, token);
    params.delete("token");
    const rest = params.toString();
    window.history.replaceState({}, "", window.location.pathname + (rest ? `?${rest}` : ""));
  } catch {
    // localStorage can throw in private-browsing/storage-blocked contexts — the
    // cookie path still covers same-site deployments either way.
  }
}

function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

export function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  return fetch(input, {
    ...init,
    credentials: "include",
    headers: { ...authHeader(), ...(init.headers || {}) },
  });
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}
