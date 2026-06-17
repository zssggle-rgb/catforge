import { Alert, Card, Descriptions, Typography } from "antd";
import type { Core3V2BusinessReportResponse } from "../../../types";
import { ReleaseStatusBadge } from "./ReleaseStatusBadge";

const { Title, Paragraph, Text } = Typography;

export function TargetConclusionStrip({ report }: { report: Core3V2BusinessReportResponse }) {
  return (
    <Card className="core3-real-data-conclusion" bordered={false}>
      <div className="core3-real-data-conclusion-head">
        <div>
          <Text type="secondary">目标型号</Text>
          <Title level={2}>{report.target.display_name_cn}</Title>
        </div>
        <ReleaseStatusBadge status={report.release_status} />
      </div>
      <Paragraph className="core3-real-data-conclusion-text">{report.executive_conclusion_cn}</Paragraph>
      <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }}>
        <Descriptions.Item label="尺寸段">{report.target.size_segment_cn ?? "待确认"}</Descriptions.Item>
        <Descriptions.Item label="价格带">{report.target.price_band_cn ?? "待确认"}</Descriptions.Item>
        <Descriptions.Item label="数据状态">{report.target.data_status_cn}</Descriptions.Item>
        <Descriptions.Item label="汇报状态">{report.release_status.status_name_cn}</Descriptions.Item>
      </Descriptions>
      {report.release_status.gate_reason_cn && (
        <Alert type={report.release_status.can_present ? "warning" : "error"} showIcon title={report.release_status.gate_reason_cn} />
      )}
    </Card>
  );
}
