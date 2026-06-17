# CatForge 彩电核心三竞品 MVP 设计

## 1. 背景与目标

> 详细设计已经拆分到 `docs/core3_mvp/`，请从 `docs/core3_mvp/README.md` 按数据流顺序阅读。本文只保留概要。

本设计基于 `cankao/CatForge_彩电核心三竞品生成_MVP_PRD_PostgreSQL版.docx` 和 `cankao/CatForge_彩电核心三竞品生成_MVP_详细设计_PostgreSQL版.docx`。MVP 的主链路是：

1. 从 PostgreSQL 读取彩电 SKU、12 个月分渠道量价、参数、宣传卖点和评论数据。
2. 对任意目标 SKU 或型号生成市场画像、标准参数、卖点激活、评论主题、用户任务、目标客群和价值战场。
3. 从全量候选 SKU 中输出三类核心竞品：正面对打、价格/销量挤压、高端标杆/潜在下探。
4. 为每个竞品输出可回溯的证据卡、组件分、业务理由、置信度和不足原因。
5. 支持批量生成、总览展示，以及 `sku_competitor_core3.csv` 和 `evidence_cards.jsonl` 导出。

本 MVP 不做完整 CatForge 品类生产工具，不做多品类，不做 Gold Set 标注系统，不暴露 prompt、内部生成方法或工厂侧迁移工具。

## 2. 现有系统映射

当前仓库已经有三部分可复用能力：

- 基础数据表：`raw_sku_master`、`raw_market_fact`、`raw_sku_param`、`raw_sku_claim`、`raw_sku_comment`、`evidence_item`。
- Goal1/Goal3 派生结果：`sku_param_normalized`、`sku_claim_result`、`sku_comment_topic_result`、`sku_task_score`、`sku_battlefield_score`、`sku_competitor_result`。
- 前端工作台：`apps/factory-web/src/App.tsx` 统一菜单，`WorkbenchPage` 承载 Goal3 工作台页面。

但新 MVP 不能直接塞进 Goal3 工作台：

- Goal3 页面是完整资产工作台，包含资产库、映射、校准、导出预览，不符合本 MVP “只展示核心三竞品结果”的边界。
- 现有竞品类型是 `direct`、`substitute`、`benchmark`、`potential`，新文档要求固定三槽位：`direct`、`pressure`、`benchmark_potential`。
- 现有 `run_goal1_analysis` 以 fixture 为中心，会重置项目数据，不适合作为 PostgreSQL 生产数据链路。

结论：复用底层 schema、证据模型、规则 DSL 和样式体系，但新增独立 MVP 服务、API、结果表和前端页面组。

## 3. 隔离策略

### 3.1 后端隔离

新增后端命名空间：

- Router：`apps/api-server/app/api/core3_mvp.py`
- Service 包：`apps/api-server/app/services/core3_mvp/`
- Schema：`apps/api-server/app/schemas/core3_mvp.py`
- 规则配置：`apps/api-server/app/rules/tv_core3_mvp_rules.json`
- Alembic：新增 `0004_tv_core3_mvp.py`

API 前缀统一使用：

```text
/api/mvp/core3/projects/{project_id}/...
```

不修改现有 Goal1、Goal2、Goal3 API 行为。

### 3.2 前端隔离

新增前端页面组：

```text
apps/factory-web/src/pages/core3/
  Core3Mvp.tsx
  core3Pages.ts
  core3Format.ts
  core3Pages.test.ts
```

在主菜单新增顶级入口“彩电核心三竞品 MVP”，进入后由 `Core3Mvp` 自己管理三页：

- 批量总览
- 单 SKU 竞品报告
- 竞品证据卡

不要把这些页面放入 `goal3-workbench` 的 children，也不要复用 `WorkbenchPage` 做条件分支。

## 4. PostgreSQL 数据模型

### 4.1 输入来源

优先读取现有 CatForge raw tables：

- `raw_sku_master`
- `raw_market_fact`
- `raw_sku_param`
- `raw_sku_claim`
- `raw_sku_comment`

同时在数据访问层保留生产 PostgreSQL 视图适配点，便于对接文档中的命名：

- `sku_master`
- `market_fact`
- `sku_param_raw`
- `sku_claim_raw`
- `sku_comment_raw`

第一版实现可通过 SQLAlchemy ORM 读取现有 raw tables。若生产库已有文档命名视图，后续只需在 `core3_data_access.py` 增加表名映射，不影响 API 和前端。

### 4.2 新增结果表

新增表使用 `core3_` 前缀，避免与现有 Goal1/Goal3 结果混用。

#### `core3_pipeline_run`

- `run_id`
- `project_id`
- `category_code`
- `status`
- `target_sku_code`
- `scope`
- `rule_version`
- `counts`
- `diagnostics`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

#### `core3_sku_market_profile`

