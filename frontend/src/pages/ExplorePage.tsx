import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis
} from "recharts";
import { apiUrl, fetchJson, formatExactDecimal } from "../api";
import { EmptyState, ErrorState, LoadingState, PageHeading } from "../components/Common";
import type { CodeItem, CodePage, Observation, ObservationPage, TargetMetadata } from "../types";

type FilterKey = "ref_area" | "counterpart_area" | "trade_flow" | "product_scheme" | "product" | "freq" | "start_period" | "end_period";
type Filters = Record<FilterKey, string>;
const blankFilters: Filters = { ref_area: "", counterpart_area: "", trade_flow: "", product_scheme: "", product: "", freq: "", start_period: "", end_period: "" };
const conceptFilters: Partial<Record<FilterKey, string>> = {
  ref_area: "REF_AREA", counterpart_area: "COUNTERPART_AREA", trade_flow: "TRADE_FLOW",
  product_scheme: "PRODUCT_SCHEME", product: "PRODUCT", freq: "FREQ"
};

function labelFor(code: string, labels: Map<string, string>): string {
  if (code === "AFR_WORLD") return `${labels.get(code) ?? "World"} · Aggregate`;
  return labels.get(code) ?? code;
}

function FilterSelect({ id, label, value, options, onChange }: { id: FilterKey; label: string; value: string; options: CodeItem[]; onChange: (id: FilterKey, value: string) => void }) {
  return <label className="field" htmlFor={id}><span>{label}</span><select id={id} value={value} onChange={(event) => onChange(id, event.target.value)}><option value="">All</option>{options.map((option) => <option key={option.code} value={option.code}>{labelFor(option.code, new Map([[option.code, option.labels.en ?? option.code]]))}</option>)}</select></label>;
}

