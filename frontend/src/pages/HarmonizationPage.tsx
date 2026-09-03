import { useEffect, useState } from "react";
import { fetchJson } from "../api";
import { EmptyState, ErrorState, LoadingState, MetricCard, PageHeading, StatusBadge } from "../components/Common";
import { useApi } from "../hooks/useApi";
import type { HarmonizationSummary, Lineage, MappingRow, ObservationPage } from "../types";

export default function HarmonizationPage() {
  const summary = useApi<HarmonizationSummary>("/api/v1/harmonization/summary");
  const mappings = useApi<MappingRow[]>("/api/v1/harmonization/mappings");
  const observations = useApi<ObservationPage>("/api/v1/afr-trade?limit=100");
  const [selected, setSelected] = useState("");
  const [lineage, setLineage] = useState<Lineage | null>(null);
  const [lineageError, setLineageError] = useState<string | null>(null);
  useEffect(() => {
    if (!selected) { setLineage(null); return; }
    let active = true;
    fetchJson<Lineage>(`/api/v1/afr-trade/${selected}/lineage`).then((value) => active && setLineage(value)).catch((reason: Error) => active && setLineageError(reason.message));
    return () => { active = false; };
  }, [selected]);
  const error = summary.error || mappings.error || observations.error;
  const batch = summary.data?.latest_batch;
  return <div className="page-width page-content">
    <PageHeading eyebrow="Source-to-target governance" title="Harmonisation">Inspect mapping decisions, execution counts, rejection evidence, and observation-level lineage.</PageHeading>
    {(summary.loading || mappings.loading || observations.loading) && <LoadingState label="Loading harmonisation evidence…" />}{error && <ErrorState message={error} />}
    {summary.data && <section className="source-target-panel compact-flow"><div><span>Source</span><strong>{summary.data.source}</strong></div><b aria-hidden="true">→</b><div><span>Target</span><strong>{summary.data.target}</strong></div></section>}
    {batch ? <section className="section-block"><div className="section-heading"><div><p className="eyebrow">Latest execution</p><h2>Harmonisation batch {batch.id}</h2></div><StatusBadge value={batch.status} /></div><div className="metric-grid four"><MetricCard label="Source received" value={batch.source_received} detail={`${batch.source_valid} source-valid`} /><MetricCard label="Transformed" value={batch.transformed} /><MetricCard label="Inserted / updated" value={`${batch.inserted} / ${batch.updated}`} /><MetricCard label="Rejected" value={batch.rejected} detail={`${batch.mapping_errors} mapping · ${batch.target_validation_errors} target validation errors`} /></div><p className="audit-line"><strong>Mapping:</strong> {batch.mapping_definition_id}({batch.mapping_version})</p>{summary.data?.rejection_reasons.length ? <div className="tag-row">{summary.data.rejection_reasons.map((row) => <span className="reason-tag" key={row.reason}>{row.reason.replaceAll("_", " ")} <strong>{row.count}</strong></span>)}</div> : null}</section> : summary.data && <EmptyState title="No harmonisation batch has been run.">Execution evidence will appear after the first governed batch.</EmptyState>}
    {mappings.data && <section className="section-block"><div className="section-heading"><div><p className="eyebrow">Mapping registry</p><h2>Concept mapping matrix</h2></div><p>{mappings.data.length} explicit source concept decisions.</p></div><div className="table-wrap"><table><thead><tr><th>Source concept</th><th>Target concept</th><th>Mapping type</th><th>Status</th></tr></thead><tbody>{mappings.data.map((row, index) => <tr key={`${row.source_concept}-${row.target_concept}-${index}`}><td><code>{row.source_concept}</code></td><td>{row.target_concept ? <code>{row.target_concept}</code> : "—"}</td><td><StatusBadge value={row.mapping_type} /></td><td><StatusBadge value={row.status} /></td></tr>)}</tbody></table></div></section>}
    {observations.data && <section className="section-block"><div className="section-heading"><div><p className="eyebrow">Audit trail</p><h2>Observation lineage</h2></div>{observations.data.items.length ? <label className="field compact" htmlFor="lineage-observation"><span>Target observation</span><select id="lineage-observation" value={selected} onChange={(event) => { setSelected(event.target.value); setLineageError(null); }}><option value="">Select an observation</option>{observations.data.items.map((row) => <option key={row.id} value={row.id}>{row.TIME_PERIOD} · {row.REF_AREA} · {row.TRADE_FLOW}</option>)}</select></label> : null}</div>{!observations.data.items.length ? <EmptyState title="No target observation is available for lineage display.">The current target warehouse contains no target-valid observations.</EmptyState> : !selected ? <EmptyState title="Select an observation.">Choose a target record to trace it back to UN Comtrade.</EmptyState> : lineageError ? <ErrorState message={lineageError} /> : lineage ? <div className="lineage"><div><span>Target observation</span><strong>#{lineage.target.id} · {lineage.target.dataset}</strong><small>{lineage.target.time_period} · {lineage.target.obs_value}</small></div><b>↓</b><div><span>Harmonisation batch</span><strong>#{lineage.harmonization_batch ?? "—"}</strong></div><b>↓</b><div><span>Mapping</span><strong>{lineage.mapping.definition}({lineage.mapping.version})</strong></div><b>↓</b><div><span>Source trade observation</span><strong>#{lineage.source_observation.id ?? "—"}</strong><small>{lineage.source_observation.key_hash}</small></div><b>↓</b><div><span>Source ingestion batch</span><strong>#{lineage.source_ingestion_batch ?? "—"}</strong></div><b>↓</b><div><span>Provider</span><strong>{lineage.provider}</strong></div></div> : <LoadingState label="Loading observation lineage…" />}</section>}
  </div>;
}
