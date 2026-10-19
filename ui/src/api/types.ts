/**
 * TypeScript interfaces mirroring the Pydantic response/request models
 * in src/auditiq/api/schemas.py.
 *
 * These are the single source of truth for the frontend's view of the API.
 * Keep in sync with openapi.json / schemas.py when the backend changes.
 */

// -- Error envelope --------------------------------------------------------

export type ErrorCode =
  | "bad_request"
  | "validation_failed"
  | "not_found"
  | "materiality_unset"
  | "ingest_failed"
  | "schema_drift"
  | "internal_error";

export interface ErrorBody {
  code: ErrorCode;
  message: string;
  details: Record<string, unknown>;
}

export interface ErrorOut {
  error: ErrorBody;
}

// -- Meta -----------------------------------------------------------------

export interface MetaOut {
  version: string;
  statements: string[];
  bases: string[];
  units: string[];
  encoder_kinds: string[];
  mapping_statuses: string[];
  mapping_methods: string[];
  fs_measures: string[];
  classifications: string[];
  severities: string[];
  exception_kinds: string[];
  exception_statuses: string[];
  document_kinds: string[];
  erp_sources: string[];
  cors_origins: string[];
  features: Record<string, boolean>;
}

export interface HealthOut {
  status: string;
  version: string;
}

// -- Engagement -----------------------------------------------------------

export interface EngagementSummaryOut {
  engagement_id: number;
  client_code: string;
  client_name: string;
  period: string;
  basis: string;
  materiality_value: number | null;
  materiality_basis: string | null;
  tb_lines: number;
  tb_documents: number;
  fs_documents: number;
  fs_lines: number;
  fs_subtotals: number;
  fs_unmapped_rows: number;
  mappings: Record<string, number>;
  resolved_lines: number;
  pending_lines: number;
  intake_status: string;
  recon_run_id: number | null;
  recon_status: string | null;
  recon_exposure_a: number;
  recon_exposure_b: number;
  open_exceptions: number;
}

export interface EngagementInfoOut {
  engagement_id: number;
  client_code: string;
  period: string;
  basis: string;
  materiality_value: number | null;
  materiality_basis: string | null;
}

export interface CreateEngagementIn {
  client_code: string;
  period: string;
  basis?: string;
  client_name?: string;
}

// -- Documents ------------------------------------------------------------

export interface DocumentOut {
  document_id: number;
  engagement_id: number | null;
  kind: string;
  system: string;
  filename: string;
  file_hash: string;
  uploaded_at: string | null;
  parse_stats: Record<string, unknown>;
}

// -- Trial Balance --------------------------------------------------------

export interface TbLineOut {
  line_id: number;
  document_id: number;
  raw_code: string;
  raw_name: string;
  group_name: string;
  erp_acc_type: string;
  amount: number;
  side: string;
  unit: string;
  normalized_amount: number;
  source_row: number | null;
  fsli_code: string | null;
  mapping_status: string | null;
  mapping_method: string | null;
  mapping_confidence: number | null;
}

export interface PageOut {
  items: TbLineOut[];
  total: number;
  limit: number;
  offset: number;
}

// -- Ingestion ------------------------------------------------------------

export interface TbIngestOut {
  engagement_id: number;
  document_id: number;
  source: string;
  client_code: string;
  period: string;
  basis: string;
  unit: string;
  lines: number;
  duplicates_skipped: number;
  total_debit: number;
  total_credit: number;
  balanced: boolean;
  balance_difference: number;
}

export interface ValidationIssueOut {
  code: string;
  severity: string;
  message: string;
}

export interface FsIngestOut {
  engagement_id: number;
  document_id: number;
  reader: string;
  company: string;
  period: string;
  prior_period: string;
  unit: string;
  basis: string;
  pages: number;
  rows: number;
  lines: number;
  mapped: number;
  unmapped: number;
  subtotals: number;
  by_statement: Record<string, number>;
  by_layer: Record<string, number>;
  tables: number;
  encoder: string;
  tuned: boolean;
  issues: ValidationIssueOut[];
  mapped_weighted: number;
}

export interface FsUnmappedLabelOut {
  statement: string;
  label: string;
}

export interface FsCoverageOut {
  path: string;
  reader: string;
  company: string;
  period: string;
  unit: string;
  rows: number;
  mapped: number;
  by_layer: Record<string, number>;
  encoder: string;
  tuned: boolean;
  unmapped: FsUnmappedLabelOut[];
  unmapped_rows: number;
  coverage: number;
}

// -- Mapping --------------------------------------------------------------

export interface MapIn {
  encoder?: string | null;
  use_llm?: boolean;
}

export interface MappingSummaryOut {
  engagement_id: number;
  lines: number;
  resolved: number;
  review: number;
  by_layer: Record<string, number>;
  llm_calls: number;
  tuned: boolean;
  encoder: string;
  resolution_rate: number;
}

