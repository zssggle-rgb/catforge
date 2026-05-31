import {
  AppstoreOutlined,
  BarChartOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  ExportOutlined,
  FileSearchOutlined,
  PlayCircleOutlined,
  ProjectOutlined,
  SafetyCertificateOutlined
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Input,
  Layout,
  Menu,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message
} from "antd";
import type { UploadProps } from "antd";
import { useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import { WorkbenchPage } from "./pages/Workbench";
import { pipelineSteps, sampleFiles } from "./pages/pipelineSteps";
import { isWorkbenchPageKey, workbenchPages, type WorkbenchPageKey } from "./pages/workbenchPages";
import type { AssetResponse, DataQualityResponse, ExportResponse, PipelineResult, Project, ReviewQueueResponse } from "./types";

const { Header, Sider, Content } = Layout;
const { Title, Text } = Typography;

type PageKey = "projects" | "dashboard" | "import" | "quality" | "assets" | "review" | "export" | WorkbenchPageKey;

const menuItems = [
  { key: "projects", icon: <ProjectOutlined />, label: "项目" },
  { key: "dashboard", icon: <AppstoreOutlined />, label: "项目看板" },
  { key: "import", icon: <CloudUploadOutlined />, label: "数据导入" },
  { key: "quality", icon: <FileSearchOutlined />, label: "质量报告" },
  { key: "assets", icon: <DatabaseOutlined />, label: "资产列表" },
  { key: "review", icon: <SafetyCertificateOutlined />, label: "复核队列" },
  { key: "export", icon: <ExportOutlined />, label: "运行态导出" },
  {
    key: "goal3-workbench",
    icon: <BarChartOutlined />,
    label: "Goal3 工作台",
    children: workbenchPages.map((page) => ({
      key: page.key,
      icon: page.group === "library" ? <DatabaseOutlined /> : page.group === "result" ? <BranchesOutlined /> : <FileSearchOutlined />,
      label: page.label
    }))
  }
];

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [page, setPage] = useState<PageKey>("projects");
  const [loading, setLoading] = useState(false);
  const selectedProject = useMemo(
    () => projects.find((project) => project.project_id === selectedProjectId),
    [projects, selectedProjectId]
  );

  const refreshProjects = async () => {
    const next = await api.listProjects();
    setProjects(next);
    if (!selectedProjectId && next[0]) {
      setSelectedProjectId(next[0].project_id);
    }
  };

  useEffect(() => {
    refreshProjects().catch((error) => message.error(error.message));
  }, []);

  const guardedPage = selectedProject ? page : "projects";

  return (
    <Layout className="app-shell">
      <Sider width={232} className="app-sider">
        <div className="brand-block">
          <div className="brand-mark">品</div>
          <div>
            <div className="brand-title">CatForge 品铸</div>
            <div className="brand-subtitle">品类资产生产工作台</div>
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[guardedPage]}
          defaultOpenKeys={["goal3-workbench"]}
          items={menuItems}
          onClick={({ key }) => setPage(key as PageKey)}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <Space className="header-content" align="center">
            <div>
              <Text type="secondary">当前项目</Text>
              <div className="project-name">{selectedProject?.name ?? "未选择项目"}</div>
            </div>
            <Select
              className="project-select"
              placeholder="选择项目"
              value={selectedProjectId}
              options={projects.map((project) => ({
                value: project.project_id,
                label: `${project.name} · ${project.category_code}`
              }))}
              onChange={setSelectedProjectId}
            />
          </Space>
        </Header>
        <div className="mobile-nav">
          <Menu
            mode="horizontal"
            selectedKeys={[guardedPage]}
            items={menuItems}
            onClick={({ key }) => setPage(key as PageKey)}
          />
        </div>
        <Content className="app-content">
          {guardedPage === "projects" && (
            <ProjectsPage
              projects={projects}
              selectedProjectId={selectedProjectId}
              loading={loading}
              onSelect={setSelectedProjectId}
              onCreate={async (payload) => {
                setLoading(true);
                try {
                  const created = await api.createProject(payload);
                  await refreshProjects();
                  setSelectedProjectId(created.project_id);
                  setPage("dashboard");
                  message.success("项目已创建");
                } finally {
                  setLoading(false);
                }
              }}
            />
          )}
          {guardedPage === "dashboard" && selectedProject && <DashboardPage project={selectedProject} />}
          {guardedPage === "import" && selectedProject && <DataImportPage project={selectedProject} />}
          {guardedPage === "quality" && selectedProject && <DataQualityPage project={selectedProject} />}
          {guardedPage === "assets" && selectedProject && <AssetsPage project={selectedProject} />}
          {guardedPage === "review" && selectedProject && <ReviewQueuePage project={selectedProject} />}
          {guardedPage === "export" && selectedProject && <RuntimeExportPage project={selectedProject} />}
          {selectedProject && isWorkbenchPageKey(guardedPage) && <WorkbenchPage project={selectedProject} pageKey={guardedPage} />}
        </Content>
      </Layout>
    </Layout>
  );
}

