import { SearchOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Empty, Input, Space, Typography, message } from "antd";
import { ReactNode, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type { Core3V2BusinessReportResponse, Core3V2CoreCompetitor, Core3V2EvidenceTraceResponse, Project } from "../../types";
import { CandidateAuditPanel } from "./components/CandidateAuditPanel";
import { CoreCompetitorCards } from "./components/CoreCompetitorCards";
import { DataScopeBar } from "./components/DataScopeBar";
import { EvidenceMatrix } from "./components/EvidenceMatrix";
import { EvidenceTraceDrawer } from "./components/EvidenceTraceDrawer";
import { ReportExportActions } from "./components/ReportExportActions";
import { ReviewHintPanel } from "./components/ReviewHintPanel";
import { TargetConclusionStrip } from "./components/TargetConclusionStrip";
import { buildReportView, businessPairsFromPayload, core3RealDataDefaultQuery } from "./core3RealDataFormat";

const { Title, Paragraph, Text } = Typography;

export function Core3RealDataReport({ project, icon }: { project: Project; icon?: ReactNode }) {
  const [query, setQuery] = useState(core3RealDataDefaultQuery);
  const [report, setReport] = useState<Core3V2BusinessReportResponse>();
  const [loading, setLoading] = useState(false);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [trace, setTrace] = useState<Core3V2EvidenceTraceResponse>();

  const load = async (nextQuery = query) => {
    setLoading(true);
    try {
      setReport(await api.core3V2Report(project.project_id, nextQuery.trim()));
    } catch (error) {
      setReport(undefined);
      message.error(error instanceof Error ? error.message : "读取核心竞品报告失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(core3RealDataDefaultQuery);
  }, [project.project_id]);

  const view = useMemo(() => (report ? buildReportView(report) : undefined), [report]);

  const traceEvidence = async (competitor: Core3V2CoreCompetitor, shortRef: string) => {
    setTraceOpen(true);
    setTrace(undefined);
    setTraceLoading(true);
    try {
      setTrace(await api.core3V2EvidenceTrace(project.project_id, report?.target.sku_code ?? competitor.competitor_sku_code, shortRef));
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
            {icon} 核心竞品报告
          </Title>
          <Text type="secondary">先看三竞品是谁，再看为什么成立和证据是否充分。</Text>
        </div>
        <Space.Compact className="core3-real-data-search">
          <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入型号或商品编码" onPressEnter={() => load()} />
          <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={() => load()}>
            查看报告
          </Button>
        </Space.Compact>
      </div>
      {report && view ? (
        <>
          <DataScopeBar scope={report.data_scope} />
          <TargetConclusionStrip report={report} />
          <ReviewHintPanel hint={report.review_hint} />
          {!view.canShowReport ? (
            <Card>
              <Empty description={report.release_status.review_hint_cn ?? report.release_status.gate_reason_cn} />
            </Card>
          ) : (
            <>
              <Card className="core3-real-data-panel" title="为什么是这些竞品" extra={<ReportExportActions exports={report.exports} />}>
                <Paragraph>{report.why_these_competitors_cn}</Paragraph>
                <Paragraph>{report.battlefield_summary_cn}</Paragraph>
                <Alert type="info" showIcon title={report.data_quality_note_cn} />
              </Card>
              <CoreCompetitorCards slots={view.roleSlots} onTrace={traceEvidence} />
              <EvidenceMatrix competitors={report.core_competitors} evidenceRowsByCompetitor={view.evidenceRowsByCompetitor} />
              <div className="core3-real-data-two-columns">
                <CandidateAuditPanel items={view.candidateAuditItems} />
                <Card title="推导摘要" className="core3-real-data-panel">
                  {view.visibleSections.length > 0 ? (
                    view.visibleSections.slice(0, 4).map((section) => (
                      <div key={section.section_code} className="core3-real-data-section-summary">
                        <Text strong>{section.section_title_cn}</Text>
                        {businessPairsFromPayload(section.section_payload, 4).map((item) => (
                          <div key={`${section.section_code}:${item.label}`}>
                            <Text type="secondary">{item.label}：</Text>
                            {item.value}
                          </div>
                        ))}
                      </div>
                    ))
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无推导摘要" />
                  )}
                </Card>
              </div>
            </>
          )}
          <EvidenceTraceDrawer open={traceOpen} loading={traceLoading} trace={trace} onClose={() => setTraceOpen(false)} />
        </>
      ) : (
        <Card>
          <Empty description="请输入目标型号或商品编码查看报告" />
        </Card>
      )}
    </div>
  );
}
