import { Card, Empty, Table, Tag } from "antd";
import type { TableProps } from "antd";
import { pipelineStatusLabel, safeBusinessText } from "../core3RealDataFormat";

type Row = Record<string, unknown>;

export function PipelineRunTimeline({ modules }: { modules: Row[] }) {
  const columns: NonNullable<TableProps<Row>["columns"]> = [
    { title: "模块", dataIndex: "module_code", width: 120, render: (value) => safeBusinessText(value) },
    { title: "状态", dataIndex: "status", width: 120, render: (value) => <Tag>{pipelineStatusLabel(value)}</Tag> },
    { title: "输入", dataIndex: "input_count", width: 100 },
    { title: "输出", dataIndex: "output_count", width: 100 },
    {
      title: "说明",
      dataIndex: "summary_cn",
      render: (value, row) => safeBusinessText(value ?? row.message_cn ?? row.reason_cn ?? "已记录运行结果")
    }
  ];
  return (
    <Card title="模块运行快照" className="core3-real-data-panel">
      {modules.length > 0 ? (
        <Table size="small" rowKey={(row) => String(row.module_run_id ?? row.module_code)} dataSource={modules} columns={columns} pagination={false} />
      ) : (
        <Empty description="暂无模块运行快照" />
      )}
    </Card>
  );
}