function ProjectsPage({
  projects,
  selectedProjectId,
  loading,
  onSelect,
  onCreate
}: {
  projects: Project[];
  selectedProjectId?: string;
  loading: boolean;
  onSelect: (projectId: string) => void;
  onCreate: (payload: { name: string; category_code: string; description?: string }) => Promise<void>;
}) {
  const [form] = Form.useForm();
  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>项目管理</Title>
          <Text type="secondary">创建和选择彩电品类资产生产项目。</Text>
        </div>
      </div>
      <div className="two-column-grid">
        <Card title="创建项目" size="small">
          <Form
            form={form}
            layout="vertical"
            initialValues={{ category_code: "TV" }}
            onFinish={async (values) => {
              await onCreate(values);
              form.resetFields();
            }}
          >
            <Form.Item label="项目名称" name="name" rules={[{ required: true, message: "请输入项目名称" }]}>
              <Input placeholder="例如：彩电 2026W21 样例项目" />
            </Form.Item>
            <Form.Item label="品类代码" name="category_code">
              <Select options={[{ value: "TV", label: "TV · 彩电" }]} />
            </Form.Item>
            <Form.Item label="说明" name="description">
              <Input.TextArea rows={3} placeholder="记录数据批次、渠道范围或验收口径" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              创建项目
            </Button>
          </Form>
        </Card>
        <Card title="项目列表" size="small">
          <Table
            size="small"
            rowKey="project_id"
            dataSource={projects}
            pagination={false}
            locale={{ emptyText: <Empty description="暂无项目" /> }}
            rowClassName={(record) => (record.project_id === selectedProjectId ? "selected-row" : "")}
            columns={[
              { title: "项目", dataIndex: "name" },
              { title: "品类", dataIndex: "category_code", width: 90 },
              { title: "版本", dataIndex: "version", width: 100 },
              {
                title: "操作",
                width: 96,
                render: (_, record: Project) => (
                  <Button size="small" onClick={() => onSelect(record.project_id)}>
                    选择
                  </Button>
                )
              }
            ]}
          />
        </Card>
      </div>
    </section>
  );
}

function DashboardPage({ project }: { project: Project }) {
  const [results, setResults] = useState<PipelineResult[]>([]);
  const [running, setRunning] = useState<string>();

  const runStep = async (step: string) => {
    setRunning(step);
    try {
      const result = await api.runStep(project.project_id, step);
      setResults((prev) => [result, ...prev.filter((item) => item.step !== step)]);
      message.success(result.message);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "流水线执行失败");
    } finally {
      setRunning(undefined);
    }
  };

  const runAll = async () => {
    for (const step of pipelineSteps) {
      await runStep(step.key);
    }
  };

  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>项目看板</Title>
          <Text type="secondary">按确定性规则执行 CatForge MVP 资产生产流水线。</Text>
        </div>
        <Button type="primary" icon={<PlayCircleOutlined />} onClick={runAll} disabled={Boolean(running)}>
          顺序执行全部
        </Button>
      </div>
      <Descriptions bordered size="small" column={3} className="detail-strip">
        <Descriptions.Item label="项目">{project.name}</Descriptions.Item>
        <Descriptions.Item label="品类">{project.category_code}</Descriptions.Item>
        <Descriptions.Item label="版本">{project.version}</Descriptions.Item>
      </Descriptions>
      <div className="step-grid">
        {pipelineSteps.map((step) => {
          const result = results.find((item) => item.step === step.key);
          return (
            <Card key={step.key} size="small" title={step.label}>
              <Text type="secondary">{step.description}</Text>
              <div className="card-footer">
                <Button
                  icon={<PlayCircleOutlined />}
                  loading={running === step.key}
                  onClick={() => runStep(step.key)}
                >
                  执行
                </Button>
                {result && <Tag color="green">已完成</Tag>}
              </div>
              {result && <pre className="json-preview">{JSON.stringify(result.counts, null, 2)}</pre>}
            </Card>
          );
        })}
      </div>
    </section>
  );
}

