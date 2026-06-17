import { describe, expect, it } from "vitest";
import type { Core3V2BusinessReportResponse } from "../../types";
import {
  buildReportView,
  candidateAuditItems,
  evidenceRowsForCard,
  formatCore3V2Date,
  pipelineStatusLabel,
  releaseStatusName,
  roleLabel
} from "./core3RealDataFormat";

describe("Core3 真实数据格式化", () => {
  it("中文化状态和角色", () => {
    expect(roleLabel("direct_fight")).toBe("正面对打竞品");
    expect(releaseStatusName("review_required")).toBe("需复核");
    expect(pipelineStatusLabel("success")).toBe("已完成");
    expect(formatCore3V2Date("2026-06-13T10:00:00Z")).toContain("2026");
  });

  it("生成证据矩阵行", () => {
    expect(
      evidenceRowsForCard({
        target_sku_code: "TV900001",
        target_display_name_cn: "海信 85E8Q Pro",
        competitor_sku_code: "TV900002",
        competitor_display_name_cn: "TCL 85Q10L",
        role_code: "direct_fight",
        role_name_cn: "正面对打竞品",
        headline_cn: "TCL 85Q10L 是正面对打竞品",
        summary_cn: "同尺寸、同价格带、同战场。",
        one_sentence_reason_cn: "双方争夺同一批大屏游戏体育用户。",
        battlefield_name_cn: "游戏体育战场",
        confidence_label_cn: "高可信",
        price_evidence_cn: "价格带接近",
        channel_evidence_cn: null,
        param_evidence_cn: "同为 85 英寸 Mini LED 高刷新",
        claim_value_evidence_cn: null,
        task_audience_evidence_cn: null,
        market_evidence_cn: "销量趋势接近",
        comment_evidence_cn: "评论都集中在游戏和观赛",
        key_difference_cn: "竞品分区更高",
        target_advantage_cn: "目标价格更稳",
        competitor_advantage_cn: "竞品亮度更高",
        strategy_implication_cn: "正面保持游戏体育表达",
        risk_note_cn: null,
        evidence_short_refs: []
      }).map((row) => row.label)
    ).toEqual(["价格证据", "参数证据", "市场证据", "评论证据"]);
  });

  it("把候选池审计转成业务摘要", () => {
    expect(
      candidateAuditItems({
        候选池概况: { 全量型号: 6, 战场重合: 4 },
        已选择竞品数: 3,
        空缺槽位数: 0,
        复核问题: ["样例周期较短"]
      })
    ).toHaveLength(4);
  });

  it("根据发布门禁生成报告可见性和角色槽位", () => {
    const view = buildReportView(sampleReport("review_required"));
    expect(view.visibility).toBe("review_with_report");
    expect(view.canShowReport).toBe(true);
    expect(view.roleSlots.map((slot) => slot.role_code)).toEqual([
      "direct_fight",
      "price_volume_pressure",
      "benchmark_potential"
    ]);
    expect(view.evidenceRowsByCompetitor.TV900002).toHaveLength(2);
  });

  it("阻断报告只允许显示摘要", () => {
    const view = buildReportView(sampleReport("blocked"));
    expect(view.visibility).toBe("blocked_summary");
    expect(view.canShowReport).toBe(false);
  });
});

function sampleReport(statusCode: string): Core3V2BusinessReportResponse {
  return {
    project_id: "core3_local_validation",
    category_code: "TV",
    target: {
      sku_code: "TV900001",
      model_name: "85E8Q Pro",
      brand_name: "海信",
      display_name_cn: "海信 85E8Q Pro",
      size_segment_cn: "85 英寸",
      price_band_cn: "6000-7500",
      data_status_cn: "已生成报告"
    },
    report_title_cn: "海信 85E8Q Pro 核心竞品报告",
    executive_conclusion_cn: "当前核心竞品集中在游戏体育和家庭观影升级。",
    data_scope: {
      period_cn: "26W 样例周期",
      channel_scope_cn: "线上渠道",
      platform_scope_cn: "专业电商",
      sample_note_cn: "当前结果仅代表已接入数据。",
      data_scope_note_cn: "当前样例数据内。"
    },
    release_status: {
      status_code: statusCode,
      status_name_cn: statusCode === "blocked" ? "已阻断" : "需复核",
      gate_reason_cn: "样例范围需说明。",
      data_scope_note_cn: "当前样例数据内。",
      can_present: statusCode !== "blocked",
      can_release: false
    },
    core_competitors: [
      {
        competitor_sku_code: "TV900002",
        competitor_model_name: "85Q10L",
        competitor_brand_name: "TCL",
        competitor_display_name_cn: "TCL 85Q10L",
        role_code: "direct_fight",
        role_name_cn: "正面对打竞品",
        one_sentence_reason_cn: "同尺寸、同价格、同战场。",
        battlefield_fit_cn: "游戏体育战场",
        market_pressure_cn: "销量趋势接近",
        key_difference_cn: "竞品分区更高",
        target_advantage_cn: "目标价格更稳",
        competitor_advantage_cn: "竞品亮度更高",
        strategy_implication_cn: "正面对打",
        confidence_label_cn: "高可信",
        evidence_short_refs: [{ short_ref: "E01" }]
      }
    ],
    why_these_competitors_cn: "同尺寸、同价格带、战场重合。",
    battlefield_summary_cn: "主要落在游戏体育战场。",
    evidence_cards: [
      {
        target_sku_code: "TV900001",
        target_display_name_cn: "海信 85E8Q Pro",
        competitor_sku_code: "TV900002",
        competitor_display_name_cn: "TCL 85Q10L",
        role_code: "direct_fight",
        role_name_cn: "正面对打竞品",
        headline_cn: "正面对打",
        summary_cn: "证据充分。",
        one_sentence_reason_cn: "同战场。",
        battlefield_name_cn: "游戏体育战场",
        confidence_label_cn: "高可信",
        price_evidence_cn: "价格带接近",
        market_evidence_cn: "销量趋势接近",
        key_difference_cn: "分区不同",
        target_advantage_cn: "价格稳",
        competitor_advantage_cn: "亮度高",
        strategy_implication_cn: "正面表达",
        evidence_short_refs: [{ short_ref: "E01" }]
      }
    ],
    sections: [],
    candidate_audit: { 候选池概况: { 全量型号: 6 }, 已选择竞品数: 1 },
    review_hint: {
      review_required: statusCode !== "released",
      message_cn: "样例范围需说明。",
      review_count: 1
    },
    exports: [],
    data_quality_note_cn: "当前样例数据仅用于本地验证。"
  };
}

