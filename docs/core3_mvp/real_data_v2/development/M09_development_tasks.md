# M09 用户任务开发任务

## 1. 模块目标

M09 的开发目标是基于 M08 SKU 综合信号画像，推导每个 SKU 与 10 个 TV MVP 用户任务之间的候选关系、任务得分、关系等级、置信度、证据拆分和复核问题。

M09 要解决的工程问题：

1. 将“用户任务”从评论标签、卖点标签、单个参数中解耦，改为由参数能力、卖点表达、评论场景和市场验证四域证据共同推导。
2. 对每个 SKU 和每个 seed 用户任务都保留候选判断、得分计算、封顶降级、复核触发和业务解释。
3. 为 M10 目标客群、M11 价值战场、M12 候选召回、M13 竞品评分、M14 核心三选择和 M15 高层展示提供统一任务口径。
4. 对 85E7Q 这类“参数强、评论多、市场有、结构化卖点缺失”的 SKU，既要识别高端画质、客厅影院、体育观看等强相关任务，也要明确缺结构化卖点证据和不能由评论单域直接升为主任务。
5. 用 `profile_hash`、`feature_view_hash`、`task_seed_version`、`task_seed_hash`、`rule_version` 支撑增量重算、复核追溯和下游失效传播。
6. 输出可给业务展示页二次加工的中文原因，但不输出内部过程性语言、SQL、JSON、公式或“AI判断”式文案。

M09 必须固化以下边界：

- M09 只消费 M08 `core3_sku_signal_profile`、`core3_sku_signal_evidence_matrix`、`core3_sku_downstream_feature_view where for_module='M09'`。
- M09 不直接读取原始 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data`。
- M09 不直接读取 M03、M04b、M06、M07 散表做业务字段判断。
- M09 不从原始评论或评论基础分类直接贴用户任务标签。
- M09 不把“产品体验/服务体验/物流安装/价格感知/未知初判”直接当成用户任务。
- M09 不把卖点 code、评论主题 code 或单个参数直接等同于任务结论。
- M09 不生成目标客群。
- M09 不生成价值战场。
- M09 不做战场内卖点价值分层。
- M09 不召回候选 SKU。
- M09 不选择核心竞品。
- M09 不输出高层页最终报告。
- M09 不把 `unknown`、空值、`-` 或缺失值当成 false。
- M09 不伪造 85E7Q 的结构化卖点证据。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M09 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M09_user_task_requirements.md` |
| M09 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M09_user_task_design.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M08 任务 | `docs/core3_mvp/real_data_v2/development/M08_development_tasks.md` |
| M08 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M08_sku_signal_profile_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 参考模块 | `cankao/catforge_sop_md/modules/M09_用户任务模块.md` |
| 任务 seed | `apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` |

编码前必须确认：

- M08 已输出 `core3_sku_signal_profile`，并包含 `profile_hash`、`domain_completeness_json`、`missing_signals_json`、`risk_signals_json`。
- M08 已输出 `core3_sku_signal_evidence_matrix`，并能按 SKU、证据域和 evidence refs 回溯。
- M08 已输出 `core3_sku_downstream_feature_view where for_module='M09'`，并包含 `feature_view_hash` 或 `view_hash`。
- M08 feature view 中已有任务所需的参数、卖点、评论、价格感知、服务信号、市场和可比池裁剪特征。
- M02 `core3_evidence_atom` 可通过 M08 evidence refs 回溯，但 M09 不直接扫描 M02 生成业务判断。
- `tv_core3_mvp_seed_v0_2.json` 中 `user_tasks` 正好覆盖 10 个 MVP 任务。
- INFRA 已提供 run context、hash 工具、runner 协议、复核 issue 约定、current 版本约定和测试 fixture 基础。

## 3. 本次范围

本次开发任务拆分覆盖 M09 的后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 4 张 M09 输出表 |
| model/schema | 新增任务 seed、M09 输入、候选、分域得分、任务得分、证据拆分、复核、runner、API schema |
| seed loader | 读取并校验真实 TV 用户任务 seed，保存 seed 版本和 hash |
| M08 input loader | 只读取 M08 profile、feature view、evidence matrix |
| candidate builder | 对每个 SKU x 10 个任务生成候选或拒绝/阻塞记录 |
| domain scorer | 分别计算参数、卖点、评论、市场四域支撑分 |
| risk evaluator | 执行 comment_only、service_only、single_param_only、missing_structured_claim 等封顶和复核规则 |
| relation classifier | 输出 main、secondary、weak、insufficient、blocked 关系等级 |
| confidence calculator | 基于任务分、证据覆盖、M08 画像置信度和证据质量计算置信度 |
| business reason builder | 生成业务化中文原因，禁止内部字段名和技术过程文案外露 |
| evidence breakdown | 输出参数、卖点、评论、市场、风险、seed、profile 分域证据拆分 |
| review issue | 输出缺 M08 特征视图、评论单域、服务单域、单参数、冲突、缺结构化卖点、市场样本不足等复核问题 |
| invalidation | 任务结果变化时登记 M10-M16 下游影响 |
| runner/API | 运行入口、任务列表查询、任务详情查询、证据拆分查询、复核问题查询 |
| 测试 | 单元、集成、API、增量、边界、85E7Q fixture |

本次不做：

