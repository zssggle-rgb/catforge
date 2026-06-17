import { Card, Empty, Table } from "antd";
import type { TableProps } from "antd";
import type { Core3V2CoreCompetitor } from "../../../types";
import type { Core3RealDataEvidenceRow } from "../core3RealDataFormat";

type EvidenceRecord = {
  key: string;
  competitor: string;
  label: string;
  value: string;
};

export function EvidenceMatrix({
  competitors,
  evidenceRowsByCompetitor
}: {
  competitors: Core3V2CoreCompetitor[];
  evidenceRowsByCompetitor: Record<string, Core3RealDataEvidenceRow[]>;
}) {
  const rows: EvidenceRecord[] = competitors.flatMap((competitor) =>
    (evidenceRowsByCompetitor[competitor.competitor_sku_code] ?? []).map((row) => ({
      key: `${competitor.competitor_sku_code}:${row.key}`,
      competitor: competitor.competitor_display_name_cn,
      label: row.label,
      value: row.value
    }))
  );
  const columns: NonNullable<TableProps<EvidenceRecord>["columns"]> = [
    { title: "竞品", dataIndex: "competitor", width: 220 },
    { title: "证据类型", dataIndex: "label", width: 150 },
    { title: "业务证据", dataIndex: "value" }
  ];
  return (
    <Card title="证据矩阵" className="core3-real-data-panel">
      {rows.length > 0 ? (
        <Table size="small" rowKey="key" dataSource={rows} columns={columns} pagination={false} />
      ) : (
        <Empty description="当前报告暂未返回可展示证据" />
      )}
    </Card>
  );
}

