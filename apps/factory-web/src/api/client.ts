import type {
  AssetResponse,
  DataQualityResponse,
  ExportResponse,
  PipelineResult,
  Project,
  ReviewQueueResponse,
  SourceFile
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `请求失败: ${response.status}`);
  }
  return response.json() as Promise<T>;
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
    })
};