- 不实现 M10 目标客群。
- 不实现 M11 价值战场。
- 不实现 M11.5 战场内卖点价值分层。
- 不实现 M12 候选池召回。
- 不实现 M13 竞品组件评分。
- 不实现 M14 核心三竞品选择。
- 不实现 M15 高层报告页。
- 不实现前端页面。
- 不部署到 205。
- 不修改任务 seed 内容，seed 只读校验。
- 不新增临时用户任务。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/user_task_schemas.py
apps/api-server/app/services/core3_real_data/user_task_repositories.py
apps/api-server/app/services/core3_real_data/task_seed_loader.py
apps/api-server/app/services/core3_real_data/m09_feature_view_loader.py
apps/api-server/app/services/core3_real_data/task_candidate_builder.py
apps/api-server/app/services/core3_real_data/task_domain_scorer.py
apps/api-server/app/services/core3_real_data/task_risk_evaluator.py
apps/api-server/app/services/core3_real_data/task_relation_classifier.py
apps/api-server/app/services/core3_real_data/task_confidence_calculator.py
apps/api-server/app/services/core3_real_data/task_business_reason_builder.py
apps/api-server/app/services/core3_real_data/task_evidence_breakdown_builder.py
apps/api-server/app/services/core3_real_data/task_review_issue_builder.py
apps/api-server/app/services/core3_real_data/task_invalidation_publisher.py
apps/api-server/app/services/core3_real_data/user_task_service.py
apps/api-server/app/services/core3_real_data/user_task_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `user_task_schemas.py` | M09 内部 typed contracts、枚举、runner summary |
| `user_task_repositories.py` | 读取 M08 输入、写入 M09 输出、查询 current 结果 |
| `task_seed_loader.py` | 读取 `tv_core3_mvp_seed_v0_2.json`、校验 10 个任务、生成 seed hash |
| `m09_feature_view_loader.py` | 加载并校验 M08 M09 feature view、profile、evidence matrix |
| `task_candidate_builder.py` | 生成 SKU x 任务候选、拒绝、阻塞和候选原因 |
| `task_domain_scorer.py` | 分别计算参数、卖点、评论、市场支撑分和代表证据 |
| `task_risk_evaluator.py` | 计算风险扣分、封顶、复核原因 |
| `task_relation_classifier.py` | 根据得分、证据域覆盖和封顶结果输出关系等级 |
| `task_confidence_calculator.py` | 计算 M09 task confidence |
| `task_business_reason_builder.py` | 生成业务中文解释和结构化中文解释片段 |
| `task_evidence_breakdown_builder.py` | 生成分域证据拆分记录 |
| `task_review_issue_builder.py` | 生成 task 级和 SKU 级复核问题 |
| `task_invalidation_publisher.py` | M09 result hash 变化时登记 M10-M16 下游失效 |
| `user_task_service.py` | M09 编排 service |
| `user_task_runner.py` | M09 runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0016_core3_real_data_user_task.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0016_core3_real_data_user_task.py` | 新增 M09 4 张输出表、索引、唯一键、枚举约束 |
| `core3_real_data.py` schema | 导出 M09 运行、任务列表、任务详情、证据拆分和复核问题 response |
| `core3_real_data.py` API | 增加 M09 v2 API，不能影响旧接口 |
| `constants.py` | 补 M09 task code、candidate status、relation level、evidence domain、review issue type |
| `runner.py` | 注册 M09 runner，不改变 M00-M08 逻辑 |
| `conftest.py` | 增加 M08 输入 fixture、任务 seed fixture、85E7Q fixture |

如果 Alembic 当前最新编号不是 `0015`，编码时按最新编号顺延，但 migration 内容仍只能包含 M09 表、索引、约束。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m09_task_seed_loader.py
apps/api-server/tests/core3_real_data/test_m09_feature_view_loader.py
apps/api-server/tests/core3_real_data/test_m09_candidate_builder.py
apps/api-server/tests/core3_real_data/test_m09_domain_scorer.py
apps/api-server/tests/core3_real_data/test_m09_risk_evaluator.py
apps/api-server/tests/core3_real_data/test_m09_relation_classifier.py
apps/api-server/tests/core3_real_data/test_m09_confidence_calculator.py
apps/api-server/tests/core3_real_data/test_m09_business_reason_builder.py
apps/api-server/tests/core3_real_data/test_m09_evidence_breakdown_builder.py
apps/api-server/tests/core3_real_data/test_m09_review_issue_builder.py
apps/api-server/tests/core3_real_data/test_m09_repositories.py
apps/api-server/tests/core3_real_data/test_m09_runner.py
apps/api-server/tests/core3_real_data/test_m09_api.py
apps/api-server/tests/core3_real_data/test_m09_no_business_outputs.py
apps/api-server/tests/core3_real_data/test_m09_85e7q_fixture.py
```

## 5. 不允许改文件

本模块开发时不得修改以下范围：

```text
apps/web/
apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json
docs/core3_mvp/real_data_v2/sop_requirements/
docs/core3_mvp/real_data_v2/sop_detailed_design/
cankao/
```

不得在 M09 中改动或重写：

- M00-M08 已有 migration 的业务含义。
- M03 参数抽取逻辑。
- M04a/M04b 卖点激活逻辑。
- M05/M06 评论抽取和下游信号逻辑。
- M07 市场画像和可比池逻辑。
- M08 SKU 画像和 feature view 口径。
- 205 部署脚本或 nginx 配置。

如果发现上游 M08 特征不够，M09 只输出 `blocked` 或 `review_required`，不能在本模块绕过 M08 重新拼装散表。

## 6. 数据库迁移任务

### 6.1 新增 migration

新增：

```text
apps/api-server/alembic/versions/0016_core3_real_data_user_task.py
```

新增 4 张表：

| 表 | 粒度 | 用途 |
| --- | --- | --- |
| `core3_sku_task_candidate` | SKU + task + input fingerprint | 记录进入候选、被拒绝、阻塞或需复核的原因 |
| `core3_sku_task_score` | SKU + task + rule version | 记录任务分、关系等级、置信度和业务解释 |
| `core3_sku_task_evidence_breakdown` | SKU + task + evidence domain | 记录参数、卖点、评论、市场、风险、seed、profile 分域证据 |
| `core3_sku_task_review_issue` | SKU + task 或 SKU 级 issue | 记录复核问题和阻塞原因 |

### 6.2 通用字段

