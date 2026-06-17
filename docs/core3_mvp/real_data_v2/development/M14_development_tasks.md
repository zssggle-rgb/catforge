# M14 三槽位核心竞品选择开发任务

## 1. 模块目标

M14 的开发目标是基于 M12 候选池和 M13 组件/角色评分，为每个目标 SKU 选择 0-3 个核心竞品，并把每个入选或未入选候选的业务角色、选择理由、证据、差异、风险和复核状态保存为 M15 可直接消费的数据结构。

M14 要回答的业务问题不是“候选总分前三是谁”，而是：

1. 目标 SKU 最值得关注的核心竞品是谁，数量可以是 0-3 个。
2. 每个核心竞品代表哪一种竞争压力：正面对打、价格/销量挤压、高端标杆/潜在下探。
3. 为什么不能按 M13 `component_total_score` 直接取前三。
4. 为什么某些候选分数不低但没有入选。
5. 如果某个槽位为空，是没有候选、证据不足、候选重复，还是需要复核。
6. 对 85E7Q 这类真实样例，如何说明同品牌内部竞争、同价位挤压、同系列替代、卖点数据缺口和服务评论边界。

M14 要解决的工程问题：

1. 固化三槽位选择结果，输出入选、空槽、未选原因和复核问题。
2. 建立 M14 独立结果表，不把选择结果混在 M13 评分表或 M15 报告表里。
3. 固化 M14 只消费 M12/M13/M08/M11/M11.5/M02 上游产物，不直接读取原始四表。
4. 固化 M14 不重新计算 M13 组件分和角色分。
5. 固化同品牌 SKU 可以入选，不能设置品牌上限。
6. 固化同系列去重按业务信息增量判断，不按品牌或型号前缀简单排除。
7. 固化服务信号只作为服务参考或风险，不进入产品核心三槽位主因。
8. 输出 M15 所需的中文业务结论、空槽说明、未选原因和 evidence 引用。
9. 输出 M16 所需的复核问题、规则版本、输入指纹和下游失效信号。

M14 必须固化以下边界：

- M14 不生成候选池，M12 负责。
- M14 不重新计算组件分、角色分或 evidence completeness，M13 负责。
- M14 不直接读取 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data`。
- M14 不读取 M12 未召回候选之外的全量 SKU。
- M14 不生成最终高层报告页面，M15 负责。
- M14 不调用 LLM 做首版选择。
- M14 不强行凑满 3 个核心竞品。
- M14 不按 `component_total_score` Top3 入选。
- M14 不排除同品牌 SKU，不设置“同一品牌最多 1 个”。
- M14 不把 85 寸、同品牌、同系列作为唯一入选理由。
- M14 不把结构化卖点缺失写成“卖点弱”，只能写成“宣传卖点数据缺口”。
- M14 不把安装、配送、客服、售后等服务评论当成产品核心竞品入选主因。
- M14 不写线下渠道、全渠道或 12 个月口径；当前真实样例只支持 `26W01-26W23` 线上口径。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M14 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M14_core3_selection_requirements.md` |
| M14 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M14_core3_selection_design.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M12 任务 | `docs/core3_mvp/real_data_v2/development/M12_development_tasks.md` |
| M13 任务 | `docs/core3_mvp/real_data_v2/development/M13_development_tasks.md` |
| M13 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M13_component_scoring_design.md` |
| M08 任务 | `docs/core3_mvp/real_data_v2/development/M08_development_tasks.md` |
| M11 任务 | `docs/core3_mvp/real_data_v2/development/M11_development_tasks.md` |
| M11.5 任务 | `docs/core3_mvp/real_data_v2/development/M11_5_development_tasks.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 方法论 | `cankao/CatForge_竞品生成SOP_详细指导_v1.md` |
| SOP 参考模块 | `cankao/catforge_sop_md/modules/M14_三槽位核心竞品选择模块.md` |
| UI 规范 | `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md` |

编码前必须确认：

- M12 已输出 current `core3_candidate_pool`。
- M12 已输出 current `core3_candidate_recall_reason`。
- M12 已输出 current `core3_candidate_feature_snapshot`。
- M13 已输出 current `core3_candidate_component_score`。
- M13 已输出 current `core3_candidate_role_score`，至少包含 `direct_fight`、`price_volume_pressure`、`benchmark_potential` 三个核心角色。
- M13 已输出 `core3_candidate_component_explanation`，可用于入选和未选理由。
- M13 已输出 `core3_candidate_score_review_issue`，M14 可读取 unresolved blocker/review 问题。
- M08 已输出目标和候选 SKU 画像、同系列信息、缺失风险和 profile hash。
- M11/M11.5 已输出战场和战场内卖点价值摘要，M14 用于中文理由和资格校验。
- M02 evidence 状态可用于证据有效性校验。
- INFRA 已提供 run context、hash 工具、current 版本约定、runner 协议、复核 issue 约定和测试 fixture 基础。

## 3. 本次范围

本次开发任务拆分覆盖 M14 后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 5 张 M14 输出表、索引、唯一键、外键和 current 版本约束 |
| model/schema | 新增三槽位、选择状态、审计决策、空槽原因、压力等级、复核问题等枚举和 Pydantic schema |
| 输入读取 | 读取 M12 候选、M13 分数/解释/问题、M08 画像、M11 战场、M11.5 卖点价值、M02 evidence 状态 |
| 槽位候选 | 构建正面对打、价格/销量挤压、高端标杆/潜在下探三个槽位候选列表 |
| 硬门槛 | 对每个槽位应用角色分、置信度、证据完整度、市场信号、语义信号和 blocker 规则 |
| 槽位选择分 | 计算 `slot_selection_score`，区别于 M13 `component_total_score` |
| 跨槽冲突 | 同一候选只能占用一个核心槽位 |
| 同系列去重 | 按业务信息增量去重，不设置品牌上限 |
| 空槽说明 | 每个目标每次运行必须输出 3 条槽位决策，空槽也要说明原因 |
| 中文结论 | 输出六层业务结论：结论、主战场、推导、证据、差异、风险 |
| 候选审计 | 对所有 M12/M13 候选输出 selected/rejected/review/blocked 审计 |
| 复核问题 | 输出 empty pool、missing role、全空、高分低证据、服务信号、重复冲突等问题 |
| 增量失效 | 用 M12/M13/evidence/rule fingerprint 控制重算，并登记 M15-M16 下游失效 |
| runner/API | 提供 M14 运行入口和技术追溯 API，业务展示由 M15 API 承接 |
| 测试 | 单元、repository、service、API、增量、边界、85E7Q fixture |

本次不做：

