import {
  CheckCircleOutlined,
  CloudUploadOutlined,
  ExportOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined
} from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Empty, Input, Space, Statistic, Table, Tabs, Tag, Typography, message } from "antd";
import type { TableProps } from "antd";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Project, RuntimeExportResponse, WorkbenchCollectionResponse, WorkbenchExportPreview, WorkbenchOverviewResponse } from "../types";
import type { WorkbenchPageKey } from "./workbenchPages";

const { Title, Text } = Typography;

type Row = Record<string, unknown>;
type Columns = NonNullable<TableProps<Row>["columns"]>;

const libraryPageConfig: Partial<
  Record<WorkbenchPageKey, { title: string; apiType: string; assetType: string; codeKey: string }>
> = {
  "wb-parameters": { title: "标准参数库", apiType: "parameters", assetType: "parameters", codeKey: "param_code" },
  "wb-claims": { title: "标准卖点库", apiType: "claims", assetType: "claims", codeKey: "claim_code" },
  "wb-comment-topics": { title: "评论主题库", apiType: "comment-topics", assetType: "comment-topics", codeKey: "topic_code" },
  "wb-tasks": { title: "用户任务库", apiType: "tasks", assetType: "tasks", codeKey: "task_code" },
  "wb-target-groups": { title: "目标人群库", apiType: "target-groups", assetType: "target-groups", codeKey: "target_group_code" },
  "wb-battlefields": { title: "价值战场库", apiType: "battlefields", assetType: "battlefields", codeKey: "battlefield_code" }
};

export function WorkbenchPage({ project, pageKey }: { project: Project; pageKey: WorkbenchPageKey }) {
  const config = libraryPageConfig[pageKey];
  if (pageKey === "wb-data-overview") {
    return <DataOverviewPage project={project} />;
  }
  if (config) {
    return <LibraryWorkbench project={project} config={config} />;
  }
  if (pageKey === "wb-mappings") {
    return <MappingWorkbench project={project} />;
  }
  if (pageKey === "wb-sku-results") {
    return <SkuResultsPage project={project} />;
  }
  if (pageKey === "wb-sku-detail") {
    return <SkuDetailPage project={project} />;
  }
  if (pageKey === "wb-competitors") {
    return <CompetitorResultsPage project={project} />;
  }
  if (pageKey === "wb-calibration") {
    return <CalibrationReportPage project={project} />;
  }
  return <ExportPreviewPage project={project} />;
}

function DataOverviewPage({ project }: { project: Project }) {
  const [overview, setOverview] = useState<WorkbenchOverviewResponse>();
  const [loading, setLoading] = useState(false);
  const [fixtureLoading, setFixtureLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setOverview(await api.workbenchOverview(project.project_id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取数据概览失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [project.project_id]);

  const useFixture = async () => {
    setFixtureLoading(true);
    try {
      await api.useWorkbenchFixture(project.project_id);
      await load();
      message.success("1000-SKU 风格夹具已完成分析");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "夹具分析失败");
    } finally {
      setFixtureLoading(false);
    }
  };

  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>数据概览</Title>
          <Text type="secondary">彩电源数据剖析、缺失率、重复项和未映射簇。</Text>
        </div>
        <Space wrap>
          <Button icon={<CloudUploadOutlined />} loading={fixtureLoading} onClick={useFixture}>
            使用夹具数据
          </Button>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>
            刷新
          </Button>
        </Space>
      </div>
      {overview ? (
        <>
          <div className="metric-grid">
            <MetricCard title="SKU" value={overview.sku_count} />
            <MetricCard title="品牌" value={overview.brand_count} />
            <MetricCard title="渠道" value={overview.channel_count} />
            <MetricCard title="参数行" value={overview.raw_parameter_row_count} />
            <MetricCard title="卖点行" value={overview.raw_claim_row_count} />
            <MetricCard title="评论行" value={overview.raw_comment_row_count} />
            <MetricCard title="量价行" value={overview.market_fact_row_count} />
            <MetricCard title="重复 SKU" value={numberValue(overview.duplicate_sku_count)} />
          </div>
          <Descriptions bordered size="small" column={2} className="detail-strip">
            <Descriptions.Item label="时间范围">{JSON.stringify(overview.time_range ?? {})}</Descriptions.Item>
            <Descriptions.Item label="质量状态">{String(nested(overview, ["quality_summary", "status"]) ?? "unknown")}</Descriptions.Item>
          </Descriptions>
          <Tabs
            items={[
              {
                key: "missing",
                label: "缺失率",
                children: <DataTable rows={arrayRows(overview.missing_field_rates)} />
              },
              {
                key: "params",
                label: "未映射参数",
                children: <DataTable rows={arrayRows(overview.unmapped_parameter_fields)} />
              },
              {
                key: "claims",
                label: "未映射卖点簇",
                children: <DataTable rows={arrayRows(overview.unmapped_claim_clusters)} />
              },
              {
                key: "quality",
                label: "质量问题",
                children: <DataTable rows={arrayRows(overview.quality_issues)} />
              }
            ]}
          />
        </>
      ) : (
        <Empty description="暂无数据概览" />
      )}
    </section>
  );
}