4 张输出表都必须保留：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid/text | 是 | 主键 |
| `project_id` | text | 是 | 项目 ID |
| `category_code` | text | 是 | MVP 为 `TV` |
| `batch_id` | text | 是 | 批次 ID |
| `run_id` | text | 否 | 全链路运行 ID |
| `module_run_id` | text | 否 | M09 模块运行 ID |
| `sku_code` | text | 是 | SKU 编号 |
| `model_code` | text | 否 | 真实样例中如 `TV00029115` |
| `model_name` | text | 否 | 真实样例中如 `85E7Q` |
| `rule_version` | text | 是 | 默认 `core3_mvp_real_data_v2_m09_v1` |
| `task_seed_version` | text | 是 | 默认 `tv_core3_mvp_seed_v0_2` |
| `task_seed_file_version` | text | 是 | seed 文件内 `core3-mvp-0.2.0` |
| `task_seed_hash` | text | 是 | seed 文件内容 hash |
| `profile_hash` | text | 是 | M08 SKU profile hash |
| `feature_view_hash` | text | 是 | M08 M09 view hash |
| `input_fingerprint` | text | 是 | 输入指纹 |
| `result_hash` | text | 是 | 输出内容 hash |
| `is_current` | boolean | 是 | 是否当前版本 |
| `processing_status` | text | 是 | `success`、`warning`、`review_required`、`blocked`、`failed` |
| `review_required` | boolean | 是 | 是否需要复核 |
| `review_status` | text | 是 | `auto_pass`、`review_required`、`approved`、`rejected`、`waived` |
| `review_reason_json` | jsonb | 是 | 复核原因 |
| `created_at` | timestamptz | 是 | 创建时间 |
| `updated_at` | timestamptz | 是 | 更新时间 |

### 6.3 `core3_sku_task_candidate`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `task_code` | text | 是 | 10 个 seed 任务之一 |
| `task_name_cn` | text | 是 | 中文业务名 |
| `candidate_status` | text | 是 | `active`、`rejected`、`review_required`、`blocked` |
| `candidate_sources_json` | jsonb | 是 | 命中的来源数组：param、claim、comment、market、price_perception、service_signal、seed_gap |
| `candidate_source_count` | integer | 是 | 有效来源数 |
| `initial_candidate_score` | numeric | 是 | 候选初始分 |
| `candidate_reason_cn` | text | 是 | 中文候选原因 |
| `candidate_reason_parts_json` | jsonb | 是 | 参数、卖点、评论、市场候选原因拆分 |
| `candidate_evidence_refs_json` | jsonb | 是 | 候选代表 evidence refs |
| `rejected_reason_json` | jsonb | 是 | 被拒绝原因 |
| `blocked_reason_json` | jsonb | 是 | 阻塞原因 |

唯一键：

```text
ux_m09_task_candidate_current(project_id, category_code, batch_id, sku_code, task_code, rule_version, task_seed_hash)
  where is_current = true
```

索引：

- `(project_id, category_code, batch_id, sku_code, is_current)`
- `(project_id, category_code, batch_id, task_code, candidate_status, is_current)`
- `(project_id, category_code, batch_id, input_fingerprint)`
- GIN `candidate_sources_json`

### 6.4 `core3_sku_task_score`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `task_code` | text | 是 | 10 个 seed 任务之一 |
| `task_name_cn` | text | 是 | 中文业务名 |
| `candidate_id` | text | 否 | 对应 candidate |
| `task_score` | numeric | 是 | 封顶和扣分后的任务分 |
| `raw_task_score` | numeric | 是 | 封顶前任务分 |
| `relation_level` | text | 是 | `main`、`secondary`、`weak`、`insufficient`、`blocked` |
| `confidence` | numeric | 是 | 置信度 |
| `param_signal_score` | numeric | 是 | 参数支撑分 |
| `claim_signal_score` | numeric | 是 | 卖点支撑分 |
| `comment_signal_score` | numeric | 是 | 评论支撑分 |
| `market_signal_score` | numeric | 是 | 市场支撑分 |
| `risk_penalty` | numeric | 是 | 风险扣分 |
| `cap_applied_json` | jsonb | 是 | 封顶规则，如 comment_only、service_only、single_param_only |
| `evidence_domain_coverage_json` | jsonb | 是 | 四域覆盖状态 |
| `business_reason_cn` | text | 是 | 业务中文解释 |
| `business_reason_parts_json` | jsonb | 是 | 中文解释拆分 |
| `next_module_payload_json` | jsonb | 是 | M10-M15 可消费的精简 payload |

唯一键：

```text
ux_m09_task_score_current(project_id, category_code, batch_id, sku_code, task_code, rule_version, task_seed_hash)
  where is_current = true
```

索引：

- `(project_id, category_code, batch_id, sku_code, relation_level, is_current)`
- `(project_id, category_code, batch_id, task_code, relation_level, is_current)`
- `(project_id, category_code, batch_id, task_score desc)`
- `(project_id, category_code, batch_id, confidence desc)`
- `(profile_hash, feature_view_hash, task_seed_hash, rule_version)`
- GIN `cap_applied_json`
- GIN `next_module_payload_json`

### 6.5 `core3_sku_task_evidence_breakdown`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `task_code` | text | 是 | 10 个 seed 任务之一 |
| `task_score_id` | text | 否 | 对应 score |
| `evidence_domain` | text | 是 | `param`、`claim`、`comment`、`market`、`risk`、`seed`、`profile` |
| `support_level` | text | 是 | `strong`、`medium`、`weak`、`missing`、`conflict`、`not_applicable` |
| `domain_score` | numeric | 是 | 该域得分 |
| `domain_weight` | numeric | 是 | 该任务该域权重 |
| `weighted_score` | numeric | 是 | 加权贡献 |
| `evidence_count` | integer | 是 | 证据数量 |
| `dedup_comment_count` | integer | 否 | 评论域去重评论数 |
| `effective_sentence_count` | integer | 否 | 评论域有效句子数 |
| `evidence_refs_json` | jsonb | 是 | evidence refs |
| `source_feature_refs_json` | jsonb | 是 | M08 feature refs |
| `domain_reason_cn` | text | 是 | 中文分域原因 |
| `domain_risk_json` | jsonb | 是 | 缺失、冲突和风险 |

唯一键：

```text
ux_m09_task_breakdown_current(project_id, category_code, batch_id, sku_code, task_code, evidence_domain, rule_version, task_seed_hash)
  where is_current = true
```

索引：

- `(project_id, category_code, batch_id, sku_code, task_code, is_current)`
- `(project_id, category_code, batch_id, evidence_domain, support_level, is_current)`
- GIN `evidence_refs_json`
- GIN `source_feature_refs_json`