- 不实现 M15 证据卡或高层报告 payload。
- 不实现 M16 全链路编排和复核页面。
- 不实现前端页面。
- 不部署到 205。
- 不修改 M12 候选池召回逻辑。
- 不修改 M13 组件评分逻辑。
- 不修改 M08/M11/M11.5 上游画像和战场逻辑。
- 不对旧 `core3_mvp` 粗粒度页面做改造。
- 不启用真实 LLM 裁决。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/core3_selection_schemas.py
apps/api-server/app/services/core3_real_data/core3_selection_repositories.py
apps/api-server/app/services/core3_real_data/core3_selection_input_loader.py
apps/api-server/app/services/core3_real_data/core3_selection_policy.py
apps/api-server/app/services/core3_real_data/core3_selection_slot_candidate_builder.py
apps/api-server/app/services/core3_real_data/core3_selection_gate_checker.py
apps/api-server/app/services/core3_real_data/core3_selection_scorer.py
apps/api-server/app/services/core3_real_data/core3_selection_conflict_resolver.py
apps/api-server/app/services/core3_real_data/core3_selection_duplicate_resolver.py
apps/api-server/app/services/core3_real_data/core3_selection_reason_builder.py
apps/api-server/app/services/core3_real_data/core3_selection_slot_decision_builder.py
apps/api-server/app/services/core3_real_data/core3_selection_audit_builder.py
apps/api-server/app/services/core3_real_data/core3_selection_review_issue_builder.py
apps/api-server/app/services/core3_real_data/core3_selection_invalidation_publisher.py
apps/api-server/app/services/core3_real_data/core3_selection_service.py
apps/api-server/app/services/core3_real_data/core3_selection_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `core3_selection_schemas.py` | M14 枚举、typed contracts、input/output DTO |
| `core3_selection_repositories.py` | 读取 M12/M13/M08/M11/M11.5/M02，写入 M14 五张表 |
| `core3_selection_input_loader.py` | 加载目标 SKU 的候选、评分、角色分、解释和复核问题 |
| `core3_selection_policy.py` | 规则版本、阈值、槽位配置、中文槽位名 |
| `core3_selection_slot_candidate_builder.py` | 构建三个槽位候选列表 |
| `core3_selection_gate_checker.py` | 应用槽位硬门槛、阻断和 review 条件 |
| `core3_selection_scorer.py` | 计算 `slot_selection_score`、业务信息增量和策略价值 |
| `core3_selection_conflict_resolver.py` | 处理同一候选跨槽冲突 |
| `core3_selection_duplicate_resolver.py` | 处理同系列和高度重复候选 |
| `core3_selection_reason_builder.py` | 生成六层中文业务结论和风险话术 |
| `core3_selection_slot_decision_builder.py` | 生成 selected/empty/review/blocked 槽位状态 |
| `core3_selection_audit_builder.py` | 生成全部候选 selected/rejected/review/blocked 审计 |
| `core3_selection_review_issue_builder.py` | 生成 M14 选择复核问题 |
| `core3_selection_invalidation_publisher.py` | M14 结果变化时登记 M15-M16 下游失效 |
| `core3_selection_service.py` | M14 编排 service |
| `core3_selection_runner.py` | M14 runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0022_core3_real_data_core3_selection.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0022_core3_real_data_core3_selection.py` | 新增 M14 五张表、索引、唯一键、外键和 downgrade |
| `core3_real_data.py` schema | 导出 M14 run、selection、slot、audit、issue response |
| `core3_real_data.py` API | 增加 M14 v2 内部运行和技术追溯 API |
| `constants.py` | 补 M14 slot、status、decision、empty reason、issue type |
| `runner.py` | 注册 M14 runner，不改变 M00-M13 逻辑 |
| `conftest.py` | 增加 M14 三槽位 fixture、M13 分数 fixture、85E7Q selection fixture |

如果 Alembic 当前最新编号不是 `0021`，编码时按最新编号顺延，但 migration 内容仍只能包含 M14 表、索引、约束。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m14_selection_schemas.py
apps/api-server/tests/core3_real_data/test_m14_selection_policy.py
apps/api-server/tests/core3_real_data/test_m14_input_loader.py
apps/api-server/tests/core3_real_data/test_m14_slot_candidate_builder.py
apps/api-server/tests/core3_real_data/test_m14_slot_gate_checker.py
apps/api-server/tests/core3_real_data/test_m14_slot_selection_scorer.py
apps/api-server/tests/core3_real_data/test_m14_conflict_resolver.py
apps/api-server/tests/core3_real_data/test_m14_duplicate_resolver.py
apps/api-server/tests/core3_real_data/test_m14_reason_builder.py
apps/api-server/tests/core3_real_data/test_m14_slot_decision_builder.py
apps/api-server/tests/core3_real_data/test_m14_audit_builder.py
apps/api-server/tests/core3_real_data/test_m14_review_issue_builder.py
apps/api-server/tests/core3_real_data/test_m14_repositories.py
apps/api-server/tests/core3_real_data/test_m14_selection_service.py
apps/api-server/tests/core3_real_data/test_m14_runner.py
apps/api-server/tests/core3_real_data/test_m14_api.py
apps/api-server/tests/core3_real_data/test_m14_85e7q_fixture.py
```

## 5. 不允许改文件

本模块开发时不得修改以下范围：

```text
apps/web/
apps/factory-web/src/pages/
apps/api-server/app/services/core3_mvp/
apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json
docs/core3_mvp/real_data_v2/sop_requirements/
docs/core3_mvp/real_data_v2/sop_detailed_design/
cankao/
```

不得修改的业务逻辑：

- M12 候选池召回规则。
- M13 组件分、角色分、证据完整度和复核问题规则。
- M08 SKU 画像生成逻辑。
- M11/M11.5 战场和卖点价值分层逻辑。
- 原始四表结构。
- 旧 `core3_mvp` 页面或 API。

不得引入的行为：

- 从原始四表直接取数补判断。
- 从全量 SKU 中补选 M12 未召回候选。
- 按 M13 总分直接取前三。
- 为了凑满 3 个选择低置信候选。
- 以品牌为排除或降权规则。
- 使用服务参考分补产品核心槽位。
- 在测试中调用外部 LLM。
- 在 M14 API 中暴露面向高层主屏的内部公式和英文枚举。

## 6. 数据库迁移任务

### 6.1 migration 文件

建议新增：

```text
apps/api-server/alembic/versions/0022_core3_real_data_core3_selection.py
```

新增五张表：

```text
core3_competitor_selection_run
core3_competitor_selection
core3_competitor_slot_decision
core3_competitor_selection_audit
core3_competitor_selection_review_issue
```

M14 不单独设计全局任务表。运行状态由 M16 `core3_module_run` 管理；M14 结果表通过 `run_id`、`input_fingerprint`、`result_hash` 和 `rule_version` 追溯。

### 6.2 `core3_competitor_selection_run`

用途：记录一次目标 SKU 三槽位选择运行，回答候选数、已评分数、入选数、空槽数、复核状态和选择摘要。

字段：

| 字段 | 类型建议 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `project_id` | uuid/text | 必填 |
| `category_code` | text | 必填，MVP 为 `TV` |
| `batch_id` | uuid/text | 必填 |
| `run_id` | uuid/text | 必填 |
| `module_run_id` | uuid/text | 可空，关联 M16 run |
| `target_sku_code` | text | 必填 |
| `target_model_name` | text | 必填 |
| `target_brand_name` | text | 可空 |
| `candidate_count` | integer | M12 current 候选数 |
| `scored_candidate_count` | integer | M13 已评分候选数 |
| `selected_count` | integer | 0-3 |
| `empty_slot_count` | integer | 0-3 |
| `review_candidate_count` | integer | 需复核候选数 |
| `blocked_candidate_count` | integer | 被 blocker 阻断候选数 |
| `selection_status` | text | success/limited/review_required/blocked/failed |
| `selection_summary_cn` | text | 中文选择摘要 |
| `empty_slots_json` | jsonb | 空槽摘要 |
| `selection_policy_json` | jsonb | 本次规则阈值快照 |
| `target_profile_hash` | text | 必填 |
| `m12_recall_fingerprint` | text | 必填 |
| `m13_score_fingerprint` | text | 必填 |
| `open_m13_issue_fingerprint` | text | 可空 |
| `evidence_revision` | text | 可空 |
| `rule_version` | text | 必填，默认 `m14_core3_selection_v1` |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

约束：

```sql
create unique index uq_core3_competitor_selection_run_current
on core3_competitor_selection_run(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, target_sku_code, selection_status)`
- `(project_id, category_code, batch_id, selection_status, created_at desc)`
- `(project_id, category_code, batch_id, run_id)`

### 6.3 `core3_competitor_selection`

用途：记录每个入选核心竞品，是 M15 核心竞品卡的主输入。每条记录代表一个候选在一个唯一槽位入选。

字段：

