import { type ChangeEvent, type DragEvent, useRef, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";

import { ApiError } from "@/api/client";
import { useBatches, usePasteJson, useUploadFile } from "@/api/hooks";
import type { SourceType } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { BatchStatusChip } from "@/components/StatusChip";
import { Spinner } from "@/components/Spinner";
import { fmtBytes, fmtNumber, fmtRelative } from "@/lib/format";

const COPY: Record<
  SourceType,
  { title: string; help: string; accept: string }
> = {
  sap: {
    title: "SAP — fuel & procurement",
    help: "SE16N CSV export. Semicolon-delimited, UTF-8, German decimal commas + DD.MM.YYYY dates. Plant codes resolved against the per-org lookup.",
    accept: ".csv,text/csv",
  },
  utility: {
    title: "Utility — electricity",
    help: "Either a portal CSV export or a text-extractable PDF bill. Both flow through the same pipeline. Scanned PDFs are flagged for manual entry.",
    accept: ".csv,.pdf,text/csv,application/pdf",
  },
  travel: {
    title: "Corporate travel",
    help: "Paste the JSON response from a Concur Reporting v4 /reports/{id}/expenses call. Schema documented in SOURCES.md.",
    accept: "",
  },
};

export function Imports() {
  return (
    <>
      <PageHeader
        title="Imports"
        subtitle="Upload source data; parsers run asynchronously and the queue updates when they finish."
      />
      <div className="p-6 space-y-6">
        <Tabs.Root
          defaultValue="sap"
          className="bg-white border border-surface-border rounded"
        >
          <Tabs.List className="flex border-b border-surface-border">
            <TabTrigger value="sap">SAP</TabTrigger>
            <TabTrigger value="utility">Utility</TabTrigger>
            <TabTrigger value="travel">Travel</TabTrigger>
          </Tabs.List>
          <Tabs.Content value="sap" forceMount>
            <FileTab source="sap" />
          </Tabs.Content>
          <Tabs.Content value="utility" forceMount>
            <FileTab source="utility" />
          </Tabs.Content>
          <Tabs.Content value="travel" forceMount>
            <TravelTab />
          </Tabs.Content>
        </Tabs.Root>

        <RecentBatches />
      </div>
    </>
  );
}

function TabTrigger({
  value,
  children,
}: {
  value: string;
  children: React.ReactNode;
}) {
  return (
    <Tabs.Trigger
      value={value}
      className="px-4 py-2 text-sm border-b-2 -mb-px border-transparent text-ink-muted
                 data-[state=active]:border-ink data-[state=active]:text-ink"
    >
      {children}
    </Tabs.Trigger>
  );
}

function FileTab({ source }: { source: SourceType }) {
  const upload = useUploadFile();
  const fileInput = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const submit = (file: File) => {
    upload.mutate({ source_type: source, file });
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const file = e.dataTransfer.files[0];
    if (file) submit(file);
  };

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) submit(file);
    e.target.value = ""; // allow re-uploading the same file
  };

  return (
    <div className="p-6">
      <div className="text-sm text-ink-muted mb-3">{COPY[source].help}</div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        className={[
          "border border-dashed rounded p-8 text-center transition-colors",
          drag
            ? "bg-surface-muted border-ink"
            : "border-surface-border bg-surface-subtle",
        ].join(" ")}
      >
        <div className="text-sm font-medium">Drop file here</div>
        <div className="text-xs text-ink-muted mt-1">or</div>
        <button className="btn mt-2" onClick={() => fileInput.current?.click()}>
          Choose file
        </button>
        <input
          ref={fileInput}
          type="file"
          className="hidden"
          accept={COPY[source].accept}
          onChange={onChange}
        />
      </div>

      <UploadResult mutation={upload} />
    </div>
  );
}

function TravelTab() {
  const paste = usePasteJson();
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const submit = () => {
    setErr(null);
    try {
      const payload = JSON.parse(text);
      paste.mutate({ payload, file_name: "concur_paste.json" });
    } catch (e) {
      setErr("Not valid JSON: " + (e as Error).message);
    }
  };

  return (
    <div className="p-6">
      <div className="text-sm text-ink-muted mb-3">{COPY.travel.help}</div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder='{"metadata": {...}, "trips": [...]}'
        className="w-full h-64 font-mono text-xs p-3 border border-surface-border rounded resize-y
                   focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/20"
      />
      <div className="flex items-center gap-3 mt-3">
        <button
          className="btn-primary"
          onClick={submit}
          disabled={!text || paste.isPending}
        >
          {paste.isPending ? "Submitting…" : "Submit"}
        </button>
        {err && <div className="text-sm text-status-rejected">{err}</div>}
      </div>

      <UploadResult mutation={paste} />
    </div>
  );
}

function UploadResult({
  mutation,
}: {
  mutation: {
    isPending: boolean;
    isSuccess: boolean;
    isError: boolean;
    data?: any;
    error?: unknown;
  };
}) {
  if (mutation.isError) {
    return (
      <div className="mt-4 text-sm text-status-rejected">
        {(mutation.error as ApiError)?.message ?? "Upload failed"}
      </div>
    );
  }
  if (mutation.isSuccess && mutation.data) {
    const b = mutation.data;
    return (
      <div className="mt-4 text-sm flex items-center gap-3">
        {b.deduped ? (
          <span className="text-ink-muted">
            Already imported — batch #{b.id}
          </span>
        ) : (
          <span>
            Queued batch #{b.id} (
            <span className="font-mono text-xs">
              {b.file_sha256.slice(0, 12)}
            </span>
            )
          </span>
        )}
        <BatchStatusChip status={b.status} />
      </div>
    );
  }
  return null;
}

function RecentBatches() {
  const q = useBatches();
  if (q.isLoading) return <Spinner />;
  if (!q.data?.results.length) {
    return (
      <EmptyState
        title="No imports yet"
        body="Upload a file above to get started."
      />
    );
  }
  return (
    <div className="bg-white border border-surface-border rounded">
      <div className="h-10 px-3 border-b border-surface-border flex items-center font-medium text-sm">
        Recent batches
      </div>
      <table className="w-full">
        <thead>
          <tr className="border-b border-surface-border">
            <th className="th">#</th>
            <th className="th">File</th>
            <th className="th">Source</th>
            <th className="th">Uploaded</th>
            <th className="th text-right">Size</th>
            <th className="th text-right">Rows ok / total</th>
            <th className="th text-right">Errors</th>
            <th className="th">Status</th>
          </tr>
        </thead>
        <tbody>
          {q.data.results.map((b) => (
            <tr
              key={b.id}
              className="border-b last:border-0 border-surface-border hover:bg-surface-subtle"
            >
              <td className="td font-mono text-xs text-ink-muted">{b.id}</td>
              <td className="td font-mono text-xs truncate max-w-[280px]">
                {b.file_name}
              </td>
              <td className="td uppercase tracking-wider text-xs text-ink-muted">
                {b.source_type}
              </td>
              <td className="td text-ink-muted">
                {fmtRelative(b.uploaded_at)}
              </td>
              <td className="td num text-right text-ink-muted">
                {fmtBytes(b.file_size_bytes)}
              </td>
              <td className="td num text-right">
                {fmtNumber(b.rows_ok)} / {fmtNumber(b.rows_total)}
              </td>
              <td className="td num text-right">
                {b.rows_failed > 0 ? (
                  <span className="text-amber-700">
                    {fmtNumber(b.rows_failed)}
                  </span>
                ) : (
                  "—"
                )}
              </td>
              <td className="td">
                <BatchStatusChip status={b.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
