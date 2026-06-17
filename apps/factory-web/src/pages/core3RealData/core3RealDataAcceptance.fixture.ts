import type { Core3V2BusinessReportResponse, Core3V2CoreCompetitor, Core3V2EvidenceCard } from "../../types";

const competitors: Core3V2CoreCompetitor[] = [
  {
    competitor_sku_code: "TV900002",
    competitor_model_name: "85Q10L",
    competitor_brand_name: "TCL",
    competitor_display_name_cn: "TCL 85Q10L",
    role_code: "direct_fight",
    role_name_cn: "正面对打竞品",
    one_sentence_reason_cn: "同为 85 英寸 Mini LED，同价位、同游戏体育战场，直接争夺同一批客厅大屏用户。",
    battlefield_fit_cn: "游戏体育战场高度重合",
    market_pressure_cn: "样例周期内销量走势接近目标型号",
    key_difference_cn: "分区和峰值亮度更激进",
    target_advantage_cn: "海信在价格稳定和观赛口碑上更稳",
    competitor_advantage_cn: "TCL 在控光规格上更强势",
    strategy_implication_cn: "正面表达游戏体育和大屏影院，不回避参数对比",
    confidence_label_cn: "高可信",
    evidence_short_refs: [{ short_ref: "E01" }, { short_ref: "E02" }]
  },
  {
    competitor_sku_code: "TV900003",
    competitor_model_name: "MAX 85 2026",
    competitor_brand_name: "红米",
    competitor_display_name_cn: "红米 MAX 85 2026",
    role_code: "price_volume_pressure",
    role_name_cn: "价格/销量挤压竞品",
    one_sentence_reason_cn: "同尺寸但价格下探，样例销量更高，对预算敏感家庭形成挤压。",
    battlefield_fit_cn: "家庭大屏与价格价值战场重合",
    market_pressure_cn: "低价高量形成明显入口压力",
    key_difference_cn: "画质参数低于目标，但价格门槛更低",
    target_advantage_cn: "目标在高刷、控光和接口完整度上更强",
    competitor_advantage_cn: "价格更容易转化预算敏感用户",
    strategy_implication_cn: "强调多花预算换来的游戏、观赛和画质确定性",
    confidence_label_cn: "中高可信",
    evidence_short_refs: [{ short_ref: "E03" }, { short_ref: "E04" }]
  },
  {
    competitor_sku_code: "TV900004",
    competitor_model_name: "85U7N",
    competitor_brand_name: "海信",
    competitor_display_name_cn: "海信 85U7N",
    role_code: "benchmark_potential",
    role_name_cn: "高端标杆/潜在下探竞品",
    one_sentence_reason_cn: "同品牌同尺寸，价格更高但价值战场相邻，可作为高端标杆和潜在下探压力。",
    battlefield_fit_cn: "画质升级和游戏体育战场相邻",
    market_pressure_cn: "销量不高但对品质升级人群有标杆作用",
    key_difference_cn: "高端控光、亮度和音响规格更强",
    target_advantage_cn: "目标在主流预算内更容易成交",
    competitor_advantage_cn: "高端画质表达更完整",
    strategy_implication_cn: "把同品牌高端能力转化为目标型号的可信背书",
    confidence_label_cn: "中高可信",
    evidence_short_refs: [{ short_ref: "E05" }, { short_ref: "E06" }]
  }
];

const evidenceCards: Core3V2EvidenceCard[] = competitors.map((competitor) => ({
  target_sku_code: "TV900001",
  target_display_name_cn: "海信 85E8Q Pro",
  competitor_sku_code: competitor.competitor_sku_code,
  competitor_display_name_cn: competitor.competitor_display_name_cn,
  role_code: competitor.role_code,
  role_name_cn: competitor.role_name_cn,
  headline_cn: `${competitor.competitor_display_name_cn}：${competitor.role_name_cn}`,
  summary_cn: competitor.one_sentence_reason_cn,
  one_sentence_reason_cn: competitor.one_sentence_reason_cn,
  battlefield_name_cn: competitor.battlefield_fit_cn,
  confidence_label_cn: competitor.confidence_label_cn,
  price_evidence_cn: "价格带、价位差和销量走势已纳入候选判断。",
  channel_evidence_cn: "线上专业电商与平台电商均有覆盖。",
  param_evidence_cn: "屏幕尺寸、刷新率、背光、亮度和接口参数形成可比基础。",
  claim_value_evidence_cn: "卖点围绕大屏影院、游戏高刷、体育观赛和画质升级展开。",
  task_audience_evidence_cn: "用户任务集中在主机游戏、体育观赛、家庭影院和品质升级。",
  market_evidence_cn: competitor.market_pressure_cn,
  comment_evidence_cn: "评论样本覆盖游戏、体育、家庭观影、画质、安装服务和价格感知。",
  key_difference_cn: competitor.key_difference_cn,
  target_advantage_cn: competitor.target_advantage_cn,
  competitor_advantage_cn: competitor.competitor_advantage_cn,
  strategy_implication_cn: competitor.strategy_implication_cn,
  evidence_short_refs: competitor.evidence_short_refs
}));