| 字段 | 类型建议 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `selection_run_id` | uuid/text | 外键到 `core3_competitor_selection_run` |
| `candidate_pool_id` | uuid/text | 外键到 M12 pair |
| `component_score_id` | uuid/text | 外键到 M13 component score |
| `role_score_id` | uuid/text | 外键到对应 M13 role score |
| `project_id` | uuid/text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | uuid/text | 必填 |
| `run_id` | uuid/text | 必填 |
| `target_sku_code` | text | 必填 |
| `target_model_name` | text | 必填 |
| `candidate_sku_code` | text | 必填 |
| `candidate_model_name` | text | 必填 |
| `candidate_brand_name` | text | 可空 |
| `same_brand_flag` | boolean | 必填，只作说明，不用于降权 |
| `model_family_key` | text | 可空 |
| `slot_code` | text | direct_fight/price_volume_pressure/benchmark_potential |
| `slot_name_cn` | text | 中文槽位名 |
| `selection_rank` | integer | MVP 每槽最多 1，固定 1 |
| `primary_battlefield_code` | text | 可空 |
| `primary_battlefield_name_cn` | text | 可空 |
| `slot_selection_score` | numeric | 必填 |
| `role_score` | numeric | M13 对应角色分 |
| `component_total_score` | numeric | M13 组件总分，仅辅助 |
| `confidence` | numeric | 入选置信度 |
| `evidence_completeness_score` | numeric | M13 证据完整度 |
| `pressure_level` | text | high/medium_high/medium/review_required |
| `business_conclusion_cn` | text | 一句话业务结论 |
| `battlefield_reason_cn` | text | 战场理由 |
| `task_audience_reason_cn` | text | 任务/客群理由 |
| `claim_value_reason_cn` | text | 卖点价值理由 |
| `price_channel_reason_cn` | text | 价格/渠道理由 |
| `market_reason_cn` | text | 市场压力理由 |
| `target_advantage_cn` | text | 目标 SKU 优势 |
| `competitor_advantage_cn` | text | 入选竞品优势 |
| `strategy_implication_cn` | text | 策略含义 |
| `risk_note_cn` | text | 可空 |
| `component_scores_json` | jsonb | 关键组件分 |
| `role_scores_json` | jsonb | 各角色分摘要 |
| `selection_evidence_json` | jsonb | 选择证据结构 |
| `review_required` | boolean | 必填 |
| `review_reason` | text | 可空 |
| `evidence_ids` | uuid[]/jsonb | 必填，可为空数组 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

约束：

```sql
create unique index uq_core3_competitor_selection_current_slot
on core3_competitor_selection(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  slot_code,
  rule_version
)
where is_current = true;

create unique index uq_core3_competitor_selection_current_candidate
on core3_competitor_selection(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  candidate_sku_code,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, target_sku_code, selection_rank)`
- `(project_id, category_code, batch_id, target_sku_code, slot_selection_score desc)`
- `(project_id, category_code, batch_id, slot_code, pressure_level)`
- `evidence_ids` GIN，若使用 jsonb 则对 jsonb 建 GIN。

### 6.4 `core3_competitor_slot_decision`

用途：记录三个槽位的最终状态。即使槽位为空，每个目标每次运行也必须输出 3 条记录。

字段：

| 字段 | 类型建议 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `selection_run_id` | uuid/text | 外键到 selection run |
| `selected_competitor_selection_id` | uuid/text | 可空，入选记录 |
| `project_id` | uuid/text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | uuid/text | 必填 |
| `run_id` | uuid/text | 必填 |
| `target_sku_code` | text | 必填 |
| `slot_code` | text | 三槽位之一 |
| `slot_name_cn` | text | 中文槽位名 |
| `decision_status` | text | selected/empty/review_required/blocked |
| `selected_candidate_sku_code` | text | 可空 |
| `top_candidate_sku_code` | text | 可空 |
| `slot_candidate_count` | integer | 必填 |
| `eligible_candidate_count` | integer | 必填 |
| `empty_reason_code` | text | 可空 |
| `empty_reason_cn` | text | 可空 |
| `review_reason` | text | 可空 |
| `top_candidate_score` | numeric | 可空 |
| `top_candidate_confidence` | numeric | 可空 |
| `decision_payload_json` | jsonb | 必填 |
| `evidence_ids` | uuid[]/jsonb | 必填，可为空数组 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

约束：

```sql
create unique index uq_core3_competitor_slot_decision_current
on core3_competitor_slot_decision(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  slot_code,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, decision_status, empty_reason_code)`
- `(project_id, category_code, batch_id, target_sku_code, slot_code)`

### 6.5 `core3_competitor_selection_audit`

用途：记录每个候选入选、未选、复核或阻断原因。M15 的“候选池与未选原因”折叠区读取该表。

字段：

| 字段 | 类型建议 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `selection_run_id` | uuid/text | 外键到 selection run |
| `candidate_pool_id` | uuid/text | 外键到 M12 pair |
| `component_score_id` | uuid/text | 可空，外键到 M13 component score |
| `project_id` | uuid/text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | uuid/text | 必填 |
| `run_id` | uuid/text | 必填 |
| `target_sku_code` | text | 必填 |
| `candidate_sku_code` | text | 必填 |
| `candidate_model_name` | text | 必填 |
| `candidate_brand_name` | text | 可空 |
| `model_family_key` | text | 可空 |
| `evaluated_slot_codes_json` | jsonb | 必填 |
| `decision` | text | selected/rejected/review/blocked |
| `selected_slot_code` | text | 可空 |
| `best_slot_code` | text | 可空 |
| `decision_reason_cn` | text | 中文原因 |
| `failed_conditions_json` | jsonb | 未满足条件 |
| `slot_scores_json` | jsonb | 各槽位分和选择分 |
| `candidate_total_score` | numeric | 可空，M13 总分 |
| `best_role_score` | numeric | 可空 |
| `evidence_completeness_score` | numeric | 可空 |
| `confidence` | numeric | 可空 |
| `risk_flags_json` | jsonb | 必填 |
| `duplicate_with_candidate_sku_code` | text | 可空 |
| `business_distinctiveness_score` | numeric | 可空 |
| `strategic_value_score` | numeric | 可空 |
| `evidence_ids` | uuid[]/jsonb | 必填，可为空数组 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

约束：

```sql
create unique index uq_core3_competitor_selection_audit_current
on core3_competitor_selection_audit(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  candidate_sku_code,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, target_sku_code, decision)`
- `(project_id, category_code, batch_id, selected_slot_code, best_role_score desc)`
- `(project_id, category_code, batch_id, target_sku_code, best_slot_code)`

### 6.6 `core3_competitor_selection_review_issue`

用途：记录 M14 选择复核问题。M16 读取该表进入复核队列；M15 根据 unresolved issue 调整报告语气。

字段：

| 字段 | 类型建议 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `selection_run_id` | uuid/text | 外键到 selection run |
| `selection_id` | uuid/text | 可空，关联入选记录 |
| `slot_decision_id` | uuid/text | 可空，关联槽位决策 |
| `selection_audit_id` | uuid/text | 可空，关联审计 |
| `project_id` | uuid/text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | uuid/text | 必填 |
| `run_id` | uuid/text | 必填 |
| `target_sku_code` | text | 必填 |
| `slot_code` | text | 可空 |
| `candidate_sku_code` | text | 可空 |
| `issue_scope` | text | run/slot/candidate/selection |
| `issue_type` | text | 见枚举 |
| `issue_level` | text | warning/review/blocker |
| `issue_message_cn` | text | 中文问题 |
| `suggested_action_cn` | text | 可空 |
| `source_payload_json` | jsonb | 问题上下文 |
| `evidence_ids` | uuid[]/jsonb | 必填，可为空数组 |
| `resolved_status` | text | open/resolved/ignored |
| `resolved_by` | text | 可空 |
| `resolved_at` | timestamptz | 可空 |
| `resolution_note` | text | 可空 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

