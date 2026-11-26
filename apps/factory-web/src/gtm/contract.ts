// GTM BFF v1. The server owns business conclusions, units, permissions and evidence.
export const pages = {
  daily: "每日重点工作", "key-model": "重点产品表现", "own-monitor": "我品价格巡检",
  launch: "竞品上新提醒", "rival-monitor": "竞品价格监控", competitor: "竞品洞察分析",
  premium: "品牌溢价分析", "todo-center": "待办任务中心", reports: "订阅报告"
} as const;
export type Page = keyof typeof pages;
export type Route = Page | "chat" | "history" | "help";
export const pageTabs: Partial<Record<Page, readonly (readonly [string, string])[]>> = {
  competitor: [["product", "产品对比"], ["value", "用户价值分析"], ["weight", "卖点称重"], ["price-volume", "价量联动分析"]],
  premium: [["value-index", "价值指数"], ["voc", "VOC指数"]]
};
export interface Choice { id: string; label: string }
export interface Category extends Choice { subcategories: Choice[] }
export interface Workspace extends Choice { categories: Category[]; channels: Choice[] }
export interface Context {
  version: "1"; mode: "live" | "sample"; user: {name: string; role: string};
  projects: Workspace[];
}
export interface Filters {
  category_code: string; channel: string; subcategory: string;
  period: "today" | "yesterday" | "7d" | "30d" | "custom";
  date_from: string; date_to: string; query: string;
}
export interface Scope extends Filters { project_id: string; page: Page; tab: string; offset: number; limit: number }
export interface Selection {model_id: string; competitor_ids: string[]; brand_ids: string[]}
export type FacetKey = "brand" | "severity" | "status" | "owner" | "cadence";
export interface Facet {key: FacetKey; label: string; options: Choice[]}
export type Tone = "teal" | "red" | "orange" | "purple";
export interface Evidence {
  evidence_id: string; source: string; observed_at: string | null; excerpt: string;
  source_file_id?: string | null; raw_row_id?: string | null; evidence_url?: string | null;
}
export interface Insight {
  label: string; title: string; tone: Tone; body: string; bullets: string[];
  question?: string | null; evidence: Evidence[];
}
export interface Metric {
  label: string; value: number | string | null; unit?: string; hint?: string; target?: Page; tone?: Tone;
  basis?: {grain: string; population: string; source_batch: string; coverage_from: string; coverage_to: string; synced_at: string | null};
}
export type Cell = string | number | null;
export interface Chart {
  title: string; kind: "line" | "distribution"; unit: string;
  points: {label: string; value: number | null}[];
}
export interface Column { key: string; label: string; unit?: string }
export type Operation = "complete-task" | "acknowledge-alert" | "ignore-alert" | "subscribe-report" | "unsubscribe-report" |
  "create-report" | "edit-report" | "publish-report" | "import-floor" | "create-campaign" | "set-key-models";
export interface InputField {key: string; label: string; kind: "text" | "textarea" | "date" | "file"; required: boolean; value?: string}
export interface Action { operation: Operation; label: string; fields?: InputField[] }
export interface Attachment { id: string; name: string }
export interface Row {
  id: string; title: string; cells: Record<string, Cell>; evidence: Evidence[];
  drilldown?: import("./workbench/projection").DetailRef;
  detail: {label: string; value: Cell}[]; actions: Action[];
}
export interface DataTable { id: string; title: string; columns: Column[]; rows: Row[]; total: number; target?: Page }
export interface View {
  version: "1"; project_id: string; category_code: string; page: Page; tab: string;
  snapshot_id: string; as_of: string | null; status: "ready" | "partial" | "unavailable"; notice: string | null;
  method_version?: string | null; confidence?: number | null; review_status?: string | null;
  facets?: Facet[];
  insights: Insight[]; metrics: Metric[]; charts: Chart[]; tables: DataTable[]; actions: Action[];
}
export interface ChatItem {role: "user" | "assistant"; text: string; evidence: Evidence[]}
export interface Conversation extends Choice { messages: ChatItem[] }
export interface Receipt { id: string; message: string }
export interface Origin {page: Page; tab: string; snapshot_id: string; scope?: Scope & Partial<Selection>}

export function readRoute(hash: string): {route: Route; conversation: string} {
  const [name, id] = hash.replace(/^#\/?/, "").split("/");
  const route = Object.hasOwn(pages, name) || ["chat", "history", "help"].includes(name) ? name as Route : "daily";
  try {return {route, conversation: route === "chat" && id ? decodeURIComponent(id) : ""};}
  catch {return {route: "chat", conversation: ""};}
}
export function defaultFilters(category: string): Filters {
  return {category_code: category, channel: "", subcategory: "", period: "today", date_from: "", date_to: "", query: ""};
}
export function displayValue(value: Cell | undefined, unit = "") {
  if (value == null || value === "" || value === "-") return "—";
  return (typeof value === "number" ? value.toLocaleString("zh-CN", {maximumFractionDigits: 4}) : value) + unit;
}
