import { type FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import {
  useActivity,
  usePatchActivity,
  useTransitionActivity,
} from "@/api/hooks";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { StatusChip } from "@/components/StatusChip";
import { fmtDate, fmtNumber, fmtRelative } from "@/lib/format";

export function QueueDetail() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const q = useActivity(id ? Number(id) : null);

  if (q.isLoading) return <div className="p-6"><Spinner /></div>;
  if (q.isError || !q.data) return <div className="p-6 text-sm text-status-rejected">Not found.</div>;

  const r = q.data;

  return (
    <>
      <PageHeader
        title={`Record #${r.id}`}
        subtitle={
          <>
            <Link to="/queue" className="text-ink-muted hover:text-ink">← queue</Link>
            <span className="mx-2 text-ink-subtle">·</span>
            <span className="font-mono text-xs">{r.category.code}</span>
            <span className="mx-2 text-ink-subtle">·</span>
            <span className="font-mono text-xs">S{r.scope}</span>
            <span className="mx-2 text-ink-subtle">·</span>
            <span className="font-mono text-xs">v{r.version}</span>
          </>
        }
        actions={<TransitionButtons recordId={r.id} state={r.review_state} />}
      />

      <div className="p-6 space-y-6">
        {r.hints.length > 0 && (
          <div className="space-y-1.5">
            {r.hints.map((h) => (
              <div key={h.code} className="bg-amber-50 border border-amber-200 text-amber-900 px-3 py-2 rounded text-sm flex items-start gap-2">
                <span className="font-mono text-xs uppercase tracking-wider mt-0.5">{h.code}</span>
                <span>{h.message}</span>
              </div>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <RawPanel raw={r.raw_payload} line={r.source_line} />
          <NormalizedPanel record={r} />
        </div>

        <Meta record={r} />
      </div>
    </>
  );
}

function RawPanel({ raw, line }: { raw: unknown; line?: number }) {
  return (
    <div className="bg-white border border-surface-border rounded">
      <div className="h-10 px-3 border-b border-surface-border flex items-center justify-between">
        <div className="text-sm font-medium">Raw payload</div>
        {line !== undefined && (
          <div className="font-mono text-xs text-ink-subtle">line {line}</div>
        )}
      </div>
      <pre className="p-3 text-xs font-mono overflow-auto max-h-[480px] whitespace-pre-wrap leading-relaxed">
        {raw ? JSON.stringify(raw, null, 2) : "(no source record)"}
      </pre>
    </div>
  );
}

function NormalizedPanel({ record }: { record: ReturnType<typeof useActivity>["data"] & {} }) {
  const patch = usePatchActivity();
  const [value, setValue] = useState(record.value);
  const [facility, setFacility] = useState(record.facility_code);
  const [notes, setNotes] = useState(record.notes);
  const [conflict, setConflict] = useState<unknown>(null);

  const dirty = value !== record.value || facility !== record.facility_code || notes !== record.notes;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setConflict(null);
    patch.mutate(
      { id: record.id, version: record.version, body: { value, facility_code: facility, notes } },
      {
        onError: (err) => {
          if ((err as ApiError).status === 412) {
            setConflict((err as ApiError).body);
          }
        },
      }
    );
  };

  return (
    <div className="bg-white border border-surface-border rounded">
      <div className="h-10 px-3 border-b border-surface-border flex items-center justify-between">
        <div className="text-sm font-medium">Normalized</div>
        <StatusChip state={record.review_state} />
      </div>
      <form onSubmit={submit} className="p-3 space-y-3 text-sm">
        <Field label="Value">
          <input
            className="input w-full font-mono num text-right"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={record.review_state === "locked"}
          />
          <div className="text-xs text-ink-subtle mt-1">Unit <span className="font-mono">{record.unit.code}</span></div>
        </Field>
        <Field label="Facility / meter">
          <input
            className="input w-full font-mono"
            value={facility}
            onChange={(e) => setFacility(e.target.value)}
            disabled={record.review_state === "locked"}
          />
        </Field>
        <Field label="Notes">
          <textarea
            className="input w-full font-mono text-xs h-20 py-1 resize-y"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={record.review_state === "locked"}
          />
        </Field>

        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-surface-border text-xs">
          <KV label="Activity date" value={<span className="font-mono">{fmtDate(record.activity_date)}</span>} />
          <KV label="Period" value={
            <span className="font-mono">
              {record.period_start ? `${fmtDate(record.period_start)} → ${fmtDate(record.period_end)}` : "—"}
            </span>
          } />
          <KV label="Emission factor" value={
            record.emission_factor ? (
              <span className="font-mono">
                {record.emission_factor.kg_co2e_per_unit} {record.emission_factor.region} {record.emission_factor.year}
              </span>
            ) : <span className="text-ink-subtle">none pinned</span>
          } />
          <KV label="kg CO₂e" value={<span className="font-mono num">{record.emissions_kg_co2e ? fmtNumber(record.emissions_kg_co2e) : "—"}</span>} />
        </div>

        {conflict !== null && (
          <div className="bg-amber-50 border border-amber-200 text-amber-900 px-3 py-2 rounded text-sm">
            <div className="font-medium mb-1">Conflict — another analyst edited this record.</div>
            <div className="text-xs">Reload the page to see the current state. Your unsaved changes are still in the form above.</div>
          </div>
        )}

        <div className="flex items-center gap-2 pt-2">
          <button
            type="submit"
            className="btn-primary"
            disabled={!dirty || patch.isPending || record.review_state === "locked"}
          >
            {patch.isPending ? "Saving…" : "Save"}
          </button>
          {patch.isError && (patch.error as ApiError).status !== 412 && (
            <div className="text-sm text-status-rejected">{(patch.error as ApiError).message}</div>
          )}
        </div>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-ink-muted mb-1">{label}</label>
      {children}
    </div>
  );
}

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-ink-subtle uppercase tracking-wider text-[10px]">{label}</div>
      <div className="mt-0.5">{value}</div>
    </div>
  );
}

function Meta({ record }: { record: ReturnType<typeof useActivity>["data"] & {} }) {
  return (
    <div className="bg-white border border-surface-border rounded p-4 text-xs grid grid-cols-2 md:grid-cols-4 gap-y-3 gap-x-6">
      <KV label="Created" value={<span className="font-mono">{fmtRelative(record.created_at)}</span>} />
      <KV label="Updated" value={<span className="font-mono">{fmtRelative(record.updated_at)}</span>} />
      <KV label="Reviewed" value={
        record.reviewed_at ? <span className="font-mono">{fmtRelative(record.reviewed_at)}</span>
                           : <span className="text-ink-subtle">—</span>
      } />
      <KV label="Locked" value={
        record.locked_at ? <span className="font-mono">{fmtRelative(record.locked_at)}</span>
                         : <span className="text-ink-subtle">—</span>
      } />
      <KV label="Source batch" value={
        record.batch_id ? <Link to={`/imports`} className="font-mono text-ink hover:underline">#{record.batch_id}</Link>
                        : <span className="text-ink-subtle">—</span>
      } />
      <KV label="Version" value={<span className="font-mono">v{record.version}</span>} />
    </div>
  );
}

function TransitionButtons({ recordId, state }: { recordId: number; state: string }) {
  const approve = useTransitionActivity("approve");
  const flag = useTransitionActivity("flag");
  const reject = useTransitionActivity("reject");

  if (state === "locked") {
    return <span className="text-xs text-ink-muted">Locked for audit</span>;
  }

  return (
    <>
      <button className="btn" onClick={() => flag.mutate({ id: recordId })}>Flag</button>
      <button className="btn" onClick={() => reject.mutate({ id: recordId })}>Reject</button>
      <button className="btn-primary" onClick={() => approve.mutate({ id: recordId })}>Approve</button>
    </>
  );
}