`issue_type` 首版枚举：

```text
empty_candidate_pool
missing_role_score
all_slots_empty
low_confidence_top_candidate
high_score_low_evidence
insufficient_market_evidence
service_only_candidate
selection_conflict
duplicate_candidate
missing_direct_battlefield
missing_pressure_signal
missing_benchmark_signal
claim_missing_risk
sample_limited
blocked_by_m13_issue
unknown
```

约束：

```sql
create unique index uq_core3_competitor_selection_review_issue_current
on core3_competitor_selection_review_issue(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  coalesce(slot_code, ''),
  coalesce(candidate_sku_code, ''),
  issue_scope,
  issue_type,
  result_hash,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, resolved_status, issue_level)`
- `(project_id, category_code, batch_id, target_sku_code, slot_code)`
- `(project_id, category_code, batch_id, issue_type, created_at desc)`

### 6.7 downgrade

`downgrade()` 只删除 M14 五张表和相关索引，不触碰 M00-M13 表。

如果 M15/M16 已消费 M14 结果，回滚前必须先标记下游结果失效或清理下游引用，避免 M15 报告悬空引用。

## 7. model/schema 任务

### 7.1 枚举

在 `core3_selection_schemas.py` 或共享 constants 中定义以下枚举。

三槽位：

```text
direct_fight
price_volume_pressure
benchmark_potential
```

槽位中文名：

| slot_code | slot_name_cn |
| --- | --- |
| `direct_fight` | 正面对打竞品 |
| `price_volume_pressure` | 价格/销量挤压竞品 |
| `benchmark_potential` | 高端标杆/潜在下探竞品 |

运行状态：

```text
success
limited
review_required
blocked
failed
```

槽位决策状态：

```text
selected
empty
review_required
blocked
```

候选审计决策：

```text
selected
rejected
review
blocked
```

空槽原因：

```text
no_candidate
low_confidence
insufficient_market_evidence
insufficient_semantic_evidence
duplicate_with_selected
service_only
sample_limited
blocked_by_review_issue
```

压力等级：

```text
high
medium_high
medium
review_required
```

复核 issue level：

```text
warning
review
blocker
```

### 7.2 规则配置 schema

新增 `SelectionPolicy`：

```text
rule_version
role_score_candidate_threshold
auto_select_confidence_threshold
auto_select_evidence_threshold
slot_selection_auto_threshold
role_score_close_gap
duplicate_similarity_threshold
brand_limit_enabled
max_selected_per_target
max_selected_per_slot
```

默认值：

| 参数 | 默认值 |
| --- | ---: |
| `rule_version` | `m14_core3_selection_v1` |
| `role_score_candidate_threshold` | 0.60 |
| `auto_select_confidence_threshold` | 0.50 |
| `auto_select_evidence_threshold` | 0.50 |
| `slot_selection_auto_threshold` | 0.60 |
| `role_score_close_gap` | 0.05 |
| `duplicate_similarity_threshold` | 0.85 |
| `brand_limit_enabled` | false |
| `max_selected_per_target` | 3 |
| `max_selected_per_slot` | 1 |

规则要求：

- `brand_limit_enabled` 必须默认为 false。
- 首版不得开放品牌上限配置给业务页面。
- `max_selected_per_target` 不得大于 3。
- `max_selected_per_slot` MVP 固定为 1。

### 7.3 输入 DTO

新增内部 DTO：

```text
SelectionRunContext
SelectionInputBundle
SelectionCandidateInput
SelectionComponentScoreInput
SelectionRoleScoreInput
SelectionM13IssueInput
SlotCandidate
SlotCandidateGateResult
SlotCandidateScoreBreakdown
ResolvedSelectionCandidate
SelectionReasonPayload
SelectionEvidencePayload
```

`SelectionCandidateInput` 必须包含：

- `candidate_pool_id`
- `target_sku_code`
- `target_model_name`
- `candidate_sku_code`
- `candidate_model_name`
- `candidate_brand_name`
- `same_brand_flag`
- `model_family_key`
- `candidate_relation_types_json`
- `candidate_role_hints_json`
- `recall_strength`
- `feature_snapshot_hash`
- `target_profile_hash`
- `candidate_profile_hash`

`SelectionComponentScoreInput` 必须包含：

- `component_score_id`
- `component_total_score`
- `direct_fight_score`
- `price_volume_pressure_score`
- `benchmark_potential_score`
- `configuration_pressure_score`
- `service_reference_score`
- `evidence_completeness_score`
- `confidence`
- `sample_status`
- `risk_flags_json`
- `main_strengths_json`
- `main_gaps_json`
- `evidence_ids`
- `input_fingerprint`
- `result_hash`

`SelectionRoleScoreInput` 必须包含：

- `role_score_id`
- `role_code`
- `role_score`
- `role_confidence`
- `auto_select_eligible`
- `support_level`
- `reason_cn`
- `evidence_ids`
- `review_required`
- `review_reason`

### 7.4 输出 response schema

在 `apps/api-server/app/schemas/core3_real_data.py` 导出：

```text
Core3SelectionRunResponse
Core3CompetitorSelectionResponse
Core3SlotDecisionResponse
Core3SelectionAuditResponse
Core3SelectionReviewIssueResponse
Core3SelectionRunSummaryResponse
Core3SelectionAuditListResponse
```

技术 API 可以保留 code 字段；面向 M15 的业务字段必须准备中文：

- `slot_name_cn`
- `business_conclusion_cn`
- `battlefield_reason_cn`
- `task_audience_reason_cn`
- `claim_value_reason_cn`
- `price_channel_reason_cn`
- `market_reason_cn`
- `target_advantage_cn`
- `competitor_advantage_cn`
- `strategy_implication_cn`
- `risk_note_cn`
- `empty_reason_cn`
- `decision_reason_cn`
- `issue_message_cn`
- `suggested_action_cn`

### 7.5 schema 测试要求

必须测试：

- 三槽位枚举完整，且没有 `service_reference` 作为核心槽位。
- `brand_limit_enabled` 默认 false。
- `max_selected_per_target <= 3`。
- `component_total_score` 字段说明为辅助排序，不是入选依据。
- response 中中文字段非空。
- 空槽 response 可以没有 candidate，但必须有 `empty_reason_code` 和 `empty_reason_cn`。
- audit response 对 selected/rejected/review/blocked 都可序列化。
- review issue 枚举包含 M13 blocker、低证据、服务信号、重复冲突等类型。

## 8. repository 任务

### 8.1 repository 类

新增 `Core3SelectionRepository`，也可以按项目现有模式拆为多个 repository，但必须保持 M14 的读写边界清晰。

建议接口：

```text
list_current_candidate_pairs(context, target_sku_code) -> list[SelectionCandidateInput]
list_current_component_scores(context, target_sku_code) -> dict[candidate_pool_id, SelectionComponentScoreInput]
list_current_role_scores(context, target_sku_code) -> dict[candidate_pool_id, dict[slot_code, SelectionRoleScoreInput]]
list_current_component_explanations(context, candidate_pool_ids) -> dict[candidate_pool_id, list[ComponentExplanationInput]]
list_open_m13_score_issues(context, target_sku_code) -> list[M13IssueInput]
get_target_signal_profile(context, target_sku_code) -> SkuSignalProfileInput | None
list_candidate_signal_profiles(context, candidate_sku_codes) -> dict[sku_code, SkuSignalProfileInput]
list_battlefield_portfolios(context, sku_codes) -> dict[sku_code, BattlefieldPortfolioInput]
list_claim_value_summaries(context, sku_codes) -> dict[sku_code, ClaimValueSummaryInput]
validate_evidence_ids(context, evidence_ids) -> EvidenceValidationResult
replace_current_selection_results(run, selections, slot_decisions, audits, review_issues) -> None
get_current_selection_run(context, target_sku_code, rule_version) -> SelectionRunRecord | None
list_current_selections(context, target_sku_code) -> list[SelectionRecord]
list_current_slot_decisions(context, target_sku_code) -> list[SlotDecisionRecord]
list_current_selection_audits(context, target_sku_code, filters) -> list[SelectionAuditRecord]
list_open_selection_review_issues(context, target_sku_code, filters) -> list[SelectionReviewIssueRecord]
```

