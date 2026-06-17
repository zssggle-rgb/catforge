import { describe, expect, it } from "vitest";
import { core3RealDataAcceptanceReport } from "./core3RealDataAcceptance.fixture";
import { assertBusinessPayloadSafe, findBusinessPayloadIssues } from "./core3RealDataGuards";
import { buildReportView, businessPairsFromPayload, core3RealDataDefaultQuery } from "./core3RealDataFormat";

describe("Core3 真实数据最终验收", () => {
  it("报告先展示三竞品是谁，再展示成立原因和证据", () => {
    const view = buildReportView(core3RealDataAcceptanceReport);

    expect(view.canShowReport).toBe(true);
    expect(view.roleSlots.map((slot) => slot.role_name_cn)).toEqual([
      "正面对打竞品",
      "价格/销量挤压竞品",
      "高端标杆/潜在下探竞品"
    ]);
    expect(view.roleSlots.map((slot) => slot.competitor?.competitor_sku_code)).toEqual([
      "TV900002",
      "TV900003",
      "TV900004"
    ]);
    expect(view.evidenceRowsByCompetitor.TV900002.map((row) => row.label)).toContain("卖点证据");
    expect(view.evidenceRowsByCompetitor.TV900003.map((row) => row.label)).toContain("评论证据");
    expect(view.allShortRefs.map((ref) => ref.short_ref)).toEqual(["E01", "E02", "E03", "E04", "E05", "E06"]);
  });

  it("推导摘要只保留业务语言", () => {
    const view = buildReportView(core3RealDataAcceptanceReport);
    const displayText = [
      core3RealDataAcceptanceReport.report_title_cn,
      core3RealDataAcceptanceReport.executive_conclusion_cn,
      core3RealDataAcceptanceReport.why_these_competitors_cn,
      core3RealDataAcceptanceReport.battlefield_summary_cn,
      core3RealDataAcceptanceReport.data_quality_note_cn,
      ...view.roleSlots.map((slot) => `${slot.role_name_cn}${slot.competitor?.one_sentence_reason_cn ?? ""}`),
      ...view.visibleSections.flatMap((section) =>
        businessPairsFromPayload(section.section_payload, 8).flatMap((item) => [item.label, item.value])
      )
    ].join("\n");

    expect(findBusinessPayloadIssues(displayText)).toEqual([]);
    expect(displayText).toContain("当前本地验收样例内");
    expect(displayText).toContain("价值战场");
    expect(displayText).not.toMatch(/AI|prompt|review_required|blocked|market_aggregate|comment_signal|task_battlefield/i);
  });

  it("高层展示边界拦截内部字段和过程文案", () => {
    const issues = findBusinessPayloadIssues({
      display_payload_json: { note: "comment_signal 命中" },
      summary_cn: "AI 认为来自 market_aggregate 的推导成立",
      status_cn: "review_required"
    });

    expect(issues.length).toBeGreaterThanOrEqual(3);
  });

  it("默认查询保留 85E7Q，同时验收样例用有卖点 SKU 覆盖完整报告", () => {
    expect(core3RealDataDefaultQuery).toBe("85E7Q");
    expect(core3RealDataAcceptanceReport.target.sku_code).toBe("TV900001");
    expect(core3RealDataAcceptanceReport.evidence_cards.every((card) => card.claim_value_evidence_cn)).toBe(true);
    expect(() =>
      assertBusinessPayloadSafe({
        target_sku_code: core3RealDataAcceptanceReport.target.sku_code,
        summary_cn: core3RealDataAcceptanceReport.data_quality_note_cn
      })
    ).not.toThrow();
  });
});