### 6.6 `core3_sku_task_review_issue`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `task_code` | text | 否 | 为空表示 SKU 级问题 |
| `issue_type` | text | 是 | 复核类型 |
| `issue_severity` | text | 是 | `info`、`warning`、`blocking` |
| `issue_status` | text | 是 | `open`、`resolved`、`waived` |
| `issue_reason_cn` | text | 是 | 中文复核原因 |
| `issue_detail_json` | jsonb | 是 | 结构化复核详情 |
| `affected_output_json` | jsonb | 是 | 影响的候选、得分或关系等级 |
| `evidence_refs_json` | jsonb | 是 | 相关证据 |
| `suggested_action_cn` | text | 是 | 建议复核动作 |

`issue_type` 至少覆盖：

```text
missing_feature_view
missing_feature
conflict
comment_only
service_only
single_param_only
market_limited
claim_missing
comment_quality_risk
seed_gap
high_score_contradiction
profile_blocked
missing_structured_claim
param_only
unknown_input
```

唯一键：

```text
ux_m09_task_review_issue_current(project_id, category_code, batch_id, sku_code, coalesce(task_code, ''), issue_type, input_fingerprint)
  where is_current = true
```

索引：

- `(project_id, category_code, batch_id, issue_status, issue_severity, is_current)`
- `(project_id, category_code, batch_id, sku_code, issue_type, is_current)`
- `(project_id, category_code, batch_id, task_code, issue_type, is_current)`

## 7. model/schema 任务

### 7.1 枚举

在 `user_task_schemas.py` 和必要的 API schema 中定义：

```text
TaskCandidateStatus = active | rejected | review_required | blocked
TaskCandidateSource = param | claim | comment | market | price_perception | service_signal | seed_gap
TaskRelationLevel = main | secondary | weak | insufficient | blocked
TaskEvidenceDomain = param | claim | comment | market | risk | seed | profile
TaskSupportLevel = strong | medium | weak | missing | conflict | not_applicable
TaskReviewIssueType = missing_feature_view | missing_feature | conflict | comment_only | service_only | single_param_only | market_limited | claim_missing | comment_quality_risk | seed_gap | high_score_contradiction | profile_blocked | missing_structured_claim | param_only | unknown_input
```

### 7.2 seed schema

新增 typed contracts：

| schema | 关键字段 |
| --- | --- |
| `UserTaskSeedSet` | `category_code`、`file_version`、`task_seed_version`、`task_seed_hash`、`tasks` |
| `UserTaskSeed` | `task_code`、`task_name_cn`、`definition_cn`、`aliases`、`keywords`、`score_rule` |
| `TaskScoreRule` | `claim_weight`、`param_weight`、`comment_weight`、`market_weight`、阈值、封顶规则 |
| `TaskMappingRule` | 参数、卖点、评论主题、市场信号映射 |

必须校验 10 个任务：

```text
TASK_LIVING_ROOM_CINEMA
TASK_PREMIUM_PICTURE_AV
TASK_GAMING_ENTERTAINMENT
TASK_SPORTS_WATCHING
TASK_LARGE_SCREEN_REPLACEMENT
TASK_CHILD_EYE_CARE
TASK_SENIOR_EASY_USE
TASK_VALUE_PURCHASE
TASK_NEW_HOME_DECORATION
TASK_BEDROOM_SECOND_TV
```

M09 必须以真实 seed 的 10 个任务为准，不能使用旧 SOP 参考中 8 个任务，也不能临时新增任务。

### 7.3 M08 输入 schema

新增：

| schema | 用途 |
| --- | --- |
| `M09FeatureViewInput` | 承载 M08 `for_module='M09'` 特征包 |
| `M09SkuProfileInput` | 承载 M08 SKU profile 摘要、状态和 `profile_hash` |
| `M09EvidenceMatrixInput` | 承载 M08 分域 evidence matrix |
| `M09TaskFeatureBundle` | 合并 profile、feature view、evidence matrix 后的单 SKU 输入 |

输入 schema 必须表达：

- `profile_status`
- `profile_hash`
- `feature_view_hash`
- `input_fingerprint`
- `domain_completeness_json`
- `missing_signals_json`
- `risk_signals_json`
- 参数任务特征
- 卖点任务特征
- 评论 `task_cue` 特征
- 价格感知特征
- 服务信号特征
- 市场和可比池特征
- evidence refs

### 7.4 输出 schema

新增：

| schema | 用途 |
| --- | --- |
| `TaskCandidateRecord` | 对应 `core3_sku_task_candidate` |
| `TaskDomainScore` | 参数、卖点、评论、市场单域评分 |
| `TaskRiskDecision` | 风险扣分、封顶和复核 |
| `TaskScoreRecord` | 对应 `core3_sku_task_score` |
| `TaskEvidenceBreakdownRecord` | 对应 `core3_sku_task_evidence_breakdown` |
| `TaskReviewIssueRecord` | 对应 `core3_sku_task_review_issue` |
| `M09RunRequest` | runner/API 请求 |
| `M09RunSummary` | 运行汇总 |
| `SkuTaskListResponse` | SKU 任务列表 API 返回 |
| `SkuTaskDetailResponse` | 单任务详情 API 返回 |
| `SkuTaskEvidenceResponse` | 证据拆分 API 返回 |

输出 schema 必须避免把内部调试字段直接暴露给前端高层页面。API 可以返回机器字段，但业务页面消费时必须有中文业务字段。

## 8. repository 任务

### 8.1 读取职责

`UserTaskRepository` 只允许读取：

| 来源 | 查询 |
| --- | --- |
| M08 profile | `core3_sku_signal_profile where is_current=true` |
| M08 feature view | `core3_sku_downstream_feature_view where for_module='M09' and is_current=true` |
| M08 evidence matrix | `core3_sku_signal_evidence_matrix where is_current=true` |
| M02 evidence atom | 仅按 M08 evidence refs 批量回溯，不做业务扫描 |
| M09 历史输出 | 查询可复用 current 记录和旧版本失效 |

不得增加以下 repository 查询：

- 直接查 `week_sales_data`。
- 直接查 `attribute_data`。
- 直接查 `selling_points_data`。
- 直接查 `comment_data`。
- 直接查 M03/M04b/M06/M07 散表做业务判断。

### 8.2 写入职责

`UserTaskRepository` 必须支持：

