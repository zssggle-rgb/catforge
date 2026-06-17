export interface Project {
  project_id: string;
  name: string;
  category_code: string;
  description?: string | null;
  version: string;
  status: string;
}

export interface SourceFile {
  source_file_id: string;
  project_id: string;
  file_name: string;
  file_type: string;
  status: string;
  row_count: number;
}

export interface PipelineResult {
  step: string;
  status: string;
  counts: Record<string, number>;
  message: string;
}

export interface AssetResponse {
  asset_type: string;
  count: number;
  items: Record<string, unknown>[];
}

export interface DataQualityResponse {
  project_id: string;
  summary: Record<string, unknown>;
  issues: Record<string, unknown>[];
}

export interface ReviewQueueResponse {
  count: number;
  items: Record<string, unknown>[];
}

export interface ExportResponse {
  package_id: string;
  package_path: string;
  files: string[];
  status: string;
  message: string;
}

export interface WorkbenchCollectionResponse {
  count: number;
  items: Record<string, unknown>[];
  library_type?: string;
}

export interface WorkbenchOverviewResponse extends Record<string, unknown> {
  project_id: string;
  sku_count: number;
  brand_count: number;
  channel_count: number;
  raw_parameter_row_count: number;
  raw_claim_row_count: number;
  raw_comment_row_count: number;
  market_fact_row_count: number;
}

export interface WorkbenchExportPreview extends Record<string, unknown> {
  project_id: string;
  category_code: string;
  file_list: Record<string, unknown>[];
  approved_deliverables: string[];
  release_gate: Record<string, unknown>;
  released_asset_version?: Record<string, unknown> | null;
  asset_versions: Record<string, unknown>[];
}

export interface RuntimeExportResponse {
  export_id: string;
  project_id: string;
  asset_version_id: string;
  status: string;
  manifest_json: Record<string, unknown>;
  file_path: string;
  content_hash: string;
  created_by: string;
}

export interface Core3RunResponse {
  run_id: string;
  status: string;
  scope: string;
  target_sku_code?: string | null;
  counts: Record<string, number>;
  warnings: string[];
  diagnostics: Record<string, unknown>;
  latest_report_ref?: string | null;
}

export interface Core3CompetitorBrief {
  role: "direct" | "pressure" | "benchmark_potential";
  role_name: string;
  competitor_sku_code?: string | null;
  competitor_brand?: string | null;
  competitor_model_name?: string | null;
  competitor_series?: string | null;
  battlefield_code?: string | null;
  score: number;
  component_scores: Record<string, number | null>;
  reason?: string | null;
  confidence: number;
  confidence_level: "high" | "medium" | "low";
  review_flag: boolean;
  insufficient_reasons: string[];
  evidence_ids: string[];
  evidence_categories?: string[];
  evidence_card?: Record<string, unknown>;
}

export interface Core3SkuReport {
  project_id: string;
  run_id: string;
  target_sku: {
    sku_code: string;
    brand?: string | null;
    model_name?: string | null;
    series?: string | null;
  };
  derivation_summary?: Record<string, unknown>;
  market_profile: Record<string, unknown>;
  standard_params: Record<string, Record<string, unknown>>;
  activated_claims: Record<string, unknown>[];
  comment_topics: Record<string, unknown>[];
  tasks: Record<string, unknown>[];
  target_groups: Record<string, unknown>[];
  battlefields: Record<string, unknown>[];
  core_competitors: Core3CompetitorBrief[];
  extraction_diagnostics: Record<string, unknown>;
  confidence_level: "high" | "medium" | "low";
  review_flag: boolean;
  insufficient_reasons: string[];
}

export interface Core3OverviewRow {
  target_sku_code: string;
  brand?: string | null;
  model_name?: string | null;
  primary_battlefield?: string | null;
  direct_competitor?: Record<string, unknown> | null;
  pressure_competitor?: Record<string, unknown> | null;
  benchmark_potential_competitor?: Record<string, unknown> | null;
  confidence_level: "high" | "medium" | "low";
  review_flag: boolean;
  insufficient_reasons: string[];
}

export interface Core3Overview {
  project_id: string;
  latest_run_id: string;
  analyzed_sku_count: number;
  confidence_distribution: Record<"high" | "medium" | "low", number>;
  insufficient_reason_top5: { reason: string; count: number }[];
  rows: Core3OverviewRow[];
}