export const core3RealDataAcceptanceReport: Core3V2BusinessReportResponse = {
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
  report_title_cn: "海信 85E8Q Pro 核心三竞品报告",
  executive_conclusion_cn: "当前三竞品分别承担正面对打、价格销量挤压和高端标杆三种业务角色。",
  data_scope: {
    period_cn: "26W01 到 26W06",
    channel_scope_cn: "线上渠道",
    platform_scope_cn: "专业电商与平台电商",
    sample_note_cn: "本地验收样例覆盖 6 个彩电型号。",
    data_scope_note_cn: "当前本地验收样例内，205 恢复后需用真实数据重跑。"
  },
  release_status: {
    status_code: "review_required",
    status_name_cn: "需复核",
    gate_reason_cn: "样例规模有限，但链路与展示规则可验收。",
    data_scope_note_cn: "当前本地验收样例内。",
    can_present: true,
    can_release: false
  },
  core_competitors: competitors,
  why_these_competitors_cn:
    "先以同尺寸、价格带、渠道和销量形成候选池，再叠加参数、卖点、评论、用户任务、目标客群和价值战场证据，最后按三种竞品角色选择核心三竞品。",
  battlefield_summary_cn:
    "海信 85E8Q Pro 的主要战场是游戏体育和家庭影院；TCL 85Q10L 在同一战场正面对打，红米形成价格/销量挤压，海信 85U7N 形成同品牌高端标杆。",
  evidence_cards: evidenceCards,
  sections: [
    {
      section_code: "business_path",
      section_title_cn: "竞品推导路径",
      section_order: 1,
      display_status_cn: "展示",
      section_payload: {
        数据基础: "市场、参数、卖点和评论四类证据均已接入。",
        候选形成: "同尺寸、同价位和同渠道先形成可比候选池。",
        角色确认: "按正面对打、价格销量挤压、高端标杆三类业务角色落位。"
      },
      evidence_short_refs: [{ short_ref: "E01" }, { short_ref: "E03" }, { short_ref: "E05" }]
    },
    {
      section_code: "battlefield_path",
      section_title_cn: "价值战场判断",
      section_order: 2,
      display_status_cn: "展示",
      section_payload: {
        主战场: "游戏体育与家庭影院",
        目标证据: "高刷、接口、控光、观赛评论和大屏影院卖点同时支撑。",
        竞品证据: "三款竞品分别在同战场、价格价值和高端升级方向形成压力。"
      },
      evidence_short_refs: [{ short_ref: "E02" }, { short_ref: "E04" }, { short_ref: "E06" }]
    }
  ],
  candidate_audit: {
    候选池概况: { 全量型号: 6, 进入候选: 5, 排除样本: 1 },
    已选择竞品数: 3,
    空缺槽位数: 0,
    复核问题: ["样例数据规模有限，205 恢复后需用真实数据重跑"]
  },
  review_hint: {
    review_required: true,
    severity_name_cn: "中等",
    message_cn: "本地验收可展示完整业务链路，真实发布需等待 205 恢复后复核。",
    suggested_action_cn: "205 恢复后使用真实 PostgreSQL 数据执行全链路运行。",
    review_count: 1
  },
  exports: [
    {
      export_type: "markdown",
      export_title_cn: "核心三竞品汇报稿",
      export_payload: "# 海信 85E8Q Pro 核心三竞品报告\n\n当前三竞品角色完整。",
      data_scope_note_cn: "当前本地验收样例内。",
      export_status_cn: "可预览",
      media_type: "text/markdown"
    }
  ],
  data_quality_note_cn: "当前本地验收样例内已覆盖完整链路；205 恢复后必须用真实数据复跑并保留数据范围说明。"
};
