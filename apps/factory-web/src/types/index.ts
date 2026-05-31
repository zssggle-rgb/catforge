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
