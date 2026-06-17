import { BarChartOutlined, BranchesOutlined, FileSearchOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Empty, Select, Space, Spin, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../../api/client";
import type { Project } from "../../types";
import { Core3Mvp } from "./Core3Mvp";
import { businessText } from "./core3Format";
import { core3Pages, type Core3PageKey } from "./core3Pages";

const { Text, Title } = Typography;

const pageIcons: Record<Core3PageKey, ReactNode> = {
  "core3-overview": <BarChartOutlined />,
  "core3-report": <FileSearchOutlined />,
  "core3-evidence": <BranchesOutlined />
};

export function Core3StandaloneApp() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [pageKey, setPageKey] = useState<Core3PageKey>("core3-report");
  const [loadingProjects, setLoadingProjects] = useState(false);

  const selectedProject = useMemo(
    () => projects.find((project) => project.project_id === selectedProjectId),
    [projects, selectedProjectId]
  );

  const refreshProjects = async () => {
    setLoadingProjects(true);
    try {
      const next = await api.listProjects();
      setProjects(next);
      setSelectedProjectId((current) => current ?? next[0]?.project_id);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取数据批次失败");
    } finally {
      setLoadingProjects(false);
    }
  };

  useEffect(() => {
    refreshProjects();
  }, []);

  return (
    <main className="core3-standalone-shell">
      <header className="core3-standalone-header">
        <div className="core3-standalone-title">
          <div className="core3-standalone-mark">竞</div>
          <div>
            <Title level={1}>海信彩电三竞品研判</Title>
            <Text>围绕核心型号，快速看清正面对打、价格挤压和高端标杆三类竞争关系。</Text>
          </div>
        </div>
        <Space className="core3-standalone-controls" wrap>
          <div className="core3-project-picker">
            <Text type="secondary">数据批次</Text>
            <Select
              value={selectedProjectId}
              loading={loadingProjects}
              placeholder="选择彩电数据批次"
              options={projects.map((project) => ({
                value: project.project_id,
                label: businessText(project.name)
              }))}
              onChange={setSelectedProjectId}
            />
          </div>
          <Button icon={<ReloadOutlined />} loading={loadingProjects} onClick={refreshProjects}>
            刷新批次
          </Button>
        </Space>
      </header>

      <nav className="core3-standalone-nav" aria-label="三竞品页面导航">
        {core3Pages.map((page) => (
          <button
            key={page.key}
            type="button"
            className={`core3-nav-button${pageKey === page.key ? " is-active" : ""}`}
            onClick={() => setPageKey(page.key)}
          >
            <span className="core3-nav-icon">{pageIcons[page.key]}</span>
            <span>{page.label}</span>
          </button>
        ))}
      </nav>

      <section className="core3-standalone-content">
        {loadingProjects && !selectedProject ? (
          <Spin />
        ) : selectedProject ? (
          <>
            <Alert
              className="core3-business-alert"
              type="info"
              showIcon
              title={`当前数据批次：${businessText(selectedProject.name)}`}
              description="用于查看核心竞品结论、相对优势、关键证据和需复核风险。"
            />
            <Core3Mvp project={selectedProject} pageKey={pageKey} />
          </>
        ) : (
          <Empty
            className="core3-empty"
            description="暂无可查看的数据批次，请先导入彩电商品数据并运行三竞品生成。"
          />
        )}
      </section>
    </main>
  );
}
