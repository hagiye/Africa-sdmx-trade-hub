import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const metadata = {
  agency: "AFRSTAT", dataflow: "AFR_TRADE", version: "1.0",
  DSD: { agency: "AFRSTAT", id: "AFR_TRADE", version: "1.0" },
  dimensions: ["FREQ", "REF_AREA", "COUNTERPART_AREA", "TRADE_FLOW", "PRODUCT_SCHEME", "PRODUCT", "UNIT_MEASURE", "TIME_PERIOD"],
  attributes: ["UNIT_MULT", "SOURCE"],
  components: [
    { position: 1, concept: "FREQ", role: "dimension", codelist: { agency: "AFRSTAT", id: "CL_FREQ", version: "1.0" }, required: true },
    { position: 2, concept: "REF_AREA", role: "dimension", codelist: { agency: "AFRSTAT", id: "CL_AFR_AREA", version: "1.0" }, required: true },
    { position: 3, concept: "COUNTERPART_AREA", role: "dimension", codelist: { agency: "AFRSTAT", id: "CL_AFR_AREA", version: "1.0" }, required: true },
    { position: 4, concept: "TRADE_FLOW", role: "dimension", codelist: { agency: "AFRSTAT", id: "CL_TRADE_FLOW", version: "1.0" }, required: true },
    { position: 5, concept: "PRODUCT_SCHEME", role: "dimension", codelist: { agency: "AFRSTAT", id: "CL_PRODUCT_SCHEME", version: "1.0" }, required: true },
    { position: 6, concept: "PRODUCT", role: "dimension", codelist: { agency: "AFRSTAT", id: "CL_PRODUCT", version: "1.0" }, required: true },
    { position: 7, concept: "UNIT_MEASURE", role: "dimension", codelist: { agency: "AFRSTAT", id: "CL_UNIT_MEASURE", version: "1.0" }, required: true }
  ],
  codelists: [
    { agency: "AFRSTAT", id: "CL_AFR_AREA", version: "1.0", code_count: 2 },
    { agency: "AFRSTAT", id: "CL_FREQ", version: "1.0", code_count: 1 },
    { agency: "AFRSTAT", id: "CL_TRADE_FLOW", version: "1.0", code_count: 2 },
    { agency: "AFRSTAT", id: "CL_PRODUCT_SCHEME", version: "1.0", code_count: 1 },
    { agency: "AFRSTAT", id: "CL_PRODUCT", version: "1.0", code_count: 1 },
    { agency: "AFRSTAT", id: "CL_UNIT_MEASURE", version: "1.0", code_count: 1 }
  ],
  disclaimer: "Independent portfolio demonstration; not an official African Union or STATAFRIC artefact."
};

const codes: Record<string, Array<{ code: string; parent_code: null; labels: Record<string, string> }>> = {
  CL_AFR_AREA: [{ code: "TN", parent_code: null, labels: { en: "Tunisia", fr: "Tunisie" } }, { code: "AFR_WORLD", parent_code: null, labels: { en: "World", fr: "Monde" } }],
  CL_FREQ: [{ code: "A", parent_code: null, labels: { en: "Annual", fr: "Annuel" } }],
  CL_TRADE_FLOW: [{ code: "IMPORT", parent_code: null, labels: { en: "Imports", fr: "Importations" } }],
  CL_PRODUCT_SCHEME: [{ code: "SITC4", parent_code: null, labels: { en: "SITC Revision 4", fr: "CTCI Révision 4" } }],
  CL_PRODUCT: [{ code: "TOTAL", parent_code: null, labels: { en: "Total merchandise", fr: "Total marchandises" } }],
  CL_UNIT_MEASURE: [{ code: "USD", parent_code: null, labels: { en: "US dollars", fr: "Dollars US" } }]
};

const observation = { id: 7, FREQ: "A", REF_AREA: "TN", COUNTERPART_AREA: "AFR_WORLD", TRADE_FLOW: "IMPORT", PRODUCT_SCHEME: "SITC4", PRODUCT: "TOTAL", UNIT_MEASURE: "USD", TIME_PERIOD: "2023", OBS_VALUE: "1234567.8900", UNIT_MULT: "0", SOURCE: "UN_COMTRADE" };

function installApi(result: "data" | "empty" | "error" = "data") {
  const mock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    let body: unknown = {};
    let status = 200;
    if (url.includes("/api/v1/summary")) body = { harmonised_observations: 1, reporting_countries: 1, counterpart_areas: 1, available_periods: { count: 1, earliest: "2023", latest: "2023" }, source_observations: 3, source_dataset: "UNSD:IMTS(1.2)", target_dataflow: "AFRSTAT:AFR_TRADE(1.0)", target_dsd_version: "1.0" };
    else if (url.includes("/api/v1/afr-trade/metadata")) body = metadata;
    else if (url.includes("/api/v1/codelists/")) { const id = Object.keys(codes).find((key) => url.includes(key))!; body = { items: codes[id], total: codes[id].length, page: 1, page_size: 500, pages: 1 }; }
    else if (url.includes("/api/v1/afr-trade?")) { if (result === "error") status = 503; else body = { items: result === "empty" ? [] : [observation], total: result === "empty" ? 0 : 1, limit: 1000, offset: 0 }; }
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function renderAt(path: string) { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>); }
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("statistical explorer", () => {
  it("renders the landing page with live KPIs and disclaimer", async () => {
    installApi(); renderAt("/");
    expect(await screen.findByRole("heading", { name: "Pan-African SDMX Trade Data Hub", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("Target-valid records")).toBeInTheDocument();
    expect(screen.getAllByText(/not an official AU\/STATAFRIC platform/i).length).toBeGreaterThan(0);
  });

  it("provides explicit filters and renders labelled API results", async () => {
    const fetchMock = installApi(); renderAt("/explore");
    const reporter = await screen.findByLabelText("Reporter");
    await waitFor(() => expect((reporter as HTMLSelectElement).options.length).toBeGreaterThan(1));
    await userEvent.selectOptions(reporter, "TN");
    await userEvent.click(screen.getByRole("button", { name: "Apply Filters" }));
    expect(await screen.findByText("1,234,567.8900")).toBeInTheDocument();
    expect(screen.getAllByText("Tunisia").length).toBeGreaterThan(0);
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes("ref_area=TN"))).toBe(true));
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeEnabled();
  });

  it("renders a clear empty result state", async () => {
    installApi("empty"); renderAt("/explore");
    expect(await screen.findByText("No observations match these filters.")).toBeInTheDocument();
  });

  it("renders a concise service error instead of a blank page", async () => {
    installApi("error"); renderAt("/explore");
    expect(await screen.findByText("Information unavailable")).toBeInTheDocument();
    expect(screen.getByText("The statistics service is temporarily unavailable.")).toBeInTheDocument();
  });

  it("renders target components and bilingual codelist labels", async () => {
    installApi(); renderAt("/metadata");
    expect((await screen.findAllByText("AFRSTAT:AFR_TRADE(1.0)")).length).toBeGreaterThan(0);
    expect(screen.getByText("REF_AREA")).toBeInTheDocument();
    expect(await screen.findByText("Tunisie")).toBeInTheDocument();
    expect(screen.getAllByText(/Independent portfolio demonstration/).length).toBeGreaterThan(0);
  });
});