export default function ExplorePage() {
  const [metadata, setMetadata] = useState<TargetMetadata | null>(null);
  const [codes, setCodes] = useState<Record<string, CodeItem[]>>({});
  const [filters, setFilters] = useState<Filters>(blankFilters);
  const [applied, setApplied] = useState<Filters>(blankFilters);
  const [results, setResults] = useState<ObservationPage | null>(null);
  const [loadingMeta, setLoadingMeta] = useState(true);
  const [loadingResults, setLoadingResults] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"table" | "chart">("table");
  const [sort, setSort] = useState<{ key: keyof Observation; direction: 1 | -1 }>({ key: "TIME_PERIOD", direction: 1 });

  useEffect(() => {
    let active = true;
    fetchJson<TargetMetadata>("/api/v1/afr-trade/metadata")
      .then(async (meta) => {
        if (!active) return;
        setMetadata(meta);
        const entries = await Promise.all(meta.codelists.map(async (item) => {
          const page = await fetchJson<CodePage>(`/api/v1/codelists/${item.agency}/${item.id}/${item.version}/codes?page_size=500`);
          return [item.id, page.items] as const;
        }));
        if (active) setCodes(Object.fromEntries(entries));
      })
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoadingMeta(false));
    return () => { active = false; };
  }, []);

  const queryPath = useMemo(() => {
    const query = new URLSearchParams();
    Object.entries(applied).forEach(([key, value]) => value && query.set(key, value));
    query.set("limit", "1000");
    return `/api/v1/afr-trade?${query.toString()}`;
  }, [applied]);

  useEffect(() => {
    let active = true;
    setLoadingResults(true);
    setError(null);
    fetchJson<ObservationPage>(queryPath)
      .then((value) => active && setResults(value))
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoadingResults(false));
    return () => { active = false; };
  }, [queryPath]);

  const componentOptions = (key: FilterKey) => {
    const concept = conceptFilters[key];
    const reference = metadata?.components.find((item) => item.concept === concept)?.codelist;
    return reference ? codes[reference.id] ?? [] : [];
  };
  const labels = useMemo(() => new Map(Object.values(codes).flat().map((code) => [code.code, code.labels.en ?? code.code])), [codes]);
  const sortedRows = useMemo(() => [...(results?.items ?? [])].sort((a, b) => String(a[sort.key] ?? "").localeCompare(String(b[sort.key] ?? ""), undefined, { numeric: true }) * sort.direction), [results, sort]);

  const updateFilter = (key: FilterKey, value: string) => setFilters((current) => ({ ...current, [key]: value }));
  const apply = (event: FormEvent) => { event.preventDefault(); setApplied({ ...filters }); };
  const reset = () => { setFilters(blankFilters); setApplied(blankFilters); };
  const toggleSort = (key: keyof Observation) => setSort((current) => ({ key, direction: current.key === key ? (current.direction === 1 ? -1 : 1) : 1 }));

  const downloadCsv = () => {
    if (!results?.items.length) return;
    const fields: Array<keyof Observation> = ["TIME_PERIOD", "REF_AREA", "COUNTERPART_AREA", "TRADE_FLOW", "PRODUCT_SCHEME", "PRODUCT", "UNIT_MEASURE", "OBS_VALUE"];
    const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const body = [fields.join(","), ...results.items.map((row) => fields.map((field) => escape(row[field])).join(","))].join("\r\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([body], { type: "text/csv;charset=utf-8" }));
    link.download = "afr-trade-filtered-results.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const selectedLabel = (key: FilterKey) => applied[key] ? labelFor(applied[key], labels) : "All";
  const chartData = sortedRows.map((row) => ({ ...row, plottedValue: Number(row.OBS_VALUE) }));

  return <div className="page-width page-content">
    <PageHeading eyebrow="Statistical dissemination" title="Data Explorer">Query harmonised AFR_TRADE observations using canonical dimensions and human-readable labels.</PageHeading>
    <form className="filter-panel" onSubmit={apply} aria-label="AFR_TRADE filters">
      <div className="filter-grid">
        <FilterSelect id="ref_area" label="Reporter" value={filters.ref_area} options={componentOptions("ref_area")} onChange={updateFilter} />
        <FilterSelect id="counterpart_area" label="Counterpart" value={filters.counterpart_area} options={componentOptions("counterpart_area")} onChange={updateFilter} />
        <FilterSelect id="trade_flow" label="Trade flow" value={filters.trade_flow} options={componentOptions("trade_flow")} onChange={updateFilter} />
        <FilterSelect id="product_scheme" label="Product scheme" value={filters.product_scheme} options={componentOptions("product_scheme")} onChange={updateFilter} />
        <FilterSelect id="product" label="Product" value={filters.product} options={componentOptions("product")} onChange={updateFilter} />
        <FilterSelect id="freq" label="Frequency" value={filters.freq} options={componentOptions("freq")} onChange={updateFilter} />
        <label className="field" htmlFor="start_period"><span>Start period</span><input id="start_period" inputMode="numeric" placeholder="e.g. 2022" value={filters.start_period} onChange={(e) => updateFilter("start_period", e.target.value)} /></label>
        <label className="field" htmlFor="end_period"><span>End period</span><input id="end_period" inputMode="numeric" placeholder="e.g. 2024" value={filters.end_period} onChange={(e) => updateFilter("end_period", e.target.value)} /></label>
      </div>
      <div className="filter-actions"><button className="button primary" type="submit" disabled={loadingMeta}>Apply Filters</button><button className="button secondary" type="button" onClick={reset}>Reset</button></div>
    </form>

    {error && <ErrorState message={error} />}
    {loadingResults && <LoadingState label="Querying harmonised observations…" />}
    {!loadingResults && results && <>
      <section className="results-summary" aria-label="Results summary">
        <div><span>Reporter</span><strong>{selectedLabel("ref_area")}</strong></div><div><span>Counterpart</span><strong>{selectedLabel("counterpart_area")}</strong></div><div><span>Flow</span><strong>{selectedLabel("trade_flow")}</strong></div><div><span>Product</span><strong>{selectedLabel("product")}</strong></div><div><span>Period range</span><strong>{applied.start_period || "First"}–{applied.end_period || "Latest"}</strong></div><div><span>Observations</span><strong>{results.total.toLocaleString()}</strong></div>
      </section>
      <div className="results-toolbar">
        <div className="segmented" aria-label="Result view"><button className={view === "table" ? "active" : ""} onClick={() => setView("table")}>Table</button><button className={view === "chart" ? "active" : ""} onClick={() => setView("chart")}>Chart</button></div>
        <div><button className="button secondary small" disabled={!results.items.length} onClick={downloadCsv}>Download CSV</button></div>
      </div>
      {!results.items.length ? <EmptyState title="No observations match these filters.">Try broadening the selected areas, product, flow, or period range.</EmptyState> : view === "table" ?
        <div className="table-wrap"><table><thead><tr>{([ ["TIME_PERIOD", "Period"], ["REF_AREA", "Reporter"], ["COUNTERPART_AREA", "Counterpart"], ["TRADE_FLOW", "Trade flow"], ["PRODUCT", "Product"], ["UNIT_MEASURE", "Unit"], ["OBS_VALUE", "Value"] ] as Array<[keyof Observation, string]>).map(([key, label]) => <th key={key} scope="col"><button className="sort-button" onClick={() => toggleSort(key)}>{label}{sort.key === key ? (sort.direction === 1 ? " ↑" : " ↓") : ""}</button></th>)}</tr></thead><tbody>{sortedRows.map((row) => <tr key={row.id}><td>{row.TIME_PERIOD}</td><td>{labelFor(row.REF_AREA, labels)}</td><td>{labelFor(row.COUNTERPART_AREA, labels)}</td><td>{labelFor(row.TRADE_FLOW, labels)}</td><td>{labelFor(row.PRODUCT, labels)}</td><td>{labelFor(row.UNIT_MEASURE, labels)}</td><td className="numeric">{formatExactDecimal(row.OBS_VALUE)}</td></tr>)}</tbody></table></div>
        : <div className="chart-panel" aria-label="Observation time series chart"><ResponsiveContainer width="100%" height={380}><LineChart data={chartData} margin={{ top: 16, right: 24, bottom: 12, left: 24 }}><CartesianGrid strokeDasharray="3 3" stroke="#d9e1e8" /><XAxis dataKey="TIME_PERIOD" /><YAxis width={90} /><Tooltip content={({ active, payload }) => { const row = payload?.[0]?.payload as Observation | undefined; return active && row ? <div className="chart-tooltip"><strong>{row.TIME_PERIOD}</strong><span>{formatExactDecimal(row.OBS_VALUE)} {labelFor(row.UNIT_MEASURE, labels)}</span><span>{labelFor(row.REF_AREA, labels)} → {labelFor(row.COUNTERPART_AREA, labels)}</span><span>{labelFor(row.TRADE_FLOW, labels)}</span></div> : null; }} /><Line type="monotone" dataKey="plottedValue" stroke="#1261a0" strokeWidth={3} dot={{ r: 4 }} /></LineChart></ResponsiveContainer></div>}
      <details className="api-query"><summary>View API Query</summary><div><code>{queryPath}</code><button className="button secondary small" onClick={() => navigator.clipboard.writeText(apiUrl(queryPath))}>Copy</button></div><p>The CSV download contains the current filtered result set and is not an SDMX exchange format.</p></details>
    </>}
  </div>;
}
