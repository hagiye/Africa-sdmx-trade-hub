import { PageHeading } from "../components/Common";

const stages = [
  ["UN Comtrade", "Provider of the bounded merchandise trade source data"],
  ["SDMX Metadata Registry", "Source and target structures, concepts, and codelists"],
  ["Parser", "Provider JSON interpreted without losing source context"],
  ["Source Validation", "Structure, codes, values, geography, scope, and quality"],
  ["Source Warehouse", "Deterministic identities and ingestion-batch lineage"],
  ["Mapping Registry", "Versioned DIRECT, RENAME, TRANSFORM, DERIVE, DROP, and DEFER decisions"],
  ["AFR_TRADE Harmonisation", "Registry-driven source-to-target transformation"],
  ["Target Validation", "Independent target DSD and codelist checks"],
  ["Harmonised Warehouse", "Target-valid observations or explicit rejection evidence"],
  ["FastAPI", "Read-only statistical and metadata interfaces"],
  ["Data Explorer", "Accessible recruiter-facing dissemination interface"]
];

export default function ArchitecturePage() {
  return <div className="page-width page-content">
    <PageHeading eyebrow="System design" title="Architecture">A metadata-led statistical processing chain with explicit validation and audit boundaries.</PageHeading>
    <div className="architecture-flow">{stages.map(([name, description], index) => <div className="architecture-step" key={name}><div><span>{String(index + 1).padStart(2, "0")}</span><section><h2>{name}</h2><p>{description}</p></section></div>{index < stages.length - 1 && <b aria-hidden="true">↓</b>}</div>)}</div>
    <section className="section-block"><div className="section-heading"><div><p className="eyebrow">Implemented stack</p><h2>Technology</h2></div><p>Technologies currently present in this repository.</p></div><div className="technology-grid">{["Python", "FastAPI", "PostgreSQL", "SQLAlchemy", "Alembic", "SDMX", "React", "TypeScript", "Docker"].map((item) => <span key={item}>{item}</span>)}</div></section>
  </div>;
}