function LibraryWorkbench({
  project,
  config
}: {
  project: Project;
  config: { title: string; apiType: string; assetType: string; codeKey: string };
}) {
  const [data, setData] = useState<WorkbenchCollectionResponse>();
  const [loading, setLoading] = useState(false);
  const [reviewing, setReviewing] = useState<string>();

  const load = async () => {
    setLoading(true);
    try {
      setData(await api.workbenchLibrary(project.project_id, config.apiType));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取资产库失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [project.project_id, config.apiType]);

  const review = async (
    row: Row,
    decision: "approved" | "rejected" | "needs_split" | "needs_merge" | "deprecated" | "pending"
  ) => {
    const assetId = String(row[config.codeKey] ?? row.object_code ?? "");
    setReviewing(`${assetId}:${decision}`);
    try {
      await api.reviewWorkbenchAsset(project.project_id, config.assetType, assetId, decision);
      await load();
      message.success("复核结果已写回资产库");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "复核失败");
    } finally {
      setReviewing(undefined);
    }
  };

  const rows = data?.items ?? [];
  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>{config.title}</Title>
          <Text type="secondary">来源、原始样例、派生特征、映射血缘、证据与版本状态。</Text>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>
          刷新
        </Button>
      </div>
      <DataTable
        rows={rows}
        loading={loading}
        leadingKeys={[config.codeKey, "object_name", "source_basis", "confidence", "review_status", "asset_version", "rule_version"]}
        extraColumns={[
          {
            title: "复核",
            key: "actions",
            fixed: "right",
            width: 260,
            render: (_value: unknown, row: Row) => (
              <Space>
                <Button size="small" icon={<CheckCircleOutlined />} loading={reviewing === `${row[config.codeKey]}:approved`} onClick={() => review(row, "approved")}>
                  通过
                </Button>
                <Button size="small" danger loading={reviewing === `${row[config.codeKey]}:rejected`} onClick={() => review(row, "rejected")}>
                  拒绝
                </Button>
                <Button size="small" onClick={() => review(row, "needs_split")}>
                  拆分
                </Button>
                <Button size="small" onClick={() => review(row, "needs_merge")}>
                  合并
                </Button>
              </Space>
            )
          }
        ]}
      />
    </section>
  );
}

