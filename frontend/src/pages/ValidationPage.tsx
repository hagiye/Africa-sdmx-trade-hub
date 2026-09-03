import { ErrorState, LoadingState, PageHeading, MetricCard, EmptyState, StatusBadge } from "../components/Common";
import { useApi } from "../hooks/useApi";
import type { FindingsPage, ValidationRule, ValidationSummary } from "../types";

export default function ValidationPage() {
  const summary = useApi<ValidationSummary>("/api/v1/validation/summary");
  const rules = useApi<ValidationRule[]>("/api/v1/validation/rules");
  const findings = useApi<FindingsPage>("/api/v1/validation/findings?limit=50");
  const error = summary.error || rules.error || findings.error;
  const loading = summary.loading || rules.loading || findings.loading;
  return <div className="page-width page-content">
    <PageHeading eyebrow="Quality assurance" title="Validation evidence">Review stored rule outcomes produced while source observations enter the statistical warehouse.</PageHeading>
    {loading && <LoadingState label="Loading validation evidence…" />}{error && <ErrorState message={error} />}
    {summary.data && <div className="metric-grid four"><MetricCard label="Validated observations" value={summary.data.validated_observations} /><MetricCard label="Warnings" value={summary.data.warnings} /><MetricCard label="Errors" value={summary.data.errors} /><MetricCard label="Rejected" value={summary.data.rejected} /></div>}
    {rules.data && <section className="section-block"><div className="section-heading"><div><p className="eyebrow">Rule outcomes</p><h2>Validation rules</h2></div><p>Counts reflect persisted findings, not fabricated examples.</p></div>{rules.data.length ? <div className="table-wrap"><table><thead><tr><th>Rule</th><th>Category</th><th>Severity</th><th>Concept</th><th>Count</th></tr></thead><tbody>{rules.data.map((row, index) => <tr key={`${row.rule}-${row.severity}-${index}`}><td>{row.rule}</td><td>{row.category}</td><td><StatusBadge value={row.severity} /></td><td>{row.concept ?? "—"}</td><td>{row.count}</td></tr>)}</tbody></table></div> : <EmptyState title="No validation findings are stored.">Accepted observations may have passed without producing warning or error findings.</EmptyState>}</section>}
    {findings.data && <section className="section-block"><div className="section-heading"><div><p className="eyebrow">Audit detail</p><h2>Recent findings</h2></div><p>{findings.data.total} stored finding(s), newest first.</p></div>{findings.data.items.length ? <div className="table-wrap"><table><thead><tr><th>Batch</th><th>Observation</th><th>Rule</th><th>Severity</th><th>Concept</th><th>Invalid value</th><th>Message</th></tr></thead><tbody>{findings.data.items.map((row) => <tr key={row.id}><td>{row.batch}</td><td>{row.observation ?? "Rejected"}</td><td>{row.rule}</td><td><StatusBadge value={row.severity} /></td><td>{row.concept ?? "—"}</td><td>{row.invalid_value ?? "—"}</td><td>{row.message}</td></tr>)}</tbody></table></div> : <EmptyState title="No detailed findings.">There are no stored validation findings to display.</EmptyState>}</section>}
  </div>;
}
