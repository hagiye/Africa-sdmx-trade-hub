import { useEffect, useState } from "react";
import { fetchJson } from "../api";
import { EmptyState, ErrorState, LoadingState, PageHeading } from "../components/Common";
import { useApi } from "../hooks/useApi";
import type { CodePage, TargetMetadata } from "../types";

export default function MetadataPage() {
  const { data, loading, error } = useApi<TargetMetadata>("/api/v1/afr-trade/metadata");
  const [selected, setSelected] = useState("");
  const [codes, setCodes] = useState<CodePage | null>(null);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [codesLoading, setCodesLoading] = useState(false);

  useEffect(() => { if (data?.codelists.length && !selected) setSelected(data.codelists[0].id); }, [data, selected]);
  useEffect(() => {
    const reference = data?.codelists.find((item) => item.id === selected);
    if (!reference) return;
    let active = true;
    setCodesLoading(true);
    setCodeError(null);
    fetchJson<CodePage>(`/api/v1/codelists/${reference.agency}/${reference.id}/${reference.version}/codes?page_size=500`)
      .then((value) => active && setCodes(value))
      .catch((reason: Error) => active && setCodeError(reason.message))
      .finally(() => active && setCodesLoading(false));
    return () => { active = false; };
  }, [data, selected]);

  return <div className="page-width page-content">
    <PageHeading eyebrow="Structural metadata" title="AFR_TRADE metadata">Inspect the target structure and controlled code lists used to interpret harmonised observations.</PageHeading>
    {loading && <LoadingState />}{error && <ErrorState message={error} />}
    {data && <>
      <section className="identity-grid" aria-label="Target structure identity">
        <div><span>Target agency</span><strong>{data.agency}</strong></div><div><span>Dataflow</span><strong>{data.dataflow}</strong></div><div><span>Version</span><strong>{data.version}</strong></div><div><span>DSD</span><strong>{data.DSD.agency}:{data.DSD.id}({data.DSD.version})</strong></div>
      </section>
      <aside className="notice"><strong>Independent model</strong><p>{data.disclaimer}</p></aside>
      <section className="section-block"><div className="section-heading"><div><p className="eyebrow">Data structure definition</p><h2>Target components</h2></div><p>Ordered dimensions, measure, and observation attributes from the canonical target definition.</p></div>
        <div className="table-wrap"><table><thead><tr><th>Position</th><th>Concept</th><th>Role</th><th>Codelist</th><th>Required</th></tr></thead><tbody>{data.components.map((item) => <tr key={`${item.role}-${item.concept}`}><td>{item.position ?? "—"}</td><td><code>{item.concept}</code></td><td>{item.role.replaceAll("_", " ")}</td><td>{item.codelist ? `${item.codelist.agency}:${item.codelist.id}(${item.codelist.version})` : "—"}</td><td>{item.required ? "Yes" : "No"}</td></tr>)}</tbody></table></div>
      </section>
      <section className="section-block"><div className="section-heading"><div><p className="eyebrow">Controlled vocabularies</p><h2>Codelist viewer</h2></div><label className="field compact" htmlFor="codelist"><span>Codelist</span><select id="codelist" value={selected} onChange={(event) => setSelected(event.target.value)}>{data.codelists.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.code_count} codes</option>)}</select></label></div>
        {codesLoading && <LoadingState label="Loading codelist codes…" />}{codeError && <ErrorState message={codeError} />}{codes && !codes.items.length && <EmptyState title="No codes available.">This codelist is currently empty.</EmptyState>}{codes?.items.length ? <div className="table-wrap compact-table"><table><thead><tr><th>Code</th><th>English label</th><th>French label</th><th>Type / category</th></tr></thead><tbody>{codes.items.map((item) => <tr key={item.code}><td><code>{item.code}</code></td><td>{item.labels.en ?? "—"}</td><td lang="fr">{item.labels.fr ?? "—"}</td><td>{item.code === "AFR_WORLD" ? "Aggregate" : item.parent_code ?? "—"}</td></tr>)}</tbody></table></div> : null}
      </section>
      <section className="source-target-panel"><div><span>Source DSD</span><strong>UNSD:IMTS(1.2)</strong><p>Source observations are validated against their source metadata before harmonisation.</p></div><b aria-hidden="true">→</b><div><span>Target DSD</span><strong>AFRSTAT:AFR_TRADE(1.0)</strong><p>Transformed observations are validated again against the independent target metadata.</p></div></section>
    </>}
  </div>;
}