export interface Core3EvidenceResponse {
  project_id: string;
  run_id: string;
  target_sku_code: string;
  count: number;
  items: {
    role: "direct" | "pressure" | "benchmark_potential";
    competitor_sku_code?: string | null;
    evidence_categories: string[];
    evidence_card: Record<string, unknown>;
    evidence_items: Record<string, unknown>[];
  }[];
}

export interface Core3V2DataScope {
  period_cn: string;
  channel_scope_cn: string;
  platform_scope_cn: string;
  sample_note_cn: string;
  data_scope_note_cn: string;
  updated_at?: string | null;
}

export interface Core3V2ReleaseStatus {
  status_code: "not_ready" | "review_required" | "releasable" | "released" | "blocked" | string;
  status_name_cn: string;
  gate_reason_cn: string;
  data_scope_note_cn: string;
  review_hint_cn?: string | null;
  can_present: boolean;
  can_release: boolean;
}

export interface Core3V2TargetProfile {
  sku_code: string;
  model_name?: string | null;
  brand_name?: string | null;
  display_name_cn: string;
  size_segment_cn?: string | null;
  price_band_cn?: string | null;
  data_status_cn: string;
}

export interface Core3V2EvidenceShortRef {
  short_ref: string;
  evidence_domain_cn?: string | null;
  evidence_title_cn?: string | null;
  source_cn?: string | null;
  snippet_cn?: string | null;
}

export interface Core3V2CoreCompetitor {
  competitor_sku_code: string;
  competitor_model_name?: string | null;
  competitor_brand_name?: string | null;
  competitor_display_name_cn: string;
  role_code: "direct_fight" | "price_volume_pressure" | "benchmark_potential" | string;
  role_name_cn: string;
  one_sentence_reason_cn: string;
  battlefield_fit_cn: string;
  market_pressure_cn: string;
  key_difference_cn: string;
  target_advantage_cn: string;
  competitor_advantage_cn: string;
  strategy_implication_cn: string;
  confidence_label_cn: string;
  risk_note_cn?: string | null;
  evidence_short_refs: Core3V2EvidenceShortRef[];
}

export interface Core3V2EvidenceCard {
  target_sku_code: string;
  target_display_name_cn: string;
  competitor_sku_code: string;
  competitor_display_name_cn: string;
  role_code: string;
  role_name_cn: string;
  headline_cn: string;
  summary_cn: string;
  one_sentence_reason_cn: string;
  battlefield_name_cn: string;
  confidence_label_cn: string;
  price_evidence_cn?: string | null;
  channel_evidence_cn?: string | null;
  param_evidence_cn?: string | null;
  claim_value_evidence_cn?: string | null;
  task_audience_evidence_cn?: string | null;
  market_evidence_cn?: string | null;
  comment_evidence_cn?: string | null;
  key_difference_cn: string;
  target_advantage_cn: string;
  competitor_advantage_cn: string;
  strategy_implication_cn: string;
  risk_note_cn?: string | null;
  evidence_short_refs: Core3V2EvidenceShortRef[];
}

export interface Core3V2ReportSection {
  section_code: string;
  section_title_cn: string;
  section_order: number;
  display_status_cn: string;
  section_payload: Record<string, unknown>;
  evidence_short_refs: Core3V2EvidenceShortRef[];
}

export interface Core3V2ReviewHint {
  review_required: boolean;
  severity_name_cn?: string | null;
  message_cn: string;
  suggested_action_cn?: string | null;
  review_count: number;
}

export interface Core3V2ExportItem {
  export_type: string;
  export_title_cn: string;
  export_payload: string;
  data_scope_note_cn: string;
  export_status_cn: string;
  failure_reason?: string | null;
  media_type: string;
}

export interface Core3V2BusinessReportResponse {
  project_id: string;
  category_code: string;
  target: Core3V2TargetProfile;
  report_title_cn: string;
  executive_conclusion_cn: string;
  data_scope: Core3V2DataScope;
  release_status: Core3V2ReleaseStatus;
  core_competitors: Core3V2CoreCompetitor[];
  why_these_competitors_cn: string;
  battlefield_summary_cn: string;
  evidence_cards: Core3V2EvidenceCard[];
  sections: Core3V2ReportSection[];
  candidate_audit: Record<string, unknown>;
  review_hint: Core3V2ReviewHint;
  exports: Core3V2ExportItem[];
  data_quality_note_cn: string;
}

