# CatForge / 品铸

CatForge 是内部品类资产生产工具。当前仓库实现了彩电 TV 品类的第一个可运行 MVP 垂直切片：样例数据导入、数据质量报告、规则化参数归一、卖点映射、评论主题识别、用户任务与价值战场评分、市场指标、复核队列和运行态资产包导出。

Goal1 核心分析引擎已加入后端：规则从 YAML/JSON DSL 读取和校验，不再只依赖硬编码启发式；分析结果包含证据、置信度、规则版本、资产版本和复核状态；竞品引擎会输出 direct、benchmark、substitute 等类型及组件分；Gold Set 支持导入、评测和生成不自动发布的校准草案。

Goal2 生产化加固已加入后端：作业具备幂等键、输入指纹、重试、checkpoint、取消、并发锁和诊断；资产版本支持 draft / in_review / released / archived 生命周期和 released 不可变约束；审计事件覆盖规则编辑、发布、导出、回滚等敏感动作；新的运行态导出 API 会校验发布状态、白名单文件和禁止内容模式。

运行态导出严格使用白名单，不导出提示词、评测集构建器、跨品类迁移模板、规则生成器等工厂能力。

## 目录

```text
apps/api-server      FastAPI + SQLAlchemy 后端
apps/factory-web     React + TypeScript + Ant Design 中文工作台
contracts            输入数据 JSON Schema
docs                 需求、契约、架构和导出边界
docs/goal1           Goal1 规则引擎、竞品、评测、API 和迁移规范
docs/goal2           Goal2 作业可靠性、版本治理、审计、导出边界和运行手册
examples             彩电样例 CSV 和期望结果
examples/goal1       Goal1 规则、fixture、Gold Set 和最小验收期望
examples/goal2       Goal2 发布 manifest 样例、导出白名单和禁止模式
schemas/goal1        Goal1 JSON Schema
schemas/goal2        Goal2 JSON Schema
infra                部署扩展预留
scripts              辅助脚本预留
```

## 本地运行

后端本地默认使用 SQLite 回退，Docker Compose 使用 PostgreSQL + Redis。

```bash
cd apps/api-server
uv run --extra dev uvicorn app.main:app --reload --port 8000
```

```bash
cd apps/factory-web
npm install
npm run dev
```

访问：

- 前端工作台：http://localhost:5173
- 后端健康检查：http://localhost:8000/healthz
- OpenAPI：http://localhost:8000/docs

## Docker Compose

```bash
docker compose up --build
```

启动后包含：

- `api`：FastAPI，端口 `8000`
- `web`：Vite 开发服务，端口 `5173`
- `postgres`：PostgreSQL
- `redis`：Redis，同步本地 fallback 已保留

## 验收流程

1. 在前端创建一个 `TV` 项目。
2. 进入“数据导入”，点击“导入内置样例数据”。
3. 进入“质量报告”，确认严重问题为 0。
4. 进入“项目看板”，点击“顺序执行全部”。
5. 进入“资产列表”，查看参数、卖点、评论主题、任务、战场和市场指标。
6. 进入“复核队列”，检查低置信、冲突、高价值 SKU、样本不足等复核项。
7. 进入“运行态导出”，导出白名单资产包。

## 自动化测试

后端：

```bash
cd apps/api-server
uv run --extra dev python -m pytest
```

前端：

```bash
cd apps/factory-web
npm test
npm run build
```

后端测试覆盖：

- `/healthz`
- 样例数据导入和质量报告
- 参数归一、卖点映射、评论主题、任务战场评分
- 复核队列生成
- 运行态导出白名单边界
- 缺失 `sku_code` 的质量问题
- Goal1 规则 DSL 校验、阈值变更生效、TV fixture 端到端分析
- Goal1 竞品 direct/benchmark/substitute 输出、证据卡、Gold Set 评测和校准草案
- Goal2 job 幂等、重试、契约失败、checkpoint、取消和并发锁
- Goal2 released 不可变、改动创建 draft、运行态导出白名单/禁止模式、审计和回滚

## 关键 API

- `GET /healthz`
- `GET /readyz`
- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `POST /projects/{project_id}/files`
- `POST /projects/{project_id}/imports`
- `GET /projects/{project_id}/data-quality`
- `POST /projects/{project_id}/profile`
- `POST /projects/{project_id}/pipeline/{step}`
- `GET /projects/{project_id}/assets/{asset_type}`
- `GET /projects/{project_id}/review-queue`
- `POST /review-queue/{review_id}/decision`
- `POST /projects/{project_id}/export-runtime`

Goal1 后端 API 使用 `/api` 前缀：

- `POST /api/rule-sets/validate`
- `POST /api/rule-sets`
- `GET /api/rule-sets/{rule_set_id}`
- `POST /api/rule-sets/{rule_set_id}/activate`
- `POST /api/projects/{project_id}/run-analysis`
- `GET /api/projects/{project_id}/analysis-runs/{run_id}`
- `GET /api/projects/{project_id}/sku/{sku_code}/analysis`
- `GET /api/projects/{project_id}/sku/{sku_code}/competitors`
- `GET /api/projects/{project_id}/evidence/{evidence_id}`
- `POST /api/projects/{project_id}/gold-labels/import`
- `POST /api/projects/{project_id}/evaluation/run`
- `GET /api/projects/{project_id}/evaluation/{evaluation_id}`
- `POST /api/projects/{project_id}/calibration/run`

Goal2 后端 API 使用 `/api` 前缀：

- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`
- `POST /api/jobs/{job_id}/retry`
- `GET /api/jobs/{job_id}/diagnostics`
- `POST /api/assets/versions`
- `POST /api/assets/{asset_id}/edit`
- `POST /api/assets/{asset_id}/submit-review`
- `POST /api/assets/{asset_id}/approve`
- `POST /api/assets/{asset_id}/release`
- `GET /api/assets/{asset_id}/versions`
- `GET /api/assets/diff?from_version=&to_version=`
- `POST /api/assets/{asset_id}/rollback`
- `POST /api/assets/{asset_id}/archive`
- `POST /api/projects/{project_id}/runtime-export`
- `GET /api/exports/{export_id}`
- `GET /api/exports/{export_id}/download`
- `GET /api/audit?project_id=&object_type=&object_id=&action=`
- `POST /api/audit/permission-change`
- `GET /api/metrics`

## 运行态导出边界

允许导出的文件名由 `docs/05_export_boundary.md` 和后端 `asset_exporter.py` 共同约束。当前导出包只包含：

- `std_param_def.csv`
- `std_claim_def.csv`
- `comment_topic_def.csv`
- `user_task_def.csv`
- `target_group_def.csv`
- `battlefield_def.csv`
- `mapping_rules.csv`
- `scoring.yaml`
- `competitor_rule.yaml`
- `sample_sku_results.csv`
- `sample_evidence_cards.jsonl`
- `asset_readme.md`
- `release_note.md`