function MappingWorkbench({ project }: { project: Project }) {
  const [data, setData] = useState<WorkbenchCollectionResponse>();
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      setData(await api.workbenchMappings(project.project_id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取映射规则失败");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, [project.project_id]);
  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>映射规则</Title>
          <Text type="secondary">参数、卖点、评论主题、任务、人群、战场和竞品规则的语义图边。</Text>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>
          刷新
        </Button>
      </div>
      <DataTable
        rows={data?.items ?? []}
        loading={loading}
        leadingKeys={["source_type", "source_code", "target_type", "target_code", "relation_type", "weight", "confidence", "review_status"]}
      />
    </section>
  );
}

function SkuResultsPage({ project }: { project: Project }) {
  const [data, setData] = useState<WorkbenchCollectionResponse>();
  const [selectedSku, setSelectedSku] = useState<string>();
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      const next = await api.workbenchSkuResults(project.project_id);
      setData(next);
      setSelectedSku((current) => current ?? String(next.items[0]?.sku_code ?? ""));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取 SKU 结果失败");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, [project.project_id]);
  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>SKU 批量结果</Title>
          <Text type="secondary">批量检查卖点激活、任务、人群、战场、价值层、竞品数量与复核状态。</Text>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>
          刷新
        </Button>
      </div>
      <DataTable
        rows={data?.items ?? []}
        loading={loading}
        leadingKeys={[
          "sku_code",
          "brand",
          "model",
          "price_band",
          "channels",
          "sales_volume",
          "top_activated_claims",
          "top_user_tasks",
          "target_groups",
          "battlefield_assignments",
          "direct_competitor_count",
          "confidence",
          "review_status"
        ]}
        extraColumns={[
          {
            title: "质检",
            key: "detail",
            fixed: "right",
            width: 90,
            render: (_value: unknown, row: Row) => (
              <Button size="small" onClick={() => setSelectedSku(String(row.sku_code ?? ""))}>
                查看
              </Button>
            )
          }
        ]}
      />
      {selectedSku && <SkuDetailPanel project={project} skuCode={selectedSku} compact />}
    </section>
  );
}

function SkuDetailPage({ project }: { project: Project }) {
  const [skuCode, setSkuCode] = useState("TV00029115");
  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>单 SKU 质检</Title>
          <Text type="secondary">信号卡、参数、卖点、评论证据、任务、人群、战场、竞品和证据卡。</Text>
        </div>
        <Input.Search className="sku-search" value={skuCode} onChange={(event) => setSkuCode(event.target.value)} onSearch={setSkuCode} enterButton="打开" />
      </div>
      <SkuDetailPanel project={project} skuCode={skuCode} />
    </section>
  );
}

