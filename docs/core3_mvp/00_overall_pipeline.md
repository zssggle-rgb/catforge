# 00 总体流程设计

## 1. 设计目标

MVP 要证明一件事：基于 PostgreSQL 中已有彩电 SKU 数据，系统能从一个目标 SKU 出发，经过可解释的中间步骤，产出三个核心竞品和证据卡。

三个竞品槽位固定：

- `direct`：正面对打，和目标 SKU 抢同一批用户。
- `pressure`：价格/销量挤压，用更低价格、更强销量或更强降价信号挤压目标。
- `benchmark_potential`：高端标杆/潜在下探，参数或卖点更强，或降价后进入目标价格带。

## 2. 系统边界

新增独立 MVP 链路：

```text
apps/api-server/app/api/core3_mvp.py
apps/api-server/app/services/core3_mvp/
apps/api-server/app/schemas/core3_mvp.py
apps/api-server/app/rules/tv_core3_mvp_rules.json
apps/factory-web/src/pages/core3/
```

不混用：

- 不把 MVP 页面塞进 `WorkbenchPage`。
- 不把三竞品结果写入现有 `sku_competitor_result` 作为主结果。
- 不调用会重置 fixture 数据的 `run_goal1_analysis()` 作为生产链路。

可复用：

- `raw_sku_master`
- `raw_market_fact`
- `raw_sku_param`
- `raw_sku_claim`
- `raw_sku_comment`
- `evidence_item`
- 项目选择器、Ant Design 表格、现有测试 fixture。

## 3. 流水线步骤

### Step 1：读取数据

读取项目范围内 5 类数据：

- SKU 主数据。
- 12 个月分渠道量价。
- 原始参数。
- 宣传卖点。
- 评论。

输出 `Core3InputBundle`，不做业务判断。

### Step 2：建立运行上下文

创建一次 `core3_pipeline_run`，记录：

- 单 SKU 或批量。
- 目标 SKU。
- 输入数据指纹。
- 规则版本。
- 数据健康摘要。

输出 `Core3RunContext`。

### Step 3：加载预制知识资产

加载 `tv_core3_mvp_seed_v0_2.json`，得到参数、卖点、评论主题、任务、客群、战场和映射规则。预制知识只提供识别框架，不直接生成 SKU 结论。

输出：

- `PresetAssetCatalog`
- `rule_version`
- seed schema 校验结果

### Step 4：真实数据抽取

从 raw 参数、宣传文本和评论中抽取真实 SKU 特征：

- raw 参数字段画像。
- 参数 alias 匹配。
- 参数值解析和单位归一。
- 宣传文本切句和卖点命中。
- 评论切句、主题分类和情感判断。
- 新字段、新短语、新主题候选。

输出：

- 标准参数候选和值。
- 卖点激活证据。
- 评论主题样例句。
- `candidate_param_alias`
- `candidate_claim`
- `candidate_comment_topic`

### Step 5：计算市场画像

按 SKU 聚合量价：

- 加权均价。
- 最新价格。
- 12 个月销量/销额。
- 渠道占比。
- 3 个月价格下探。
- 3 个月销量增长。
- 价格/销量分位。

写入 `core3_sku_market_profile`。

### Step 6：计算语义特征

对每个 SKU 生成：

- 标准参数。
- 标准卖点激活。
- 评论主题。

写入 `core3_sku_feature_profile` 的第一部分。

### Step 7：计算任务、客群、战场

任务、客群和战场不是直接写死或从评论抽标签，而是由参数、卖点、评论和量价信号推导：

- 用户任务。
- 目标客群。
- 价值战场。

写入 `core3_sku_feature_profile` 的第二部分。

### Step 8：召回候选池

以目标 SKU 的战场、价格、尺寸、渠道、任务为条件召回候选。

写入 `core3_competitor_candidate`。

### Step 9：计算组件分与槽位分

对每个候选计算：

- 相似类组件。
- 压力类组件。
- 标杆类组件。
- 三个槽位分。

更新 `core3_competitor_candidate.component_scores` 和 `slot_scores`。

### Step 10：选择核心三竞品

按三槽位硬门槛、排序、去重、品牌分散、系列去重选择结果。

写入 `core3_competitor_result`。

### Step 11：生成证据卡和报告

为每个角色生成 evidence card，输出页面报告和导出文件。

写入 `core3_evidence_card`。

## 4. 总体对象模型

```text
Core3InputBundle
  project
  sku_master_rows
  market_fact_rows
  param_rows
  claim_rows
  comment_rows
  evidence_index

Core3RunContext
  run_id
  project_id
  category_code
  target_sku_codes
  scope
  rule_version
  input_fingerprint
  warnings

Core3SkuSnapshot
  sku_identity
  market_profile
  standard_params
  claim_activations
  comment_topics
  task_scores
  target_group_scores
  battlefield_scores
  evidence_ids
  confidence

Core3CandidateCard
  target_sku_code
  candidate_sku_code
  component_scores
  slot_scores
  gate_reasons
  evidence_ids

Core3ResultCard
  role
  competitor_sku_code
  score
  reason
  confidence
  insufficient_reasons
  evidence_card
```

## 5. 持久化总表

新增表：

- `core3_pipeline_run`
- `core3_sku_market_profile`
- `core3_sku_feature_profile`
- `core3_competitor_candidate`
- `core3_competitor_result`
- `core3_evidence_card`

每张表必须包含：

- `project_id`
- `category_code`
- `run_id`
- `created_at`
- `updated_at`

结果表还必须包含：

- `confidence`
- `evidence_ids`
- `rule_version` 或可追溯的规则版本字段。

## 6. API 总入口

```text
GET  /api/mvp/core3/projects/{project_id}/data-status
POST /api/mvp/core3/projects/{project_id}/run
GET  /api/mvp/core3/projects/{project_id}/overview
GET  /api/mvp/core3/projects/{project_id}/sku/{sku_or_model}/report
GET  /api/mvp/core3/projects/{project_id}/sku/{sku_or_model}/competitors/core3
GET  /api/mvp/core3/projects/{project_id}/sku/{sku_or_model}/competitors/evidence
GET  /api/mvp/core3/projects/{project_id}/export/core3.csv
GET  /api/mvp/core3/projects/{project_id}/export/evidence-cards.jsonl
```

## 7. 第一版默认决策

- 数据源先走现有 `raw_*` 表。
- 型号搜索支持大小写无关包含匹配。
- 单 SKU 和批量都支持，页面主演示优先单 SKU。
- 中间结果落 PostgreSQL。
- 规则配置用 JSON 文件。
- 不启用 LLM。
