import type { ReactNode } from "react";

export function PageHeading({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return (
    <header className="page-heading">
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p>{children}</p>
    </header>
  );
}

export function LoadingState({ label = "Loading statistical information…" }: { label?: string }) {
  return <div className="state-panel loading" role="status"><span className="spinner" aria-hidden="true" />{label}</div>;
}

export function ErrorState({ message }: { message: string }) {
  return <div className="state-panel error" role="alert"><strong>Information unavailable</strong><span>{message}</span></div>;
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return <div className="state-panel empty"><strong>{title}</strong><span>{children}</span></div>;
}

export function StatusBadge({ value }: { value: string }) {
  return <span className={`status status-${value.toLowerCase()}`}>{value.replaceAll("_", " ")}</span>;
}

export function MetricCard({ label, value, detail }: { label: string; value: ReactNode; detail?: string }) {
  return <article className="metric-card"><p>{label}</p><strong>{value}</strong>{detail && <small>{detail}</small>}</article>;
}
