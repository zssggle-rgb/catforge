import {
  BarChartOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  PartitionOutlined,
  PlayCircleOutlined,
  ProjectOutlined
} from "@ant-design/icons";
import { Alert, Button, Card, Empty, Layout, Select, Space, Tabs, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type { Project } from "../../types";
import { Core3RealDataEvidence } from "./Core3RealDataEvidence";
import { Core3RealDataInitialization } from "./Core3RealDataInitialization";
import { Core3RealDataOverview } from "./Core3RealDataOverview";
import { Core3RealDataPipeline } from "./Core3RealDataPipeline";
import { Core3RealDataReport } from "./Core3RealDataReport";
import {
  core3RealDataPages,
  defaultCore3RealDataPageKey,
  type Core3RealDataPageKey
} from "./core3RealDataPages";

const { Content } = Layout;
const { Title, Text } = Typography;

export function Core3RealDataApp({
  project,
  pageKey,
  embedded = false
}: {
  project?: Project;
  pageKey?: Core3RealDataPageKey;
  embedded?: boolean;
}) {
  const [projects, setProjects] = useState<Project[]>(project ? [project] : []);
  const [selectedProjectId, setSelectedProjectId] = useState<string | undefined>(project?.project_id);
  const [activePage, setActivePage] = useState<Core3RealDataPageKey>(pageKey ?? defaultCore3RealDataPageKey);
  const selectedProject = useMemo(
    () => project ?? projects.find((item) => item.project_id === selectedProjectId),
    [project, projects, selectedProjectId]
  );

  useEffect(() => {
    if (project) {
      setSelectedProjectId(project.project_id);
      return;
    }
    api
      .listProjects()
      .then((items) => {
        setProjects(items);
        if (!selectedProjectId && items[0]) {
          setSelectedProjectId(items[0].project_id);
        }
      })
      .catch((error) => message.error(error instanceof Error ? error.message : "读取项目失败"));
  }, [project?.project_id]);

  useEffect(() => {
    if (pageKey) {
      setActivePage(pageKey);
    }
  }, [pageKey]);

  const page = (
    <section className="core3-real-data-page page-section">
      <div className="core3-real-data-page-head">
        <div>
          <Text type="secondary">CatForge 彩电核心三竞品真实数据 MVP</Text>
          <Title level={2}>核心竞品业务报告</Title>
        </div>
        {!project && (
          <Select
            className="core3-real-data-project-select"
            placeholder="选择项目"
            value={selectedProjectId}
            options={projects.map((item) => ({
              value: item.project_id,
              label: `${item.name} · ${item.category_code}`
            }))}
            onChange={setSelectedProjectId}
          />
        )}
      </div>
      <Alert
        className="core3-real-data-top-note"
        type="info"
        showIcon
        title="页面只展示 M15/M16 已生成的业务结论、证据和门禁状态；不会在前端重新计算竞品。"
      />
      {!embedded && (
        <Tabs
          activeKey={activePage}
          onChange={(key) => setActivePage(key as Core3RealDataPageKey)}
          items={core3RealDataPages.map((item) => ({
            key: item.key,
            label: item.label
          }))}
        />
      )}
      {selectedProject ? (
        <Core3RealDataPage project={selectedProject} pageKey={embedded ? pageKey ?? activePage : activePage} />
      ) : (
        <Card>
          <Empty description="请选择项目后查看真实数据三竞品报告" />
          <Button type="primary" icon={<ProjectOutlined />} onClick={() => api.listProjects().then(setProjects)}>
            刷新项目
          </Button>
        </Card>
      )}
    </section>
  );

  if (embedded) {
    return page;
  }
  return (
    <Layout className="core3-real-data-standalone">
      <Content className="core3-real-data-standalone-content">{page}</Content>
    </Layout>
  );
}

function Core3RealDataPage({ project, pageKey }: { project: Project; pageKey: Core3RealDataPageKey }) {
  if (pageKey === "core3-real-data-initialization") {
    return <Core3RealDataInitialization project={project} icon={<PlayCircleOutlined />} />;
  }
  if (pageKey === "core3-real-data-overview") {
    return <Core3RealDataOverview project={project} icon={<DatabaseOutlined />} />;
  }
  if (pageKey === "core3-real-data-evidence") {
    return <Core3RealDataEvidence project={project} icon={<FileSearchOutlined />} />;
  }
  if (pageKey === "core3-real-data-pipeline") {
    return <Core3RealDataPipeline project={project} icon={<PartitionOutlined />} />;
  }
  return <Core3RealDataReport project={project} icon={<BarChartOutlined />} />;
}