- `profile_id`
- `run_id`
- `project_id`
- `category_code`
- `sku_code`
- `brand`
- `model_name`
- `series`
- `price_wavg_12m`
- `price_latest`
- `sales_volume_12m`
- `sales_amount_12m`
- `channel_share`
- `price_drop_rate_3m`
- `sales_growth_3m`
- `price_percentile`
- `sales_percentile`
- `source_evidence_ids`
- `confidence`

#### `core3_competitor_candidate`

- `candidate_id`
- `run_id`
- `project_id`
- `category_code`
- `target_sku_code`
- `candidate_sku_code`
- `battlefield_code`
- `slot_scores`
- `component_scores`
- `gate_status`
- `gate_reasons`
- `evidence_ids`
- `confidence`

#### `core3_competitor_result`

- `result_id`
- `run_id`
- `project_id`
- `category_code`
- `target_sku_code`
- `role`: `direct` / `pressure` / `benchmark_potential`
- `competitor_sku_code`
- `battlefield_code`
- `score`
- `component_scores`
- `reason`
- `confidence`
- `confidence_level`
- `review_flag`
- `insufficient_reasons`
- `evidence_ids`
- `evidence_card`

唯一约束：

- `(run_id, target_sku_code, role)`
- `(run_id, target_sku_code, competitor_sku_code)`

## 5. 计算流水线

### 5.1 服务拆分

```text
core3_data_access.py
  load_project_input()
  resolve_sku_code()
  data_status()

core3_market_profile.py
  build_market_profiles()

core3_feature_pipeline.py
  normalize_params()
  activate_claims()
  summarize_comment_topics()
  score_tasks_groups_battlefields()

core3_competitor_engine.py
  build_candidate_pool()
  calculate_component_scores()
  select_core3()
  build_evidence_card()

core3_report_service.py
  overview()
  sku_report()
  evidence_cards()
  export_core3_csv()
  export_evidence_jsonl()
```

第一版同步运行即可，使用现有 `JobRun` 不是必须。若批量耗时超过前端可接受范围，再把 `run-core3` 包装进已有 job 服务。

### 5.2 市场画像

核心指标：

- `price_wavg_12m = SUM(sales_amount) / NULLIF(SUM(sales_volume), 0)`
- `price_latest = latest_period_sales_amount / latest_period_sales_volume`
- `sales_volume_12m = SUM(sales_volume)`
- `sales_amount_12m = SUM(sales_amount)`
- `channel_share[channel] = sales_volume_in_channel / total_sales_volume`
- `price_drop_rate_3m = (price_avg_prev_3m - price_latest) / price_avg_prev_3m`
- `sales_growth_3m = (volume_latest_3m - volume_prev_3m) / volume_prev_3m`

缺失值处理：

- 缺失、空字符串、`-` 和 null 都是 unknown，不能当成 false。
- 没有价格或销量时不输出高置信竞品。
- 评论缺失时评论分权重置为 0，并降低置信度。

### 5.3 三槽位选择

角色定义：

- `direct`：正面对打，回答“谁和我最像、抢同一批用户”。
- `pressure`：价格/销量挤压，回答“谁用更低价格或更强销量抢用户”。
- `benchmark_potential`：高端标杆/潜在下探，回答“谁更强或一降价就会压到我”。

每个候选都计算三套 slot score：

```text
direct =
  battlefield_similarity * 0.25
  + claim_similarity * 0.20
  + price_similarity * 0.15
  + channel_overlap * 0.10
  + size_similarity * 0.10
  + task_similarity * 0.10
  + sales_strength * 0.10

pressure =
  task_similarity * 0.25
  + price_advantage * 0.25
  + sales_strength * 0.20
  + channel_overlap * 0.10
  + battlefield_similarity * 0.10
  + price_drop_signal * 0.10

benchmark_potential =
  param_superiority * 0.25
  + claim_superiority * 0.20
  + battlefield_similarity * 0.20
  + sales_or_amount_strength * 0.15
  + price_premium_or_downshift * 0.15
  + channel_overlap * 0.05
```

选择规则：

1. 每个槽位先按本槽位分排序。
2. 依次选择 `direct`、`pressure`、`benchmark_potential`。
3. 同一 `competitor_sku_code` 不得重复。
4. 同系列高度相似型号只保留一个。
5. 三个结果尽量不要全来自同一品牌，除非分数显著领先。
6. 候选不满足硬门槛时输出 `insufficient_comparable_pool`、`weak_direct`、`weak_pressure` 或 `weak_benchmark_potential`，不硬凑。

### 5.4 证据卡

每个竞品结果至少覆盖 3 类证据：

- 价格证据
- 渠道证据
- 参数证据
- 标准卖点证据
- 销量/趋势证据
- 评论证据

证据卡字段：

- `target`
- `competitor`
- `role`
- `component_scores`
- `price_comparison`
- `sales_comparison`
- `channel_overlap`
- `param_comparison`
- `claim_comparison`
- `task_battlefield_similarity`
- `comment_evidence`
- `evidence_ids`
- `reason_summary`