function SkuDetailPanel({ project, skuCode, compact = false }: { project: Project; skuCode: string; compact?: boolean }) {
  const [detail, setDetail] = useState<Row>();
  const [loading, setLoading] = useState(false);
  const load = async () => {
    if (!skuCode) return;
    setLoading(true);
    try {
      setDetail(await api.workbenchSkuDetail(project.project_id, skuCode));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取单 SKU 详情失败");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, [project.project_id, skuCode]);
  if (!detail) {
    return <Card size="small" loading={loading} title={compact ? `SKU ${skuCode}` : undefined} />;
  }
  return (
    <div className={compact ? "detail-panel compact-detail" : "detail-panel"}>
      <Tabs
        items={[
          { key: "signal", label: "信号卡", children: <pre className="json-preview">{JSON.stringify(detail.signal_card, null, 2)}</pre> },
          { key: "params", label: "参数", children: <DataTable rows={arrayRows(detail.normalized_parameters)} loading={loading} /> },
          { key: "claims", label: "卖点", children: <DataTable rows={arrayRows(detail.activated_standard_claims)} loading={loading} /> },
          { key: "comments", label: "评论证据", children: <DataTable rows={arrayRows(detail.comment_topic_evidence)} loading={loading} /> },
          { key: "tasks", label: "任务", children: <DataTable rows={arrayRows(detail.user_task_scores)} loading={loading} /> },
          { key: "groups", label: "人群", children: <DataTable rows={arrayRows(detail.target_group_scores)} loading={loading} /> },
          { key: "battlefields", label: "战场", children: <DataTable rows={arrayRows(detail.battlefield_scores)} loading={loading} /> },
          { key: "layers", label: "价值层", children: <DataTable rows={arrayRows(detail.claim_value_layers)} loading={loading} /> },
          { key: "competitors", label: "竞品", children: <DataTable rows={arrayRows(detail.competitor_relationships)} loading={loading} /> },
          { key: "evidence", label: "证据卡", children: <DataTable rows={arrayRows(detail.evidence_cards)} loading={loading} /> },
          { key: "report", label: "报告预览", children: <pre className="json-preview">{JSON.stringify(detail.report_preview, null, 2)}</pre> }
        ]}
      />
    </div>
  );
}

function CompetitorResultsPage({ project }: { project: Project }) {
  const [skuCode, setSkuCode] = useState("");
  const [data, setData] = useState<WorkbenchCollectionResponse>();
  const [loading, setLoading] = useState(false);
  const load = async (nextSku = skuCode) => {
    setLoading(true);
    try {
      setData(await api.workbenchCompetitors(project.project_id, nextSku || undefined));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取竞品结果失败");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load("");
  }, [project.project_id]);
  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>竞品证据</Title>
          <Text type="secondary">按战场查看直接、替代、标杆和潜在竞品及组件分。</Text>
        </div>
        <Input.Search className="sku-search" placeholder="SKU 可选" value={skuCode} onChange={(event) => setSkuCode(event.target.value)} onSearch={load} enterButton="筛选" />
      </div>
      <DataTable
        rows={data?.items ?? []}
        loading={loading}
        leadingKeys={["target_sku_code", "competitor_sku_code", "battlefield_code", "competitor_type", "rank", "score", "component_scores", "evidence_ids", "confidence", "review_status"]}
      />
    </section>
  );
}

function CalibrationReportPage({ project }: { project: Project }) {
  const [report, setReport] = useState<Row>();
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true);
    try {
      setReport(await api.workbenchCalibration(project.project_id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取校准报告失败");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, [project.project_id]);
  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>市场校准</Title>
          <Text type="secondary">参数覆盖、卖点覆盖、PSI、SSI、CPI、样本充分性和复核汇总。</Text>
        </div>
        <Button icon={<FileSearchOutlined />} loading={loading} onClick={load}>
          刷新
        </Button>
      </div>
      {report ? (
        <>
          <div className="metric-grid">
            <MetricCard title="参数覆盖项" value={arrayRows(report.parameter_coverage).length} />
            <MetricCard title="卖点指标项" value={arrayRows(report.claim_coverage).length} />
            <MetricCard title="评论主题项" value={arrayRows(report.comment_topic_coverage).length} />
            <MetricCard title="发布建议" value={String(report.release_recommendation ?? "unknown")} />
          </div>
          <Tabs
            items={[
              { key: "params", label: "参数覆盖", children: <DataTable rows={arrayRows(report.parameter_coverage)} /> },
              { key: "claims", label: "卖点校准", children: <DataTable rows={arrayRows(report.claim_coverage)} /> },
              { key: "topics", label: "评论覆盖", children: <DataTable rows={arrayRows(report.comment_topic_coverage)} /> },
              { key: "review", label: "复核汇总", children: <pre className="json-preview">{JSON.stringify(report.expert_review_summary, null, 2)}</pre> },
              { key: "metrics", label: "评估指标", children: <pre className="json-preview">{JSON.stringify(report.evaluation_metrics, null, 2)}</pre> }
            ]}
          />
        </>
      ) : (
        <Empty description="暂无校准报告" />
      )}
    </section>
  );
}

function ExportPreviewPage({ project }: { project: Project }) {
  const [preview, setPreview] = useState<WorkbenchExportPreview>();
  const [exported, setExported] = useState<RuntimeExportResponse>();
  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [exporting, setExporting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setPreview(await api.workbenchExportPreview(project.project_id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取导出预览失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [project.project_id]);

  const publishCandidate = async () => {
    setPublishing(true);
    try {
      const version = `tv_goal3_${Date.now()}`;
      const created = await api.createAssetVersion({
        project_id: project.project_id,
        asset_type: "runtime_asset",
        category_code: project.category_code,
        version,
        created_by: "factory-web",
        manifest_json: {
          quality_gates: { workbench_reviewed: true, export_boundary_checked: true },
          files: preview?.file_list ?? [],
          approved_deliverables: preview?.approved_deliverables ?? []
        }
      });
      const assetId = String(created.asset_version_id);
      await api.submitAssetReview(assetId);
      await api.approveAssetVersion(assetId);
      await api.releaseAssetVersion(assetId);
      await load();
      message.success("内部候选版本已发布");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "发布候选失败");
    } finally {
      setPublishing(false);
    }
  };

  const exportRuntime = async () => {
    setExporting(true);
    try {
      const assetId = preview?.released_asset_version?.asset_version_id;
      const result = await api.exportReleasedRuntime(project.project_id, typeof assetId === "string" ? assetId : undefined);
      setExported(result);
      message.success("运行态资产包已生成");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "运行态导出失败");
    } finally {
      setExporting(false);
    }
  };

  const gate = preview?.release_gate ?? {};
  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>运行态导出预览</Title>
          <Text type="secondary">仅预览和导出已批准运行态交付物。</Text>
        </div>
        <Space wrap>
          <Button icon={<SafetyCertificateOutlined />} loading={publishing} onClick={publishCandidate}>
            发布内部候选
          </Button>
          <Button type="primary" icon={<ExportOutlined />} loading={exporting} disabled={!gate.export_allowed} onClick={exportRuntime}>
            导出运行态
          </Button>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>
            刷新
          </Button>
        </Space>
      </div>
      {preview && (
        <>
          <Alert
            className="export-alert"
            type={gate.export_allowed ? "success" : "warning"}
            showIcon
            message={gate.export_allowed ? "发布门禁已开放" : "发布门禁未开放"}
            description={String(gate.internal_boundary ?? "")}
          />
          <div className="metric-grid">
            <MetricCard title="白名单文件" value={preview.file_list.length} />
            <MetricCard title="批准交付物" value={preview.approved_deliverables.length} />
            <MetricCard title="资产版本" value={String(preview.released_asset_version?.version ?? "unreleased")} />
          </div>
          <Tabs
            items={[
              { key: "files", label: "文件清单", children: <DataTable rows={preview.file_list} /> },
              { key: "deliverables", label: "交付物", children: <DataTable rows={preview.approved_deliverables.map((item) => ({ deliverable: item }))} /> },
              { key: "versions", label: "版本", children: <DataTable rows={preview.asset_versions} /> },
              { key: "manifest", label: "Manifest", children: <pre className="json-preview">{JSON.stringify(preview.export_manifest_preview, null, 2)}</pre> },
              { key: "blocked", label: "禁止内容", children: <DataTable rows={arrayRows(preview.factory_exclusions).map((item) => ({ blocked: item.value ?? item }))} /> }
            ]}
          />
        </>
      )}
      {exported && (
        <Alert
          className="export-alert"
          type="success"
          showIcon
          message="导出完成"
          description={`导出 ID：${exported.export_id}；文件：${exported.file_path}`}
        />
      )}
    </section>
  );
}

function DataTable({
  rows,
  loading = false,
  leadingKeys,
  extraColumns = []
}: {
  rows: Row[];
  loading?: boolean;
  leadingKeys?: string[];
  extraColumns?: Columns;
}) {
  const columns = useMemo(() => buildColumns(rows, leadingKeys, extraColumns), [rows, leadingKeys, extraColumns]);
  return (
    <Table<Row>
      size="small"
      rowKey={(row, index) => String(row.id ?? row.object_code ?? row.sku_code ?? row.evidence_id ?? row.review_id ?? row.export_id ?? index)}
      loading={loading}
      dataSource={rows}
      columns={columns}
      scroll={{ x: true }}
      pagination={{ pageSize: 10 }}
      locale={{ emptyText: <Empty description="暂无记录" /> }}
    />
  );
}

function buildColumns(rows: Row[], leadingKeys?: string[], extraColumns: Columns = []): Columns {
  const keys = rows[0] ? Object.keys(rows[0]).filter((key) => !["created_at", "updated_at"].includes(key)) : [];
  const ordered = [...(leadingKeys ?? []), ...keys].filter((key, index, array) => keys.includes(key) && array.indexOf(key) === index);
  return [
    ...ordered.slice(0, 14).map((key) => ({
      title: columnTitle(key),
      dataIndex: key,
      key,
      width: columnWidth(key),
      render: (value: unknown) => renderWorkbenchCell(value)
    })),
    ...extraColumns
  ];
}

function MetricCard({ title, value }: { title: string; value: string | number }) {
  return (
    <Card size="small">
      <Statistic title={title} value={value} valueStyle={{ fontSize: typeof value === "string" && value.length > 14 ? 16 : 22 }} />
    </Card>
  );
}

function renderWorkbenchCell(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return <Text type="secondary">unknown</Text>;
  }
  if (typeof value === "boolean") {
    return <Tag color={value ? "green" : "default"}>{value ? "true" : "false"}</Tag>;
  }
  if (typeof value === "number") {
    return <Text>{Number.isInteger(value) ? value : value.toFixed(4)}</Text>;
  }
  if (Array.isArray(value)) {
    return (
      <Space wrap size={[4, 4]}>
        {value.slice(0, 6).map((item, index) => (
          <Tag key={`${String(item)}-${index}`}>{String(item)}</Tag>
        ))}
        {value.length > 6 && <Tag>+{value.length - 6}</Tag>}
      </Space>
    );
  }
  if (typeof value === "object") {
    return <Text className="mono-cell">{JSON.stringify(value)}</Text>;
  }
  const text = String(value);
  if (["approved", "auto_pass", "completed", "released"].includes(text)) {
    return <Tag color="green">{text}</Tag>;
  }
  if (["rejected", "failed", "deprecated"].includes(text)) {
    return <Tag color="red">{text}</Tag>;
  }
  if (["pending", "needs_review", "needs_split", "needs_merge", "draft"].includes(text)) {
    return <Tag color="gold">{text}</Tag>;
  }
  return <Text>{text}</Text>;
}

function columnTitle(key: string) {
  const titles: Record<string, string> = {
    source_basis: "来源依据",
    raw_fields_or_text_examples: "原始样例",
    derived_features: "派生特征",
    mapping_lineage: "映射血缘",
    evidence_ids: "证据 ID",
    confidence: "置信度",
    review_status: "复核状态",
    asset_version: "资产版本",
    rule_version: "规则版本",
    last_reviewer: "最近复核人",
    review_timestamp: "复核时间"
  };
  return titles[key] ?? key;
}

function columnWidth(key: string) {
  if (key.includes("raw") || key.includes("derived") || key.includes("lineage") || key.includes("evidence")) return 260;
  if (key.includes("version") || key.includes("status") || key.includes("confidence")) return 130;
  if (key.includes("code") || key.includes("id")) return 190;
  return 160;
}

function arrayRows(value: unknown): Row[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item, index) => (typeof item === "object" && item !== null ? (item as Row) : { index, value: item }));
}

function nested(row: Row, path: string[]) {
  return path.reduce<unknown>((current, key) => (typeof current === "object" && current !== null ? (current as Row)[key] : undefined), row);
}

function numberValue(value: unknown) {
  return typeof value === "number" ? value : Number(value ?? 0);
}