### 8.2 读取边界

允许读取：

```text
core3_candidate_pool
core3_candidate_recall_reason
core3_candidate_feature_snapshot
core3_candidate_component_score
core3_candidate_role_score
core3_candidate_component_explanation
core3_candidate_score_review_issue
core3_sku_signal_profile
core3_sku_battlefield_portfolio
core3_sku_battlefield_claim_value_summary
core3_evidence_atom
```

禁止读取：

```text
week_sales_data
attribute_data
selling_points_data
comment_data
M15 report tables
old core3_mvp tables
```

M14 repository 必须从 M12 current 候选开始，不能从全量 SKU 或 M07 可比池补候选。

### 8.3 输入完整性检查

repository 或 input loader 必须识别：

- M12 候选池为空。
- 候选缺 M13 component score。
- 候选缺核心 role score。
- 候选存在 unresolved M13 blocker。
- 候选只剩服务参考高分。
- target profile 缺失。
- candidate profile 缺失。
- evidence_ids 为空或 evidence 已失效。

这些情况不能静默跳过，必须进入 run status、slot decision、audit 或 review issue。

### 8.4 写入策略

`replace_current_selection_results` 必须在单事务内完成：

1. 按业务键将旧 current run 置 `is_current=false`。
2. 将旧 current selection 置 `is_current=false`。
3. 将旧 current slot decision 置 `is_current=false`。
4. 将旧 current audit 置 `is_current=false`。
5. 将旧 current review issue 置 `is_current=false`，但保留 M16 resolution 字段历史。
6. 插入新 run。
7. 插入新 selection。
8. 插入 3 条 slot decision。
9. 插入所有候选 audit。
10. 插入 review issue。

事务要求：

- 不允许 M15 看到只有 run 没有 slot decision 的半成品。
- 不允许同一候选 current 入选多个槽位。
- 不允许 selected_count 与 selection 行数不一致。
- 不允许没有 slot_decision 就返回 success。

### 8.5 fingerprint 和 hash

目标级 `input_fingerprint`：

```text
hash(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  target_profile_hash,
  m12_recall_fingerprint,
  m13_score_fingerprint,
  open_m13_issue_fingerprint,
  evidence_revision,
  selection_policy_json,
  rule_version
)
```

`result_hash`：

```text
hash(
  selected_competitor_sku_codes_by_slot,
  slot_decisions,
  audit_decisions,
  review_required,
  selection_summary_cn
)
```

审计行和 issue 行可以使用 run 级 `input_fingerprint`，但 `result_hash` 要包含本行关键业务字段，避免重复插入。

### 8.6 repository 测试

必须测试：

- 只加载 M12 current pair。
- 非 M12 候选不会被读取。
- M13 缺 component score 时进入 blocked/review。
- M13 缺核心 role score 时写 `missing_role_score`。
- unresolved M13 blocker 阻断自动入选。
- replace current 在单事务内写五类结果。
- 重跑后旧记录 `is_current=false`，新记录 `is_current=true`。
- 每次运行必须写 3 条 slot decision。
- 同一目标同一候选 current 最多入选一次。
- 不读取原始四表。

## 9. service 任务

### 9.1 主服务

新增 `Core3SelectionService`：

```text
run_target_selection(context, target_sku_code, rule_version="m14_core3_selection_v1") -> SelectionRunResult
run_batch_selection(context, target_scope) -> SelectionBatchResult
get_selection_audit(context, target_sku_code, filters) -> SelectionAuditList
get_selection_run(context, target_sku_code, run_id=None, rule_version=None) -> SelectionRunResult
```

### 9.2 处理流程

M14 service 必须按以下步骤执行：

1. 读取 `run_context`：`project_id`、`category_code`、`batch_id`、`run_id`、目标 SKU、`rule_version`。
2. 加载 `SelectionPolicy`，默认 `m14_core3_selection_v1`。
3. 读取 M12 current 候选池。
4. 读取 M13 current component score、role score、component explanation 和 unresolved issue。
5. 读取目标和候选 M08 画像、M11 战场、M11.5 卖点价值摘要。
6. 校验 evidence 状态。
7. 候选池为空时写 blocked 或 review_required run，并输出 3 条 blocked/empty slot decision。
8. M13 核心 role score 缺失时写 `missing_role_score` blocker。
9. 构建三个槽位候选列表。
10. 对每个槽位候选应用硬门槛和阻断规则。
11. 计算 `slot_selection_score`。
12. 处理同一候选跨槽冲突。
13. 处理同系列或高度重复候选。
14. 每个槽位最多选择 1 个候选。
15. 若槽位无候选或仅有低置信候选，输出 empty 或 review_required slot decision。
16. 为入选候选生成六层中文业务结论。
17. 为全部候选生成 audit。
18. 生成 M14 复核问题。
19. 构建 run summary。
20. 同事务写入五张 M14 输出表。
21. 发布 M15-M16 下游失效事件。

### 9.3 槽位候选构建

#### 正面对打 `direct_fight`

进入候选条件：

```text
direct_fight_score >= role_score_candidate_threshold
and confidence >= 0.45
and evidence_completeness_score >= 0.45
and not unresolved_blocker
```

还需满足至少两类可比：

- 战场可比。
- 价格可比。
- 尺寸可比。
- 平台可比。
- 任务/客群可比。
- 卖点/参数可比。

不得仅因同尺寸入选。

#### 价格/销量挤压 `price_volume_pressure`

进入候选条件：

```text
price_volume_pressure_score >= role_score_candidate_threshold
and confidence >= 0.45
and not unresolved_blocker
and (
  price_advantage_score > 0
  or market_threat_score >= 0.65
  or price_trend_score >= 0.60
)
```

如果没有价格、销量、销额或趋势证据，即使任务相似也不能自动入选。

#### 高端标杆/潜在下探 `benchmark_potential`

进入候选条件：

```text
benchmark_potential_score >= role_score_candidate_threshold
and confidence >= 0.45
and not unresolved_blocker
and (
  param_superiority_score > 0
  or claim_superiority_score > 0
  or price_trend_score >= 0.60
  or sales_amount_strength_score >= 0.65
)
```

如果只有价格更高，没有参数、卖点、销额或下探证据，不能自动入选。

### 9.4 槽位选择分

M14 计算 `slot_selection_score`：

```text
slot_selection_score =
  role_score * 0.45
  + evidence_completeness_score * 0.15
  + market_pressure_or_validity_score * 0.15
  + business_distinctiveness_score * 0.15
  + strategic_value_score * 0.10
  - selection_risk_penalty
```

说明：

- `role_score` 来自 M13 对应角色分。
- `evidence_completeness_score` 来自 M13。
- `market_pressure_or_validity_score` 来自 M13 价格、销量、销额、趋势组件组合。
- `business_distinctiveness_score` 由 M14 判断与已选候选的信息增量。
- `strategic_value_score` 由 M14 判断定价、防守、上探、卖点表达价值。
- `selection_risk_penalty` 包括高分低证据、样本不足、服务信号过重、同系列重复、关键字段缺失等。

`component_total_score` 只能作为 tie-breaker，不得进入主公式的决定性分项，不得单独决定入选。

### 9.5 业务信息增量

`business_distinctiveness_score` 首版规则：

