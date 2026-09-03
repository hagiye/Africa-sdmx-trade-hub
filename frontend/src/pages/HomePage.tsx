import { Link } from "react-router-dom";
import { MetricCard, ErrorState, LoadingState } from "../components/Common";
import Pipeline from "../components/Pipeline";
import { useApi } from "../hooks/useApi";
import type { Summary } from "../types";

export default function HomePage() {
  const { data, loading, error } = useApi<Summary>("/api/v1/summary");
  const periodLabel = data?.available_periods.count
    ? `${data.available_periods.earliest}–${data.available_periods.latest}`
    : "None published";
  return (
    <>
      <section className="hero page-width">
        <div className="hero-copy">
          <p className="eyebrow">Official-statistics engineering portfolio</p>
          <h1>Pan-African SDMX Trade Data Hub</h1>
          <p className="hero-lead">A portfolio implementation demonstrating SDMX metadata management, statistical validation, source-to-target harmonisation, data lineage, PostgreSQL warehousing and API-based dissemination.</p>
          <div className="button-row">
            <Link className="button primary" to="/explore">Explore Data</Link>
            <Link className="button secondary" to="/metadata">View Metadata</Link>
            <a className="button secondary" href="/docs">API Documentation</a>
            <Link className="text-link" to="/architecture">Architecture →</Link>
          </div>
        </div>
        <aside className="hero-note">
          <span className="classification">Demonstration system</span>
          <h2>Transparent by design</h2>
          <p>Source and target structures, validation evidence, mapping decisions, and observation lineage remain inspectable throughout the pipeline.</p>
        </aside>
      </section>

      <section className="section page-width" aria-labelledby="coverage-heading">
        <div className="section-heading"><div><p className="eyebrow">Current warehouse</p><h2 id="coverage-heading">Statistical coverage</h2></div><p>Live values from the PostgreSQL-backed API.</p></div>
        {loading && <LoadingState label="Loading current coverage…" />}
        {error && <ErrorState message={error} />}
        {data && <div className="metric-grid">
          <MetricCard label="Harmonised observations" value={data.harmonised_observations.toLocaleString()} detail="Target-valid records" />
          <MetricCard label="Reporting countries" value={data.reporting_countries.toLocaleString()} detail="Canonical target areas" />
          <MetricCard label="Counterpart areas" value={data.counterpart_areas.toLocaleString()} detail="Countries, regions, aggregates" />
          <MetricCard label="Available periods" value={periodLabel} detail={`${data.available_periods.count} distinct period(s)`} />
          <MetricCard label="Source dataset" value={data.source_dataset} detail={`${data.source_observations} warehouse records`} />
          <MetricCard label="Target DSD version" value={data.target_dsd_version} detail={data.target_dataflow} />
        </div>}
      </section>

      <section className="section section-tint"><div className="page-width">
        <div className="section-heading"><div><p className="eyebrow">Processing model</p><h2>From provider data to a governed API</h2></div><p>Every transition has explicit metadata, validation, or audit evidence.</p></div>
        <Pipeline />
      </div></section>

      <section className="section page-width two-column-callout">
        <div><p className="eyebrow">Start with the data</p><h2>Inspect statistics and their meaning together</h2><p>The explorer keeps human-readable labels beside exact target codes and gives technical reviewers the matching REST query.</p></div>
        <Link className="button primary" to="/explore">Open Data Explorer</Link>
      </section>
    </>
  );
}
