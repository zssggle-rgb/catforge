import { CalendarOutlined, DatabaseOutlined } from "@ant-design/icons";
import { Alert, Space, Tag, Typography } from "antd";
import type { Core3V2DataScope } from "../../../types";
import { dataScopeSummary, formatCore3V2Date } from "../core3RealDataFormat";

const { Text } = Typography;

export function DataScopeBar({ scope }: { scope?: Core3V2DataScope | null }) {
  return (
    <div className="core3-real-data-scope">
      <Space wrap size={[8, 8]}>
        <Tag icon={<DatabaseOutlined />} color="blue">
          {scope?.period_cn ?? "数据周期待确认"}
        </Tag>
        <Tag>{scope?.channel_scope_cn ?? "渠道范围待确认"}</Tag>
        <Tag>{scope?.platform_scope_cn ?? "平台范围待确认"}</Tag>
        <Text type="secondary">
          <CalendarOutlined /> {formatCore3V2Date(scope?.updated_at)}
        </Text>
      </Space>
      <Alert type="info" showIcon title={dataScopeSummary(scope)} className="core3-real-data-scope-note" />
    </div>
  );
}