1. `mark_previous_records_not_current(...)`
2. `bulk_insert_candidates(...)`
3. `bulk_insert_scores(...)`
4. `bulk_insert_evidence_breakdowns(...)`
5. `bulk_insert_review_issues(...)`
6. `get_current_task_scores(...)`
7. `get_task_detail(...)`
8. `get_task_evidence_breakdown(...)`
9. `list_review_issues(...)`

写入约定：

- 同一 SKU、task、rule、seed hash 的新结果写入前，旧 current 记录必须置为 `is_current=false`。
- 写入 candidate、score、breakdown、review issue 必须在同一事务内完成。
- 任一 SKU feature view 缺失时，该 SKU 的 10 个任务应写 `blocked` 或复核问题，不能静默跳过。
- repository 不计算业务分，只负责持久化和查询。

### 8.3 查询返回顺序

SKU 任务列表默认排序：

1. `relation_level` 按 main、secondary、weak、insufficient、blocked。
2. `task_score desc`。
3. `confidence desc`。
4. seed 中任务顺序。

任务详情必须返回：

- 任务中文名。
- 关系等级。
- 分数和置信度。
- 四域得分。
- 业务解释。
- 分域证据拆分。
- 复核问题。

## 9. service 任务

### 9.1 编排流程

`UserTaskService.run(...)` 按以下步骤执行：

1. 构建 run context 和 `module_run_id`。
2. 加载并校验任务 seed。
3. 读取 SKU 范围内 M08 profile、M09 feature view、evidence matrix。
4. 对缺失 M08 feature view 的 SKU 生成 `missing_feature_view` 阻塞问题。
5. 对每个有效 SKU 遍历 10 个 seed 任务。
6. `TaskCandidateBuilder` 生成候选、拒绝或阻塞。
7. `TaskDomainScorer` 计算参数、卖点、评论、市场四域支撑分。
8. `TaskRiskEvaluator` 应用风险扣分、封顶和复核规则。
9. `TaskRelationClassifier` 输出关系等级。
10. `TaskConfidenceCalculator` 输出置信度。
11. `TaskBusinessReasonBuilder` 生成中文业务解释。
12. `TaskEvidenceBreakdownBuilder` 生成分域证据拆分。
13. `TaskReviewIssueBuilder` 生成复核问题。
14. 计算 `result_hash`，判断是否需要写入或复用。
15. 事务写入 4 张输出表。
16. `TaskInvalidationPublisher` 登记 M10-M16 下游失效。
17. 返回 `M09RunSummary`。

### 9.2 候选生成规则

候选遍历粒度必须是 SKU x 10 个 seed 任务。进入候选的条件满足任一即可：

| 触发来源 | 条件 |
| --- | --- |
| 参数触发 | 命中任务核心参数，参数值不是 `unknown`，且参数初始支撑达到最低阈值 |
| 卖点触发 | 命中任务核心卖点，状态为 high/medium，或存在可解释的 `param_only` 技术支撑 |
| 评论触发 | M08 汇总的 M06 `task_cue` 命中任务主题，并满足去重评论或有效句子阈值 |
| 市场触发 | 命中任务所需的价格带、销量、价格每英寸、平台或可比池信号 |
| 价格感知触发 | 支撑 `TASK_VALUE_PURCHASE` 或 `TASK_LARGE_SCREEN_REPLACEMENT` |
| 服务信号触发 | 只可侧面支撑 `TASK_NEW_HOME_DECORATION`，不能支撑画质、游戏、体育等产品任务 |

候选初始分建议：

```text
initial_candidate_score =
  max(param_candidate_score, claim_candidate_score, comment_candidate_score, market_candidate_score)
  + min(candidate_source_count * 0.05, 0.15)
  - candidate_risk_penalty
```

### 9.3 分域评分规则

任务得分按 seed `score_rule` 权重计算：

```text
raw_task_score =
  claim_signal_score * claim_weight
  + param_signal_score * param_weight
  + comment_signal_score * comment_weight
  + market_signal_score * market_weight

task_score = clamp(raw_task_score - risk_penalty, 0, 1)
```

分域要求：

| 域 | 输入 | 评分要求 |
| --- | --- | --- |
| 参数 | M08 参数画像和 M09 view 参数特征 | unknown 不当 false；数值参数按阈值或可比池分位；冲突进入风险 |
| 卖点 | M08 最终卖点激活和证据拆分 | 缺结构化卖点不能归零；`param_only` 可支撑但要复核或降置信 |
| 评论 | M08 汇总的 M06 `task_cue` | 必须使用去重评论和有效句子；纯物流安装不支撑产品任务 |
| 市场 | M08 市场画像和可比池摘要 | 使用价格带、销量、价格每英寸、渠道、样本状态；样本不足触发复核 |

### 9.4 封顶和复核规则

必须实现以下封顶：

| 条件 | 处理 |
| --- | --- |
| `comment_only` | 仅评论命中时，最高 `weak`，如果接近 secondary 阈值则复核 |
| `service_only` | 仅服务信号命中时，最高 `weak`，且只允许影响新家装修搭配侧面 |
| `single_param_only` | 仅单个参数命中时，最高 `weak` |
| `missing_structured_claim` | 结构化卖点缺失但任务依赖卖点时，最高 `secondary` 并复核 |
| `param_only` | 仅参数支撑技术任务时，可候选但业务解释必须说明缺少宣传或用户反馈证据 |
| `market_limited` | 市场样本不足且市场权重大，最高 `secondary` 并复核 |
| `conflict` | 参数、评论或市场冲突时，最高 `secondary` 并复核 |
| `missing_feature_view` | 缺 M08 M09 feature view 时，关系等级 `blocked` |
| `profile_blocked` | M08 profile blocked 时，关系等级 `blocked` |

`unknown`、空值和 `-` 只能降低完整度或触发 `unknown_input`，不能生成负向结论。

### 9.5 关系等级

默认判定：

| relation_level | 条件 |
| --- | --- |
| `main` | `task_score >= 0.75`，至少 3 个证据域支撑，且参数或卖点有效 |
| `secondary` | `0.60 <= task_score < 0.75`，至少 2 个证据域支撑，且不是仅评论 |
| `weak` | `0.40 <= task_score < 0.60`，或被封顶到 weak |
| `insufficient` | `task_score < 0.40`，证据不足 |
| `blocked` | 缺 M08 feature view、profile blocked 或 seed 校验阻塞 |

