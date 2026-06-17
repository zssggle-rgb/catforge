import { Descriptions, Drawer, Empty, Spin, Typography } from "antd";
import type { Core3V2EvidenceTraceResponse } from "../../../types";

const { Paragraph, Text } = Typography;

export function EvidenceTraceDrawer({
  open,
  loading,
  trace,
  onClose
}: {
  open: boolean;
  loading: boolean;
  trace?: Core3V2EvidenceTraceResponse;
  onClose: () => void;
}) {
  return (
    <Drawer title="证据追溯" width={520} open={open} onClose={onClose}>
      {loading ? (
        <Spin />
      ) : trace ? (
        <div className="core3-real-data-trace">
          <Paragraph type="secondary">{trace.trace_usage_cn}</Paragraph>
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="短证据编号">{trace.short_ref}</Descriptions.Item>
            <Descriptions.Item label="证据类型">{trace.evidence_domain_cn ?? "待确认"}</Descriptions.Item>
            <Descriptions.Item label="证据标题">{trace.evidence_title_cn ?? "待确认"}</Descriptions.Item>
            <Descriptions.Item label="来源">{trace.source_cn ?? "样例数据"}</Descriptions.Item>
            <Descriptions.Item label="置信度">{trace.confidence ?? "待确认"}</Descriptions.Item>
          </Descriptions>
          {trace.snippet_cn && (
            <div className="core3-real-data-snippet">
              <Text type="secondary">证据片段</Text>
              <Paragraph>{trace.snippet_cn}</Paragraph>
            </div>
          )}
        </div>
      ) : (
        <Empty description="请选择短证据编号" />
      )}
    </Drawer>
  );
}

