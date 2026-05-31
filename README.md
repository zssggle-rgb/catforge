# CatForge / 品铸

CatForge 是内部品类资产生产工具。当前仓库实现了彩电 TV 品类的第一个可运行 MVP 垂直切片：样例数据导入、数据质量报告、规则化参数归一、卖点映射、评论主题识别、用户任务与价值战场评分、市场指标、复核队列和运行态资产包导出。

运行态导出严格使用白名单，不导出提示词、评测集构建器、跨品类迁移模板、规则生成器等工厂能力。

## 目录

```text
apps/api-server      FastAPI + SQLAlchemy 后端
apps/factory-web     React + TypeScript + Ant Design 中文工作台
contracts            输入数据 JSON Schema
docs                 需求、契约、架构和导出边界
examples             彩电样例 CSV 和期望结果
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

## 关键 API

- `GET /healthz`
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