被封顶规则覆盖时，以更低等级为准。

### 9.6 置信度

置信度建议公式：

```text
confidence =
  task_score * 0.35
  + evidence_domain_coverage_score * 0.25
  + m08_profile_confidence * 0.20
  + evidence_quality_score * 0.20
  - confidence_risk_penalty
```

置信度必须受以下因素影响：

- M08 profile confidence。
- evidence domain 覆盖数量。
- evidence refs 是否可回溯。
- 评论去重质量。
- 市场样本状态。
- 结构化卖点缺失。
- 参数 unknown 或口径冲突。

### 9.7 中文业务解释

`TaskBusinessReasonBuilder` 输出：

```text
business_reason_parts_json.ability_basis_cn
business_reason_parts_json.value_expression_cn
business_reason_parts_json.user_feedback_cn
business_reason_parts_json.market_validation_cn
business_reason_parts_json.review_points_cn
business_reason_cn
```

业务解释要求：

- 使用业务语言说明“为什么这个 SKU 服务这个用户任务”。
- 先说能力基础，再说用户反馈和市场验证，最后说待复核点。
- 不出现 SQL、JSON、字段名、公式、内部 code、`task_cue`、`profile_hash`、`feature_view_hash`、“AI判断”等字样。
- 对缺结构化卖点的 85E7Q，要说“当前缺少结构化卖点资料，需要复核宣传证据”，不能说“无卖点”。
- 对评论单域命中，要说“用户反馈提供线索，但缺少参数/卖点/市场共同支撑”，不能输出高置信主任务。

## 10. runner/API 任务

### 10.1 runner

新增 runner：

```python
run_m09_user_task(
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_codes: list[str] | None = None,
    task_codes: list[str] | None = None,
    force: bool = False,
    task_seed_version: str = "tv_core3_mvp_seed_v0_2",
    rule_version: str = "core3_mvp_real_data_v2_m09_v1",
) -> M09RunSummary
```

runner 要求：

- 默认处理 batch 内所有有 M08 profile 或 M08 M09 feature view 的 SKU。
- `task_codes` 不传时必须遍历 10 个 seed 任务。
- `force=false` 时复用 hash 未变化的历史 current 结果。
- `force=true` 时重算并写新版本。
- seed 校验阻塞时本次 run 标记 failed 或 blocked，不写半成品业务结论。
- 单 SKU 缺 feature view 时只阻塞该 SKU，不影响其他 SKU。

### 10.2 API

新增 v2 API：

```text
POST /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/runs/m09-user-task
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/runs/{run_id}/m09
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/tasks
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/tasks/{task_code}
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/tasks/{task_code}/evidence
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/task-review-issues
```

API response 要求：

- 支持按 `relation_level`、`task_code`、`review_required`、`processing_status` 过滤。
- SKU 任务列表默认只返回 current 结果。
- 任务详情返回中文任务名、关系等级、四域得分、业务解释、证据拆分和复核点。
- 证据接口返回 M08/M02 refs，不重新读取原始表。
- API 不应直接作为高层页文案；高层页最终呈现由 M15/FRONTEND 设计转换。

## 11. 增量策略

### 11.1 输入指纹

`input_fingerprint` 至少包含：

```text
project_id
category_code
batch_id
sku_code
task_code
profile_hash
feature_view_hash
M08 evidence matrix result_hash
task_seed_hash
task_seed_version
task_seed_file_version
rule_version
threshold_version
cap_rule_version
```

### 11.2 可复用条件

历史结果可复用必须同时满足：

- M08 `profile_hash` 未变化。
- M08 M09 `feature_view_hash` 未变化。
- M08 evidence matrix 相关 `result_hash` 未变化。
- `task_seed_hash` 未变化。
- `task_seed_version` 未变化。
- `rule_version`、阈值版本、封顶规则版本未变化。
- 历史记录 `is_current=true`。
- 历史记录 `processing_status` 不是 `failed` 或 `blocked`。

### 11.3 下游失效

M09 任一 SKU 的 task score、relation level、confidence、review status 或 business payload 变化时，必须登记下游影响：

```text
M10 target group
M11 battlefield
M11.5 claim value layer
M12 candidate recall
M13 component scoring
M14 core3 selection
M15 evidence report
M16 review acceptance
```

失效 payload 至少包含：

- `changed_sku_code`
- `changed_task_codes`
- `old_result_hash`
- `new_result_hash`
- `affected_modules`
- `reason="m09_user_task_changed"`

## 12. 真实数据和 fixture 验收

### 12.1 样例数据约束

开发测试必须体现真实样例数据约束：

- 市场窗口为 `26W01` 到 `26W23`，不能出现 12 月口径。
- 当前样例市场模型约 35 个，参数约 35 个，评论约 33 个，结构化卖点约 5 个。
- 当前样例均为海信品牌，不能按内部/外部品牌过滤；海信 SKU 也可以互为竞品或任务参照。
- 当前市场数据主要是线上，含专业电商、平台电商；不能推导线下任务结论。
- 评论存在重复、拆句和通用好评，必须依赖 M05/M06/M08 的去重和有效句子口径。
- 参数缺失、卖点缺失、评论缺失只表示 unknown 或证据不足，不能当 false。

### 12.2 85E7Q 验收样例

85E7Q fixture 必须包含：

| 项 | 值 |
| --- | --- |
| `model_code` | `TV00029115` |
| `model_name` | `85E7Q` |
| 参数 | 85 英寸、4K、300HZ、Mini LED、5200 亮度、3500 分区、HDMI2.1、4GB/64GB、海信星海 |
| 评论 | 原始评论约 3621 条，去重评论 ID 可覆盖 `1648` |
| 市场 | `26W01` 到 `26W23`，线上，专业电商、平台电商 |
| 结构化卖点 | 缺失或不足，必须触发 `missing_structured_claim` |

85E7Q 任务预期：

