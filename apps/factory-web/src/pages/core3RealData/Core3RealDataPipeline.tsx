import { ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Empty, Space, Table, Tag, Typography, message } from "antd";
import type { TableProps } from "antd";
import { ReactNode, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Core3V2ListResponse, Core3V2PipelineRunListResponse, Core3V2PipelineRunResponse, Project } from "../../types";
import { PipelineRunTimeline } from "./components/PipelineRunTimeline";
import { formatCore3V2Date, pipelineStatusLabel, safeBusinessText } from "./core3RealDataFormat";

const { Title, Text } = Typography;
type Row = Record<string, unknown>;

export function Core3RealDataPipeline({ project, icon }: { project: Project; icon?: ReactNode }) {
  const [runs, setRuns] = useState<Core3V2PipelineRunListResponse>();
  const [latest, setLatest] = useState<Core3V2PipelineRunResponse>();
  const [modules, setModules] = useState<Row[]>([]);
  const [reviews, setReviews] = useState<Row[]>([]);
  const [gates, setGates] = useState<Row[]>([]);
  const [acceptance, setAcceptance] = useState<Row>();
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const runList = await api.core3V2PipelineRuns(project.project_id);
      setRuns(runList);
      let latestRun: Core3V2PipelineRunResponse | undefined;
      try {
        latestRun = await api.core3V2PipelineRunLatest(project.project_id);
        setLatest(latestRun);
      } catch {
        latestRun = runList.items[0] as Core3V2PipelineRunResponse | undefined;
        setLatest(latestRun);
      }
      if (latestRun?.run_id) {
        const [moduleRows, reviewRows, gateRows, acceptancePayload] = await Promise.all([
          api.core3V2PipelineModules(project.project_id, latestRun.run_id),
          api.core3V2PipelineReviews(project.project_id, latestRun.run_id),
          api.core3V2PipelineReleaseGates(project.project_id, latestRun.run_id),
          api.core3V2PipelineAcceptance(project.project_id, latestRun.run_id).catch(() => undefined)
        ]);
        setModules(listItems(moduleRows));
        setReviews(listItems(reviewRows));
        setGates(listItems(gateRows));
        setAcceptance(acceptancePayload);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取生产线状态失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [project.project_id]);

  return (
    <div className="core3-real-data-stack">
      <div className="core3-real-data-section-head">
        <div>
          <Title level={3}>
            {icon} 生产线状态
          </Title>
          <Text type="secondary">给运营人员确认数据是否跑通、是否需要复核、是否可进入业务展示。</Text>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>
          刷新
        </Button>
      </div>
      {latest ? (
        <>
          <Card className="core3-real-data-panel" title="最近一次生产线运行">
            <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }}>
              <Descriptions.Item label="运行状态">
                <Tag>{pipelineStatusLabel(latest.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="发布状态">{safeBusinessText(latest.release_status)}</Descriptions.Item>
              <Descriptions.Item label="数据批次">{latest.data_batch_id ?? "待确认"}</Descriptions.Item>
              <Descriptions.Item label="说明">{latest.summary_cn ?? "已记录运行结果"}</Descriptions.Item>
            </Descriptions>
          </Card>
          <PipelineRunTimeline modules={modules} />
          <div className="core3-real-data-two-columns">
            <Card title="复核项" className="core3-real-data-panel">
              <SimpleRows rows={reviews} empty="暂无复核项" />
            </Card>
            <Card title="发布门禁" className="core3-real-data-panel">
              <SimpleRows rows={gates} empty="暂无发布门禁" />
            </Card>
          </div>
          <Card title="验收摘要" className="core3-real-data-panel">
            {acceptance ? (
              <Descriptions size="small" column={1}>
                {Object.entries(acceptance).slice(0, 8).map(([key, value]) => (
                  <Descriptions.Item key={key} label={safeBusinessText(key)}>
                    {safeBusinessText(value)}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无验收摘要" />
            )}
          </Card>
        </>
      ) : (
        <Card>
          <Alert type="warning" showIcon title={runs?.summary_cn ?? "当前项目尚未生成生产线运行记录"} />
        </Card>
      )}
    </div>
  );
}

function listItems(response: Core3V2ListResponse | undefined): Row[] {
  return (response?.items ?? []) as Row[];
}

function SimpleRows({ rows, empty }: { rows: Row[]; empty: string }) {
  if (rows.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty} />;
  }
  const columns: NonNullable<TableProps<Row>["columns"]> = [
    {
      title: "对象",
      render: (_value, row) => safeBusinessText(row.target_sku_code ?? row.review_id ?? row.release_gate_id ?? row.module_code ?? "全部")
    },
    {
      title: "状态",
      render: (_value, row) => <Tag>{pipelineStatusLabel(row.review_status ?? row.gate_status ?? row.status)}</Tag>
    },
    {
      title: "说明",
      render: (_value, row) => safeBusinessText(row.message_cn ?? row.gate_reason_cn ?? row.issue_summary_cn ?? row.summary_cn ?? row.reason_cn)
    },
    {
      title: "时间",
      width: 170,
      render: (_value, row) => formatCore3V2Date(String(row.updated_at ?? row.created_at ?? ""))
    }
  ];
  return <Table size="small" rowKey={(row) => String(row.review_id ?? row.release_gate_id ?? row.target_sku_code)} dataSource={rows} columns={columns} pagination={false} />;
}
