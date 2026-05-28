/**
 * Typed fetch client.
 *
 * Responsibilities:
 *   * Acquire and attach the CSRF token to unsafe methods. In dev (same-origin
 *     Vite proxy) we can read the `csrftoken` cookie via document.cookie. In
 *     prod the SPA is at *.onrender.com and the API is at a different
 *     subdomain, so document.cookie can't see the backend's cookie — we read
 *     the token from the JSON body of /api/auth/csrf and keep it in module
 *     state. (The session cookie itself still flows correctly thanks to
 *     credentials:"include" + SameSite=None.)
 *   * Send credentials so the sessionid cookie flows.
 *   * Set X-Org-ID from the UI store so backend pins per-request org context.
 *   * Normalize errors into ApiError with status + body — TanStack Query's
 *     retry policy keys off `.status`.
 *   * Broadcast a `auth:unauthorized` window event on 401 so the App shell
 *     can drop the user back to /login without each hook re-implementing
 *     the redirect.
 */

import { useUiStore } from "@/store/ui";

// Dev: empty string → Vite proxies /api to localhost:8000.
// Prod: VITE_API_BASE_URL is set on the static-site service to the backend's
// public URL (e.g. https://breathe-web.onrender.com). Backend has CORS
// allowlisted to the frontend origin + SameSite=None on session cookies.
const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

// CSRF token cached in module state. Populated by ensureCsrf(); refreshed on
// 403 in case the backend rotated it. Per-tab, in-memory only — survives
// SPA navigations, dies on full reload (which is fine, we re-fetch).
let csrfToken: string | null = null;

function getCookie(name: string): string | null {
  const m = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)")
  );
  return m ? decodeURIComponent(m[1]) : null;
}

function resolveCsrf(): string | null {
  // Same-origin dev: prefer cookie (always fresh, no race with ensureCsrf).
  // Cross-origin prod: cookie is unreadable, so fall back to module state.
  return getCookie("csrftoken") ?? csrfToken;
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  ifMatch?: number | string;
  /** Skip pinning X-Org-ID — useful for auth endpoints. */
  noOrg?: boolean;
  /** Internal: set by retry path to avoid infinite loops. */
  _retried?: boolean;
}

export async function api<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = (opts.method ?? "GET").toUpperCase();
  const headers = new Headers(opts.headers ?? {});

  if (UNSAFE.has(method)) {
    const csrf = resolveCsrf();
    if (csrf) headers.set("X-CSRFToken", csrf);
  }
  if (opts.ifMatch !== undefined) headers.set("If-Match", String(opts.ifMatch));
  if (!opts.noOrg) {
    const orgId = useUiStore.getState().orgId;
    if (orgId) headers.set("X-Org-ID", String(orgId));
  }

  let body: BodyInit | undefined;
  if (opts.body !== undefined) {
    if (opts.body instanceof FormData) {
      body = opts.body;
      // Don't set Content-Type; browser sets multipart boundary.
    } else {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(opts.body);
    }
  }

  const res = await fetch(BASE + path, {
    ...opts, method, headers, body,
    credentials: "include",
  });

  // 204 No Content
  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let parsed: unknown = undefined;
  if (text) {
    try { parsed = JSON.parse(text); }
    catch { parsed = text; }
  }

  if (!res.ok) {
    // Refresh CSRF once on 403 and retry the original request, in case the
    // backend rotated the token (e.g. after a server restart).
    if (res.status === 403 && UNSAFE.has(method) && !opts._retried) {
      try {
        await ensureCsrf();
        return api<T>(path, { ...opts, _retried: true });
      } catch {
        // Fall through to normal error throwing.
      }
    }

    // 401: tell the shell so it can drop the user back to /login.
    if (res.status === 401) {
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }

    const msg = (parsed as { detail?: string } | undefined)?.detail
      ?? `${method} ${path} ${res.status}`;
    throw new ApiError(res.status, parsed, msg);
  }
  return parsed as T;
}

/** Fetch the CSRF token and cache it. Call on app boot, also before any
 *  POST/PATCH/DELETE where the session may have just changed (login). */
export async function ensureCsrf(): Promise<void> {
  const data = await api<{ csrftoken: string }>("/api/auth/csrf", { noOrg: true });
  if (data?.csrftoken) csrfToken = data.csrftoken;
}