| 情况 | 分值 |
| --- | ---: |
| 代表不同槽位压力，且战场/价格/尺寸/策略含义不同 | 1.00 |
| 与已选候选有部分重合，但角色不同 | 0.70 |
| 同系列同尺寸同价位同战场，只有小参数差异 | 0.30 |
| 与已选候选高度重复 | 0.00 |

同系列重复不得直接排除。只有在业务信息高度重复时，才保留解释更强或选择分更高的候选。

### 9.6 跨槽冲突

同一 `candidate_sku_code` 最终只能占用一个槽位。

规则：

1. 计算候选在所有槽位的 `slot_selection_score`。
2. 若最高槽位领先第二槽位超过 `role_score_close_gap`，选择最高槽位。
3. 若分差很小，按业务解释更清晰、策略含义更直接的槽位选择。
4. 价格接近偏正面对打。
5. 明显低价偏价格/销量挤压。
6. 明显高端、参数更强或有下探风险偏高端标杆/潜在下探。
7. 未占用槽位写 audit，说明“该候选已作为另一个角色入选”。
8. 分差很小且证据不足时写 `selection_conflict` review issue。

### 9.7 同系列去重

不得使用品牌上限。当前真实样例均为海信，品牌上限会误伤真实竞品选择。

同系列重复处理：

1. 使用 M12/M08 的 `model_family_key`、尺寸、价格带、战场、角色分、组件解释判断重复。
2. 高度重复时，保留 `slot_selection_score` 更高且业务解释更强的候选。
3. 如果两个同系列候选分别代表不同压力，例如一个低价挤压、一个高端下探，可以同时入选不同槽位。
4. 被去重候选写 `core3_competitor_selection_audit`，`decision='rejected'`，原因 `duplicate_with_selected`。
5. 多个同系列候选分数接近且业务信息增量不足时写 `duplicate_candidate` warning 或 review。

### 9.8 入选中文理由

每个入选竞品必须输出六层信息：

1. 结论：它是什么角色的核心竞品。
2. 主战场：它在哪个价值战场对目标构成压力。
3. 推导：从战场、任务、客群、卖点价值、市场压力逐步说明。
4. 证据：列出关键 evidence。
5. 差异：目标优势和竞品优势。
6. 风险：说明样本不足、卖点缺失、评论噪声或同品牌内部口径限制。

一句话模板：

| 槽位 | 模板 |
| --- | --- |
| 正面对打 | 它与目标在{尺寸/价格带}、{主战场}和线上主销平台上高度接近，是用户在同一预算下最可能同时比较的型号。 |
| 价格/销量挤压 | 它承接相近的{任务/客群}需求，并通过{更低价格/更强销量/促销趋势}对目标形成防守压力。 |
| 高端标杆/潜在下探 | 它在{关键参数/卖点价值/高端市场表现}上强于目标，若价格下探会压缩目标的上探空间。 |

风险话术：

| 场景 | 中文表达 |
| --- | --- |
| 结构化卖点缺失 | 目标缺结构化卖点记录，本次以参数、评论和市场证据补充判断，宣传证据仍需复核。 |
| 服务信号 | 服务体验只作为风险或服务侧参考，不作为产品核心竞品入选主因。 |
| 同品牌 | 当前样例数据均为海信型号，本次识别的是同品牌内部的同价位、同战场或同系列竞争关系。 |
| 空槽 | 暂无高置信候选。原因：该槽位候选证据不足，需要补充市场或语义证据后复核。 |

### 9.9 复核问题生成

M14 必须生成以下问题：

| issue_type | 触发 |
| --- | --- |
| `empty_candidate_pool` | M12 候选池为空 |
| `missing_role_score` | M13 核心角色分缺失 |
| `all_slots_empty` | 三个槽位都为空 |
| `low_confidence_top_candidate` | 槽位最高候选置信度不足 |
| `high_score_low_evidence` | 高分但证据完整度低 |
| `insufficient_market_evidence` | 入选或候选缺有效市场证据 |
| `service_only_candidate` | 候选只有服务信号 |
| `selection_conflict` | 同一候选跨槽冲突且分差很小 |
| `duplicate_candidate` | 多个同系列候选高度重复 |
| `missing_direct_battlefield` | 正面对打缺双方战场依据 |
| `missing_pressure_signal` | 价格挤压缺价格或销量证据 |
| `missing_benchmark_signal` | 标杆槽缺参数/卖点优势或下探证据 |
| `claim_missing_risk` | 结构化卖点缺失影响卖点证据置信 |
| `blocked_by_m13_issue` | M13 unresolved blocker 阻断自动入选 |

### 9.10 service 测试

必须测试：

- 候选池为空时输出 blocked/review run、3 条 slot decision 和 `empty_candidate_pool`。
- M13 缺 role score 时输出 `missing_role_score`。
- 正面对打不能只因同尺寸入选。
- 价格挤压必须有价格、销量、销额或趋势压力。
- 高端标杆必须有参数/卖点优势、高端销额或下探证据。
- 总分最高但槽位不匹配时不入选。
- 服务参考高分不进入产品核心三槽位。
- 同候选多槽高分时只占一个槽位。
- 同品牌候选可入选。
- 多个同品牌不同业务角色不被品牌上限剔除。
- 同系列高度重复候选被审计而不是静默丢弃。
- 结构化卖点缺失写成证据缺口。
- 三个槽位都无高置信候选时不硬凑。

## 10. runner/API 任务

### 10.1 runner

新增 `core3_selection_runner.py`，并在 `runner.py` 注册 `M14`。

M16 调用形态：

```text
Core3ModuleRunner.run("M14", run_context, target_scope)
```

`target_scope` 支持：

| Scope | 含义 |
| --- | --- |
| `all_targets` | 批次内全部目标 |
| `target_sku_list` | 指定目标 |
| `changed_targets` | M12/M13/evidence 变化影响的目标 |

runner 输出：

```json
{
  "module_code": "M14",
  "status": "success",
  "input_count": 12,
  "output_count": 2,
  "selected_count": 2,
  "empty_slot_count": 1,
  "review_issue_count": 1,
  "output_hash": "sha256...",
  "warnings": [],
  "downstream_impacts": ["M15", "M16"]
}
```

### 10.2 内部 API

在 `apps/api-server/app/api/core3_real_data.py` 增加技术追溯 API：

