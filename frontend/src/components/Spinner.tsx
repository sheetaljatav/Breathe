interface Props {
  size?: number;
}

export function Spinner({ size = 16 }: Props) {
  // Single-stroke arc; no pulse animation. Inline SVG so no CSS dep.
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24"
      className="animate-spin text-ink-muted"
      aria-label="Loading"
    >
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