export interface Core3V2SkuResolveResponse {
  status: "unique" | "ambiguous" | string;
  query: string;
  target?: Core3V2TargetProfile | null;
  candidates: Core3V2TargetProfile[];
  message_cn: string;
  action_hint_cn?: string | null;
}

export interface Core3V2TargetSummary {
  target_sku_code: string;
  target_display_name_cn: string;
  brand_name?: string | null;
  report_title_cn?: string | null;
  release_status: Core3V2ReleaseStatus;
  selected_count: number;
  competitor_names_cn: string[];
  data_scope_note_cn: string;
  review_hint_cn?: string | null;
}

export interface Core3V2TargetListResponse {
  items: Core3V2TargetSummary[];
  total: number;
  limit: number;
  offset: number;
  summary_cn: string;
}

export interface Core3V2OverviewResponse {
  project_id: string;
  category_code: string;
  data_status_cn: string;
  latest_batch_id?: string | null;
  latest_run_id?: string | null;
  target_count: number;
  report_count: number;
  release_status_counts: Record<string, number>;
  data_scope: Core3V2DataScope;
  acceptance_summary_cn?: string | null;
  targets_preview: Core3V2TargetSummary[];
  summary_cn: string;
}

export interface Core3V2DataStatusResponse {
  project_id: string;
  category_code: string;
  has_data: boolean;
  latest_batch_id?: string | null;
  batch_count: number;
  target_count: number;
  report_count: number;
  latest_run_id?: string | null;
  release_status_counts: Record<string, number>;
  data_scope: Core3V2DataScope;
  summary_cn: string;
}

export interface Core3PipelineInitializationModuleStatus {
  module_code: string;
  module_name_cn: string;
  stage_name_cn: string;
  stage_description_cn: string;
  execution_status: "completed" | "partial" | "not_started" | "blocked" | "failed" | string;
  execution_status_cn: string;
  can_execute: boolean;
  can_skip: boolean;
  skip_reason_cn?: string | null;
  blocked_reason_cn?: string | null;
  expected_target_count: number;
  processed_target_count: number;
  output_count: number;
  current_output_count: number;
  review_issue_count: number;
  warning_count: number;
  latest_run_id?: string | null;
  latest_module_run_id?: string | null;
  latest_status?: string | null;
  latest_started_at?: string | null;
  latest_finished_at?: string | null;
  latest_summary_cn?: string | null;
  latest_summary_json: Record<string, unknown>;
  result_entry_url?: string | null;
}

export interface Core3PipelineInitializationStatusResponse {
  project_id: string;
  category_code: string;
  batch_id?: string | null;
  batch_status_cn: string;
  source_row_count: number;
  impacted_sku_count: number;
  clean_sku_count: number;
  latest_pipeline_run_id?: string | null;
  modules: Core3PipelineInitializationModuleStatus[];
  summary_cn: string;
}

export interface Core3PipelineInitializationRunResponse {
  project_id: string;
  category_code: string;
  batch_id?: string | null;
  module: Core3PipelineInitializationModuleStatus;
  result: {
    module_code: string;
    status: string;
    input_count: number;
    changed_input_count: number;
    output_count: number;
    output_hash?: string | null;
    warnings: string[];
    review_issues: Record<string, unknown>[];
    downstream_impacts: Record<string, unknown>[];
    summary_json: Record<string, unknown>;
    started_at?: string | null;
    finished_at?: string | null;
  };
  skipped: boolean;
  message_cn: string;
  next_action_cn?: string | null;
}

export interface Core3V2EvidenceTraceResponse {
  short_ref: string;
  target_sku_code: string;
  trace_usage_cn: string;
  evidence_domain_cn?: string | null;
  evidence_title_cn?: string | null;
  source_cn?: string | null;
  snippet_cn?: string | null;
  source_table?: string | null;
  clean_table?: string | null;
  evidence_field?: string | null;
  confidence?: number | null;
}

export interface Core3V2PipelineRunListResponse {
  items: Record<string, unknown>[];
  total: number;
  limit: number;
  offset: number;
  summary_cn: string;
}

export interface Core3V2ListResponse<T = Record<string, unknown>> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  summary_cn?: string | null;
}

export interface Core3V2PipelineRunResponse extends Record<string, unknown> {
  run_id: string;
  status: string;
  release_status: string;
  data_batch_id?: string | null;
  summary_cn?: string | null;
}