export interface PendingHeadOut {
  line_id: number;
  raw_name: string;
  raw_code: string;
  group_name: string;
  status: string;
  method: string;
  confidence: number | null;
  amount: number;
  lines: number;
  candidates: string[];
  embed_score: number | null;
  embed_margin: number | null;
  abs_amount: number;
}

export interface ResolveIn {
  line_id: number;
  fsli_code: string;
  reviewer?: string;
}

export interface BulkResolveIn {
  pairs: [number, string][];
  reviewer?: string;
}

export interface ResolutionOut {
  line_id: number;
  head: string;
  fsli_code: string | null;
  resolved_lines: number;
  reviewer: string;
}

export interface BulkResolveOut {
  resolved: ResolutionOut[];
  failures: Record<string, string>;
}

export interface MappingCountsOut {
  counts: Record<string, number>;
  total: number;
}

// -- Financial Statements -------------------------------------------------

export interface FsUnmappedOut {
  line_id: number;
  label: string;
  statement: string;
  document_id: number;
  rows: number;
  periods: string[];
  total: number;
  abs_total: number;
}

export interface FsResolveIn {
  fsli_code?: string | null;
  group_code?: string | null;
}

export interface FsResolveOut {
  line_id: number;
  label: string;
  fsli_code: string | null;
  group_code: string | null;
  resolved_rows: number;
}

// -- Materiality ----------------------------------------------------------

export interface MaterialityIn {
  value: number;
  basis?: string;
}

export interface MaterialitySuggestionOut {
  revenue: number;
  total_assets: number;
  ratio: number;
  basis: string;
  suggested: number;
  unit: string;
}

export interface MaterialityOut {
  value: number | null;
  basis: string | null;
  suggestion: MaterialitySuggestionOut | null;
}

// -- Reconciliation -------------------------------------------------------

export interface FindingOut {
  code: string;
  statement: string;
  severity: string;
  message: string;
  amount: number;
}

export interface ReconLineBriefOut {
  unit_code: string;
  name: string;
  statement: string;
  is_group: boolean;
  side_a: number;
  side_b: number;
  variance: number;
  variance_pct: number | null;
  a_lines: number;
  b_rows: number;
  classification: string;
  severity: string;
}

export interface ReconOut {
  engagement_id: number;
  run_id: number | null;
  period: string;
  basis: string;
  unit: string;
  materiality: number;
  performance_materiality: number;
  rounding_decimals: number;
  tolerance: number;
  statements: string[];
  materiality_basis: string;
  units: number;
  tied: number;
  rounding: number;
  minor: number;
  watch: number;
  material: number;
  exposure_a: number;
  exposure_a_lines: number;
  exposure_b: number;
  exposure_b_rows: number;
  attributed: number;
  findings: FindingOut[];
  worst: ReconLineBriefOut[];
  reconciled: boolean;
  status: string;
}

export interface ReconRunIn {
  materiality?: number | null;
  pm?: number;
  rounding_decimals?: number;
  statements?: string | null;
  side_b_period?: string | null;
  no_persist?: boolean;
}

export interface RunOut {
  run_id: number;
  engagement_id: number;
  period: string;
  basis: string;
  unit: string;
  statements: string;
  materiality: number;
  performance_materiality: number;
  rounding_decimals: number;
  units_total: number;
  tied: number;
  rounding: number;
  minor: number;
  watch: number;
  material: number;
  exposure_a: number;
  exposure_b: number;
}

export interface StoredLineOut {
  unit_code: string;
  name: string;
  statement: string;
  is_group: boolean;
  side_a: number;
  side_b: number;
  variance: number;
  variance_pct: number | null;
  a_lines: number;
  b_rows: number;
  classification: string;
  severity: string;
  attribution: Record<string, unknown>;
  refs: Record<string, unknown>;
}

export interface ReconLatestOut {
  run: RunOut;
  lines: StoredLineOut[];
}

export interface ReconExplainOut {
  run: RunOut;
  line: StoredLineOut;
}

// -- Exceptions -----------------------------------------------------------

export interface ExceptionOut {
  exception_id: number;
  engagement_id: number | null;
  kind: string;
  severity: string;
  status: string;
  amount: number | null;
  fsli: string | null;
  note: string;
  detail: string;
}

export interface DisposeIn {
  status: string;
  note?: string;
}

// -- Reference data -------------------------------------------------------

export interface TaxonomyItemOut {
  code: string;
  statement: string;
  category: string;
  sub_category_1: string;
  sub_category_2: string;
  name: string;
  normal_balance: string;
  description: string;
  is_debit: boolean;
}

export interface GroupOut {
  code: string;
  name: string;
  statement: string;
  members: string[];
  category: string;
  statement_code: string;
}

export interface ErpSourcesOut {
  sources: string[];
}
