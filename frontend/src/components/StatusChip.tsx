import clsx from "clsx";

import type { ReviewState } from "@/api/types";

const CLASS: Record<ReviewState, string> = {
  pending:  "chip-pending",
  flagged:  "chip-flagged",
  approved: "chip-approved",
  rejected: "chip-rejected",
  locked:   "chip-locked",
};

export function StatusChip({ state }: { state: ReviewState }) {
  return <span className={clsx(CLASS[state])}>{state}</span>;
}

export function BatchStatusChip({ status }: { status: "queued" | "parsing" | "complete" | "failed" }) {
  const cls = {
    queued:   "chip-pending",
    parsing:  "chip-flagged",
    complete: "chip-approved",
    failed:   "chip-rejected",
  }[status];
  return <span className={cls}>{status}</span>;
}
