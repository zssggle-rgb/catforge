import {
  DownloadOutlined,
  FileSearchOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SearchOutlined
} from "@ant-design/icons";
import { Button, Card, Descriptions, Empty, Input, Space, Statistic, Table, Tag, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type { Core3CompetitorBrief, Core3EvidenceResponse, Core3Overview, Core3SkuReport, Project } from "../../types";
import {
  businessLabel,
  businessText,
  businessValue,
  competitorLabel,
  confidenceColor,
  confidenceLabel,
  core3RoleLabels,
  formatNumber,
  formatPercent,
  orderCore3Roles
} from "./core3Format";
import { type Core3PageKey } from "./core3Pages";

const { Title, Text } = Typography;

export function Core3Mvp({ project, pageKey }: { project: Project; pageKey: Core3PageKey }) {
  const [targetQuery, setTargetQuery] = useState("85E7Q");
  const [overview, setOverview] = useState<Core3Overview>();
  const [report, setReport] = useState<Core3SkuReport>();
  const [evidence, setEvidence] = useState<Core3EvidenceResponse>();
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);

  const loadOverview = async () => {
    setLoading(true);
    try {
      setOverview(await api.core3Overview(project.project_id));
    } catch (error) {
      setOverview(undefined);
      showError(error, "读取批量总览失败");
    } finally {
      setLoading(false);
    }
  };

  const runBatch = async () => {
    setRunning(true);
    try {
      const result = await api.core3Run(project.project_id, { batch: true, force_recompute: true });
      message.success(`三竞品批量生成完成：${result.counts.competitor_result_count ?? 0} 条结果`);
      await loadOverview();
    } catch (error) {
      showError(error, "批量生成失败");
    } finally {
      setRunning(false);
    }
  };

  const loadReport = async (query = targetQuery) => {
    if (!query.trim()) {
      message.warning("请输入商品编号或型号");
      return;
    }
    setLoading(true);
    try {
      const next = await api.core3Report(project.project_id, query.trim());
      setReport(next);
      setTargetQuery(next.target_sku.model_name || next.target_sku.sku_code);
    } catch (error) {
      setReport(undefined);
      showError(error, "读取单品报告失败");
    } finally {
      setLoading(false);
    }
  };

  const loadEvidence = async (query = targetQuery) => {
    if (!query.trim()) {
      message.warning("请输入商品编号或型号");
      return;
    }
    setLoading(true);
    try {
      const next = await api.core3Evidence(project.project_id, query.trim());
      setEvidence(next);
    } catch (error) {
      setEvidence(undefined);
      showError(error, "读取证据卡失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setOverview(undefined);
    setReport(undefined);
    setEvidence(undefined);
  }, [project.project_id]);

  useEffect(() => {
    if (pageKey === "core3-overview") {
      loadOverview();
    }
    if (pageKey === "core3-report") {
      loadReport();
    }
    if (pageKey === "core3-evidence") {
      loadEvidence();
    }
  }, [pageKey, project.project_id]);

  if (pageKey === "core3-report") {
    return (
      <Core3SkuReportPanel
        query={targetQuery}
        loading={loading}
        report={report}
        onQueryChange={setTargetQuery}
        onSearch={loadReport}
      />
    );
  }

  if (pageKey === "core3-evidence") {
    return (
      <Core3EvidencePanel
        query={targetQuery}
        loading={loading}
        evidence={evidence}
        onQueryChange={setTargetQuery}
        onSearch={loadEvidence}
      />
    );
  }

  return (
    <Core3OverviewPanel
      projectId={project.project_id}
      overview={overview}
      loading={loading}
      running={running}
      onRefresh={loadOverview}
      onRun={runBatch}
    />
  );
}

function Core3OverviewPanel({
  projectId,
  overview,
  loading,
  running,
  onRefresh,
  onRun
}: {
  projectId: string;
  overview?: Core3Overview;
  loading: boolean;
  running: boolean;
  onRefresh: () => Promise<void>;
  onRun: () => Promise<void>;
}) {
  const exportFile = async (type: "csv" | "jsonl") => {
    try {
      if (type === "csv") {
        downloadText("三竞品结果表.csv", await api.core3Csv(projectId), "text/csv;charset=utf-8");
      } else {
        downloadText("三竞品证据包.jsonl", await api.core3EvidenceJsonl(projectId), "application/x-ndjson;charset=utf-8");
      }
    } catch (error) {
      showError(error, "导出失败");
    }
  };

  return (
    <section className="page-section core3-page">
      <div className="section-heading">
        <div>
          <Title level={2}>彩电三竞品生成</Title>
          <Text type="secondary">批量总览</Text>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={onRefresh}>
            刷新
          </Button>
          <Button type="primary" icon={<PlayCircleOutlined />} loading={running} onClick={onRun}>
            批量生成
          </Button>
          <Button icon={<DownloadOutlined />} onClick={() => exportFile("csv")} disabled={!overview}>
            导出结果表
          </Button>
          <Button icon={<DownloadOutlined />} onClick={() => exportFile("jsonl")} disabled={!overview}>
            导出证据包
          </Button>
        </Space>
      </div>

      <div className="core3-metric-grid">
        <Card size="small">
          <Statistic title="已分析商品" value={overview?.analyzed_sku_count ?? 0} />
        </Card>
        <Card size="small">
          <Statistic title="高置信" value={overview?.confidence_distribution.high ?? 0} />
        </Card>
        <Card size="small">
          <Statistic title="中置信" value={overview?.confidence_distribution.medium ?? 0} />
        </Card>
        <Card size="small">
          <Statistic title="低置信" value={overview?.confidence_distribution.low ?? 0} />
        </Card>
      </div>

      {overview ? (
        <Table
          className="core3-table"
          size="small"
          loading={loading}
          rowKey="target_sku_code"
          dataSource={overview.rows}
          scroll={{ x: 1240 }}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "目标商品", dataIndex: "target_sku_code", width: 140 },
            { title: "品牌", dataIndex: "brand", width: 100 },
            { title: "型号", dataIndex: "model_name", width: 150 },
            { title: "主战场", dataIndex: "primary_battlefield", width: 180, render: (value) => businessLabel(value) },
            {
              title: "正面对打",
              dataIndex: "direct_competitor",
              width: 220,
              render: (value) => competitorLabel(value)
            },
            {
              title: "价格/销量挤压",
              dataIndex: "pressure_competitor",
              width: 220,
              render: (value) => competitorLabel(value)
            },
            {
              title: "标杆/下探",
              dataIndex: "benchmark_potential_competitor",
              width: 220,
              render: (value) => competitorLabel(value)
            },
            {
              title: "置信度",
              dataIndex: "confidence_level",
              width: 100,
              render: (value: string) => <Tag color={confidenceColor(value)}>{confidenceLabel(value)}</Tag>
            },
            {
              title: "复核",
              dataIndex: "review_flag",
              width: 90,
              render: (value: boolean) => <Tag color={value ? "gold" : "green"}>{value ? "是" : "否"}</Tag>
            }
          ]}
        />
      ) : (
        <Empty className="core3-empty" description="暂无三竞品结果" />
      )}
    </section>
  );
}

