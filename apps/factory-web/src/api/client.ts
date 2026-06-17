import type {
  AssetResponse,
  Core3EvidenceResponse,
  Core3Overview,
  Core3PipelineInitializationRunResponse,
  Core3PipelineInitializationStatusResponse,
  Core3RunResponse,
  Core3SkuReport,
  Core3V2BusinessReportResponse,
  Core3V2CoreCompetitor,
  Core3V2DataStatusResponse,
  Core3V2EvidenceCard,
  Core3V2EvidenceTraceResponse,
  Core3V2ExportItem,
  Core3V2ListResponse,
  Core3V2OverviewResponse,
  Core3V2PipelineRunListResponse,
  Core3V2PipelineRunResponse,
  Core3V2ReportSection,
  Core3V2SkuResolveResponse,
  Core3V2TargetListResponse,
  DataQualityResponse,
  ExportResponse,
  PipelineResult,
  Project,
  RuntimeExportResponse,
  ReviewQueueResponse,
  SourceFile,
  WorkbenchCollectionResponse,
  WorkbenchExportPreview,
  WorkbenchOverviewResponse
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  return response.json() as Promise<T>;
}

async function requestText(path: string): Promise<string> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  return response.text();
}

async function responseErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return `请求失败: ${response.status}`;
  }
  try {
    const payload = JSON.parse(text) as {
      detail?: string | { message_cn?: string; action_hint_cn?: string; detail?: string };
      message_cn?: string;
      action_hint_cn?: string;
    };
    if (typeof payload.detail === "object" && payload.detail?.message_cn) {
      return [payload.detail.message_cn, payload.detail.action_hint_cn].filter(Boolean).join("；");
    }
    if (payload.message_cn) {
      return [payload.message_cn, payload.action_hint_cn].filter(Boolean).join("；");
    }
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch {
    return text;
  }
  return text;
}

