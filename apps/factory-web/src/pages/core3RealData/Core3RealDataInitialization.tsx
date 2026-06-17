import { PlayCircleOutlined, ReloadOutlined, SyncOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Empty, Space, Switch, Table, Tag, Tooltip, Typography, message } from "antd";
import type { TableProps } from "antd";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Core3PipelineInitializationModuleStatus, Core3PipelineInitializationStatusResponse, Project } from "../../types";
import { formatCore3V2Date, formatCore3V2Number, pipelineStatusLabel, safeBusinessText } from "./core3RealDataFormat";

const { Paragraph, Text, Title } = Typography;

const statusColor: Record<string, string> = {
  completed: "green",
  partial: "gold",
  not_started: "default",
  blocked: "orange",
  failed: "red"
};

export function Core3RealDataInitialization({ project, icon }: { project: Project; icon?: ReactNode }) {
  const [status, setStatus] = useState<Core3PipelineInitializationStatusResponse>();
  const [loading, setLoading] = useState(false);
  const [runningModule, setRunningModule] = useState<string>();
  const [forceRebuild, setForceRebuild] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setStatus(await api.core3V2PipelineInitialization(project.project_id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取初始化状态失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [project.project_id]);

  const runModule = async (module: Core3PipelineInitializationModuleStatus, forceOverride?: boolean) => {
    setRunningModule(module.module_code);
    const shouldForceRebuild = forceOverride ?? forceRebuild;
    try {
      const result = await api.core3V2RunInitializationModule(project.project_id, {
        module_code: module.module_code,
        batch_id: status?.batch_id,
        force_rebuild: shouldForceRebuild,
        triggered_by: shouldForceRebuild ? "factory-web-force-rebuild" : "factory-web"
      });
      message.success(result.message_cn);
      if (result.next_action_cn) {
        message.info(result.next_action_cn);
      }
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "执行失败");
    } finally {
      setRunningModule(undefined);
    }
  };

  const columns: NonNullable<TableProps<Core3PipelineInitializationModuleStatus>["columns"]> = [
    {
      title: "业务环节",
      dataIndex: "stage_name_cn",
      width: 220,
      render: (_value, row) => (
        <div className="core3-initialization-stage">
          <Text strong>{row.stage_name_cn}</Text>
          <Text type="secondary">{row.stage_description_cn}</Text>
        </div>
      )
    },
    {
      title: "状态",
      width: 120,
      render: (_value, row) => <Tag color={statusColor[row.execution_status] ?? "default"}>{row.execution_status_cn}</Tag>
    },
    {
      title: "产物",
      width: 140,
      render: (_value, row) => (
        <Space direction="vertical" size={0}>
          <Text>{formatCore3V2Number(row.current_output_count || row.output_count)} 条可用</Text>
          {row.review_issue_count > 0 && <Text type="warning">{formatCore3V2Number(row.review_issue_count)} 条待复核</Text>}
        </Space>
      )
    },
    {
      title: "覆盖",
      width: 150,
      render: (_value, row) => (
        <Text>
          {formatCore3V2Number(row.processed_target_count)}
          {row.expected_target_count > 0 ? ` / ${formatCore3V2Number(row.expected_target_count)} 个 SKU` : " 个 SKU"}
        </Text>
      )
    },
    {
      title: "最近结果",
      render: (_value, row) => (
        <Space direction="vertical" size={0}>
          <Text>{row.latest_summary_cn ?? "尚未执行"}</Text>
          <Text type="secondary">{formatCore3V2Date(row.latest_finished_at)}</Text>
        </Space>
      )
    },
    {
      title: "操作",
      width: 240,
      fixed: "right",
      render: (_value, row) => {
        const disabled = !row.can_execute && !forceRebuild;
        const running = runningModule === row.module_code;
        const defaultButton = (
          <Button
            type={row.execution_status === "failed" ? "primary" : "default"}
            icon={row.can_skip && !forceRebuild ? <SyncOutlined /> : <PlayCircleOutlined />}
            loading={running}
            disabled={disabled || Boolean(runningModule)}
            onClick={() => runModule(row)}
          >
            {actionLabel(row, forceRebuild)}
          </Button>
        );

        if (row.can_skip && !forceRebuild) {
          const rebuildDisabled = (!row.can_execute && !row.can_skip) || Boolean(runningModule);
          return (
            <Space>
              {defaultButton}
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={running}
                disabled={rebuildDisabled}
                onClick={() => runModule(row, true)}
              >
                {rebuildLabel(row)}
              </Button>
            </Space>
          );
        }
        if (!disabled) {
          return defaultButton;
        }
        return <Tooltip title={row.blocked_reason_cn ?? "请先完成上游环节"}>{defaultButton}</Tooltip>;
      }
    }
  ];

  return (
    <div className="core3-real-data-stack">
      <div className="core3-real-data-section-head">
        <div>
          <Title level={3}>
            {icon} 初始化运行
          </Title>
          <Text type="secondary">按业务环节执行真实数据处理；已形成可用产物的环节默认复用，只处理新增或变化数据。</Text>
        </div>
        <Space wrap>
          <Space>
            <Text>强制重跑</Text>
            <Switch checked={forceRebuild} onChange={setForceRebuild} />
          </Space>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>
            刷新
          </Button>
        </Space>
      </div>

      <Alert
        className="core3-real-data-scope-note"
        type="info"
        showIcon
        title="这里触发的是后台正式处理程序，不是临时脚本。"
        description="默认执行方式会读取已落库的批次与模块结果；已经完成的环节会记录复用，等待上游的环节会阻断，便于看清数据处理进度。"
      />

      {status ? (
        <>
          <div className="core3-real-data-metrics">
            <Card className="core3-real-data-panel">
              <Text type="secondary">数据批次</Text>
              <Paragraph className="core3-initialization-metric">{status.batch_id ?? "尚未读取"}</Paragraph>
              <Text type="secondary">{status.batch_status_cn}</Text>
            </Card>
            <Card className="core3-real-data-panel">
              <Text type="secondary">原始记录</Text>
              <Paragraph className="core3-initialization-metric">{formatCore3V2Number(status.source_row_count)}</Paragraph>
              <Text type="secondary">已进入批次登记</Text>
            </Card>
            <Card className="core3-real-data-panel">
              <Text type="secondary">影响 SKU</Text>
              <Paragraph className="core3-initialization-metric">{formatCore3V2Number(status.impacted_sku_count)}</Paragraph>
              <Text type="secondary">后续环节按这些 SKU 增量处理</Text>
            </Card>
            <Card className="core3-real-data-panel">
              <Text type="secondary">清洗 SKU</Text>
              <Paragraph className="core3-initialization-metric">{formatCore3V2Number(status.clean_sku_count)}</Paragraph>
              <Text type="secondary">{status.summary_cn}</Text>
            </Card>
          </div>

          <Card className="core3-real-data-panel" title="处理环节">
            <Table
              rowKey="module_code"
              loading={loading}
              columns={columns}
              dataSource={status.modules}
              pagination={false}
              scroll={{ x: 1040 }}
              expandable={{
                expandedRowRender: (row) => <InitializationModuleDetail row={row} />,
                rowExpandable: () => true
              }}
            />
          </Card>
        </>
      ) : (
        <Card className="core3-real-data-panel">
          <Empty description="暂无初始化运行状态" />
        </Card>
      )}
    </div>
  );
}