function Core3SkuReportPanel({
  query,
  loading,
  report,
  onQueryChange,
  onSearch
}: {
  query: string;
  loading: boolean;
  report?: Core3SkuReport;
  onQueryChange: (value: string) => void;
  onSearch: (query?: string) => Promise<void>;
}) {
  const market = report?.market_profile ?? {};
  const params = report ? pickParams(report.standard_params) : [];
  const competitors = useMemo(() => orderCore3Roles(report?.core_competitors ?? []), [report]);

  return (
    <section className="page-section core3-page">
      <div className="section-heading">
        <div>
          <Title level={2}>单品竞品报告</Title>
          <Text type="secondary">{report ? `${report.target_sku.brand ?? ""} ${report.target_sku.model_name ?? report.target_sku.sku_code}` : "85E7Q"}</Text>
        </div>
        <Space.Compact className="core3-search">
          <Input placeholder="输入商品编号或型号" value={query} onChange={(event) => onQueryChange(event.target.value)} onPressEnter={() => onSearch()} />
          <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={() => onSearch()}>
            搜索
          </Button>
        </Space.Compact>
      </div>

      {report ? (
        <>
          <Descriptions bordered size="small" column={{ xs: 1, sm: 2, lg: 4 }} className="detail-strip">
            <Descriptions.Item label="目标型号">{`${report.target_sku.brand ?? ""} ${report.target_sku.model_name ?? report.target_sku.series ?? ""}`}</Descriptions.Item>
            <Descriptions.Item label="近12月均价">{formatMoney(market.price_wavg_12m)}</Descriptions.Item>
            <Descriptions.Item label="12月销量">{formatNumber(market.sales_volume_12m, 0)}</Descriptions.Item>
            <Descriptions.Item label="销售强度">{formatPercent(market.sales_percentile)}</Descriptions.Item>
          </Descriptions>

          <Core3MethodologyPanel report={report} competitors={competitors} />
          <Core3CompetitorConclusion competitors={competitors} />

          <div className="core3-report-block">
            <div className="core3-report-block-heading">
              <Title level={3}>为什么判定为竞品</Title>
              <Text type="secondary">按价格带、战场、卖点、参数、渠道和销量逐项核验。</Text>
            </div>
            <div className="core3-proof-stack">
              {competitors.map((competitor) => (
                <Core3CompetitorProofCard key={competitor.role} competitor={competitor} />
              ))}
            </div>
          </div>

          <div className="core3-report-block-heading">
            <Title level={3}>目标型号画像</Title>
            <Text type="secondary">用于理解海信 85E7Q 当前参与竞争的业务基础。</Text>
          </div>
          <div className="core3-report-grid">
            <Card size="small" title="核心参数">
              <Table
                size="small"
                rowKey="param_code"
                dataSource={params}
                pagination={false}
                columns={[
                  { title: "参数项", dataIndex: "param_code", render: (value) => businessLabel(value) },
                  { title: "取值", dataIndex: "value", render: (value) => businessValue(value) },
                  { title: "证据数", dataIndex: "evidence_count", width: 90 }
                ]}
              />
            </Card>
            <SignalList title="激活卖点" rows={report.activated_claims} codeKey="claim_code" scoreKey="activation_score" />
            <SignalList title="用户任务" rows={report.tasks} codeKey="task_code" scoreKey="score" />
            <SignalList title="价值战场" rows={report.battlefields} codeKey="battlefield_code" scoreKey="final_score" />
          </div>
        </>
      ) : (
        <Empty className="core3-empty" description="暂无单品报告" />
      )}
    </section>
  );
}

