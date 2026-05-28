import { Link } from "react-router-dom";

import { useBatches, useOverview } from "@/api/hooks";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { BatchStatusChip } from "@/components/StatusChip";
import { fmtKg, fmtNumber, fmtRelative } from "@/lib/format";

export function Overview() {
  const overview = useOverview();
  const batches = useBatches();

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="Per-period emissions and review queue at a glance"
      />

      <div className="p-6 space-y-6">
        {overview.isLoading ? (
          <Spinner />
        ) : overview.data ? (
          <>
            <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <Tile label="Total emissions"  primary={fmtKg(overview.data.totals.kg_co2e)} />
              <Tile label="Pending review"   primary={fmtNumber(overview.data.totals.pending)} />
              <Tile label="Flagged"          primary={fmtNumber(overview.data.totals.flagged)} accent="amber" />
              <Tile label="Approved"         primary={fmtNumber(overview.data.totals.approved)} accent="green" />
            </section>

            <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Panel title="By scope">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-surface-border">
                      <th className="th">Scope</th>
                      <th className="th text-right">Rows</th>
                      <th className="th text-right">kg CO₂e</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[1, 2, 3].map((scope) => {
                      const row = overview.data!.by_scope.find((r) => r.scope === scope);
                      return (
                        <tr key={scope} className="border-b last:border-0 border-surface-border">
                          <td className="td font-mono">Scope {scope}</td>
                          <td className="td text-right num">{fmtNumber(row?.rows ?? 0)}</td>
                          <td className="td text-right num">{fmtKg(row?.kg_co2e ?? 0)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </Panel>

              <Panel title="Recent imports" action={<Link to="/imports" className="btn-ghost">Open</Link>}>
                {batches.isLoading ? <Spinner /> : (
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-surface-border">
                        <th className="th">File</th>
                        <th className="th">Source</th>
                        <th className="th">When</th>
                        <th className="th text-right">Rows</th>
                        <th className="th">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {batches.data?.results.slice(0, 6).map((b) => (
                        <tr key={b.id} className="border-b last:border-0 border-surface-border">
                          <td className="td font-mono text-xs truncate max-w-[260px]">{b.file_name}</td>
                          <td className="td uppercase tracking-wider text-xs text-ink-muted">{b.source_type}</td>
                          <td className="td text-ink-muted">{fmtRelative(b.uploaded_at)}</td>
                          <td className="td num text-right">{fmtNumber(b.rows_ok)}/{fmtNumber(b.rows_total)}</td>
                          <td className="td"><BatchStatusChip status={b.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Panel>
            </section>
          </>
        ) : null}
      </div>
    </>
  );
}

function Tile({ label, primary, accent }: { label: string; primary: string; accent?: "amber" | "green" }) {
  const ring = accent === "amber" ? "border-amber-200"
             : accent === "green" ? "border-green-200"
             : "border-surface-border";
  return (
    <div className={`bg-white border ${ring} rounded p-4`}>
      <div className="text-xs uppercase tracking-wider text-ink-subtle">{label}</div>
      <div className="text-2xl font-semibold mt-1 num">{primary}</div>
    </div>
  );
}

function Panel({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-surface-border rounded">
      <div className="h-10 px-3 border-b border-surface-border flex items-center justify-between">
        <div className="text-sm font-medium">{title}</div>
        {action}
      </div>
      <div className="p-1">{children}</div>
    </div>
  );
}
