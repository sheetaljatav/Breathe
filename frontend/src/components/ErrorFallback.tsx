import type { FallbackProps } from "react-error-boundary";

export function ErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-md">
        <h1 className="text-lg font-semibold mb-2">Something went wrong.</h1>
        <p className="text-sm text-ink-muted mb-4">
          The app hit an error it couldn&apos;t recover from. The team has been notified.
        </p>
        <pre className="text-xs font-mono bg-surface-muted border border-surface-border rounded p-3 overflow-auto mb-4">
          {error?.message ?? String(error)}
        </pre>
        <button className="btn" onClick={resetErrorBoundary}>
          Reload
        </button>
      </div>
    </div>
  );
}