function Core3MethodologyPanel({ report, competitors }: { report: Core3SkuReport; competitors: Core3CompetitorBrief[] }) {
  const derivation = asRecord(report.derivation_summary);
  const runCounts = asRecord(derivation.run_counts);
  const featureCounts = asRecord(derivation.target_feature_counts);
  const candidatePool = asRecord(derivation.candidate_pool);
  const targetName = [report.target_sku.brand, report.target_sku.model_name || report.target_sku.series].filter(Boolean).join(" ") || report.target_sku.sku_code;
  const market = report.market_profile ?? {};
  const topClaims = topBusinessLabels(report.activated_claims, "claim_code", 3);
  const topTasks = topBusinessLabels(report.tasks, "task_code", 3);
  const topGroups = topBusinessLabels(report.target_groups, "target_group_code", 2);
  const targetTopBattlefields = report.battlefields
    .slice(0, 3)
    .map((row) => `${businessLabel(row["battlefield_code"])} ${formatPercent(row["final_score"] ?? row["score"])}`)
    .join("、");
  const selectedText = competitors
    .map((competitor) => `${core3RoleLabels[competitor.role]}：${competitorDisplayFromBrief(competitor)}`)
    .join("；");
  const steps = [
    {
      title: "读取业务数据",
      point: `本批次读取 ${formatNumber(runCounts.sku_count, 0)} 个彩电 SKU，覆盖量价、参数、宣传卖点和评论数据。`,
      detail: `量价 ${formatNumber(runCounts.market_fact_count, 0)} 条，参数 ${formatNumber(runCounts.param_row_count, 0)} 条，卖点 ${formatNumber(runCounts.claim_row_count, 0)} 条，评论 ${formatNumber(runCounts.comment_row_count, 0)} 条。`
    },
    {
      title: "形成目标型号画像",
      point: `${targetName} 的近12月均价 ${formatMoney(market.price_wavg_12m)}，销量 ${formatNumber(market.sales_volume_12m, 0)} 台，渠道以${channelShareText(market.channel_share)}为主。`,
      detail: "这一步只描述目标型号的市场位置，不直接给出竞品结论。"
    },
    {
      title: "抽取真实产品特征",
      point: `从真实数据中归一出 ${formatNumber(featureCounts.standard_param_count, 0)} 个参数、激活 ${formatNumber(featureCounts.activated_claim_count, 0)} 个卖点、识别 ${formatNumber(featureCounts.comment_topic_count, 0)} 类评论主题。`,
      detail: `主要卖点：${topClaims || "暂无"}。这些结果来自参数、宣传文本和评论证据，不按型号写死。`
    },
    {
      title: "派生任务、客群和战场",
      point: `由特征继续推导用户任务、目标客群和价值战场。主要任务：${topTasks || "暂无"}；主要客群：${topGroups || "暂无"}。`,
      detail: `强战场：${targetTopBattlefields || "暂无"}。战场由语义分和量价市场分共同决定。`
    },
    {
      title: "召回可比较候选池",
      point: `从项目 SKU 中排除目标自身后，按同品类、尺寸、价格窗口、渠道、任务/战场交集召回候选。`,
      detail: `本目标进入候选池 ${formatNumber(candidatePool.total, 0)} 个，其中通过硬门槛 ${formatNumber(candidatePool.eligible, 0)} 个，证据不足 ${formatNumber(candidatePool.insufficient, 0)} 个。`
    },
    {
      title: "按三类竞品角色打分",
      point: "同一个候选会分别计算正面对打、价格/销量挤压、高端标杆/潜在下探三套分数。",
      detail: "正面对打看共同战场、卖点对位、价格接近；挤压看低价或销量强势；标杆看参数/卖点更强及下探风险。"
    },
    {
      title: "三槽位选择并复核证据",
      point: selectedText,
      detail: `按槽位门槛、分数排序、SKU 去重、品牌分散和“不硬凑”规则输出；本次非空入选 ${formatNumber(candidatePool.selected, 0)} 个。`
    }
  ];

  return (
    <div className="core3-method-card">
      <div className="core3-report-block-heading">
        <Title level={3}>从业务数据推导竞品的过程</Title>
        <Text type="secondary">不是直接按战场下结论，而是从数据、画像、候选池到三槽位逐步收敛。</Text>
      </div>
      <div className="core3-method-steps core3-method-steps-expanded">
        {steps.map((step, index) => (
          <div key={step.title} className="core3-method-step">
            <span>{index + 1}</span>
            <strong>{step.title}</strong>
            <p>{step.point}</p>
            <em>{step.detail}</em>
          </div>
        ))}
      </div>
    </div>
  );
}

