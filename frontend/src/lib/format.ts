/** Small formatters shared across pages. Keep this file boring. */

import { formatDistanceToNow, format as dfFormat, parseISO } from "date-fns";

export function fmtKg(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + " t · 10³";
  if (n >= 1_000) return (n / 1_000).toFixed(2) + " t";
  return n.toLocaleString(undefined, { maximumFractionDigits: 3 }) + " kg";
}

export function fmtNumber(v: number | string | null | undefined, max = 4): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: max });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dfFormat(parseISO(iso), "yyyy-MM-dd");
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  return formatDistanceToNow(parseISO(iso), { addSuffix: true });
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}
