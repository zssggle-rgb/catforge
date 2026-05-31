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

