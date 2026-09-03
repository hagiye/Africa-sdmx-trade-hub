import { Link } from "react-router-dom";
import { PageHeading } from "../components/Common";

export default function AboutPage() {
  return <div className="page-width page-content prose-page">
    <PageHeading eyebrow="Project context" title="About this demonstration">A practical portfolio project focused on the engineering disciplines behind trusted official-statistics dissemination.</PageHeading>
    <section><h2>Purpose</h2><p>The hub demonstrates how SDMX metadata, statistical validation, source-to-target harmonisation, data quality, PostgreSQL warehousing, and observation lineage can work together for African merchandise trade data.</p><p>Its design makes both data and methodology inspectable: users can review the target structure, controlled vocabularies, mapping decisions, validation findings, and the path from a target observation back to its ingestion batch.</p></section>
    <section><h2>Data source and attribution</h2><p>The bounded source observations used by this project are attributed to the <strong>UN Statistics Division / UN Comtrade</strong>. AFRSTAT is the identifier of this project's independent demonstration target model; it does not claim production of the underlying source statistics.</p></section>
    <aside className="disclaimer-card"><strong>Independent portfolio demonstration</strong><p>This project is not affiliated with, endorsed by, or an official system of the African Union or STATAFRIC.</p></aside>
    <section><h2>Explore the evidence</h2><p><Link to="/metadata">Review the target metadata</Link>, <Link to="/validation">inspect validation evidence</Link>, or <Link to="/architecture">follow the system architecture</Link>.</p></section>
  </div>;
}