function InitializationModuleDetail({ row }: { row: Core3PipelineInitializationModuleStatus }) {
  const summary = summaryPairs(row.latest_summary_json);
  return (
    <div className="core3-initialization-detail">
      <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }}>
        <Descriptions.Item label="最近运行">{row.latest_run_id ? "已记录" : "未记录"}</Descriptions.Item>
        <Descriptions.Item label="运行结果">{pipelineStatusLabel(row.latest_status)}</Descriptions.Item>
        <Descriptions.Item label="提醒数量">{formatCore3V2Number(row.warning_count)}</Descriptions.Item>
        <Descriptions.Item label="复用判断">{row.can_skip ? row.skip_reason_cn ?? "可复用已有结果" : "需要执行后确认"}</Descriptions.Item>
        <Descriptions.Item label="阻断原因">{row.blocked_reason_cn ?? "无"}</Descriptions.Item>
        <Descriptions.Item label="可用产物">{formatCore3V2Number(row.current_output_count || row.output_count)} 条</Descriptions.Item>
      </Descriptions>
      {summary.length > 0 && (
        <div className="core3-initialization-summary">
          {summary.map((item) => (
            <Tag key={item.label}>
              {item.label}：{item.value}
            </Tag>
          ))}
        </div>
      )}
    </div>
  );
}

