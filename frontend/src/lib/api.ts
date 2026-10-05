"use client";

// Backend REST client. This is a READ CACHE ONLY (see backend/README.md
// "Cache vs. live"). It's used for fast list/history views. Anything
// security- or fund-critical (e.g. "can I withdraw right now",
// "what's my cooldown") must ALSO do a live contract read via lib/contract.ts
// before the UI lets a user act — never trust the cache alone for that.

import { BACKEND_URL } from "./config";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {}
    throw new Error(`${res.status} ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---- Auth ----
export const authNonce = (address: string) =>
  req<{ address: string; nonce: string; message: string; expires_at: string }>("/auth/nonce", {
    method: "POST",
    body: JSON.stringify({ address }),
  });

export const authVerify = (address: string, message: string, signature: string) =>
  req<{ address: string; expires_at: string }>("/auth/verify", {
    method: "POST",
    body: JSON.stringify({ address, message, signature }),
  });

export const authLogout = () => req<{ status: string }>("/auth/logout", { method: "POST" });

export const authMe = () => req<{ address: string; expires_at: string }>("/auth/me");

// ---- Loans / covenants / checks / challenges (read cache) ----
export const listLoans = (params?: { lender?: string; borrower?: string }) => {
  const qs = new URLSearchParams();
  if (params?.lender) qs.set("lender", params.lender);
  if (params?.borrower) qs.set("borrower", params.borrower);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return req<any[]>(`/loans${suffix}`);
};
export const syncLoans = () => req<any[]>("/loans/sync", { method: "POST" });

export const getLoanCached = (loanId: number) => req<any>(`/loans/${loanId}`);
export const getLoanCovenantsCached = (loanId: number) => req<any[]>(`/loans/${loanId}/covenants`);
export const getLoanChecksCached = (loanId: number) => req<any[]>(`/loans/${loanId}/checks`);
export const getCovenantCached = (covenantId: number) => req<any>(`/covenants/${covenantId}`);
export const getCovenantChecksCached = (covenantId: number) => req<any[]>(`/covenants/${covenantId}/checks`);
export const getCheckChallengesCached = (checkId: number) => req<any[]>(`/covenants/checks/${checkId}/challenges`);

export const previewSource = (url: string) =>
  req<{ url: string; status_code: number; content_type: string | null; truncated_body: string; fetched_at: string; note: string }>(
    "/covenants/preview-source",
    { method: "POST", body: JSON.stringify({ url }) }
  );

export const healthz = () => req<any>("/healthz");
