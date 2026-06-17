import { ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Empty, Space, Statistic, Table, Typography, message } from "antd";
import type { TableProps } from "antd";
import { ReactNode, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Core3V2DataStatusResponse, Core3V2OverviewResponse, Core3V2TargetSummary, Project } from "../../types";
import { DataScopeBar } from "./components/DataScopeBar";
import { ReleaseStatusBadge } from "./components/ReleaseStatusBadge";
import { formatCore3V2Number, releaseStatusName } from "./core3RealDataFormat";

const { Title, Text } = Typography;

export function Core3RealDataOverview({ project, icon }: { project: Project; icon?: ReactNode }) {
  const [status, setStatus] = useState<Core3V2DataStatusResponse>();
  const [overview, setOverview] = useState<Core3V2OverviewResponse>();
  const [targets, setTargets] = useState<Core3V2TargetSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [nextStatus, nextOverview, nextTargets] = await Promise.all([
        api.core3V2DataStatus(project.project_id),
        api.core3V2Overview(project.project_id),
        api.core3V2Targets(project.project_id)
      ]);
      setStatus(nextStatus);
      setOverview(nextOverview);
      setTargets(nextTargets.items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取真实数据总览失败");
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
            {icon} 真实数据总览
          </Title>
          <Text type="secondary">先确认数据范围，再查看当前已生成报告的目标型号。</Text>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>
          刷新
        </Button>
      </div>
      {status?.data_scope && <DataScopeBar scope={status.data_scope} />}
      {status ? (
        <>
          <div className="core3-real-data-metrics">
            <Card>
              <Statistic title="目标型号" value={formatCore3V2Number(status.target_count)} />
            </Card>
            <Card>
              <Statistic title="已生成报告" value={formatCore3V2Number(status.report_count)} />
            </Card>
            <Card>
              <Statistic title="数据批次" value={formatCore3V2Number(status.batch_count)} />
            </Card>
            <Card>
              <Statistic title="可汇报结果" value={formatCore3V2Number(status.release_status_counts.releasable ?? 0)} />
            </Card>
          </div>
          <Alert type={status.has_data ? "success" : "warning"} showIcon title={overview?.summary_cn ?? status.summary_cn} />
          <Card title="目标型号报告列表" className="core3-real-data-panel">
            <Table
              size="small"
              rowKey="target_sku_code"
              loading={loading}
              dataSource={targets}
              columns={targetColumns}
              pagination={{ pageSize: 8 }}
            />
          </Card>
        </>
      ) : (
        <Card>
          <Empty description="暂无真实数据总览" />
        </Card>
      )}
    </div>
  );
}

const targetColumns: NonNullable<TableProps<Core3V2TargetSummary>["columns"]> = [
  { title: "目标型号", dataIndex: "target_display_name_cn", width: 220 },
  { title: "报告名称", dataIndex: "report_title_cn" },
  {
    title: "竞品数量",
    dataIndex: "selected_count",
    width: 110
  },
  {
    title: "核心竞品",
    dataIndex: "competitor_names_cn",
    render: (value: string[]) => value?.join("、") || "待确认"
  },
  {
    title: "汇报状态",
    dataIndex: "release_status",
    width: 120,
    render: (_value, record) => <ReleaseStatusBadge status={record.release_status} />
  },
  {
    title: "状态说明",
    dataIndex: "review_hint_cn",
    render: (value, record) => value || releaseStatusName(record.release_status.status_code)
  }
];