所有 `evidence_ids` 必须能在 `evidence_item` 查到来源。

## 6. API 设计

```text
GET  /api/mvp/core3/projects/{project_id}/data-status
POST /api/mvp/core3/projects/{project_id}/run
GET  /api/mvp/core3/projects/{project_id}/overview
GET  /api/mvp/core3/projects/{project_id}/sku/{sku_or_model}/profile
GET  /api/mvp/core3/projects/{project_id}/sku/{sku_or_model}/battlefields
GET  /api/mvp/core3/projects/{project_id}/sku/{sku_or_model}/competitors/core3
GET  /api/mvp/core3/projects/{project_id}/sku/{sku_or_model}/competitors/evidence
GET  /api/mvp/core3/projects/{project_id}/sku/{sku_or_model}/report
GET  /api/mvp/core3/projects/{project_id}/export/core3.csv
GET  /api/mvp/core3/projects/{project_id}/export/evidence-cards.jsonl
```

`POST /run` 请求体：

```json
{
  "target_sku_code": "TV00029115",
  "target_model": "85E7Q",
  "batch": false,
  "force_recompute": false
}
```

响应体必须包含：

- `run_id`
- `status`
- `counts`
- `warnings`
- `latest_report_ref`

## 7. 前端页面设计

### 7.1 入口

主菜单新增顶级项：

```text
彩电核心三竞品 MVP
```

页面内部使用 tabs 或 segmented 控制三页，避免与现有 Goal3 工作台混杂。

### 7.2 批量总览页

内容：

- 已分析 SKU 数
- 高/中/低置信结果数量
- 无法生成原因 Top5
- 批量结果表：目标型号、品牌、主战场、三个竞品、置信度、复核标记
- 操作：运行批量生成、导出 CSV、导出 JSONL

### 7.3 单 SKU 竞品报告页

内容：

- 输入框支持 `sku_code` 或型号，例如 `85E7Q`
- 目标 SKU 市场画像
- 核心参数
- 激活卖点
- 用户任务
- 目标客群
- 价值战场
- 三张竞品卡：`direct`、`pressure`、`benchmark_potential`

### 7.4 竞品证据卡页

内容：

- 三竞品切换
- 价格/销量/渠道对比
- 参数和卖点对比
- 任务/战场相似度
- 评论证据
- `evidence_id` 明细
- 候选池 TopN 抽屉：说明为什么未入选

## 8. 测试设计

### 8.1 后端测试

新增 `apps/api-server/tests/test_core3_mvp.py`：

- 数据状态 API 能统计 SKU、品牌、渠道、量价、参数、卖点、评论数量。
- 输入 `TV00029115` 或 `85E7Q` 能解析到目标 SKU。
- `run` 后能生成市场画像、候选池和三槽位结果。
- 每个高置信结果至少有 3 类证据。
- 三槽位不能重复 SKU。
- 修改价格/销量 fixture 后，`pressure` 或战场 market score 发生变化。
- 价格、销量、评论缺失时输出不足原因，不硬凑。
- export CSV/JSONL 包含规定字段。

### 8.2 前端测试

新增 `apps/factory-web/src/pages/core3/core3Pages.test.ts`：

- 页面配置只包含 MVP 三页。
- 菜单 key 不和现有 `workbenchPages` 混用。
- 角色展示顺序固定为 direct、pressure、benchmark_potential。

### 8.3 验收测试

- 页面从搜索 `85E7Q` 到展示报告在预计算场景下不超过 5 秒。
- 连续演示 10 分钟无空白页和明显前端错误。
- 后端测试、前端测试、前端 build 全部通过。

## 9. 实施顺序

1. 新增后端 schema、models、migration、规则文件和空 router。
2. 实现 `data-status`、SKU/model 解析和市场画像，先打通 PostgreSQL 数据读取。
3. 实现参数/卖点/评论/任务/战场计算，输出目标 SKU report 的前半部分。
4. 实现候选池、组件分、三槽位选择、去重和不足原因。
5. 实现证据卡和导出。
6. 新增前端独立 MVP 页面组和 API client 方法。
7. 补齐后端/前端测试，最后再接入主菜单。

## 10. 待确认事项

1. 生产 PostgreSQL 当前真实表名是现有 `raw_*`，还是文档中的 `sku_master` / `market_fact` / `sku_param_raw` 等视图。
2. 型号搜索是否需要支持模糊匹配，例如输入 `85E7Q` 自动匹配 `model_name` 含该字符串的 SKU。
3. MVP 演示是否只要求重点型号即时生成，还是必须预先批量算完 1000 SKU。
4. 是否需要在第一版启用 LLM 裁决。建议第一版不启用，先用确定性三槽位规则，LLM 作为后续增强。