function actionLabel(row: Core3PipelineInitializationModuleStatus, forceRebuild: boolean): string {
  if (row.module_code === "M00" && row.execution_status === "completed") {
    return forceRebuild ? "重新读取" : "读取增量";
  }
  if (forceRebuild) {
    return "强制重跑";
  }
  if (row.can_skip) {
    return "复用结果";
  }
  if (row.execution_status === "partial") {
    return "补跑增量";
  }
  if (row.execution_status === "failed") {
    return "重新执行";
  }
  return "执行";
}

function rebuildLabel(row: Core3PipelineInitializationModuleStatus): string {
  if (row.module_code === "M00") {
    return "重新读取";
  }
  return "重新执行";
}

function summaryPairs(summary: Record<string, unknown>): { label: string; value: string }[] {
  const pairs: { label: string; value: string }[] = [];
  appendSummary(pairs, "数据批次", summary.batch_id);
  appendSummary(pairs, "原始表记录", summary.row_counts);
  appendSummary(pairs, "清洗记录", summary.clean_counts);
  appendSummary(pairs, "质量提示", summary.issue_counts);
  appendSummary(pairs, "影响 SKU", summary.impacted_sku_count);
  appendSummary(pairs, "处理 SKU", summary.processed_target_count);
  appendSummary(pairs, "可用产物", summary.current_output_count);
  appendSummary(pairs, "跳过原因", summary.skip_reason_cn);
  return pairs.slice(0, 8);
}

function appendSummary(items: { label: string; value: string }[], label: string, value: unknown): void {
  const text = readableSummaryValue(value);
  if (text && text !== "-") {
    items.push({ label, value: text });
  }
}

function readableSummaryValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "number") {
    return formatCore3V2Number(value);
  }
  if (typeof value === "string") {
    return safeBusinessText(value);
  }
  if (Array.isArray(value)) {
    return value.length > 0 ? `${formatCore3V2Number(value.length)} 项` : "-";
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) {
      return "-";
    }
    return entries
      .slice(0, 4)
      .map(([key, item]) => `${summaryKeyLabel(key)} ${formatSummaryLeaf(item)}`)
      .join("，");
  }
  return safeBusinessText(value);
}

function formatSummaryLeaf(value: unknown): string {
  if (typeof value === "number") {
    return formatCore3V2Number(value);
  }
  if (Array.isArray(value)) {
    return `${formatCore3V2Number(value.length)} 项`;
  }
  if (typeof value === "object" && value !== null) {
    return `${formatCore3V2Number(Object.keys(value).length)} 项`;
  }
  return safeBusinessText(value);
}

function summaryKeyLabel(key: string): string {
  return (
    {
      clean_sku: "商品",
      market: "市场",
      attribute: "参数",
      claim: "卖点",
      comment: "评论",
      quality: "质量",
      price: "价格",
      sales: "销售",
      sku: "商品",
      task: "任务",
      target_group: "客群",
      battlefield: "战场"
    }[key] ?? safeBusinessText(key)
  );
}