| 任务 | 预期 |
| --- | --- |
| 高端画质影音 | Mini LED、亮度、分区、画质评论、高端价格带可支撑；缺结构化卖点需复核 |
| 客厅影院观影 | 85 英寸、4K、高亮、大屏家庭评论、市场可支撑；不能无证据扩展音响能力 |
| 体育赛事观看 | 高刷和运动/看球评论可支撑；需与游戏娱乐区分 |
| 游戏娱乐 | 高刷、HDMI2.1 可进入候选；缺低延迟/VRR/游戏评论时不应直接 main |
| 大屏换新 | 85 英寸、价格每英寸、销量、尺寸空间评论可支撑；需要 M07 可比池验证 |
| 性价比购买 | 需要价格分位、销量、促销或价格评论；如果价格不低只能 weak 或 insufficient |
| 新家装修搭配 | 尺寸空间、外观、挂装、安装服务评论可侧面支撑；纯安装不能替代产品任务 |
| 儿童护眼 | 需要护眼参数或儿童家庭评论；无证据不能高分 |
| 长辈易用 | 需要语音、长辈模式、易用评论；无证据不能高分 |
| 卧室/副屏 | 85E7Q 不应泛化为卧室/副屏主任务 |

## 13. 测试任务

### 13.1 seed loader 测试

`test_m09_task_seed_loader.py`：

- `test_task_seed_has_10_tasks`
- `test_task_seed_rejects_missing_required_task`
- `test_task_seed_rejects_weight_sum_not_one`
- `test_task_seed_hash_is_stable`
- `test_task_seed_uses_real_v0_2_names_not_old_8_task_reference`

### 13.2 feature view loader 测试

`test_m09_feature_view_loader.py`：

- `test_m09_loads_only_m08_feature_view`
- `test_m09_blocks_without_feature_view`
- `test_m09_does_not_query_raw_tables`
- `test_profile_blocked_becomes_task_blocked`
- `test_unknown_input_preserved_as_unknown`

### 13.3 candidate builder 测试

`test_m09_candidate_builder.py`：

- `test_candidate_created_by_param_trigger`
- `test_candidate_created_by_claim_trigger`
- `test_candidate_created_by_comment_trigger_with_dedup_threshold`
- `test_candidate_created_by_market_trigger`
- `test_service_signal_only_limited_to_new_home_decoration`
- `test_missing_feature_view_generates_blocked_candidates`
- `test_candidate_and_score_separated`

### 13.4 scorer 和 risk 测试

`test_m09_domain_scorer.py`、`test_m09_risk_evaluator.py`：

- `test_unknown_param_not_false`
- `test_missing_structured_claim_does_not_zero_task`
- `test_market_unknown_signal_not_negative`
- `test_comment_only_capped_to_weak`
- `test_service_only_not_product_task`
- `test_single_param_only_capped_to_weak`
- `test_param_only_sets_review_reason`
- `test_market_limited_caps_secondary`
- `test_conflict_caps_secondary`

### 13.5 relation 和 confidence 测试

`test_m09_relation_classifier.py`、`test_m09_confidence_calculator.py`：

- `test_main_requires_three_domains_and_param_or_claim`
- `test_secondary_requires_two_domains_not_comment_only`
- `test_weak_for_low_score_or_cap`
- `test_blocked_for_missing_feature_view`
- `test_confidence_uses_profile_confidence`
- `test_confidence_penalizes_low_evidence_quality`

### 13.6 business reason 测试

`test_m09_business_reason_builder.py`、`test_m09_no_business_outputs.py`：

- `test_business_reason_cn_no_internal_tokens`
- `test_business_reason_mentions_missing_structured_claim_as_review_point`
- `test_business_reason_does_not_say_ai_judgement`
- `test_business_reason_does_not_expose_sql_json_formula`
- `test_comment_only_reason_is_business_warning_not_main_conclusion`

### 13.7 repository、runner、API 测试

`test_m09_repositories.py`、`test_m09_runner.py`、`test_m09_api.py`：

- `test_repository_marks_previous_current_false`
- `test_repository_writes_four_output_tables_in_transaction`
- `test_runner_skips_when_input_fingerprint_unchanged`
- `test_runner_force_recomputes`
- `test_runner_invalidates_m10_to_m16_on_result_hash_change`
- `test_api_runs_m09`
- `test_api_lists_sku_tasks_sorted_by_relation_and_score`
- `test_api_returns_task_evidence_breakdown`
- `test_api_lists_review_issues`

### 13.8 85E7Q fixture 测试

`test_m09_85e7q_fixture.py`：

- `test_85e7q_premium_picture_supported_with_missing_claim_review`
- `test_85e7q_living_room_cinema_supported_by_size_picture_market`
- `test_85e7q_sports_distinguished_from_gaming`
- `test_85e7q_gaming_not_main_without_game_specific_evidence`
- `test_85e7q_large_screen_replacement_uses_market_pool`
- `test_85e7q_value_purchase_not_high_if_price_not_low`
- `test_85e7q_child_eye_care_not_high_without_eye_care_evidence`
- `test_85e7q_senior_easy_use_not_high_without_ease_evidence`
- `test_85e7q_bedroom_second_tv_not_main_for_85_inch`
- `test_85e7q_comment_count_and_dedup_refs_preserved`

## 14. 开发子任务拆分

### M09-1 迁移和 schema

目标：

- 创建 `0016_core3_real_data_user_task.py`。
- 创建 `user_task_schemas.py`。
- 在 API schema 中暴露必要 response。

验收：

- 4 张表、唯一键、索引存在。
- task seed、candidate、score、breakdown、review issue schema 可实例化。
- enum 覆盖全部设计值。

### M09-2 seed loader

目标：

- 实现 `TaskSeedLoader`。
- 校验 `tv_core3_mvp_seed_v0_2.json` 中 10 个真实任务。
- 生成 `task_seed_hash`。

验收：

- seed 版本、文件版本、hash 可写入输出。
- 缺任务、权重不为 1、重复 task code 均阻塞。

### M09-3 M08 输入加载

目标：

- 实现 `M09FeatureViewLoader`。
- 只读取 M08 profile、M09 feature view、evidence matrix。

验收：

- 缺 feature view 输出 `missing_feature_view`。
- profile blocked 输出 blocked。
- 单元测试证明不直接读取原始表和上游散表。

### M09-4 候选生成

目标：

