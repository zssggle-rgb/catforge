import type {
  Core3V2BusinessReportResponse,
  Core3V2CoreCompetitor,
  Core3V2DataScope,
  Core3V2EvidenceCard,
  Core3V2EvidenceShortRef,
  Core3V2ReleaseStatus,
  Core3V2ReportSection
} from "../../types";
import { assertBusinessPayloadSafe } from "./core3RealDataGuards";
import { core3RealDataRoleOrder } from "./core3RealDataPages";

export const core3RealDataDefaultQuery = "85E7Q";

export type ReportVisibility = "blocked_summary" | "not_ready" | "review_with_report" | "full_report";

export interface Core3RealDataCompetitorSlot {
  role_code: string;
  role_name_cn: string;
  competitor?: Core3V2CoreCompetitor;
  missing_reason_cn?: string;
}

export interface Core3RealDataEvidenceRow {
  key: string;
  label: string;
  value: string;
}

export interface Core3RealDataBusinessPair {
  label: string;
  value: string;
}

export interface Core3RealDataReportView {
  visibility: ReportVisibility;
  statusLabel: string;
  statusColor: string;
  canShowReport: boolean;
  roleSlots: Core3RealDataCompetitorSlot[];
  evidenceRowsByCompetitor: Record<string, Core3RealDataEvidenceRow[]>;
  candidateAuditItems: Core3RealDataBusinessPair[];
  visibleSections: Core3V2ReportSection[];
  allShortRefs: Core3V2EvidenceShortRef[];
}

const roleLabels: Record<string, string> = {
  direct_fight: "正面对打竞品",
  price_volume_pressure: "价格/销量挤压竞品",
  benchmark_potential: "高端标杆/潜在下探竞品"
};

const releaseStatusColors: Record<string, string> = {
  blocked: "red",
  not_ready: "default",
  review_required: "gold",
  releasable: "green",
  released: "blue"
};

const pipelineStatusLabels: Record<string, string> = {
  pending: "待执行",
  running: "执行中",
  success: "已完成",
  warning: "有提醒",
  review_required: "需复核",
  blocked: "已阻断",
  failed: "失败",
  skipped: "已跳过"
};

export function roleLabel(roleCode: string): string {
  return roleLabels[roleCode] ?? "竞品角色待确认";
}

export function releaseStatusLabel(status?: Core3V2ReleaseStatus | null): string {
  return status?.status_name_cn || releaseStatusName(status?.status_code);
}

export function releaseStatusName(statusCode?: string | null): string {
  if (statusCode === "blocked") {
    return "已阻断";
  }
  if (statusCode === "review_required") {
    return "需复核";
  }
  if (statusCode === "releasable") {
    return "可汇报";
  }
  if (statusCode === "released") {
    return "已发布";
  }
  return "未就绪";
}

export function releaseStatusColor(statusCode?: string | null): string {
  return releaseStatusColors[statusCode ?? ""] ?? "default";
}

export function pipelineStatusLabel(statusCode: unknown): string {
  const key = String(statusCode ?? "");
  return pipelineStatusLabels[key] ?? safeBusinessText(key, "状态待确认");
}