| API | 方法 | 用途 |
| --- | --- | --- |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/core3-selection/run` | POST | 触发目标 SKU 三槽位选择 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/core3-selection/runs/{run_id}` | GET | 查看选择运行 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/core3-selection/current` | GET | 查看当前三槽位选择 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/selection-audit` | GET | 查看入选、未选、空槽和复核原因 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/selection-review-issues` | GET | 查询 M14 复核问题 |

API 边界：

- M14 API 是技术追溯和调度 API，不直接面向高层主屏。
- 高层报告主屏由 M15 report API 提供。
- M14 API response 可以包含 code 字段，但必须同时包含中文业务字段。
- API 不返回原始表大字段。
- API 不返回 UUID-only 证据列表，必须给出短证据摘要或交给 M15 转译。

### 10.3 增量和失效

M14 变化需要登记下游影响：

| 变化来源 | M14 动作 | 下游影响 |
| --- | --- | --- |
| M12 候选池变化 | 重算目标三槽位选择 | M15-M16 |
| M13 组件分变化 | 重算目标三槽位选择 | M15-M16 |
| M13 角色分变化 | 重算目标三槽位选择 | M15-M16 |
| M13 复核状态变化 | 重算自动入选资格和报告语气 | M15-M16 |
| M11 战场变化 | 通过 M12/M13 变化触发，必要时重写战场理由 | M14-M16 |
| M11.5 卖点价值变化 | 重算卖点理由和槽位资格 | M14-M16 |
| M08 画像变化 | 更新风险、缺失和同系列判断 | M14-M16 |
| M02 evidence 状态变化 | 更新证据、置信和复核问题 | M15-M16 |
| 选择规则变化 | 按新 `rule_version` 重算 | M15-M16 |

### 10.4 runner/API 测试

必须测试：

- runner 可按 `target_sku_list` 只处理指定目标。
- runner 可对候选池为空目标返回 review/blocked，不抛未处理异常。
- runner output_count 与 selection 行数一致。
- runner 总是输出 3 条 slot decision。
- API run 触发后可查询 current。
- audit API 支持 decision、slot_code、review_required 过滤。
- review issue API 支持 issue_type、resolved_status 过滤。
- API 不返回原始四表明细。
- M14 结果变化时发布 M15-M16 下游失效事件。

## 11. 测试任务

### 11.1 schema 和 policy

`test_m14_selection_schemas.py`：

- 三槽位枚举完整。
- `service_reference` 不能作为核心槽位。
- selection status、slot decision status、audit decision、empty reason、issue type 枚举完整。
- response 中中文业务字段存在。
- 空槽 response 无 candidate 时仍可序列化。

`test_m14_selection_policy.py`：

- 默认 `rule_version=m14_core3_selection_v1`。
- 默认 `brand_limit_enabled=false`。
- `max_selected_per_target=3`。
- 阈值为需求定义的首版值。
- 非法品牌上限配置不影响默认选择逻辑。

### 11.2 input loader 和 repository

`test_m14_input_loader.py`：

- 只加载 M12 current candidate。
- 缺 M13 component score 进入 review。
- 缺 `direct_fight`、`price_volume_pressure`、`benchmark_potential` 之一写 `missing_role_score`。
- unresolved M13 blocker 阻断自动入选。
- evidence 失效进入低证据复核。

`test_m14_repositories.py`：

- 五张表 current 版本唯一。
- replace current 在事务内写 run、selection、slot、audit、issue。
- 每次运行写 3 条 slot_decision。
- 重跑保留历史。
- 同一候选不能 current 入选两个槽位。
- 不读取原始四表。

### 11.3 slot builder 和 gate checker

`test_m14_slot_candidate_builder.py`：

- direct_fight 从 M13 `direct_fight_score` 构建。
- pressure 从 M13 `price_volume_pressure_score` 构建。
- benchmark 从 M13 `benchmark_potential_score` 构建。
- 同一候选可以先进入多个槽位候选列表。
- 服务参考不构建为核心槽位。

`test_m14_slot_gate_checker.py`：

- 正面对打必须至少两类可比，不能只靠尺寸。
- 价格/销量挤压必须有价格、销量、销额或趋势证据。
- 高端标杆必须有参数、卖点、销额或下探证据。
- 高分低证据不能自动入选。
- M13 blocker 阻断自动入选。
- `sample_status=insufficient` 降级为 review。

### 11.4 scorer、冲突和去重

`test_m14_slot_selection_scorer.py`：

- `slot_selection_score` 使用 role、证据、市场、业务增量、策略价值和风险惩罚。
- `component_total_score` 不能单独决定入选。
- 高风险候选有 penalty。
- 业务信息增量影响排序。

`test_m14_conflict_resolver.py`：

- 同一候选多槽高分时只占一个槽。
- 分差超过 `role_score_close_gap` 时选最高槽。
- 分差很小时按价格关系和业务解释判断。
- 冲突写 audit 和 `selection_conflict` issue。

`test_m14_duplicate_resolver.py`：

- 同品牌候选不被排除。
- 不执行“同一品牌最多 1 个”。
- 同系列同尺寸同战场高度重复时只保留业务增量更强者。
- 同系列但不同压力可以同时入选不同槽位。
- 被去重候选写 rejected audit。

### 11.5 reason、slot、audit、issue

`test_m14_reason_builder.py`：

- 入选候选输出六层中文业务结论。
- 正面对打理由包含双方战场依据。
- 价格挤压理由包含价格、销量、销额或趋势压力。
- 高端标杆理由包含参数/卖点优势、高端销额或下探风险。
- 结构化卖点缺失写宣传证据缺口，不写卖点弱。
- 服务评论只写风险或服务参考，不写核心入选主因。
- 同品牌写同品牌内部竞争或同系列替代，不写外部品牌对抗。

`test_m14_slot_decision_builder.py`：

- 每次运行输出 3 条 slot decision。
- 槽位无候选时输出 `empty_reason_code=no_candidate`。
- 低置信候选输出 `decision_status=review_required`。
- 被 M13 issue 阻断输出 `blocked_by_review_issue`。

`test_m14_audit_builder.py`：

- selected 候选写入 selected audit。
- 总分高但不入选写 rejected audit。
- 高分低证据写 review audit。
- 同系列重复写 duplicate reason。
- 每个 M12/M13 候选都有 audit，不静默消失。

`test_m14_review_issue_builder.py`：

- 候选池为空写 `empty_candidate_pool`。
- 三槽位全空写 `all_slots_empty`。
- 正面对打缺战场写 `missing_direct_battlefield`。
- 价格挤压缺压力信号写 `missing_pressure_signal`。
- 标杆缺优势信号写 `missing_benchmark_signal`。
- 只有服务信号写 `service_only_candidate`。

### 11.6 service、runner、API

`test_m14_selection_service.py`：

- 正常输入输出 0-3 个 selection。
- 不强行凑满 3 个。
- 不按总分 Top3。
- 同品牌可以入选。
- 服务信号不能补产品核心槽位。
- M15 可直接读取 selection、slot、audit。

`test_m14_runner.py`：

- 支持 all_targets、target_sku_list、changed_targets。
- 输出 summary 包含 selected_count、empty_slot_count、review_issue_count。
- 失败目标不会阻断其他目标运行。

`test_m14_api.py`：

- POST run 返回 run summary。
- GET current 返回 selection、slot、audit summary。
- selection audit API 可筛选未选原因。
- review issue API 可筛选 open issue。

## 12. 205/85E7Q fixture 验收

### 12.1 样例数据事实

基于 205 PostgreSQL 当前真实样例，fixture 必须覆盖：

- 品类为彩电 `TV`。
- 当前样例量价型号约 35 个。
- 品牌均为海信。
- 周期为 `26W01` 到 `26W23`。
- 渠道为线上。
- 平台为 `专业电商` 和 `平台电商`。
- 结构化卖点只覆盖少量型号。
- 85E7Q `model_code=TV00029115`。
- 85E7Q 有量价、参数、评论。
- 85E7Q 没有结构化卖点行。

### 12.2 85E7Q 选择断言

以 `TV00029115` / `85E7Q` 为目标，M14 必须验证：

| 断言 | 要求 |
| --- | --- |
| 输出数量 | 0-3 个都合法，不硬凑 |
| 同品牌 | 海信候选可入选，不降权、不排除 |
| 品牌上限 | 不允许“同品牌最多 1 个” |
| 正面对打 | 入选理由不能只写同为 85 寸，必须包含战场、价格、平台、任务或卖点价值依据 |
| 价格挤压 | 必须包含价格、销量、销额或趋势压力 |
| 高端标杆 | 必须包含参数/卖点优势、高端价格锚点、销额承接或下探风险 |
| 卖点缺失 | 写“宣传卖点数据缺口”，不能写“卖点弱” |
| 服务评论 | 安装、配送、售后只作为服务侧证据或风险 |
| 空槽 | 证据不足时输出空槽原因，不补弱候选 |
| 未选原因 | 分数不低但未选候选必须有 audit |
| 中文语言 | 业务字段使用中文，不把 UUID、SQL、英文内部字段作为高层表达 |

### 12.3 85E7Q 业务解释示例

M14 输出可以包含类似中文解释：

- “该候选与 85E7Q 在 85 寸、线上主销平台和高端画质战场上高度接近，属于同品牌内部的正面对打候选。”
- “该候选价格低于 85E7Q，且销量或销额表现不弱，同时大屏观影门槛未明显断档，形成价格/销量挤压。”
- “该候选在亮度、分区、刷新率或 HDMI 等关键参数上更强，如果价格下探，会压缩 85E7Q 的上探空间。”
- “85E7Q 缺结构化卖点记录，本次以参数、评论和市场证据补充判断，宣传证据仍需复核。”
- “服务体验只作为风险或服务侧参考，不作为产品核心竞品入选主因。”

M14 不需要在开发任务阶段预设 85E7Q 的最终三竞品名单。验收重点是：每个入选、未选、空槽都能解释“为什么”。

## 13. 完成标准

M14 编码完成必须满足：

1. 五张 M14 表 migration 可执行，downgrade 不影响 M00-M13 表。
2. 所有 M14 表包含 project、category、batch/run、rule_version、input_fingerprint、result_hash、is_current、审计时间。
3. M14 只消费 M12/M13/M08/M11/M11.5/M02 current 结果。
4. M14 不直接读取原始四表。
5. M14 不读取 M12 未召回候选之外的全量 SKU。
6. M14 不重新计算 M13 组件分和角色分。
7. 每个目标每次运行输出 0-3 个核心竞品。
8. 每个目标每次运行输出 3 条 slot decision。
9. 同一候选最多入选一个槽位。
10. 每个槽位 MVP 最多入选 1 个候选。
11. 不强行凑满 3 个。
12. 不按 `component_total_score` Top3。
13. `component_total_score` 只作为辅助或 tie-breaker。
14. 同品牌 SKU 可以入选。
15. 不设置品牌上限。
16. 同系列去重基于业务信息增量。
17. 服务参考候选不默认进入产品核心三槽位。
18. 正面对打解释包含双方战场依据。
19. 价格挤压解释包含价格、销量、销额或趋势压力。
20. 高端标杆解释包含参数/卖点优势、高端价格锚点、销额承接或下探风险。
21. 结构化卖点缺失写成宣传证据缺口。
22. 每个入选候选有中文六层结论和 evidence 引用。
23. 每个未选候选有 audit 原因。
24. 每个空槽有 `empty_reason_code` 和 `empty_reason_cn`。
25. M14 review issue 可被 M16 消费。
26. M15 可以直接消费 selection、slot、audit、review issue。
27. M14 结果变化时登记 M15-M16 下游失效。
28. pytest 覆盖 schema、policy、input loader、slot builder、gate、scorer、冲突、去重、reason、slot decision、audit、review issue、repository、service、runner、API、85E7Q fixture。

## 14. 风险和回滚

### 14.1 主要风险

| 风险 | 表现 | 控制 |
| --- | --- | --- |
| 把 M14 做成 TopN | 直接按总分取前三 | 单测禁止，总分只辅助 |
| 强行凑满 3 个 | 低置信候选被入选 | 空槽必须可输出 |
| 品牌上限误伤 | 全部海信样例无法选择 | 默认和测试禁止品牌上限 |
| 同系列误排除 | 不同压力候选被去掉 | 去重按业务信息增量 |
| 服务信号误用 | 服务评论导致产品核心入选 | 服务只进风险或参考 |
| 卖点缺失误判 | 85E7Q 被写成卖点弱 | 写宣传证据缺口 |
| 缺 M13 结果仍选择 | M14 回读原始表补算 | 缺 M13 写 blocked/review |
| M15 看到半成品 | run 已写但 slot/audit 未写 | 单事务 replace current |
| 复核状态丢失 | M16 resolution 被覆盖 | 历史保留，current 新版本 |

### 14.2 回滚策略

- migration downgrade 只删除 M14 五张表。
- 不影响 M00-M13 运行。
- 不影响旧 `core3_mvp`。
- 回滚前如果 M15 已生成报告，需要标记 M15 当前报告失效。
- 回滚后 M15 只能展示 M12/M13 候选与评分，不能展示核心三竞品选择。

### 14.3 降级策略

- M12 候选池为空：M14 输出 blocked/review run 和 3 个空槽。
- M13 缺角色分：M14 输出 `missing_role_score` blocker。
- 三槽位都无法自动入选：M14 输出 `all_slots_empty` review，不硬凑。
- evidence 状态不可用：保留候选 audit，降低置信并写 review issue。
- 同系列候选难以自动裁决：输出 review issue，不强制选择。

## 15. 下游依赖

### 15.1 M15 证据卡与高层报告依赖

M15 必须以以下表为主输入：

- `core3_competitor_selection_run`
- `core3_competitor_selection`
- `core3_competitor_slot_decision`
- `core3_competitor_selection_audit`
- `core3_competitor_selection_review_issue`

M15 使用：

- 三槽位入选结果。
- 空槽原因。
- 未选候选原因。
- 中文业务结论。
- 目标优势和竞品优势。
- 策略含义。
- evidence 引用和风险说明。

M15 不重新选择竞品，不重新计算 M13 分数，不从 M12 候选中补选，不直接读原始四表。

### 15.2 M16 编排和复核依赖

M16 需要读取：

- M14 run status。
- M14 review issue。
- selected_count、empty_slot_count、review_candidate_count。
- rule_version。
- input_fingerprint 和 result_hash。
- downstream impact。

M16 使用这些内容控制：

- M15 是否可生成报告。
- 是否进入业务复核队列。
- 上游变化后是否重跑 M14/M15。
- 发布门禁是否通过。

### 15.3 API 和前端依赖

后续 API 聚合和前端页面不能直接展示 M14 内部枚举、UUID 或公式。它们应通过 M15 把 M14 结果转换成高层可读的业务语言。

技术追溯页面可以展示：

- 三槽位决策。
- 未选原因。
- 复核问题。
- 证据摘要。
- 选择规则版本。

高层主屏只展示：

- 核心竞品是谁。
- 每个竞品是什么角色。
- 为什么是竞品。
- 证据够不够。
- 业务策略含义。

## 16. 建议开发子任务拆分

| 子任务 | 范围 |
| --- | --- |
| D14-01 | Alembic 新增 M14 五张表、约束和索引 |
| D14-02 | M14 enums、policy、Pydantic schema |
| D14-03 | `Core3SelectionRepository` 读取 M12/M13 和写 M14 current 结果 |
| D14-04 | `SelectionInputLoader` 输入完整性校验 |
| D14-05 | `SlotCandidateBuilder` 三槽位候选构建 |
| D14-06 | `SlotGateChecker` 硬门槛和阻断规则 |
| D14-07 | `SlotSelectionScorer` 槽位选择分 |
| D14-08 | `CrossSlotConflictResolver` 跨槽冲突处理 |
| D14-09 | `DuplicateCandidateResolver` 同系列去重 |
| D14-10 | `SelectionReasonBuilder` 六层中文结论 |
| D14-11 | `SlotDecisionBuilder` 空槽和复核状态 |
| D14-12 | `SelectionAuditBuilder` 入选、未选、复核和阻断审计 |
| D14-13 | `SelectionReviewIssueBuilder` 复核问题 |
| D14-14 | `Core3SelectionService` 编排和事务写入 |
| D14-15 | M14 runner 和技术追溯 API |
| D14-16 | 单元、集成、API 和 85E7Q fixture 回归测试 |

编码阶段如果任务过大，应按 D14 子任务继续拆小；每次编码只做一个小闭环。

## 17. 下次任务

下一个开发任务文档：

```text
docs/core3_mvp/real_data_v2/development/M15_development_tasks.md
```

M15 证据卡与高层报告模块必须以 M14 的 selection、slot decision、audit 和 review issue 为主输入。M15 不重新选择竞品，不重新计算 M13 分数，只把 M14 的三槽位结果、空槽原因、未选审计和证据链转换为高层可读的业务页面和报告 payload。