export const api = {
  listProjects: () => request<Project[]>("/projects"),
  createProject: (payload: { name: string; category_code: string; description?: string }) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify(payload) }),
  uploadFile: (projectId: string, file: File, fileType: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("file_type", fileType);
    return request<SourceFile>(`/projects/${projectId}/files`, { method: "POST", body: form });
  },
  importFile: (projectId: string, payload: { source_file_id?: string; file_path?: string; file_type?: string }) =>
    request(`/projects/${projectId}/imports`, { method: "POST", body: JSON.stringify(payload) }),
  dataQuality: (projectId: string) => request<DataQualityResponse>(`/projects/${projectId}/data-quality`),
  profile: (projectId: string) => request<PipelineResult>(`/projects/${projectId}/profile`, { method: "POST" }),
  runStep: (projectId: string, step: string) =>
    request<PipelineResult>(`/projects/${projectId}/pipeline/${step}`, { method: "POST" }),
  listAssets: (projectId: string, assetType: string) =>
    request<AssetResponse>(`/projects/${projectId}/assets/${assetType}`),
  reviewQueue: (projectId: string) => request<ReviewQueueResponse>(`/projects/${projectId}/review-queue`),
  decideReview: (reviewId: string, decision: "approved" | "rejected" | "edited") =>
    request(`/review-queue/${reviewId}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, reviewer: "factory-web" })
    }),
  exportRuntime: (projectId: string, version: string) =>
    request<ExportResponse>(`/projects/${projectId}/export-runtime`, {
      method: "POST",
      body: JSON.stringify({ version })
    }),
  useWorkbenchFixture: (projectId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/workbench/use-fixture`, {
      method: "POST",
      body: JSON.stringify({ target_sku_code: "TV00029115" })
    }),
  workbenchOverview: (projectId: string) =>
    request<WorkbenchOverviewResponse>(`/api/projects/${projectId}/workbench/data-overview`),
  workbenchLibrary: (projectId: string, libraryType: string) =>
    request<WorkbenchCollectionResponse>(`/api/projects/${projectId}/assets/${libraryType}`),
  workbenchMappings: (projectId: string) =>
    request<WorkbenchCollectionResponse>(`/api/projects/${projectId}/assets/mappings`),
  reviewWorkbenchAsset: (
    projectId: string,
    assetType: string,
    assetId: string,
    decision: "approved" | "rejected" | "needs_split" | "needs_merge" | "deprecated" | "pending"
  ) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/assets/${assetType}/${assetId}/review`, {
      method: "PATCH",
      body: JSON.stringify({ decision, reviewer: "factory-web" })
    }),
  workbenchSkuResults: (projectId: string) =>
    request<WorkbenchCollectionResponse>(`/api/projects/${projectId}/sku-results`),
  workbenchSkuDetail: (projectId: string, skuCode: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/sku-results/${skuCode}`),
  workbenchCompetitors: (projectId: string, skuCode?: string) =>
    request<WorkbenchCollectionResponse>(
      `/api/projects/${projectId}/competitors${skuCode ? `?sku_code=${encodeURIComponent(skuCode)}` : ""}`
    ),
  workbenchCalibration: (projectId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/calibration/summary`),
  workbenchExportPreview: (projectId: string) =>
    request<WorkbenchExportPreview>(`/api/projects/${projectId}/runtime-export/preview`),
  createAssetVersion: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/assets/versions", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  submitAssetReview: (assetId: string) =>
    request<Record<string, unknown>>(`/api/assets/${assetId}/submit-review`, {
      method: "POST",
      body: JSON.stringify({ actor_id: "factory-web" })
    }),
  approveAssetVersion: (assetId: string) =>
    request<Record<string, unknown>>(`/api/assets/${assetId}/approve`, {
      method: "POST",
      body: JSON.stringify({ actor_id: "factory-web" })
    }),
  releaseAssetVersion: (assetId: string) =>
    request<Record<string, unknown>>(`/api/assets/${assetId}/release`, {
      method: "POST",
      body: JSON.stringify({ actor_id: "factory-web", approved_by: "factory-web" })
    }),
  exportReleasedRuntime: (projectId: string, assetVersionId?: string) =>
    request<RuntimeExportResponse>(`/api/projects/${projectId}/runtime-export`, {
      method: "POST",
      body: JSON.stringify({ asset_version_id: assetVersionId, created_by: "factory-web" })
    }),
  core3Run: (projectId: string, payload: { target_sku_code?: string; target_model?: string; batch?: boolean; force_recompute?: boolean }) =>
    request<Core3RunResponse>(`/api/mvp/core3/projects/${projectId}/run`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  core3Overview: (projectId: string) =>
    request<Core3Overview>(`/api/mvp/core3/projects/${projectId}/overview`),
  core3Report: (projectId: string, skuOrModel: string) =>
    request<Core3SkuReport>(`/api/mvp/core3/projects/${projectId}/sku/${encodeURIComponent(skuOrModel)}/report`),
  core3Evidence: (projectId: string, skuOrModel: string) =>
    request<Core3EvidenceResponse>(`/api/mvp/core3/projects/${projectId}/sku/${encodeURIComponent(skuOrModel)}/competitors/evidence`),
  core3Csv: (projectId: string) =>
    requestText(`/api/mvp/core3/projects/${projectId}/export/core3.csv`),
  core3EvidenceJsonl: (projectId: string) =>
    requestText(`/api/mvp/core3/projects/${projectId}/export/evidence-cards.jsonl`),
  core3V2DataStatus: (projectId: string) =>
    request<Core3V2DataStatusResponse>(`/api/mvp/core3/v2/projects/${projectId}/data-status`),
  core3V2ResolveSku: (projectId: string, query: string) =>
    request<Core3V2SkuResolveResponse>(
      `/api/mvp/core3/v2/projects/${projectId}/sku/resolve?query=${encodeURIComponent(query)}`
    ),
  core3V2Overview: (projectId: string) =>
    request<Core3V2OverviewResponse>(`/api/mvp/core3/v2/projects/${projectId}/overview`),
  core3V2Targets: (projectId: string, limit = 50, offset = 0) =>
    request<Core3V2TargetListResponse>(
      `/api/mvp/core3/v2/projects/${projectId}/targets?limit=${limit}&offset=${offset}`
    ),
  core3V2Report: (projectId: string, skuOrModel: string) =>
    request<Core3V2BusinessReportResponse>(
      `/api/mvp/core3/v2/projects/${projectId}/targets/${encodeURIComponent(skuOrModel)}/report`
    ),
  core3V2Competitors: (projectId: string, skuOrModel: string) =>
    request<Core3V2CoreCompetitor[]>(
      `/api/mvp/core3/v2/projects/${projectId}/targets/${encodeURIComponent(skuOrModel)}/competitors`
    ),
  core3V2EvidenceCards: (projectId: string, skuOrModel: string) =>
    request<Core3V2EvidenceCard[]>(
      `/api/mvp/core3/v2/projects/${projectId}/targets/${encodeURIComponent(skuOrModel)}/evidence-cards`
    ),
  core3V2ReportSections: (projectId: string, skuOrModel: string) =>
    request<Core3V2ReportSection[]>(
      `/api/mvp/core3/v2/projects/${projectId}/targets/${encodeURIComponent(skuOrModel)}/sections`
    ),
  core3V2Export: (projectId: string, skuOrModel: string, exportType: string) =>
    request<Core3V2ExportItem>(
      `/api/mvp/core3/v2/projects/${projectId}/targets/${encodeURIComponent(skuOrModel)}/exports/${encodeURIComponent(exportType)}`
    ),
  core3V2EvidenceTrace: (projectId: string, skuOrModel: string, shortRef: string) =>
    request<Core3V2EvidenceTraceResponse>(
      `/api/mvp/core3/v2/projects/${projectId}/targets/${encodeURIComponent(skuOrModel)}/evidence/${encodeURIComponent(shortRef)}/trace`
    ),
  core3V2PipelineInitialization: (projectId: string, batchId?: string) =>
    request<Core3PipelineInitializationStatusResponse>(
      `/api/mvp/core3/v2/projects/${projectId}/pipeline/initialization${
        batchId ? `?batch_id=${encodeURIComponent(batchId)}` : ""
      }`
    ),
  core3V2RunInitializationModule: (
    projectId: string,
    payload: { module_code: string; batch_id?: string | null; force_rebuild?: boolean; triggered_by?: string }
  ) =>
    request<Core3PipelineInitializationRunResponse>(
      `/api/mvp/core3/v2/projects/${projectId}/pipeline/initialization/run`,
      {
        method: "POST",
        body: JSON.stringify(payload)
      }
    ),
  core3V2PipelineRuns: (projectId: string, limit = 20, offset = 0) =>
    request<Core3V2PipelineRunListResponse>(
      `/api/mvp/core3/v2/projects/${projectId}/pipeline/runs?limit=${limit}&offset=${offset}`
    ),
  core3V2PipelineRunLatest: (projectId: string) =>
    request<Core3V2PipelineRunResponse>(`/api/mvp/core3/v2/projects/${projectId}/pipeline/runs/latest`),
  core3V2PipelineRun: (projectId: string, runId: string) =>
    request<Core3V2PipelineRunResponse>(`/api/mvp/core3/v2/projects/${projectId}/pipeline/runs/${encodeURIComponent(runId)}`),
  core3V2PipelineModules: (projectId: string, runId: string) =>
    request<Core3V2ListResponse>(`/api/mvp/core3/v2/projects/${projectId}/pipeline/runs/${encodeURIComponent(runId)}/modules`),
  core3V2PipelineReviews: (projectId: string, runId: string) =>
    request<Core3V2ListResponse>(`/api/mvp/core3/v2/projects/${projectId}/pipeline/runs/${encodeURIComponent(runId)}/reviews`),
  core3V2PipelineAcceptance: (projectId: string, runId: string) =>
    request<Record<string, unknown>>(`/api/mvp/core3/v2/projects/${projectId}/pipeline/runs/${encodeURIComponent(runId)}/acceptance`),
  core3V2PipelineReleaseGates: (projectId: string, runId: string) =>
    request<Core3V2ListResponse>(
      `/api/mvp/core3/v2/projects/${projectId}/pipeline/runs/${encodeURIComponent(runId)}/release-gates`
    ),
  core3V2SubmitReviewDecision: (
    projectId: string,
    reviewId: string,
    payload: { decision_type: string; decision_reason_cn: string; decided_by?: string; need_recompute?: boolean }
  ) =>
    request<Record<string, unknown>>(`/api/mvp/core3/v2/projects/${projectId}/reviews/${encodeURIComponent(reviewId)}/decision`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  core3V2ReleaseGate: (projectId: string, gateId: string, payload: { released_by?: string; release_note_cn?: string }) =>
    request<Record<string, unknown>>(
      `/api/mvp/core3/v2/projects/${projectId}/release-gates/${encodeURIComponent(gateId)}/release`,
      {
        method: "POST",
        body: JSON.stringify(payload)
      }
    )
};
