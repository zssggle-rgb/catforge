import { CheckCircleOutlined, ExclamationCircleOutlined } from "@ant-design/icons";
import { Card, Empty, Space, Tag, Typography } from "antd";
import type { Core3V2CoreCompetitor } from "../../../types";
import type { Core3RealDataCompetitorSlot } from "../core3RealDataFormat";

const { Paragraph, Text } = Typography;

export function CoreCompetitorCards({
  slots,
  onTrace
}: {
  slots: Core3RealDataCompetitorSlot[];
  onTrace?: (competitor: Core3V2CoreCompetitor, shortRef: string) => void;
}) {
  return (
    <div className="core3-real-data-competitor-grid">
      {slots.map((slot) => (
        <Card key={slot.role_code} className={`core3-real-data-role-card is-${slot.role_code}`} title={slot.role_name_cn}>
          {slot.competitor ? (
            <CompetitorSummary competitor={slot.competitor} onTrace={onTrace} />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={slot.missing_reason_cn} />
          )}
        </Card>
      ))}
    </div>
  );
}

function CompetitorSummary({
  competitor,
  onTrace
}: {
  competitor: Core3V2CoreCompetitor;
  onTrace?: (competitor: Core3V2CoreCompetitor, shortRef: string) => void;
}) {
  return (
    <div className="core3-real-data-competitor">
      <div className="core3-real-data-competitor-title">{competitor.competitor_display_name_cn}</div>
      <Paragraph className="core3-real-data-competitor-reason">{competitor.one_sentence_reason_cn}</Paragraph>
      <div className="core3-real-data-competitor-points">
        <Point label="价值战场" value={competitor.battlefield_fit_cn} />
        <Point label="市场压力" value={competitor.market_pressure_cn} />
        <Point label="关键差异" value={competitor.key_difference_cn} />
        <Point label="策略含义" value={competitor.strategy_implication_cn} />
      </div>
      <Space wrap className="core3-real-data-ref-list">
        <Tag color="green" icon={<CheckCircleOutlined />}>
          {competitor.confidence_label_cn}
        </Tag>
        {competitor.risk_note_cn && (
          <Tag color="red" icon={<ExclamationCircleOutlined />}>
            {competitor.risk_note_cn}
          </Tag>
        )}
        {competitor.evidence_short_refs.map((ref) => (
          <button
            key={ref.short_ref}
            type="button"
            className="core3-real-data-ref-button"
            onClick={() => onTrace?.(competitor, ref.short_ref)}
          >
            {ref.short_ref}
          </button>
        ))}
      </Space>
    </div>
  );
}

function Point({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <Text type="secondary">{label}</Text>
      <div>{value}</div>
    </div>
  );
}

