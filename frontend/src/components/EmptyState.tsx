import type { ReactNode } from "react";

interface Props {
  title: string;
  body?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ title, body, action }: Props) {
  return (
    <div className="border border-dashed border-surface-border rounded p-10 text-center bg-white">
      <div className="text-sm font-medium">{title}</div>
      {body && <div className="text-sm text-ink-muted mt-1">{body}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
