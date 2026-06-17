import { SearchOutlined } from "@ant-design/icons";
import { Button, Card, Empty, Input, Space, Tag, Typography, message } from "antd";
import { ReactNode, useState } from "react";
import { api } from "../../api/client";
import type { Core3V2EvidenceCard, Core3V2EvidenceTraceResponse, Project } from "../../types";
import { EvidenceTraceDrawer } from "./components/EvidenceTraceDrawer";
import { core3RealDataDefaultQuery } from "./core3RealDataFormat";

const { Title, Paragraph, Text } = Typography;

export function Core3RealDataEvidence({ project, icon }: { project: Project; icon?: ReactNode }) {
  const [query, setQuery] = useState(core3RealDataDefaultQuery);
  const [cards, setCards] = useState<Core3V2EvidenceCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [traceLoading, setTraceLoading] = useState(false);
  const [trace, setTrace] = useState<Core3V2EvidenceTraceResponse>();

  const load = async () => {
    setLoading(true);
    try {
      setCards(await api.core3V2EvidenceCards(project.project_id, query.trim()));
    } catch (error) {
      setCards([]);
      message.error(error instanceof Error ? error.message : "读取证据卡失败");
    } finally {
      setLoading(false);
    }
  };

  const openTrace = async (shortRef: string) => {
    setTraceOpen(true);
    setTrace(undefined);
    setTraceLoading(true);
    try {
      setTrace(await api.core3V2EvidenceTrace(project.project_id, query.trim(), shortRef));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取证据追溯失败");
    } finally {
      setTraceLoading(false);
    }
  };

  return (
    <div className="core3-real-data-stack">
      <div className="core3-real-data-section-head">
        <div>
          <Title level={3}>
            {icon} 证据卡和追溯
          </Title>
          <Text type="secondary">业务页只看短证据编号，展开后供内部核查来源。</Text>
        </div>
        <Space.Compact className="core3-real-data-search">
          <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入型号或商品编码" onPressEnter={load} />
          <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={load}>
            查看证据
          </Button>
        </Space.Compact>
      </div>
      <div className="core3-real-data-evidence-grid">
        {cards.map((card) => (
          <Card key={`${card.competitor_sku_code}:${card.role_code}`} title={card.headline_cn} className="core3-real-data-panel">
            <Tag color="blue">{card.role_name_cn}</Tag>
            <Tag>{card.confidence_label_cn}</Tag>
            <Paragraph className="core3-real-data-card-summary">{card.summary_cn}</Paragraph>
            <Paragraph>{card.one_sentence_reason_cn}</Paragraph>
            <div className="core3-real-data-ref-list">
              {card.evidence_short_refs.map((ref) => (
                <button key={ref.short_ref} type="button" className="core3-real-data-ref-button" onClick={() => openTrace(ref.short_ref)}>
                  {ref.short_ref}
                </button>
              ))}
            </div>
          </Card>
        ))}
      </div>
      {cards.length === 0 && (
        <Card>
          <Empty description="暂无证据卡，请输入已生成报告的目标型号" />
        </Card>
      )}
      <EvidenceTraceDrawer open={traceOpen} loading={traceLoading} trace={trace} onClose={() => setTraceOpen(false)} />
    </div>
  );
}

