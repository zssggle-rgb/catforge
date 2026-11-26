import type { Attachment, Context, Conversation, Choice, Filters, Operation, Origin, Receipt, Scope, Selection, View } from "./contract";

const base = (import.meta.env.VITE_GTM_API_BASE ?? "/api/gtm/v1").replace(/\/$/, "");

async function request<T>(path: string, signal?: AbortSignal, payload?: object, method = "GET"): Promise<T> {
  const response = await fetch(base + path, {
    method, signal, credentials: "same-origin",
    headers: payload ? {"Content-Type": "application/json", Accept: "application/json"} : {Accept: "application/json"},
    body: payload ? JSON.stringify(payload) : undefined
  });
  if (!response.headers.get("Content-Type")?.includes("application/json")) {
    throw new Error("GTM 接口尚未就绪，请稍后重试");
  }
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.message === "string" ? result.message : `接口请求失败（${response.status}）`);
  return result as T;
}
const projectPath = (id: string) => "/projects/" + encodeURIComponent(id);

export const gtm = {
  async context(signal: AbortSignal) {
    const data = await request<Context>("/context", signal);
    if (data?.version !== "1" || !["live", "sample"].includes(data.mode) || typeof data.user?.name !== "string" || !Array.isArray(data.projects) ||
        !data.projects.every(p => Array.isArray(p.categories) && Array.isArray(p.channels))) throw new Error("工作区接口格式有误");
    return data;
  },
  choices: (id: string, category: string, kind: "own-model" | "competitor" | "brand", search: string, signal: AbortSignal) =>
    request<Choice[]>(projectPath(id) + "/catalog?" + new URLSearchParams({category_code: category, kind, query: search, limit: "50"}), signal),
  async view(scope: Scope & Partial<Selection>, signal: AbortSignal) {
    const {project_id, page, ...params} = scope;
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) value.forEach(id => query.append(key, id));
      else if (value !== "") query.set(key, String(value));
    }
    const view = await request<View>(`${projectPath(project_id)}/views/${page}?${query}`, signal);
    if (view?.version !== "1" || !view.snapshot_id || !["ready","partial","unavailable"].includes(view.status) || view.project_id !== project_id || view.category_code !== scope.category_code ||
        view.page !== page || view.tab !== scope.tab || ![view.tables, view.charts, view.metrics, view.insights, view.actions].every(Array.isArray)) {
      throw new Error("返回的数据与当前页面或筛选范围不一致");
    }
    return view;
  },
  history: (id: string, category: string, signal: AbortSignal) =>
    request<Choice[]>(`${projectPath(id)}/conversations?category_code=${encodeURIComponent(category)}`, signal),
  conversation: (id: string, category: string, chat: string, signal: AbortSignal) =>
    request<Conversation>(`${projectPath(id)}/conversations/${encodeURIComponent(chat)}?category_code=${encodeURIComponent(category)}`, signal),
  async attach(project: string, category: string, file: File, purpose: "chat" | "floor"): Promise<Attachment> {
    const params = new URLSearchParams({category_code: category, purpose, filename: file.name});
    const response = await fetch(base + projectPath(project) + "/attachments?" + params, {
      method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/octet-stream"}, body: file
    });
    if (!response.ok) throw new Error(`附件提交失败（${response.status}）`);
    return response.json();
  },
  ask: (id: string, scope: Filters, conversation_id: string | null, question: string, request_id: string, origin: Origin | null, attachments: string[]) =>
    request<Conversation>(projectPath(id) + "/messages", undefined, {scope, conversation_id, question, request_id, origin, attachment_ids: attachments}, "POST"),
  act: (scope: Scope, operation: Operation, row_id: string | null, input: string, request_id: string, snapshot_id: string, fields: Record<string, string>) =>
    request<Receipt>(projectPath(scope.project_id) + "/actions", undefined, {scope, operation, row_id, input, request_id, snapshot_id, fields}, "POST")
};
