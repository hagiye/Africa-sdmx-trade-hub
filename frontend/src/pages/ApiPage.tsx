import { apiUrl } from "../api";
import { PageHeading } from "../components/Common";

const endpoints = [
  ["Interactive API documentation", "/docs", "Swagger UI for trying available operations."],
  ["Alternative API documentation", "/redoc", "Readable schema and endpoint reference."],
  ["AFR_TRADE observations", "/api/v1/afr-trade", "Filtered, paginated target observations."],
  ["AFR_TRADE metadata", "/api/v1/afr-trade/metadata", "Target identity, components, and codelists."],
  ["Dataflows", "/api/v1/dataflows", "Registered SDMX dataflow metadata."],
  ["Codelists", "/api/v1/codelists", "Registered controlled vocabularies."],
  ["Validation summary", "/api/v1/validation/summary", "Persisted source-validation evidence."],
  ["Harmonisation summary", "/api/v1/harmonization/summary", "Latest batch and rejection counts."]
];

export default function ApiPage() {
  return <div className="page-width page-content">
    <PageHeading eyebrow="Machine-readable access" title="API">Read-only interfaces expose statistical observations, metadata, quality evidence, and lineage.</PageHeading>
    <aside className="notice"><strong>Interface scope</strong><p>The AFR_TRADE endpoints are statistical REST endpoints. They are not presented as a complete implementation of the SDMX REST specification.</p></aside>
    <div className="endpoint-list">{endpoints.map(([name, path, description]) => <article key={path}><div><span className="method">GET</span><code>{path}</code></div><h2>{name}</h2><p>{description}</p><a href={apiUrl(path)}>{path.startsWith("/docs") || path === "/redoc" ? "Open documentation" : "View JSON"} →</a></article>)}</div>
  </div>;
}