export function formatCore3V2Number(value: unknown, digits = 0): string {
  const parsed = numberValue(value);
  if (parsed === undefined) {
    return "-";
  }
  return parsed.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

export function formatCore3V2Percent(value: unknown): string {
  const parsed = numberValue(value);
  if (parsed === undefined) {
    return "-";
  }
  return `${Math.round(parsed * 100)}%`;
}

export function formatCore3V2Date(value: string | null | undefined): string {
  if (!value) {
    return "未记录";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function dataScopeSummary(scope?: Core3V2DataScope | null): string {
  if (!scope) {
    return "当前数据范围待确认。";
  }
  return [scope.period_cn, scope.channel_scope_cn, scope.platform_scope_cn, scope.data_scope_note_cn]
    .filter(Boolean)
    .join(" · ");
}

export function buildReportView(report: Core3V2BusinessReportResponse): Core3RealDataReportView {
  assertBusinessPayloadSafe({
    report_title_cn: report.report_title_cn,
    executive_conclusion_cn: report.executive_conclusion_cn,
    why_these_competitors_cn: report.why_these_competitors_cn,
    battlefield_summary_cn: report.battlefield_summary_cn,
    data_quality_note_cn: report.data_quality_note_cn
  });
  const statusCode = report.release_status.status_code;
  const visibility: ReportVisibility =
    statusCode === "blocked"
      ? "blocked_summary"
      : statusCode === "not_ready"
        ? "not_ready"
        : statusCode === "review_required"
          ? "review_with_report"
          : "full_report";
  const ordered = orderCompetitors(report.core_competitors);
  const cardsBySku = Object.fromEntries(report.evidence_cards.map((card) => [card.competitor_sku_code, card]));
  return {
    visibility,
    statusLabel: releaseStatusLabel(report.release_status),
    statusColor: releaseStatusColor(statusCode),
    canShowReport: visibility !== "blocked_summary" && visibility !== "not_ready",
    roleSlots: core3RealDataRoleOrder.map((roleCode) => {
      const competitor = ordered.find((item) => item.role_code === roleCode);
      return {
        role_code: roleCode,
        role_name_cn: roleLabel(roleCode),
        competitor,
        missing_reason_cn: competitor ? undefined : "当前样例数据暂未形成该角色的稳定竞品。"
      };
    }),
    evidenceRowsByCompetitor: Object.fromEntries(
      report.core_competitors.map((competitor) => [
        competitor.competitor_sku_code,
        evidenceRowsForCard(cardsBySku[competitor.competitor_sku_code])
      ])
    ),
    candidateAuditItems: candidateAuditItems(report.candidate_audit),
    visibleSections: report.sections
      .filter((section) => section.display_status_cn !== "不展示")
      .sort((a, b) => a.section_order - b.section_order),
    allShortRefs: uniqueShortRefs([
      ...report.core_competitors.flatMap((item) => item.evidence_short_refs),
      ...report.evidence_cards.flatMap((item) => item.evidence_short_refs),
      ...report.sections.flatMap((item) => item.evidence_short_refs)
    ])
  };
}

export function orderCompetitors(items: Core3V2CoreCompetitor[]): Core3V2CoreCompetitor[] {
  return [...items].sort((a, b) => roleIndex(a.role_code) - roleIndex(b.role_code));
}

export function evidenceRowsForCard(card?: Core3V2EvidenceCard): Core3RealDataEvidenceRow[] {
  if (!card) {
    return [];
  }
  return [
    ["price_evidence_cn", "价格证据", card.price_evidence_cn],
    ["channel_evidence_cn", "渠道证据", card.channel_evidence_cn],
    ["param_evidence_cn", "参数证据", card.param_evidence_cn],
    ["claim_value_evidence_cn", "卖点证据", card.claim_value_evidence_cn],
    ["task_audience_evidence_cn", "任务/客群证据", card.task_audience_evidence_cn],
    ["market_evidence_cn", "市场证据", card.market_evidence_cn],
    ["comment_evidence_cn", "评论证据", card.comment_evidence_cn]
  ]
    .filter(([, , value]) => Boolean(value))
    .map(([key, label, value]) => ({ key: String(key), label: String(label), value: String(value) }));
}

export function candidateAuditItems(value: Record<string, unknown>): Core3RealDataBusinessPair[] {
  const items: Core3RealDataBusinessPair[] = [];
  appendAuditItem(items, "候选池概况", value["候选池概况"]);
  appendAuditItem(items, "已选择竞品数", value["已选择竞品数"]);
  appendAuditItem(items, "空缺槽位数", value["空缺槽位数"]);
  appendAuditItem(items, "复核问题", value["复核问题"]);
  return items.filter((item) => item.value !== "-");
}

export function businessPairsFromPayload(payload: Record<string, unknown>, maxItems = 8): Core3RealDataBusinessPair[] {
  const pairs: Core3RealDataBusinessPair[] = [];
  for (const [key, value] of Object.entries(payload)) {
    const label = safeBusinessText(key, "");
    if (!label || key.endsWith("_json") || key.endsWith("_id")) {
      continue;
    }
    const text = compactValue(value);
    if (text !== "-") {
      pairs.push({ label, value: text });
    }
    if (pairs.length >= maxItems) {
      break;
    }
  }
  return pairs;
}

export function safeBusinessText(value: unknown, fallback = "-"): string {
  const text = String(value ?? "").trim();
  if (!text) {
    return fallback;
  }
  return text
    .replace(/\bdirect_fight\b/g, "正面对打")
    .replace(/\bprice_volume_pressure\b/g, "价格/销量挤压")
    .replace(/\bbenchmark_potential\b/g, "高端标杆/潜在下探")
    .replace(/\breview_required\b/g, "需复核")
    .replace(/\breleasable\b/g, "可汇报")
    .replace(/\breleased\b/g, "已发布")
    .replace(/\bblocked\b/g, "已阻断")
    .replace(/\bnot_ready\b/g, "未就绪")
    .replace(/_/g, " ");
}

function roleIndex(roleCode: string): number {
  const index = core3RealDataRoleOrder.findIndex((item) => item === roleCode);
  return index >= 0 ? index : 99;
}

function uniqueShortRefs(refs: Core3V2EvidenceShortRef[]): Core3V2EvidenceShortRef[] {
  const seen = new Set<string>();
  const result: Core3V2EvidenceShortRef[] = [];
  for (const ref of refs) {
    if (!ref.short_ref || seen.has(ref.short_ref)) {
      continue;
    }
    seen.add(ref.short_ref);
    result.push(ref);
  }
  return result;
}

function appendAuditItem(items: Core3RealDataBusinessPair[], label: string, value: unknown): void {
  const text = compactValue(value);
  if (text !== "-") {
    items.push({ label, value: text });
  }
}

function compactValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "number") {
    return formatCore3V2Number(value);
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (typeof value === "string") {
    return safeBusinessText(value);
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => compactValue(item))
      .filter((item) => item !== "-")
      .slice(0, 6)
      .join("；") || "-";
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${safeBusinessText(key)}：${compactValue(item)}`)
      .filter((item) => !item.endsWith("：-"))
      .slice(0, 6)
      .join("；") || "-";
  }
  return String(value);
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