function DataImportPage({ project }: { project: Project }) {
  const [fileType, setFileType] = useState("sku_master");
  const [importing, setImporting] = useState(false);
  const uploadProps: UploadProps = {
    showUploadList: false,
    beforeUpload: async (file) => {
      setImporting(true);
      try {
        const uploaded = await api.uploadFile(project.project_id, file, fileType);
        await api.importFile(project.project_id, { source_file_id: uploaded.source_file_id });
        message.success(`${uploaded.file_name} 已导入`);
      } catch (error) {
        message.error(error instanceof Error ? error.message : "导入失败");
      } finally {
        setImporting(false);
      }
      return false;
    }
  };

  const importSamples = async () => {
    setImporting(true);
    try {
      for (const file of sampleFiles) {
        await api.importFile(project.project_id, { file_path: file.file_path, file_type: file.file_type });
      }
      message.success("内置样例数据已全部导入");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "样例导入失败");
    } finally {
      setImporting(false);
    }
  };

  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>数据导入</Title>
          <Text type="secondary">导入 SKU 主数据、参数、卖点、评论和量价事实。</Text>
        </div>
        <Button type="primary" icon={<CloudUploadOutlined />} loading={importing} onClick={importSamples}>
          导入内置样例数据
        </Button>
      </div>
      <Card size="small" title="上传自定义文件">
        <Space wrap>
          <Select
            value={fileType}
            onChange={setFileType}
            options={[
              { value: "sku_master", label: "SKU 主数据" },
              { value: "sku_param", label: "SKU 参数" },
              { value: "sku_claim", label: "宣传卖点" },
              { value: "sku_comment", label: "用户评论" },
              { value: "market_fact", label: "量价事实" }
            ]}
          />
          <Upload {...uploadProps}>
            <Button icon={<CloudUploadOutlined />} loading={importing}>
              选择 CSV 或 Excel 并导入
            </Button>
          </Upload>
        </Space>
      </Card>
      <div className="sample-grid">
        {sampleFiles.map((file) => (
          <Card key={file.file_type} size="small">
            <Statistic title={file.label} value={file.file_path} valueStyle={{ fontSize: 13 }} />
          </Card>
        ))}
      </div>
    </section>
  );
}

function DataQualityPage({ project }: { project: Project }) {
  const [quality, setQuality] = useState<DataQualityResponse>();
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setQuality(await api.dataQuality(project.project_id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取质量报告失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [project.project_id]);

  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>质量报告</Title>
          <Text type="secondary">查看行数、缺失、重复和数值解析问题。</Text>
        </div>
        <Button icon={<FileSearchOutlined />} onClick={load} loading={loading}>
          刷新
        </Button>
      </div>
      {quality && (
        <>
          <div className="metric-grid">
            <Card size="small">
              <Statistic title="质量状态" value={String(quality.summary.status ?? "unknown")} />
            </Card>
            <Card size="small">
              <Statistic title="问题数" value={Number(quality.summary.issue_count ?? 0)} />
            </Card>
            <Card size="small">
              <Statistic title="严重问题" value={Number(quality.summary.critical_count ?? 0)} />
            </Card>
          </div>
          <pre className="json-preview">{JSON.stringify(quality.summary.raw_row_counts, null, 2)}</pre>
          <Table
            size="small"
            rowKey={(row) => String(row.issue_id)}
            dataSource={quality.issues}
            columns={dynamicColumns(quality.issues)}
            pagination={{ pageSize: 8 }}
          />
        </>
      )}
    </section>
  );
}

function AssetsPage({ project }: { project: Project }) {
  const [assetType, setAssetType] = useState("normalized_params");
  const [asset, setAsset] = useState<AssetResponse>();
  const [loading, setLoading] = useState(false);

  const load = async (type = assetType) => {
    setLoading(true);
    try {
      setAsset(await api.listAssets(project.project_id, type));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取资产失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(assetType);
  }, [project.project_id, assetType]);

  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>资产列表</Title>
          <Text type="secondary">查看参数、卖点、评论主题、任务、战场和市场指标。</Text>
        </div>
        <Button onClick={() => load()} loading={loading}>
          刷新
        </Button>
      </div>
      <Tabs
        activeKey={assetType}
        onChange={setAssetType}
        items={[
          { key: "normalized_params", label: "参数结果" },
          { key: "claims", label: "卖点结果" },
          { key: "topics", label: "评论主题" },
          { key: "tasks", label: "用户任务" },
          { key: "battlefields", label: "价值战场" },
          { key: "market_metrics", label: "市场指标" },
          { key: "params", label: "参数定义" },
          { key: "claim_defs", label: "卖点定义" }
        ]}
      />
      <Table
        size="small"
        rowKey={(row) => String(row.result_id ?? row.score_id ?? row.param_id ?? row.claim_id ?? row.topic_id ?? row.task_id ?? row.battlefield_id)}
        loading={loading}
        dataSource={asset?.items ?? []}
        columns={dynamicColumns(asset?.items ?? [])}
        scroll={{ x: true }}
        pagination={{ pageSize: 12 }}
      />
    </section>
  );
}