function Core3CompetitorConclusion({ competitors }: { competitors: Core3CompetitorBrief[] }) {
  return (
    <div className="core3-report-block">
      <div className="core3-report-block-heading">
        <Title level={3}>竞品结论</Title>
        <Text type="secondary">先看三类竞品是谁，再看后面的判定依据。</Text>
      </div>
      <div className="core3-result-grid">
        {competitors.map((competitor) => (
          <Card key={competitor.role} size="small" className="core3-result-card">
            <div className="core3-result-role">{core3RoleLabels[competitor.role]}</div>
            <div className="core3-result-name">{competitorDisplayFromBrief(competitor)}</div>
            <p>{competitorConclusionText(competitor)}</p>
            <div className="core3-result-tags">
              <Tag color={confidenceColor(competitor.confidence_level)}>{businessConfidenceText(competitor.confidence_level)}</Tag>
              {primaryProofTags(competitor).map((tag) => (
                <Tag key={tag}>{tag}</Tag>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

function Core3CompetitorProofCard({ competitor }: { competitor: Core3CompetitorBrief }) {
  const rows = buildProofRows(competitor);
  const highlights = buildEvidenceHighlights(competitor);

  return (
    <Card
      size="small"
      className="core3-proof-card"
      title={
        <div className="core3-evidence-card-title">
          <span>{core3RoleLabels[competitor.role]}</span>
          <Tag color={confidenceColor(competitor.confidence_level)}>{competitorDisplayFromBrief(competitor)}</Tag>
        </div>
      }
    >
      <div className="core3-proof-claim">
        <div className="core3-section-label">判定结论</div>
        <p>{businessJudgementText(competitor)}</p>
      </div>

      <BattlefieldDeduction competitor={competitor} />
      <RoleGateChecklist competitor={competitor} />

      {rows.length > 0 ? (
        <div className="core3-proof-grid">
          {rows.map((row) => (
            <div key={row.label} className="core3-proof-row">
              <span>{row.label}</span>
              <strong>{row.value}</strong>
              <p>{row.note}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="core3-proof-missing">当前没有足够的量价、参数或卖点证据支撑该类竞品，建议补充可比较型号后再复核。</div>
      )}

      {rows.length > 0 && (
        <div className="core3-evidence-section">
          <div className="core3-section-label">证明链</div>
          <ul className="core3-evidence-points core3-proof-points">
            {highlights.slice(0, 6).map((itemText) => (
              <li key={itemText}>{itemText}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function BattlefieldDeduction({ competitor }: { competitor: Core3CompetitorBrief }) {
  const card = competitor.evidence_card ?? {};
  const battlefieldEvidence = asRecord(card.battlefield_evidence);
  const taskBattlefield = asRecord(card.task_battlefield_similarity);
  const sharedCode = textValue(battlefieldEvidence.shared_battlefield_code) ?? textValue(taskBattlefield.shared_battlefield_code) ?? competitor.battlefield_code;
  const sharedName = businessLabel(sharedCode);
  const targetName = productDisplayFromRecord(asRecord(card.target), "目标型号");
  const targetRow = asRecord(battlefieldEvidence.target_selected_battlefield);
  const competitorRow = asRecord(battlefieldEvidence.competitor_selected_battlefield);
  const driverLabels = battlefieldDriverLabels(sharedCode, card);

  if (sharedName === "-") {
    return null;
  }

  return (
    <div className="core3-battlefield-chain">
      <div className="core3-section-label">战场推导</div>
      <p className="core3-battlefield-summary">
        为什么是{sharedName}：先分别识别{targetName} 和 {competitorDisplayFromBrief(competitor)} 的价值战场，再在双方共同战场里选择综合强度最高的一项作为本竞品关系的主解释战场。
      </p>
      <div className="core3-battlefield-grid">
        <BattlefieldRank label="目标型号" row={targetRow} fallbackName={sharedName} />
        <BattlefieldRank label="竞品型号" row={competitorRow} fallbackName={sharedName} />
        <div className="core3-battlefield-cell">
          <span>共同解释</span>
          <strong>{sharedName}</strong>
          <p>双方都落入该战场，且该战场能解释本组竞品关系中的用户场景、卖点对位和购买比较。</p>
        </div>
      </div>
      {driverLabels.length > 0 && (
        <div className="core3-battlefield-drivers">
          <span>支撑信号</span>
          {driverLabels.map((label) => (
            <Tag key={label}>{label}</Tag>
          ))}
        </div>
      )}
    </div>
  );
}

function BattlefieldRank({ label, row, fallbackName }: { label: string; row: Record<string, unknown>; fallbackName: string }) {
  const rank = numberValue(row.rank);
  const total = numberValue(row.total);
  const score = row.final_score ?? row.score;
  const isMain = row.is_main === true || row.relation_level === "main";

  return (
    <div className="core3-battlefield-cell">
      <span>{label}</span>
      <strong>{businessLabel(row.battlefield_code) !== "-" ? businessLabel(row.battlefield_code) : fallbackName}</strong>
      <p>
        {rank && total ? `排名第 ${rank}/${total}，` : ""}
        {score !== undefined ? `强度 ${formatPercent(score)}，` : ""}
        {isMain ? "属于主战场之一。" : "需要补充证据判断是否为主战场。"}
      </p>
    </div>
  );
}

function RoleGateChecklist({ competitor }: { competitor: Core3CompetitorBrief }) {
  const checks = roleGateChecks(competitor);
  if (checks.length === 0) {
    return null;
  }
  return (
    <div className="core3-gate-checks">
      <div className="core3-section-label">槽位门槛核验</div>
      <div className="core3-gate-grid">
        {checks.map((check) => (
          <div key={check.label} className={`core3-gate-check ${check.pass ? "is-pass" : "is-fail"}`}>
            <span>{check.label}</span>
            <strong>{check.value}</strong>
            <p>{check.rule}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function roleGateChecks(competitor: Core3CompetitorBrief): { label: string; value: string; rule: string; pass: boolean }[] {
  if (!competitor.competitor_sku_code) {
    return [
      {
        label: "候选结果",
        value: "未通过",
        rule: "没有候选同时满足该槽位硬门槛和证据要求。",
        pass: false
      }
    ];
  }
  const card = competitor.evidence_card ?? {};
  const scores = asRecord(card.component_scores);
  const categoryCount = Array.isArray(competitor.evidence_categories) ? competitor.evidence_categories.length : 0;
  if (competitor.role === "direct") {
    return [
      gateCheck("战场相似", scores.battlefield_similarity, 0.55),
      gateCheck("卖点对位", scores.claim_similarity, 0.45),
      gateCheck("价格接近", scores.price_similarity, 0.45),
      { label: "证据覆盖", value: `${categoryCount} 类`, rule: "需要至少 3 类证据。", pass: categoryCount >= 3 }
    ];
  }
  if (competitor.role === "pressure") {
    const priceAdvantage = numberValue(scores.price_advantage) ?? 0;
    const salesStrength = numberValue(scores.sales_strength) ?? 0;
    return [
      gateCheck("任务相似", scores.task_similarity, 0.45),
      {
        label: "挤压信号",
        value: `价格优势 ${formatPercent(priceAdvantage)} / 销量强度 ${formatPercent(salesStrength)}`,
        rule: "价格优势需达到 25%，或销量强度达到 70%。",
        pass: priceAdvantage >= 0.25 || salesStrength >= 0.7
      },
      { label: "量价证据", value: categoryCount > 0 ? "已覆盖" : "缺失", rule: "至少要有价格或销量证据。", pass: hasAnyEvidence(competitor, ["price", "sales"]) }
    ];
  }
  return [
    {
      label: "高端/下探门槛",
      value: competitor.competitor_sku_code ? "已候选" : "未通过",
      rule: "需要参数或卖点强于目标，并具备高价、销额或下探信号。",
      pass: Boolean(competitor.competitor_sku_code)
    }
  ];
}

function gateCheck(label: string, value: unknown, threshold: number): { label: string; value: string; rule: string; pass: boolean } {
  const number = numberValue(value);
  return {
    label,
    value: formatPercent(number),
    rule: `达标线 ${formatPercent(threshold)}。`,
    pass: number !== undefined && number >= threshold
  };
}

function hasAnyEvidence(competitor: Core3CompetitorBrief, categories: string[]): boolean {
  const values = Array.isArray(competitor.evidence_categories) ? competitor.evidence_categories : [];
  return categories.some((category) => values.includes(category));
}

function Core3EvidencePanel({
  query,
  loading,
  evidence,
  onQueryChange,
  onSearch
}: {
  query: string;
  loading: boolean;
  evidence?: Core3EvidenceResponse;
  onQueryChange: (value: string) => void;
  onSearch: (query?: string) => Promise<void>;
}) {
  return (
    <section className="page-section core3-page">
      <div className="section-heading">
        <div>
          <Title level={2}>竞品证据摘要</Title>
          <Text type="secondary">{targetDisplayFromEvidence(evidence) ?? "海信 85E7Q"}</Text>
        </div>
        <Space.Compact className="core3-search">
          <Input placeholder="输入商品编号或型号" value={query} onChange={(event) => onQueryChange(event.target.value)} onPressEnter={() => onSearch()} />
          <Button type="primary" icon={<FileSearchOutlined />} loading={loading} onClick={() => onSearch()}>
            查看摘要
          </Button>
        </Space.Compact>
      </div>

      {evidence ? (
        <div className="core3-evidence-stack">
          {orderCore3Roles(evidence.items).map((item) => (
            <Core3EvidenceBusinessCard key={item.role} item={item} />
          ))}
        </div>
      ) : (
        <Empty className="core3-empty" description="暂无证据卡" />
      )}
    </section>
  );
}

type Core3EvidenceItem = Core3EvidenceResponse["items"][number];
type Core3EvidenceBackedItem = {
  role: Core3CompetitorBrief["role"];
  competitor_sku_code?: string | null;
  evidence_card?: Record<string, unknown>;
  evidence_categories?: string[];
};

function Core3EvidenceBusinessCard({ item }: { item: Core3EvidenceItem }) {
  const card = item.evidence_card ?? {};
  const competitor = asRecord(card.competitor);
  const scores = asRecord(card.component_scores);
  const price = asRecord(card.price_comparison);
  const sales = asRecord(card.sales_comparison);
  const channel = asRecord(card.channel_overlap);
  const highlights = buildEvidenceHighlights(item);
  const coverageLabels = evidenceCoverageLabels(item.evidence_categories);

  return (
    <Card
      className="core3-evidence-business-card"
      size="small"
      title={
        <div className="core3-evidence-card-title">
          <span>{core3RoleLabels[item.role]}</span>
          <Tag color="blue">{competitorDisplayFromCard(competitor, item.competitor_sku_code)}</Tag>
        </div>
      }
    >
      <div className="core3-exec-metrics">
        <BusinessMetric label="目标均价" value={formatMoney(price.target_price)} />
        <BusinessMetric label="竞品均价" value={formatMoney(price.competitor_price)} />
        <BusinessMetric label="价格关系" value={priceRelationText(price)} />
        <BusinessMetric label="12月销量" value={salesComparisonText(sales)} />
        <BusinessMetric label="渠道重合" value={formatPercent(channel.score ?? scores.channel_overlap)} />
        <BusinessMetric label="卖点相似" value={formatPercent(scores.claim_similarity)} />
      </div>

      <div className="core3-evidence-judgement">
        <div className="core3-section-label">业务判断</div>
        <p>{businessJudgementText(item)}</p>
      </div>

      <div className="core3-evidence-business-grid">
        <div className="core3-evidence-section">
          <div className="core3-section-label">关键依据</div>
          <ul className="core3-evidence-points">
            {highlights.map((itemText) => (
              <li key={itemText}>{itemText}</li>
            ))}
          </ul>
        </div>
        <div className="core3-evidence-section core3-evidence-side">
          <div className="core3-section-label">证据覆盖</div>
          <div className="core3-evidence-tags">
            {coverageLabels.map((label) => (
              <Tag key={label}>{label}</Tag>
            ))}
          </div>
          <div className="core3-evidence-count">支撑信息：{item.evidence_items.length} 条</div>
        </div>
      </div>
    </Card>
  );
}

function BusinessMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="core3-exec-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SignalList({
  title,
  rows,
  codeKey,
  scoreKey
}: {
  title: string;
  rows: Record<string, unknown>[];
  codeKey: string;
  scoreKey: string;
}) {
  return (
    <Card size="small" title={title}>
      <Table
        size="small"
        rowKey={(row) => String(row[codeKey])}
        dataSource={rows.slice(0, 8)}
        pagination={false}
        columns={[
          { title: "业务信号", dataIndex: codeKey, render: (value) => businessLabel(value) },
          {
            title: "强度",
            dataIndex: scoreKey,
            width: 90,
            render: (value) => formatNumber(value)
          },
          {
            title: "证据数",
            dataIndex: "evidence_ids",
            width: 80,
            render: (value: unknown) => (Array.isArray(value) ? value.length : 0)
          }
        ]}
      />
    </Card>
  );
}

function pickParams(params: Core3SkuReport["standard_params"]) {
  const keys = [
    "screen_size_inch",
    "mini_led_flag",
    "native_refresh_rate_hz",
    "system_refresh_rate_hz",
    "peak_brightness_nits",
    "dimming_zones",
    "hdmi_2_1_ports"
  ];
  return keys
    .filter((key) => params[key])
    .map((key) => ({
      param_code: key,
      value: params[key].normalized_value,
      evidence_count: Array.isArray(params[key].evidence_ids) ? params[key].evidence_ids.length : 0
    }));
}

function topBusinessLabels(rows: Record<string, unknown>[], codeKey: string, limit: number): string {
  return rows
    .slice(0, limit)
    .map((row) => businessLabel(row[codeKey]))
    .filter((label) => label !== "-")
    .join("、");
}

function channelShareText(value: unknown): string {
  const share = asRecord(value);
  const channels = Object.entries(share)
    .map(([code, score]) => ({ label: channelLabel(code), score: numberValue(score) ?? 0 }))
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 2)
    .map((row) => `${row.label}${formatPercent(row.score)}`);
  return channels.join("、") || "可观察渠道";
}

function targetDisplayFromEvidence(evidence?: Core3EvidenceResponse): string | undefined {
  const firstCard = evidence?.items[0]?.evidence_card;
  const target = asRecord(firstCard?.target);
  const brand = textValue(target.brand);
  const model = textValue(target.model_name) || textValue(target.series);
  const display = [brand, model].filter(Boolean).join(" ");
  return display || evidence?.target_sku_code;
}

function competitorDisplayFromBrief(competitor: Core3CompetitorBrief): string {
  return [competitor.competitor_brand, competitor.competitor_model_name || competitor.competitor_series].filter(Boolean).join(" ") || "暂未命中";
}

function productDisplayFromRecord(product: Record<string, unknown>, fallback: string): string {
  return [textValue(product.brand), textValue(product.model_name) || textValue(product.series)].filter(Boolean).join(" ") || fallback;
}

function competitorConclusionText(competitor: Core3CompetitorBrief): string {
  if (!competitor.competitor_sku_code) {
    return "暂未形成可信竞品结论，需要补充同价位或高端段可比较型号。";
  }
  return businessJudgementText(competitor);
}

function businessConfidenceText(level: Core3CompetitorBrief["confidence_level"]): string {
  if (level === "high") {
    return "证据充分";
  }
  if (level === "medium") {
    return "可用需复核";
  }
  return "证据待补充";
}

function primaryProofTags(competitor: Core3CompetitorBrief): string[] {
  const card = competitor.evidence_card ?? {};
  const price = asRecord(card.price_comparison);
  const channel = asRecord(card.channel_overlap);
  const taskBattlefield = asRecord(card.task_battlefield_similarity);
  const tags: string[] = [];
  if (competitor.battlefield_code || taskBattlefield.shared_battlefield_code) {
    tags.push(businessLabel(taskBattlefield.shared_battlefield_code ?? competitor.battlefield_code));
  }
  if (numberValue(price.target_price) !== undefined && numberValue(price.competitor_price) !== undefined) {
    tags.push(priceRelationText(price));
  }
  if (numberValue(channel.score) !== undefined) {
    tags.push(`渠道重合 ${formatPercent(channel.score)}`);
  }
  return tags.filter((tag) => tag !== "-").slice(0, 3);
}

function battlefieldDriverLabels(battlefieldCode: string | undefined | null, card: Record<string, unknown>): string[] {
  if (!battlefieldCode) {
    return [];
  }
  const taskBattlefield = asRecord(card.task_battlefield_similarity);
  const claimComparison = asRecord(card.claim_comparison);
  const targetTasks = new Set(arrayValue(taskBattlefield.target_tasks).filter((value): value is string => typeof value === "string"));
  const competitorTasks = new Set(arrayValue(taskBattlefield.competitor_tasks).filter((value): value is string => typeof value === "string"));
  const taskHints: Record<string, string[]> = {
    BF_GAMING_SPORTS: ["TASK_GAMING_ENTERTAINMENT", "TASK_SPORTS_WATCHING"],
    BF_DESIGN_HOME_FIT: ["TASK_NEW_HOME_DECORATION", "TASK_LIVING_ROOM_CINEMA"],
    BF_FAMILY_VIEWING_UPGRADE: ["TASK_LARGE_SCREEN_REPLACEMENT", "TASK_LIVING_ROOM_CINEMA"],
    BF_PREMIUM_PICTURE: ["TASK_PREMIUM_PICTURE_AV", "TASK_LIVING_ROOM_CINEMA"],
    BF_LARGE_SCREEN_VALUE: ["TASK_VALUE_PURCHASE", "TASK_LARGE_SCREEN_REPLACEMENT"]
  };
  const claimHints: Record<string, string[]> = {
    BF_GAMING_SPORTS: ["CLAIM_HIGH_REFRESH_RATE", "CLAIM_HDMI_2_1_GAMING", "CLAIM_SPORTS_MOTION_SMOOTH", "CLAIM_GAMING_LOW_LATENCY"],
    BF_DESIGN_HOME_FIT: ["CLAIM_THIN_DESIGN", "CLAIM_LARGE_SCREEN_IMMERSION", "CLAIM_SMART_VOICE_EASE"],
    BF_FAMILY_VIEWING_UPGRADE: ["CLAIM_LARGE_SCREEN_IMMERSION", "CLAIM_HIGH_BRIGHTNESS_HDR", "CLAIM_IMMERSIVE_AUDIO"],
    BF_PREMIUM_PICTURE: ["CLAIM_MINI_LED_BACKLIGHT", "CLAIM_FINE_LOCAL_DIMMING", "CLAIM_HIGH_BRIGHTNESS_HDR", "CLAIM_QLED_WIDE_COLOR"],
    BF_LARGE_SCREEN_VALUE: ["CLAIM_VALUE_FOR_MONEY", "CLAIM_LARGE_SCREEN_IMMERSION"]
  };

  const taskLabels = (taskHints[battlefieldCode] ?? [])
    .filter((code) => targetTasks.has(code) && competitorTasks.has(code))
    .map((code) => businessLabel(code));
  const claimLabels = (claimHints[battlefieldCode] ?? [])
    .filter((code) => {
      const row = asRecord(claimComparison[code]);
      return (numberValue(row.target_score) ?? 0) > 0 && (numberValue(row.competitor_score) ?? 0) > 0;
    })
    .map((code) => businessLabel(code));

  return [...taskLabels, ...claimLabels].filter((label) => label !== "-").slice(0, 6);
}

function businessJudgementText(item: Core3EvidenceBackedItem): string {
  const card = item.evidence_card ?? {};
  const competitor = asRecord(card.competitor);
  const taskBattlefield = asRecord(card.task_battlefield_similarity);
  const competitorName = competitorDisplayFromCard(competitor, item.competitor_sku_code);
  const battlefield = businessLabel(taskBattlefield.shared_battlefield_code);

  if (!item.competitor_sku_code && Object.keys(competitor).length === 0) {
    return "当前证据不足，暂不能给出可信竞品对象。需要补充同尺寸、同渠道、同价位或高端段可比较型号后再判断。";
  }

  if (item.role === "direct") {
    return `${competitorName}与目标型号处于相近价格带，${battlefield !== "-" ? `${battlefield}是双方共同强战场，` : ""}适合作为正面对打对象。`;
  }
  if (item.role === "pressure") {
    return `${competitorName}在价格或销售表现上对目标型号形成挤压，建议重点观察价格策略、渠道转化和促销节奏。`;
  }
  if (item.role === "benchmark_potential") {
    return `${competitorName}具备高端配置或高价位参考价值，可作为高端标杆和潜在下探风险对象。`;
  }
  return businessText(card.reason_summary);
}

function buildProofRows(competitor: Core3CompetitorBrief): { label: string; value: string; note: string }[] {
  const card = competitor.evidence_card ?? {};
  const scores = asRecord(card.component_scores);
  const price = asRecord(card.price_comparison);
  const sales = asRecord(card.sales_comparison);
  const channel = asRecord(card.channel_overlap);
  const taskBattlefield = asRecord(card.task_battlefield_similarity);
  const rows: { label: string; value: string; note: string }[] = [];

  const battlefield = businessLabel(taskBattlefield.shared_battlefield_code ?? competitor.battlefield_code);
  if (battlefield !== "-") {
    rows.push({
      label: "竞争场景",
      value: battlefield,
      note: `双方争夺相同消费场景，场景匹配 ${formatPercent(taskBattlefield.battlefield_similarity ?? scores.battlefield_similarity)}。`
    });
  }

  if (numberValue(price.target_price) !== undefined && numberValue(price.competitor_price) !== undefined) {
    rows.push({
      label: "价格关系",
      value: `${formatMoney(price.target_price)} 对 ${formatMoney(price.competitor_price)}`,
      note: priceRelationText(price)
    });
  }

  if (numberValue(sales.target_sales_volume_12m) !== undefined || numberValue(sales.competitor_sales_volume_12m) !== undefined) {
    rows.push({
      label: "销售表现",
      value: salesComparisonText(sales),
      note: competitor.role === "pressure" ? "竞品具备销量挤压能力。" : "销量规模足以进入对比视野。"
    });
  }

  if (numberValue(channel.score) !== undefined) {
    const channelNames = sharedChannelNames(channel);
    rows.push({
      label: "渠道对比",
      value: formatPercent(channel.score),
      note: `${channelNames.length > 0 ? channelNames.join("、") : "主要"}渠道可直接对比价格、转化和促销。`
    });
  }

  if (numberValue(scores.claim_similarity) !== undefined) {
    rows.push({
      label: "卖点对位",
      value: formatPercent(scores.claim_similarity),
      note: topClaimText(card) ?? "核心卖点具备可比性。"
    });
  }

  const paramText = topParamComparisonText(card);
  if (paramText) {
    rows.push({
      label: "参数对位",
      value: "可比较",
      note: paramText.replace(/^产品参数：/, "").replace(/。$/, "")
    });
  }

  return rows.slice(0, 6);
}

function buildEvidenceHighlights(item: Core3EvidenceBackedItem): string[] {
  const card = item.evidence_card ?? {};
  const scores = asRecord(card.component_scores);
  const price = asRecord(card.price_comparison);
  const sales = asRecord(card.sales_comparison);
  const channel = asRecord(card.channel_overlap);
  const taskBattlefield = asRecord(card.task_battlefield_similarity);
  const commentEvidence = asRecord(card.comment_evidence);
  const highlights: string[] = [];

  const targetPrice = numberValue(price.target_price);
  const competitorPrice = numberValue(price.competitor_price);
  if (targetPrice !== undefined && competitorPrice !== undefined) {
    highlights.push(`价格带：目标均价 ${formatMoney(targetPrice)}，竞品均价 ${formatMoney(competitorPrice)}，${priceRelationText(price)}。`);
  }

  const targetSales = numberValue(sales.target_sales_volume_12m);
  const competitorSales = numberValue(sales.competitor_sales_volume_12m);
  if (targetSales !== undefined && competitorSales !== undefined) {
    highlights.push(`销售表现：目标近12月销量 ${formatNumber(targetSales, 0)} 台，竞品 ${formatNumber(competitorSales, 0)} 台。`);
  }

  const sharedBattlefield = businessLabel(taskBattlefield.shared_battlefield_code);
  const battlefieldScore = formatPercent(taskBattlefield.battlefield_similarity ?? scores.battlefield_similarity);
  if (sharedBattlefield !== "-") {
    highlights.push(`主战场：双方集中在${sharedBattlefield}，战场相似度 ${battlefieldScore}。`);
  }

  const channelNames = sharedChannelNames(channel);
  if (channelNames.length > 0) {
    highlights.push(`渠道对比：${channelNames.join("、")}渠道重合，适合做同屏价格和转化对比。`);
  }

  const claimText = topClaimText(card);
  if (claimText) {
    highlights.push(claimText);
  }

  const paramText = topParamComparisonText(card);
  if (paramText) {
    highlights.push(paramText);
  }

  const targetTopics = arrayValue(commentEvidence.target_topics).length;
  const competitorTopics = arrayValue(commentEvidence.competitor_topics).length;
  if (targetTopics + competitorTopics > 0) {
    highlights.push(`用户反馈：已覆盖双方评论主题，可辅助判断画质、游戏、系统体验等口碑差异。`);
  }

  return highlights.length > 0 ? highlights.slice(0, 6) : ["已汇总量价、渠道、参数、卖点和评论信息，支持业务复核。"];
}

function topClaimText(card: Record<string, unknown>): string | undefined {
  const comparison = asRecord(card.claim_comparison);
  const labels = Object.entries(comparison)
    .map(([code, value]) => {
      const row = asRecord(value);
      const targetScore = numberValue(row.target_score) ?? 0;
      const competitorScore = numberValue(row.competitor_score) ?? 0;
      const strength = Math.min(targetScore, competitorScore);
      return { label: businessLabel(code), strength };
    })
    .filter((row) => row.label !== "-" && row.strength > 0)
    .sort((a, b) => b.strength - a.strength)
    .slice(0, 3)
    .map((row) => row.label);

  return labels.length > 0 ? `核心卖点：${labels.join("、")}是双方主要对比点。` : undefined;
}

function topParamComparisonText(card: Record<string, unknown>): string | undefined {
  const comparison = asRecord(card.param_comparison);
  const priority = [
    "screen_size_inch",
    "mini_led_flag",
    "native_refresh_rate_hz",
    "system_refresh_rate_hz",
    "peak_brightness_nits",
    "dimming_zones",
    "hdmi_2_1_ports"
  ];
  const phrases = priority
    .map((code) => {
      const row = asRecord(comparison[code]);
      if (Object.keys(row).length === 0) {
        return undefined;
      }
      const targetValue = row.target;
      const competitorValue = row.competitor;
      if (typeof targetValue === "boolean" || typeof competitorValue === "boolean") {
        return booleanParamComparisonText(code, targetValue, competitorValue);
      }
      const targetText = paramValueText(code, targetValue);
      const competitorText = paramValueText(code, competitorValue);
      if (targetText === "-" && competitorText === "-") {
        return undefined;
      }
      if (targetText === competitorText) {
        return `${businessLabel(code)}同为${targetText}`;
      }
      return `${businessLabel(code)}目标${targetText}、竞品${competitorText}`;
    })
    .filter((value): value is string => Boolean(value))
    .slice(0, 3);

  return phrases.length > 0 ? `产品参数：${phrases.join("；")}。` : undefined;
}

function booleanParamComparisonText(code: string, targetValue: unknown, competitorValue: unknown): string | undefined {
  const label = businessLabel(code);
  if (targetValue === undefined && competitorValue === undefined) {
    return undefined;
  }
  if (targetValue === competitorValue) {
    return targetValue === true ? `${label}均支持` : `${label}均未覆盖`;
  }
  return `${label}目标${targetValue === true ? "支持" : "未覆盖"}、竞品${competitorValue === true ? "支持" : "未覆盖"}`;
}

function evidenceCoverageLabels(categories: unknown): string[] {
  const labelMap: Record<string, string> = {
    price: "价格表现",
    sales: "销售表现",
    channel: "渠道对比",
    param: "核心参数",
    claim: "核心卖点",
    task_battlefield: "场景战场",
    comment: "用户反馈"
  };
  if (!Array.isArray(categories)) {
    return ["业务证据"];
  }
  const labels = categories.map((category) => (typeof category === "string" ? labelMap[category] : undefined)).filter((label): label is string => Boolean(label));
  return labels.length > 0 ? labels : ["业务证据"];
}

function competitorDisplayFromCard(competitor: Record<string, unknown>, fallbackSku?: string | null): string {
  const brand = textValue(competitor.brand);
  const model = textValue(competitor.model_name) || textValue(competitor.series);
  const display = [brand, model].filter(Boolean).join(" ");
  return display || (fallbackSku ? "已命中竞品" : "未命中");
}

function priceRelationText(price: Record<string, unknown>): string {
  const target = numberValue(price.target_price);
  const competitor = numberValue(price.competitor_price);
  if (target === undefined || competitor === undefined || competitor === 0) {
    return "-";
  }
  const delta = (target - competitor) / competitor;
  if (Math.abs(delta) < 0.03) {
    return "基本同价";
  }
  return delta > 0 ? `目标高 ${formatPercent(Math.abs(delta))}` : `目标低 ${formatPercent(Math.abs(delta))}`;
}

function salesComparisonText(sales: Record<string, unknown>): string {
  const target = numberValue(sales.target_sales_volume_12m);
  const competitor = numberValue(sales.competitor_sales_volume_12m);
  if (target === undefined && competitor === undefined) {
    return "-";
  }
  return `${formatNumber(target, 0)} / ${formatNumber(competitor, 0)}`;
}

function sharedChannelNames(channel: Record<string, unknown>): string[] {
  const targetShare = asRecord(channel.target_channel_share);
  const competitorShare = asRecord(channel.competitor_channel_share);
  return Object.keys(targetShare)
    .filter((key) => numberValue(targetShare[key]) !== undefined && numberValue(competitorShare[key]) !== undefined)
    .map((key) => channelLabel(key));
}

function channelLabel(code: string): string {
  const labels: Record<string, string> = {
    JD: "京东",
    TMALL: "天猫",
    Tmall: "天猫",
    DOUYIN: "抖音",
    OFFLINE: "线下"
  };
  return labels[code] ?? businessText(code);
}

function paramValueText(code: string, value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "boolean") {
    return businessValue(value);
  }
  const number = numberValue(value);
  if (number !== undefined) {
    const unitMap: Record<string, string> = {
      screen_size_inch: "英寸",
      native_refresh_rate_hz: "赫兹",
      system_refresh_rate_hz: "赫兹",
      refresh_rate_hz: "赫兹",
      peak_brightness_nits: "尼特",
      dimming_zones: "区",
      hdmi_2_1_ports: "个",
      ram_gb: "GB",
      storage_gb: "GB",
      speaker_power_w: "W"
    };
    return `${formatNumber(number, Number.isInteger(number) ? 0 : 2)}${unitMap[code] ?? ""}`;
  }
  return businessValue(value);
}

function formatMoney(value: unknown): string {
  const number = numberValue(value);
  return number === undefined ? "-" : `¥${formatNumber(number, 0)}`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function textValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
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

function downloadText(fileName: string, text: string, type: string) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

function showError(error: unknown, fallback: string) {
  message.error(error instanceof Error ? error.message : fallback);
}
