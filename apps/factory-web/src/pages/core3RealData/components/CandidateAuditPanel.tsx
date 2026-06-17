import { Card, Descriptions, Empty } from "antd";
import type { Core3RealDataBusinessPair } from "../core3RealDataFormat";

export function CandidateAuditPanel({ items }: { items: Core3RealDataBusinessPair[] }) {
  return (
    <Card title="候选池收敛说明" className="core3-real-data-panel">
      {items.length > 0 ? (
        <Descriptions size="small" column={1}>
          {items.map((item) => (
            <Descriptions.Item key={item.label} label={item.label}>
              {item.value}
            </Descriptions.Item>
          ))}
        </Descriptions>
      ) : (
        <Empty description="当前报告未返回候选池摘要" />
      )}
    </Card>
  );
}