function ReviewQueuePage({ project }: { project: Project }) {
  const [queue, setQueue] = useState<ReviewQueueResponse>();
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setQueue(await api.reviewQueue(project.project_id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取复核队列失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [project.project_id]);

  const decide = async (reviewId: string, decision: "approved" | "rejected" | "edited") => {
    await api.decideReview(reviewId, decision);
    message.success("复核状态已更新");
    await load();
  };

  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>复核队列</Title>
          <Text type="secondary">处理低置信、冲突、样本不足和高价值 SKU 复核项。</Text>
        </div>
        <Button onClick={load} loading={loading}>
          刷新
        </Button>
      </div>
      <Table
        size="small"
        rowKey={(row) => String(row.review_id)}
        loading={loading}
        dataSource={queue?.items ?? []}
        pagination={{ pageSize: 10 }}
        columns={[
          { title: "类型", dataIndex: "item_type", width: 110 },
          { title: "对象", dataIndex: "item_key", width: 180 },
          { title: "原因", dataIndex: "reason_code", width: 160 },
          {
            title: "置信度",
            dataIndex: "confidence",
            width: 100,
            render: (value) => Number(value).toFixed(2)
          },
          {
            title: "优先级",
            dataIndex: "priority",
            width: 100,
            render: (value) => <Tag color={value === "high" || value === "critical" ? "red" : "blue"}>{String(value)}</Tag>
          },
          { title: "状态", dataIndex: "status", width: 110 },
          {
            title: "操作",
            width: 220,
            render: (_, record) => (
              <Space>
                <Button size="small" icon={<CheckCircleOutlined />} onClick={() => decide(String(record.review_id), "approved")}>
                  通过
                </Button>
                <Button size="small" onClick={() => decide(String(record.review_id), "rejected")}>
                  拒绝
                </Button>
                <Button size="small" onClick={() => decide(String(record.review_id), "edited")}>
                  标记编辑
                </Button>
              </Space>
            )
          }
        ]}
      />
    </section>
  );
}

function RuntimeExportPage({ project }: { project: Project }) {
  const [version, setVersion] = useState("0.1.0");
  const [result, setResult] = useState<ExportResponse>();
  const [loading, setLoading] = useState(false);

  const exportRuntime = async () => {
    setLoading(true);
    try {
      const next = await api.exportRuntime(project.project_id, version);
      setResult(next);
      message.success(next.message);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "导出失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="page-section">
      <div className="section-heading">
        <div>
          <Title level={2}>运行态导出</Title>
          <Text type="secondary">导出仅含白名单文件的授权品类运行态资产包。</Text>
        </div>
      </div>
      <Card size="small" title="导出设置">
        <Space wrap>
          <Input className="version-input" value={version} onChange={(event) => setVersion(event.target.value)} />
          <Button type="primary" icon={<ExportOutlined />} loading={loading} onClick={exportRuntime}>
            导出运行态资产包
          </Button>
        </Space>
      </Card>
      {result && (
        <Alert
          className="export-alert"
          type="success"
          showIcon
          message="导出完成"
          description={
            <div>
              <div>包路径：{result.package_path}</div>
              <div>文件：{result.files.join("，")}</div>
            </div>
          }
        />
      )}
    </section>
  );
}

function dynamicColumns(rows: Record<string, unknown>[]) {
  const first = rows[0];
  if (!first) {
    return [];
  }
  return Object.keys(first)
    .filter((key) => !["created_at", "updated_at"].includes(key))
    .slice(0, 10)
    .map((key) => ({
      title: key,
      dataIndex: key,
      width: key.includes("id") || key.includes("payload") ? 220 : 150,
      render: (value: unknown) => renderCell(value)
    }));
}

function renderCell(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return <Text type="secondary">-</Text>;
  }
  if (Array.isArray(value) || typeof value === "object") {
    return <Text className="mono-cell">{JSON.stringify(value)}</Text>;
  }
  if (typeof value === "boolean") {
    return <Tag color={value ? "green" : "default"}>{value ? "是" : "否"}</Tag>;
  }
  return <Text>{String(value)}</Text>;
}

export default App;