- 实现 `TaskCandidateBuilder`。
- 对 SKU x 10 任务生成 active、rejected、review_required、blocked。

验收：

- 参数、卖点、评论、市场、价格感知、服务信号触发均可覆盖。
- 服务信号不支撑画质、游戏、体育等产品任务。
- 候选和最终得分分离。

### M09-5 分域评分

目标：

- 实现 `TaskDomainScorer`。
- 输出 param、claim、comment、market 四域分。

验收：

- unknown 不当 false。
- 缺结构化卖点不归零。
- 评论必须使用去重评论和有效句子。
- 市场样本不足不生成负向结论。

### M09-6 风险、关系、置信度

目标：

- 实现 `TaskRiskEvaluator`、`TaskRelationClassifier`、`TaskConfidenceCalculator`。

验收：

- `comment_only` 最高 weak。
- `service_only` 最高 weak。
- `single_param_only` 最高 weak。
- `missing_structured_claim` 最高 secondary 并复核。
- main 必须有至少 3 域支撑且参数或卖点有效。

### M09-7 业务解释和证据拆分

目标：

- 实现 `TaskBusinessReasonBuilder`。
- 实现 `TaskEvidenceBreakdownBuilder`。
- 实现 `TaskReviewIssueBuilder`。

验收：

- 中文解释不出现内部字段、SQL、JSON、公式或 AI 过程性语言。
- 分域证据可以回溯 M08/M02 refs。
- 复核 issue 覆盖阻塞、封顶、缺失、冲突、样本不足。

### M09-8 repository、runner、API

目标：

- 实现 `UserTaskRepository`。
- 实现 `UserTaskService` 和 `run_m09_user_task`。
- 注册 v2 API。

验收：

- 事务写入 4 张表。
- `force=false` 可按 input fingerprint 跳过。
- result hash 变化登记 M10-M16 下游失效。
- API 可查询 SKU 任务列表、任务详情、证据拆分、复核问题。

### M09-9 真实 fixture 和回归测试

目标：

- 构造 85E7Q fixture。
- 覆盖真实样例数据约束。

验收：

- 85E7Q 高端画质、客厅影院、体育观看、大屏换新按真实证据支撑。
- 游戏娱乐不因高刷/HDMI2.1 单独升为 main。
- 儿童护眼、长辈易用、卧室/副屏无证据不高分。
- 缺结构化卖点触发复核而不是伪造卖点。

## 15. 完成标准

M09 开发完成必须满足：

- migration 可升级和回滚。
- 所有新增 schema 有单元测试。
- seed loader 使用真实 `tv_core3_mvp_seed_v0_2.json` 并覆盖 10 个 MVP 任务。
- M09 不直接读取原始四表，不直接读取 M03/M04b/M06/M07 散表做业务字段判断。
- 每个 SKU x 10 任务都有 candidate 或 blocked/rejected 记录。
- score、candidate、evidence breakdown、review issue 四类输出分表保存。
- `comment_only`、`service_only`、`single_param_only`、`missing_structured_claim`、`param_only`、`market_limited`、`conflict` 等规则可测试。
- `unknown`、空值、`-` 不被当 false。
- `profile_hash`、`feature_view_hash`、`task_seed_version`、`task_seed_hash`、`rule_version` 全部落库。
- result hash 支持增量跳过和下游失效。
- 85E7Q fixture 验收通过。
- API 返回任务列表、任务详情、证据拆分和复核问题。
- 中文业务解释不包含内部字段、SQL、JSON、公式或 AI 过程性语言。
- 测试不依赖外部 LLM。

建议运行：

```text
pytest apps/api-server/tests/core3_real_data/test_m09_*.py
pytest apps/api-server/tests/core3_real_data/test_m08_*.py apps/api-server/tests/core3_real_data/test_m09_*.py
```

## 16. 风险和回滚

| 风险 | 处理 |
| --- | --- |
| M08 feature view 缺字段 | M09 输出 `missing_feature_view` 或 `missing_feature`，不绕过 M08 读散表 |
| seed 与详细设计不一致 | 以真实 seed 10 任务为准，测试锁定 task code |
| 评论噪声导致任务过度泛化 | 评论单域最高 weak，并要求去重评论和有效句子阈值 |
| 单参数导致任务过度推断 | `single_param_only` 最高 weak |
| 缺结构化卖点被误判为无卖点 | `missing_structured_claim` 降置信和复核，不归零 |
| 服务/物流评论污染产品任务 | `service_only` 仅可侧面支撑新家装修搭配 |
| 市场样本不足 | `market_limited` 降级和复核 |
| 业务解释像算法日志 | business reason 单测禁止内部 tokens |
| 增量跳过错误 | input fingerprint 覆盖 M08 hash、seed hash、rule version |

回滚方式：

- Alembic downgrade 删除 M09 4 张表。
- API 注册可按路由开关临时关闭。
- runner 注册可移除 M09，不影响 M00-M08。
- M09 输出是下游输入，回滚前需确认 M10-M16 没有依赖当前 M09 新表；若已依赖，先停止下游 runner。

## 17. 下游依赖

M10 目标客群将消费：

- `core3_sku_task_score`
- `core3_sku_task_evidence_breakdown`
- `business_reason_parts_json`
- `relation_level`
- `confidence`
- `review_required`

M11 价值战场将消费：

- main/secondary 用户任务。
- 任务的参数、卖点、评论、市场证据域覆盖。
- 高置信任务和复核任务的差异。

M12 候选召回将消费：

- SKU 任务向量。
- 任务关系等级。
- 任务置信度。
- 任务证据缺口。

M13 竞品组件评分将消费：

- 目标 SKU 和候选 SKU 的任务重合度。
- 任务关系等级差异。
- 证据域覆盖差异。

M15 高层报告将消费：

- 业务化任务解释。
- 任务证据拆分。
- 复核提示。
- 不能直接展示内部 hash、JSON、SQL、公式或 `comment_only` 等技术标签。

## 18. 下次任务

M09 完成后，下一个开发任务文档是：

```text
docs/core3_mvp/real_data_v2/development/M10_development_tasks.md
```

M10 需要基于 M09 的任务结果继续推导目标客群，不能提前在 M09 中生成客群结论。
