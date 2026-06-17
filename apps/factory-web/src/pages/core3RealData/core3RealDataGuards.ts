const uuidPattern = /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/i;
const sqlPattern = /\b(select|insert|update|delete|from|where|join|create table|alter table|drop table)\b/i;
const internalValuePattern = /\b(core3_|mvp_|source_table|clean_table|evidence_id|selection_run_id|candidate_pool_id|payload_json|raw_payload|market_aggregate|task_battlefield|comment_signal|review_required|blocked)\b/i;
const aiProcessPattern = /(ai\s*认为|模型判断|正在思考|生成过程|提示词|large language model|prompt)/i;

const safeKeyAllowList = new Set([
  "project_id",
  "category_code",
  "sku_code",
  "target_sku_code",
  "competitor_sku_code",
  "short_ref",
  "latest_run_id",
  "latest_batch_id",
  "run_id",
  "batch_id",
  "section_code",
  "role_code",
  "status_code",
  "export_type"
]);

const blockedKeySuffixes = ["_uuid", "_hash", "_fingerprint", "_payload_json"];
const blockedExactKeys = new Set([
  "uuid",
  "sql",
  "source_table",
  "clean_table",
  "evidence_field",
  "evidence_id",
  "evidence_ids",
  "selection_run_id",
  "candidate_pool_id",
  "component_score_id",
  "raw_payload",
  "source_payload_json",
  "section_payload_json"
]);

export interface BusinessPayloadIssue {
  path: string;
  reason: string;
}

export function findBusinessPayloadIssues(value: unknown, path = "$"): BusinessPayloadIssue[] {
  const issues: BusinessPayloadIssue[] = [];
  visitBusinessPayload(value, path, issues);
  return issues;
}

export function assertBusinessPayloadSafe(value: unknown): void {
  const issues = findBusinessPayloadIssues(value);
  if (issues.length > 0) {
    const first = issues[0];
    throw new Error(`${first.path}: ${first.reason}`);
  }
}

function visitBusinessPayload(value: unknown, path: string, issues: BusinessPayloadIssue[]): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => visitBusinessPayload(item, `${path}[${index}]`, issues));
    return;
  }
  if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      const lowered = key.toLowerCase();
      const keyPath = `${path}.${key}`;
      if (!safeKeyAllowList.has(lowered) && (blockedExactKeys.has(lowered) || blockedKeySuffixes.some((suffix) => lowered.endsWith(suffix)))) {
        issues.push({ path: keyPath, reason: "包含内部字段，不应进入业务展示" });
      }
      visitBusinessPayload(item, keyPath, issues);
    }
    return;
  }
  if (typeof value !== "string") {
    return;
  }
  if (uuidPattern.test(value)) {
    issues.push({ path, reason: "包含内部唯一标识" });
  }
  if (sqlPattern.test(value)) {
    issues.push({ path, reason: "包含数据库语句或表查询语言" });
  }
  if (internalValuePattern.test(value)) {
    issues.push({ path, reason: "包含内部工程字段或表名" });
  }
  if (aiProcessPattern.test(value)) {
    issues.push({ path, reason: "包含非业务化的 AI 过程文案" });
  }
}
