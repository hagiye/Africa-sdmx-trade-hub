export interface Summary {
  harmonised_observations: number;
  reporting_countries: number;
  counterpart_areas: number;
  available_periods: { count: number; earliest: string | null; latest: string | null };
  source_observations: number;
  source_dataset: string;
  target_dataflow: string;
  target_dsd_version: string;
}

export interface Observation {
  id: number;
  FREQ: string;
  REF_AREA: string;
  COUNTERPART_AREA: string;
  TRADE_FLOW: string;
  PRODUCT_SCHEME: string;
  PRODUCT: string;
  UNIT_MEASURE: string;
  TIME_PERIOD: string;
  OBS_VALUE: string;
  OBS_STATUS?: string | null;
  CONF_STATUS?: string | null;
  UNIT_MULT: string;
  DECIMALS?: number | null;
  SOURCE: string;
}

export interface ObservationPage {
  items: Observation[];
  total: number;
  limit: number;
  offset: number;
}

export interface CodelistRef { agency: string; id: string; version: string }
export interface ComponentMetadata {
  position: number | null;
  concept: string;
  role: string;
  codelist: CodelistRef | null;
  required: boolean;
}
export interface TargetMetadata {
  agency: string;
  dataflow: string;
  version: string;
  DSD: { agency: string; id: string; version: string };
  dimensions: string[];
  attributes: string[];
  components: ComponentMetadata[];
  codelists: Array<CodelistRef & { code_count: number }>;
  disclaimer: string;
}
export interface CodeItem { code: string; parent_code: string | null; labels: Record<string, string> }
export interface CodePage { items: CodeItem[]; total: number; page: number; page_size: number; pages: number }

export interface ValidationSummary { validated_observations: number; warnings: number; errors: number; rejected: number }
export interface ValidationRule { rule: string; category: string; severity: string; concept: string | null; count: number }
export interface ValidationFinding extends ValidationRule { id: number; batch: number; observation: number | null; invalid_value: string | null; message: string }
export interface FindingsPage { items: ValidationFinding[]; total: number; limit: number; offset: number }

export interface HarmonizationBatch {
  id: number; status: string; mapping_definition_id: string; mapping_version: string;
  started_at: string; finished_at: string | null; source_received: number; source_valid: number;
  transformed: number; inserted: number; updated: number; skipped: number; rejected: number;
  mapping_errors: number; target_validation_errors: number;
}
export interface HarmonizationSummary {
  source: string; target: string; latest_batch: HarmonizationBatch | null;
  rejection_reasons: Array<{ reason: string; count: number }>;
}
export interface MappingRow { source_concept: string; target_concept: string | null; mapping_type: string; status: string; transformation: string | null; notes: string | null }
export interface Lineage {
  target: { id: number; dataset: string; key_hash: string; time_period: string; obs_value: string };
  harmonization_batch: number | null;
  mapping: { definition: string; version: string };
  source_observation: { id: number | null; key_hash: string | null; dimensions: Record<string, unknown> | null };
  source_ingestion_batch: number | null;
  provider: string;
}
