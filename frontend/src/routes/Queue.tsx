import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useQueue, useTransitionActivity } from "@/api/hooks";
import type { ReviewState } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { StatusChip } from "@/components/StatusChip";
import { fmtDate, fmtNumber } from "@/lib/format";

const STATES: { value: ReviewState | ""; label: string }[] = [
  { value: "",         label: "All" },
  { value: "pending",  label: "Pending" },
  { value: "flagged",  label: "Flagged" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "locked",   label: "Locked" },
];

export function Queue() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const state = params.get("state") || "";
  const category = params.get("category") || "";
  const q = params.get("q") || "";

  const queue = useQueue({
    state: (state || undefined) as ReviewState | undefined,
    category: category || undefined,
    q: q || undefined,
  });

  // Keyboard navigation: j/k move the highlight, Enter opens, a/f act on highlighted.
  const [highlight, setHighlight] = useState(0);
  const rowsRef = useRef<HTMLTableRowElement[]>([]);

  const rows = queue.data?.results ?? [];

  const approve = useTransitionActivity("approve");
  const flag = useTransitionActivity("flag");

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "j") setHighlight((h) => Math.min(h + 1, Math.max(rows.length - 1, 0)));
      else if (e.key === "k") setHighlight((h) => Math.max(h - 1, 0));
      else if (e.key === "Enter" && rows[highlight]) nav(`/queue/${rows[highlight].id}`);
      else if (e.key === "a" && rows[highlight]) approve.mutate({ id: rows[highlight].id });
      else if (e.key === "f" && rows[highlight]) flag.mutate({ id: rows[highlight].id });
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, highlight, approve, flag, nav]);

  useEffect(() => {
    rowsRef.current[highlight]?.scrollIntoView({ block: "nearest" });
  }, [highlight]);

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
    setHighlight(0);
  };

  return (
    <>
      <PageHeader
        title="Review queue"
        subtitle={
          <>
            <span className="font-mono text-xs">j</span>/<span className="font-mono text-xs">k</span> navigate ·
            <span className="font-mono text-xs ml-1.5">Enter</span> open ·
            <span className="font-mono text-xs ml-1.5">a</span> approve ·
            <span className="font-mono text-xs ml-1.5">f</span> flag
          </>
        }
      />

      <div className="p-6 space-y-4">
        <div className="bg-white border border-surface-border rounded p-3 flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1">
            {STATES.map((s) => (
              <button
                key={s.value || "all"}
                onClick={() => setFilter("state", s.value)}
                className={[
                  "px-2 h-7 text-xs uppercase tracking-wider rounded transition-colors",
                  state === s.value
                    ? "bg-ink text-ink-inverse"
                    : "bg-surface-muted text-ink-muted hover:bg-surface-border",
                ].join(" ")}
              >
                {s.label}
              </button>
            ))}
          </div>
          <div className="h-5 w-px bg-surface-border" />
          <input
            className="input"
            placeholder="Search facility or notes…"
            value={q}
            onChange={(e) => setFilter("q", e.target.value)}
          />
        </div>

        {queue.isLoading ? <Spinner /> : !rows.length ? (
          <EmptyState
            title="Nothing here."
            body={state ? `No ${state} records.` : "Upload data on the Imports page."}
          />
        ) : (
          <div className="bg-white border border-surface-border rounded overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-surface-border">
                  <th className="th w-12">#</th>
                  <th className="th">Date</th>
                  <th className="th">Category</th>
                  <th className="th">Scope</th>
                  <th className="th">Facility</th>
                  <th className="th text-right">Value</th>
                  <th className="th">Unit</th>
                  <th className="th text-right">kg CO₂e</th>
                  <th className="th">Source</th>
                  <th className="th">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr
                    key={r.id}
                    ref={(el) => { if (el) rowsRef.current[i] = el; }}
                    onClick={() => nav(`/queue/${r.id}`)}
                    onMouseEnter={() => setHighlight(i)}
                    className={[
                      "border-b last:border-0 border-surface-border cursor-pointer",
                      highlight === i ? "bg-surface-muted" : "hover:bg-surface-subtle",
                    ].join(" ")}
                  >
                    <td className="td font-mono text-xs text-ink-muted">{r.id}</td>
                    <td className="td font-mono text-xs">{fmtDate(r.activity_date)}</td>
                    <td className="td">{r.category.label}</td>
                    <td className="td font-mono">S{r.scope}</td>
                    <td className="td font-mono text-xs">{r.facility_code || "—"}</td>
                    <td className="td num text-right">{fmtNumber(r.value)}</td>
                    <td className="td font-mono text-xs">{r.unit.code}</td>
                    <td className="td num text-right">{r.emissions_kg_co2e ? fmtNumber(r.emissions_kg_co2e, 1) : "—"}</td>
                    <td className="td uppercase text-xs text-ink-muted tracking-wider">{r.source_type ?? "—"}</td>
                    <td className="td"><StatusChip state={r.review_state} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
