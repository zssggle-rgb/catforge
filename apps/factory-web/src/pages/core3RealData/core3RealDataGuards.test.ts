import { describe, expect, it } from "vitest";
import { assertBusinessPayloadSafe, findBusinessPayloadIssues } from "./core3RealDataGuards";

describe("Core3 真实数据前端展示边界", () => {
  it("允许业务必要的项目和 SKU 字段", () => {
    expect(() =>
      assertBusinessPayloadSafe({
        project_id: "core3_local_validation",
        target_sku_code: "TV900001",
        short_ref: "E01",
        conclusion_cn: "正面对打竞品证据充分。"
      })
    ).not.toThrow();
  });

  it("拦截 UUID、SQL、内部字段和 AI 过程文案", () => {
    const issues = findBusinessPayloadIssues({
      report_section_id: "bad",
      reason: "AI 认为这个竞品成立",
      debug: "select * from core3_target_report_payload where evidence_id='550e8400-e29b-41d4-a716-446655440000'"
    });
    expect(issues.length).toBeGreaterThanOrEqual(4);
  });
});

