# M13 竞品组件评分开发任务

## 1. 模块目标

M13 的开发目标是对 M12 已召回的目标-候选 SKU pair 做组件评分和角色评分，解释候选“为什么像竞品、在哪些维度构成竞争压力、适合哪类竞品角色、证据是否可靠”。M13 输出组件分、角色分、组件解释和复核问题，为 M14 三槽位核心竞品选择提供可解释输入。

M13 要回答的问题不是“谁是最终三竞品”，而是：

1. 目标 SKU 和候选 SKU 是否争夺同一价值战场。
2. 双方是否处于可比较的价格、尺寸、平台和市场位置。
3. 候选是否在关键参数、卖点价值、任务、客群或用户感知上形成对打、拦截或下探压力。
4. 候选更适合正面对打、价格/销量挤压、高端标杆/潜在下探、配置拦截还是服务参考。
5. 每个组件分背后的证据是否完整、可靠、可追溯。
6. 哪些候选虽然分数不低，但因证据缺失、样本不足、服务信号过重或同质重复，需要 M14 谨慎选择。

M13 要解决的工程问题：

1. 将 M12 的“候选进入池理由”进一步量化为组件分和角色分。
2. 将组件分、角色分、组件解释和评分复核分表保存，方便 M14/M15/M16 消费。
3. 固化 M13 只评分 M12 候选，不能绕过 M12 从全量 SKU 中找更高分候选。
4. 固化 M13 只使用 M12 的 `core3_candidate_feature_snapshot` 作为默认评分输入，不能回读原始表补算评分。
5. 输出 18 个组件分，并对每个组件生成中文解释。组件证据缺失也要输出 explanation，不能省略。
6. 独立输出 5 类角色分：正面对打、价格/销量挤压、高端标杆/潜在下探、配置拦截、服务参考。
7. 明确服务信号边界。服务参考分不得提升产品核心角色分。
8. 明确结构化卖点缺失边界。缺结构化卖点是宣传证据缺口，不是卖点能力弱。
9. 对高分低置信、缺 M12 快照、缺市场证据、缺语义证据、参数冲突、服务过权重等风险生成复核问题。
10. 对 85E7Q `TV00029115` 这类有量价、参数、评论但无结构化卖点的目标，能解释同尺寸正面对打、高端画质、游戏体育、价格挤压、卖点缺失和服务边界。

M13 必须固化以下边界：

- M13 不增删候选池，候选池由 M12 负责。
- M13 不绕过 M12 去全量 SKU 中找更高分候选。
- M13 不选择 0-3 个核心竞品，M14 负责。
- M13 不生成高层报告结论，M15 负责。
- M13 不直接读取原始 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data`。
- M13 不重新计算 M11.5 的 PSI、SSI、SAI、CPI。
- M13 不用单一总分替代组件解释。
- M13 不把 `component_total_score` 当作最终入选结论。
- M13 不把服务保障信号当成产品核心竞争分。
- M13 不把结构化卖点缺失当成卖点弱，只能作为证据缺口。
- M13 不因为同品牌降低或排除评分。当前真实样例均为海信，同品牌 SKU 可以互为竞品。
- M13 不生成线下渠道、全渠道或 12 个月口径。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M13 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M13_component_scoring_requirements.md` |
| M13 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M13_component_scoring_design.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M12 任务 | `docs/core3_mvp/real_data_v2/development/M12_development_tasks.md` |
| M12 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M12_candidate_recall_design.md` |
| M08 任务 | `docs/core3_mvp/real_data_v2/development/M08_development_tasks.md` |
| M09 任务 | `docs/core3_mvp/real_data_v2/development/M09_development_tasks.md` |
| M10 任务 | `docs/core3_mvp/real_data_v2/development/M10_development_tasks.md` |
| M11 任务 | `docs/core3_mvp/real_data_v2/development/M11_development_tasks.md` |
| M11.5 任务 | `docs/core3_mvp/real_data_v2/development/M11_5_development_tasks.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 方法论 | `cankao/CatForge_竞品生成SOP_详细指导_v1.md` |
| SOP 参考模块 | `cankao/catforge_sop_md/modules/M13_竞品组件评分模块.md` |
| UI 规范 | `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md` |

编码前必须确认：

- M12 已输出 `core3_candidate_pool`。
- M12 已输出 `core3_candidate_recall_reason`。
- M12 已输出 `core3_candidate_feature_snapshot`，并包含 `m13_component_input_json`。
- M12 snapshot 中包含价格、渠道、尺寸、市场、参数、卖点、任务、客群、战场、证据质量等 raw 输入。
- M08 已输出目标和候选 `core3_sku_signal_profile`，可用于画像状态、缺失风险和 profile hash 校验。
- M02 evidence 可用于 evidence 状态校验和证据引用。
- M13 可以按需读取 M07/M09/M10/M11/M11.5 current 结果做一致性校验，但不能重建 M12 特征。
- INFRA 已提供 run context、hash 工具、current 版本约定、runner 协议、复核 issue 约定和测试 fixture 基础。

## 3. 本次范围

本次开发任务拆分覆盖 M13 后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 4 张 M13 输出表、索引、唯一键、外键和 current 版本约束 |
| model/schema | 新增 component、role、explanation、review issue、runner summary、API response contract |
| 输入读取 | 读取 M12 current pair、reason、snapshot、M08 profile、M02 evidence 状态 |
| 组件计算 | 实现 18 个组件分：基础可比性、战场、任务、客群、价格、尺寸、渠道、参数、卖点、市场、评论、趋势、证据完整度等 |
| 角色分 | 实现 direct_fight、price_volume_pressure、benchmark_potential、configuration_pressure、service_reference 五类角色分 |
| 角色封顶 | 无战场、无价格尺寸、无市场、无参数/卖点优势、仅服务信号、M12 review_only 等封顶 |
| 总分置信 | 计算 `component_total_score` 和综合 confidence，并明确总分只作辅助 |
| 证据完整度 | 计算 evidence completeness，处理结构化卖点缺失、evidence 失效、样本不足 |
| 中文解释 | 为每个组件生成中文业务解释，缺失也要解释 |
| 复核问题 | 输出 missing_feature_snapshot、high_score_low_confidence、service_over_weighted、param_conflict 等复核问题 |
| 增量失效 | 用 M12 pair/snapshot hash、profile hash、evidence revision、rule version 控制重算 |
| runner/API | 提供 M13 运行入口、运行摘要、组件分审计和单候选评分拆解 API |
| 测试 | 单元、repository、service、API、增量、边界、85E7Q fixture |

本次不做：

- 不实现 M14 三槽位选择。
- 不实现 M15 报告页。
- 不实现 M16 全链路编排。
- 不实现前端页面。
- 不部署到 205。
- 不修改 M12 候选池。
- 不修改 M07-M11.5 上游结果。
- 不对旧 `core3_mvp` 粗粒度页面做改造。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/component_scoring_schemas.py
apps/api-server/app/services/core3_real_data/component_scoring_repositories.py
apps/api-server/app/services/core3_real_data/component_scoring_input_loader.py
apps/api-server/app/services/core3_real_data/component_scoring_feature_normalizer.py
apps/api-server/app/services/core3_real_data/component_score_calculator.py
apps/api-server/app/services/core3_real_data/component_base_comparability_calculator.py
apps/api-server/app/services/core3_real_data/component_battlefield_fit_calculator.py
apps/api-server/app/services/core3_real_data/component_task_audience_calculator.py
apps/api-server/app/services/core3_real_data/component_price_size_channel_calculator.py
apps/api-server/app/services/core3_real_data/component_param_calculator.py
apps/api-server/app/services/core3_real_data/component_claim_value_calculator.py
apps/api-server/app/services/core3_real_data/component_market_comment_calculator.py
apps/api-server/app/services/core3_real_data/component_evidence_completeness_calculator.py
apps/api-server/app/services/core3_real_data/component_explanation_builder.py
apps/api-server/app/services/core3_real_data/component_role_score_calculator.py
apps/api-server/app/services/core3_real_data/component_role_score_capper.py
apps/api-server/app/services/core3_real_data/component_total_score_calculator.py
apps/api-server/app/services/core3_real_data/component_score_confidence_calculator.py
apps/api-server/app/services/core3_real_data/component_score_review_issue_builder.py
apps/api-server/app/services/core3_real_data/component_score_invalidation_publisher.py
apps/api-server/app/services/core3_real_data/component_scoring_service.py
apps/api-server/app/services/core3_real_data/component_scoring_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `component_scoring_schemas.py` | M13 枚举、typed contracts、component/role/explanation/issue schema |
| `component_scoring_repositories.py` | 读取 M12/M08/M02，写入 M13 四张表 |
| `component_scoring_input_loader.py` | 加载 M12 pair、reason、snapshot、M08 profile、evidence 状态 |
| `component_scoring_feature_normalizer.py` | 归一化 M12 `m13_component_input_json` |
| `component_score_calculator.py` | 18 个组件计算编排 |
| `component_base_comparability_calculator.py` | 基础可比性 |
| `component_battlefield_fit_calculator.py` | 战场重合 |
| `component_task_audience_calculator.py` | 任务和客群重合 |
| `component_price_size_channel_calculator.py` | 价格、尺寸、平台组件 |
| `component_param_calculator.py` | 参数相似和参数优势 |
| `component_claim_value_calculator.py` | 卖点价值对打、卖点优势、门槛满足 |
| `component_market_comment_calculator.py` | 市场压力、销额强度、评论感知、价格趋势 |
| `component_evidence_completeness_calculator.py` | 证据完整度和证据缺口 |
| `component_explanation_builder.py` | 组件中文解释 |
| `component_role_score_calculator.py` | 5 类角色分公式 |
| `component_role_score_capper.py` | 角色分封顶和服务边界 |
| `component_total_score_calculator.py` | 组件总分 |
| `component_score_confidence_calculator.py` | 综合置信度 |
| `component_score_review_issue_builder.py` | 评分复核问题 |
| `component_score_invalidation_publisher.py` | M13 变化时登记 M14-M16 下游失效 |
| `component_scoring_service.py` | M13 编排 service |
| `component_scoring_runner.py` | M13 runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0021_core3_real_data_component_scoring.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0021_core3_real_data_component_scoring.py` | 新增 M13 四张表、索引、唯一键、外键和 downgrade |
| `core3_real_data.py` schema | 导出 M13 component、role、explanation、issue response |
| `core3_real_data.py` API | 增加 M13 v2 内部运行和审计 API |
| `constants.py` | 补 M13 component code、role code、support level、review issue type |
| `runner.py` | 注册 M13 runner，不改变 M00-M12 逻辑 |
| `conftest.py` | 增加 M13 pair、snapshot、component input、85E7Q fixture |

如果 Alembic 当前最新编号不是 `0020`，编码时按最新编号顺延，但 migration 内容仍只能包含 M13 表、索引、约束。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m13_component_scoring_schemas.py
apps/api-server/tests/core3_real_data/test_m13_input_loader.py
apps/api-server/tests/core3_real_data/test_m13_feature_normalizer.py
apps/api-server/tests/core3_real_data/test_m13_base_comparability_calculator.py
apps/api-server/tests/core3_real_data/test_m13_battlefield_fit_calculator.py
apps/api-server/tests/core3_real_data/test_m13_task_audience_calculator.py
apps/api-server/tests/core3_real_data/test_m13_price_size_channel_calculator.py
apps/api-server/tests/core3_real_data/test_m13_param_calculator.py
apps/api-server/tests/core3_real_data/test_m13_claim_value_calculator.py
apps/api-server/tests/core3_real_data/test_m13_market_comment_calculator.py
apps/api-server/tests/core3_real_data/test_m13_evidence_completeness_calculator.py
apps/api-server/tests/core3_real_data/test_m13_component_score_calculator.py
apps/api-server/tests/core3_real_data/test_m13_role_score_calculator.py
apps/api-server/tests/core3_real_data/test_m13_role_score_capper.py
apps/api-server/tests/core3_real_data/test_m13_total_confidence_calculator.py
apps/api-server/tests/core3_real_data/test_m13_explanation_builder.py
apps/api-server/tests/core3_real_data/test_m13_review_issue_builder.py
apps/api-server/tests/core3_real_data/test_m13_repositories.py
apps/api-server/tests/core3_real_data/test_m13_runner.py
apps/api-server/tests/core3_real_data/test_m13_api.py
apps/api-server/tests/core3_real_data/test_m13_85e7q_fixture.py
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

不得在 M13 中改动或重写：

- M00-M12 已有 migration 的业务含义。
- M07 市场画像和可比池逻辑。
- M08 SKU 综合画像逻辑。
- M09 用户任务逻辑。
- M10 目标客群逻辑。
- M11 价值战场逻辑。
- M11.5 战场内卖点价值分层逻辑。
- M12 候选池召回逻辑。
- M14 三槽位选择逻辑。
- M15 报告逻辑。

不得新增以下捷径：

- 直接读取原始四表补评分。
- 对 M12 未召回的 SKU 评分。
- 缺 M12 feature snapshot 时回读散表拼快照。
- 用 `component_total_score` 直接代表核心竞品结论。
- 让服务分提升 `direct_fight_score`、`price_volume_pressure_score` 或 `benchmark_potential_score`。
- 把结构化卖点缺失记为卖点弱。
- 按品牌给同品牌候选降权。
- 在业务解释里展示 UUID、SQL、JSON、英文字段名或 AI 过程话术。

## 6. 数据库迁移任务

### 6.1 新增表

迁移文件建议为：

```text
apps/api-server/alembic/versions/0021_core3_real_data_component_scoring.py
```

新增四张表：

```text
core3_candidate_component_score
core3_candidate_role_score
core3_candidate_component_explanation
core3_candidate_score_review_issue
```

M13 不单独设计 run 表，运行状态由 M16 `core3_module_run` 管理；M13 输出表通过 `run_id`、`module_run_id`、`input_fingerprint` 追溯运行。

### 6.2 `core3_candidate_component_score`

用途：保存目标-候选 pair 的组件分总览、总分、角色分摘要、证据完整度、置信度和风险。M14 用它做槽位候选初筛，M15 用它生成证据卡摘要。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `candidate_pool_id` | uuid/text | 外键到 `core3_candidate_pool` |
| `feature_snapshot_id` | uuid/text | 外键到 `core3_candidate_feature_snapshot` |
| `project_id` | text/uuid | 必填 |
| `category_code` | text | 必填，MVP 为 `TV` |
| `batch_id` | text/uuid | 必填 |
| `run_id` | text/uuid | 必填 |
| `module_run_id` | text/uuid | 必填 |
| `target_sku_code` | text | 必填 |
| `target_model_name` | text | 必填 |
| `candidate_sku_code` | text | 必填 |
| `candidate_model_name` | text | 必填 |
| `candidate_brand_name` | text | 可空 |
| `same_brand_flag` | boolean | 必填，不用于降权 |
| `candidate_relation_types_json` | jsonb | M12 候选关系类型 |
| `candidate_role_hints_json` | jsonb | M12 角色提示 |
| `recall_strength` | text | M12 召回强度 |
| `base_comparability_score` | numeric | 必填 |
| `battlefield_fit_score` | numeric | 必填 |
| `task_overlap_score` | numeric | 必填 |
| `audience_overlap_score` | numeric | 必填 |
| `price_position_score` | numeric | 必填 |
| `price_advantage_score` | numeric | 必填 |
| `size_fit_score` | numeric | 必填 |
| `channel_overlap_score` | numeric | 必填 |
| `param_similarity_score` | numeric | 必填 |
| `param_superiority_score` | numeric | 必填 |
| `claim_confrontation_score` | numeric | 必填 |
| `claim_superiority_score` | numeric | 必填 |
| `claim_threshold_sufficiency_score` | numeric | 必填 |
| `market_threat_score` | numeric | 必填 |
| `sales_amount_strength_score` | numeric | 必填 |
| `comment_perception_score` | numeric | 必填 |
| `price_trend_score` | numeric | 必填 |
| `evidence_completeness_score` | numeric | 必填 |
| `component_scores_json` | jsonb | 18 个组件结构化结果 |
| `component_total_score` | numeric | 组件总分，仅辅助 |
| `direct_fight_score` | numeric | 冗余自 role 表 |
| `price_volume_pressure_score` | numeric | 冗余自 role 表 |
| `benchmark_potential_score` | numeric | 冗余自 role 表 |
| `configuration_pressure_score` | numeric | 冗余自 role 表 |
| `service_reference_score` | numeric | 冗余自 role 表 |
| `confidence` | numeric | 综合置信度 |
| `sample_status` | text | sufficient/limited/insufficient/unknown |
| `main_strengths_json` | jsonb | 候选强支撑点 |
| `main_gaps_json` | jsonb | 候选证据缺口 |
| `risk_flags_json` | jsonb | 风险 |
| `review_required` | boolean | 必填 |
| `review_reason` | text | 可空 |
| `positive_evidence_ids` | jsonb/array | 支撑证据 |
| `weakening_evidence_ids` | jsonb/array | 削弱证据 |
| `evidence_ids` | jsonb/array | 代表证据全集 |
| `target_profile_hash` | text | 必填 |
| `candidate_profile_hash` | text | 必填 |
| `feature_snapshot_hash` | text | M12 快照 hash |
| `component_rule_version` | text | 必填 |
| `role_rule_version` | text | 必填 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

唯一索引：

```sql
create unique index uq_core3_candidate_component_score_current
on core3_candidate_component_score(
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

- `(project_id, category_code, batch_id, target_sku_code, component_total_score desc)`
- `(project_id, category_code, batch_id, target_sku_code, direct_fight_score desc, price_volume_pressure_score desc, benchmark_potential_score desc)`
- `(project_id, category_code, batch_id, review_required, review_reason)`
- GIN `component_scores_json`

### 6.3 `core3_candidate_role_score`

用途：保存每个候选 pair 在各竞品角色上的独立分数和解释。M14 直接按角色读取该表构建三槽位候选。

每个入池 pair 至少输出 5 条 current 角色记录：

```text
direct_fight
price_volume_pressure
benchmark_potential
configuration_pressure
service_reference
```

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `candidate_component_score_id` | uuid/text | 外键到 component score |
| `candidate_pool_id` | uuid/text | 外键到 M12 pair |
| `feature_snapshot_id` | uuid/text | 外键到 M12 snapshot |
| `project_id` | text/uuid | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | text/uuid | 必填 |
| `run_id` | text/uuid | 必填 |
| `module_run_id` | text/uuid | 必填 |
| `target_sku_code` | text | 必填 |
| `candidate_sku_code` | text | 必填 |
| `role_code` | text | 角色 code |
| `role_name_cn` | text | 中文角色 |
| `role_score` | numeric | 角色分 |
| `role_confidence` | numeric | 角色置信度 |
| `role_rank_hint` | integer | 可空 |
| `auto_select_eligible` | boolean | M14 自动入选基本资格 |
| `auto_select_block_reason` | text | 可空 |
| `role_business_reason_cn` | text | 中文角色解释 |
| `role_business_reason_short_cn` | text | 短解释 |
| `formula_version` | text | 公式版本 |
| `component_contribution_json` | jsonb | 组件贡献 |
| `positive_evidence_ids` | jsonb/array | 支撑证据 |
| `weakening_evidence_ids` | jsonb/array | 削弱证据 |
| `risk_flags_json` | jsonb | 风险 |
| `review_required` | boolean | 必填 |
| `review_reason` | text | 可空 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

唯一索引：

```sql
create unique index uq_core3_candidate_role_score_current
on core3_candidate_role_score(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  candidate_sku_code,
  role_code,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, target_sku_code, role_code, role_score desc)`
- `(project_id, category_code, batch_id, role_code, auto_select_eligible, role_confidence desc)`

### 6.4 `core3_candidate_component_explanation`

用途：保存组件级解释，供 M15 证据卡、M14 未选原因和 M16 复核使用。每个入池 pair 必须对 18 个组件输出解释记录，证据缺失也要输出 `support_level='missing'`，不能省略。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `candidate_component_score_id` | uuid/text | 外键到 component score |
| `candidate_pool_id` | uuid/text | 外键到 M12 pair |
| `feature_snapshot_id` | uuid/text | 外键到 M12 snapshot |
| `project_id` | text/uuid | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | text/uuid | 必填 |
| `run_id` | text/uuid | 必填 |
| `module_run_id` | text/uuid | 必填 |
| `target_sku_code` | text | 必填 |
| `candidate_sku_code` | text | 必填 |
| `component_code` | text | 18 个组件 code |
| `component_name_cn` | text | 中文组件名 |
| `score` | numeric | 组件分 |
| `confidence` | numeric | 组件置信度 |
| `support_level` | text | strong/medium/weak/missing/conflict/not_applicable |
| `business_explanation_cn` | text | 中文业务解释 |
| `positive_summary_cn` | text | 可空 |
| `gap_summary_cn` | text | 可空 |
| `supporting_evidence_ids` | jsonb/array | 支撑证据 |
| `weakening_evidence_ids` | jsonb/array | 削弱证据 |
| `missing_evidence_reasons_json` | jsonb | 缺失原因 |
| `source_payload_json` | jsonb | 来源摘要 |
| `risk_flags_json` | jsonb | 风险 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

唯一索引：

```sql
create unique index uq_core3_candidate_component_explanation_current
on core3_candidate_component_explanation(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  candidate_sku_code,
  component_code,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, target_sku_code, candidate_sku_code)`
- `(project_id, category_code, batch_id, component_code, support_level)`
- GIN `supporting_evidence_ids`

### 6.5 `core3_candidate_score_review_issue`

用途：保存 M13 评分复核问题。M16 读取该表进入复核队列，M14 读取 unresolved blocker/review 问题决定是否允许自动入选。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `candidate_component_score_id` | uuid/text | 可空 |
| `candidate_role_score_id` | uuid/text | 可空 |
| `candidate_pool_id` | uuid/text | 可空 |
| `feature_snapshot_id` | uuid/text | 可空 |
| `project_id` | text/uuid | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | text/uuid | 必填 |
| `run_id` | text/uuid | 必填 |
| `module_run_id` | text/uuid | 必填 |
| `target_sku_code` | text | 必填 |
| `candidate_sku_code` | text | 可空 |
| `issue_scope` | text | pair/component/role/evidence |
| `component_code` | text | 可空 |
| `role_code` | text | 可空 |
| `issue_type` | text | 枚举 |
| `issue_level` | text | warning/review/blocker |
| `issue_message_cn` | text | 中文问题 |
| `suggested_action_cn` | text | 可空 |
| `source_payload_json` | jsonb | 上下文 |
| `evidence_ids` | jsonb/array | 相关证据 |
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

问题类型：

```text
missing_feature_snapshot
missing_candidate_profile
no_market_evidence
no_semantic_evidence
only_service_signal
high_score_low_confidence
param_conflict
claim_missing
sample_insufficient
component_missing
role_score_missing
service_over_weighted
same_family_duplicate_high_score
unknown
```

表达式唯一索引：

```sql
create unique index uq_core3_candidate_score_review_issue_current
on core3_candidate_score_review_issue(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  coalesce(candidate_sku_code, ''),
  issue_scope,
  coalesce(component_code, ''),
  coalesce(role_code, ''),
  issue_type,
  result_hash,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, resolved_status, issue_level)`
- `(project_id, category_code, batch_id, target_sku_code, candidate_sku_code)`

### 6.6 回滚策略

`downgrade()` 只删除 M13 四张表和相关索引，不触碰 M00-M12 表。

如果 M14-M16 已消费 M13 结果，回滚前必须先标记下游结果失效，避免 M14/M15 悬空引用。

## 7. model/schema 任务

### 7.1 组件 code

在 `component_scoring_schemas.py` 或 `constants.py` 中定义 18 个组件：

```text
base_comparability
battlefield_fit
task_overlap
audience_overlap
price_position
price_advantage
size_fit
channel_overlap
param_similarity
param_superiority
claim_confrontation
claim_superiority
claim_threshold_sufficiency
market_threat
sales_amount_strength
comment_perception
price_trend
evidence_completeness
```

### 7.2 角色 code

定义 5 类角色：

```text
direct_fight
price_volume_pressure
benchmark_potential
configuration_pressure
service_reference
```

角色对应下游：

| 角色 | 下游槽位 |
| --- | --- |
| `direct_fight` | M14 正面对打槽 |
| `price_volume_pressure` | M14 价格/销量挤压槽 |
| `benchmark_potential` | M14 高端标杆/潜在下探槽 |
| `configuration_pressure` | M14 辅助解释 |
| `service_reference` | M15 参考和 M16 复核，不默认进入核心槽 |

### 7.3 其他枚举

| 枚举 | 值 |
| --- | --- |
| support_level | strong/medium/weak/missing/conflict/not_applicable |
| sample_status | sufficient/limited/insufficient/unknown |
| issue_level | warning/review/blocker |
| issue_scope | pair/component/role/evidence |
| resolved_status | open/resolved/ignored |
| review_issue_type | missing_feature_snapshot/missing_candidate_profile/no_market_evidence/no_semantic_evidence/only_service_signal/high_score_low_confidence/param_conflict/claim_missing/sample_insufficient/component_missing/role_score_missing/service_over_weighted/same_family_duplicate_high_score/unknown |

### 7.4 typed contracts

需要定义：

- `M13RunRequest`
- `M13RunSummary`
- `M13InputPair`
- `M13FeatureSnapshotInput`
- `ComponentScore`
- `ComponentScoreSet`
- `RoleScore`
- `RoleScoreSet`
- `ComponentExplanation`
- `ComponentScoringResult`
- `CandidateComponentScoreRecord`
- `CandidateRoleScoreRecord`
- `CandidateComponentExplanationRecord`
- `CandidateScoreReviewIssueRecord`

每个 pair 级 contract 必须包含：

- `project_id`
- `category_code`
- `batch_id`
- `target_sku_code`
- `candidate_sku_code`
- `candidate_pool_id`
- `feature_snapshot_id`
- `target_profile_hash`
- `candidate_profile_hash`
- `feature_snapshot_hash`
- `component_rule_version`
- `role_rule_version`
- `rule_version`
- `input_fingerprint`
- `result_hash`

### 7.5 API schema

在 `apps/api-server/app/schemas/core3_real_data.py` 增加：

- `RunM13ComponentScoreRequest`
- `M13ComponentScoreRunResponse`
- `M13ScoreAuditResponse`
- `M13CandidateScoreDetailResponse`
- `M13CandidateComponentScoreResponse`
- `M13CandidateRoleScoreResponse`
- `M13CandidateComponentExplanationResponse`
- `M13ScoreReviewIssueResponse`

API response 中内部 code 可以保留为 hidden key，但必须提供中文展示字段：

- `component_name_cn`
- `role_name_cn`
- `support_level_cn`
- `business_explanation_cn`
- `role_business_reason_cn`
- `main_strengths_cn`
- `main_gaps_cn`
- `review_reason_cn`

## 8. repository 任务

### 8.1 输入读取边界

`ComponentScoringRepository` 必须从 M12 current 记录开始：

```text
core3_candidate_pool
join core3_candidate_feature_snapshot
left join core3_candidate_recall_reason
where is_current = true
```

允许读取：

```text
core3_candidate_pool
core3_candidate_recall_reason
core3_candidate_feature_snapshot
core3_sku_signal_profile
core3_evidence_atom
```

允许按需校验读取，但不能重建 M12 特征：

```text
core3_sku_market_profile
core3_sku_task_score
core3_sku_target_group_score
core3_sku_battlefield_score
core3_sku_claim_value_layer
```

不得直接读取：

```text
week_sales_data
attribute_data
selling_points_data
comment_data
M12 未召回的全量 SKU
M14 selection tables
M15 report tables
```

### 8.2 读取方法

需要实现：

```python
list_current_candidate_pairs(project_id, category_code, batch_id, target_sku_codes=None, candidate_pair_ids=None) -> list[CandidatePoolRecord]
get_current_feature_snapshot(candidate_pool_id) -> CandidateFeatureSnapshotRecord | None
list_current_recall_reasons(candidate_pool_id) -> list[CandidateRecallReasonRecord]
get_signal_profile(project_id, category_code, batch_id, sku_code) -> SignalProfile | None
get_evidence_status(evidence_ids: list[str]) -> dict[str, EvidenceStatus]
get_current_component_score(project_id, category_code, batch_id, target_sku_code, candidate_sku_code) -> CandidateComponentScoreRecord | None
```

### 8.3 写入方法

需要实现：

```python
upsert_component_scores(items: list[CandidateComponentScoreRecord]) -> None
upsert_role_scores(items: list[CandidateRoleScoreRecord]) -> None
upsert_component_explanations(items: list[CandidateComponentExplanationRecord]) -> None
upsert_review_issues(items: list[CandidateScoreReviewIssueRecord]) -> None
mark_previous_versions_not_current(scope: ComponentScoreWriteScope) -> None
```

写入规则：

- component、role、explanation、review issue 使用同一 pair 级 `input_fingerprint`。
- `result_hash` 相同不得重复插入业务版本。
- `result_hash` 变化时旧记录 `is_current=false`，新记录写入。
- 每个成功评分 pair 必须同时写 1 条 component score、5 条 role score、18 条 explanation。
- 任一必要 role 或 explanation 缺失时，写 blocker issue。
- 同一事务内写四类输出，避免 M14 看到半成品。

### 8.4 查询方法

API 需要：

```python
list_component_scores(project_id, category_code, batch_id, target_sku_code, filters) -> list[CandidateComponentScoreRecord]
get_component_score(project_id, category_code, batch_id, target_sku_code, candidate_sku_code) -> CandidateComponentScoreRecord | None
list_role_scores(project_id, category_code, batch_id, target_sku_code, candidate_sku_code=None) -> list[CandidateRoleScoreRecord]
list_component_explanations(project_id, category_code, batch_id, target_sku_code, candidate_sku_code) -> list[CandidateComponentExplanationRecord]
list_score_review_issues(project_id, category_code, batch_id, target_sku_code, filters) -> list[CandidateScoreReviewIssueRecord]
```

## 9. service 任务

### 9.1 编排服务

`ComponentScoringService` 负责主流程：

```python
class ComponentScoringService:
    def run(self, request: M13RunRequest) -> M13RunSummary:
        pairs = self.input_loader.load_pairs(request)
        for pair in pairs:
            self.score_pair(pair, request)
        return self.build_summary()
```

处理顺序：

1. 读取 run context。
2. 查询 M12 current candidate pair。
3. 对每个 pair 读取 current `core3_candidate_feature_snapshot`。
4. 缺快照时写 `missing_feature_snapshot` blocker issue，跳过自动评分。
5. 解析 `m13_component_input_json`、各特征 JSON 和 M12 风险。
6. 校验 evidence 状态。
7. 计算 18 个组件分。
8. 为每个组件生成 explanation，缺失也写 `support_level='missing'`。
9. 计算 5 类角色分。
10. 应用角色封顶和服务边界。
11. 计算 `component_total_score` 和综合 confidence。
12. 生成 `main_strengths_json`、`main_gaps_json`、`risk_flags_json`。
13. 生成复核问题。
14. 版本化写入四张输出表。
15. 发布 M14-M16 失效事件。

### 9.2 输入加载任务

`M13InputLoader` 必须：

- 只加载 M12 current pair。
- 校验 `hard_filter_pass=true`。
- 校验 `core3_candidate_feature_snapshot.is_current=true`。
- 校验 snapshot 和 pair 的 target/candidate 一致。
- 校验 `m13_component_input_json` 存在。
- 加载 pair 的 M12 召回理由用于证据和解释。
- 加载目标和候选 M08 profile 状态。
- 加载 evidence status。

如果入池候选缺 feature snapshot：

- 不回读散表拼快照。
- 写 `missing_feature_snapshot` blocker。
- 该 pair 不生成 component score。

### 9.3 组件计算任务

每个组件输出标准对象：

```json
{
  "component_code": "battlefield_fit",
  "score": 0.86,
  "confidence": 0.82,
  "support_level": "strong",
  "support_summary_cn": "双方主战场都指向高端画质。",
  "risk_flags": [],
  "supporting_evidence_ids": [],
  "weakening_evidence_ids": [],
  "source_payload_json": {}
}
```

18 个组件：

| 组件 | 首版要求 |
| --- | --- |
| `base_comparability` | 同品类、尺寸、价格、平台、画像状态 |
| `battlefield_fit` | M12 战场重合，M11 current 校验 |
| `task_overlap` | M12 任务重合，M09 current 校验 |
| `audience_overlap` | M12 客群重合，低置信客群降 confidence |
| `price_position` | 价格相近/更低/更高/unknown |
| `price_advantage` | 候选更低价优势，价格 unknown 为 missing |
| `size_fit` | same/adjacent_larger/adjacent_smaller/cross/unknown |
| `channel_overlap` | 专业电商/平台电商平台重合 |
| `param_similarity` | 目标主/次战场核心参数相似，不把 unknown 当 false |
| `param_superiority` | 候选关键参数优势，目标 unknown 时降置信 |
| `claim_confrontation` | 同战场卖点层级对打，结构化卖点缺失降置信 |
| `claim_superiority` | 候选卖点层级更强，目标证据缺失不直接判强 |
| `claim_threshold_sufficiency` | 价格挤压时验证门槛卖点未断档 |
| `market_threat` | 销量、销额、趋势、低价高销 |
| `sales_amount_strength` | 高价候选销额承接 |
| `comment_perception` | 评论感知和痛点差异，服务评论不提升产品核心 |
| `price_trend` | 高价下探、低价促销、趋势风险 |
| `evidence_completeness` | 市场、参数、卖点、评论、任务客群战场、召回证据完整度 |

### 9.4 组件公式任务

基础可比性：

```text
base_comparability_score =
  category_match * 0.20
  + size_comparable * 0.25
  + price_comparable * 0.25
  + platform_overlap * 0.20
  + profile_ready * 0.10
```

证据完整度：

```text
evidence_completeness_score =
  market_evidence * 0.22
  + param_evidence * 0.18
  + claim_evidence * 0.16
  + comment_evidence * 0.12
  + task_audience_battlefield_evidence * 0.22
  + recall_evidence * 0.10
```

结构化卖点缺失时：

- `claim_evidence` 不得直接为 0。
- 如果参数和评论可补证，`claim_evidence` 可按补证质量给 0.35-0.60。
- 必须标记 `structured_claim_missing` 或 `claim_missing`。

### 9.5 角色分任务

`RoleScoreCalculator` 必须输出 5 类角色。

正面对打：

```text
direct_fight_score =
  battlefield_fit_score * 0.22
  + claim_confrontation_score * 0.18
  + task_overlap_score * 0.14
  + audience_overlap_score * 0.10
  + price_position_score * 0.12
  + size_fit_score * 0.08
  + channel_overlap_score * 0.08
  + market_threat_score * 0.08
```

价格/销量挤压：

```text
price_volume_pressure_score =
  task_overlap_score * 0.18
  + audience_overlap_score * 0.10
  + price_advantage_score * 0.22
  + market_threat_score * 0.18
  + battlefield_fit_score * 0.12
  + channel_overlap_score * 0.08
  + claim_threshold_sufficiency_score * 0.07
  + price_trend_score * 0.05
```

高端标杆/潜在下探：

```text
benchmark_potential_score =
  param_superiority_score * 0.20
  + claim_superiority_score * 0.18
  + battlefield_fit_score * 0.18
  + sales_amount_strength_score * 0.14
  + price_premium_or_downshift_score * 0.14
  + task_overlap_score * 0.08
  + channel_overlap_score * 0.05
  + evidence_completeness_score * 0.03
```

配置拦截：

```text
configuration_pressure_score =
  param_superiority_score * 0.30
  + claim_superiority_score * 0.25
  + price_position_score * 0.15
  + battlefield_fit_score * 0.15
  + evidence_completeness_score * 0.10
  + market_threat_score * 0.05
```

服务参考：

```text
service_reference_score =
  service_signal_strength * 0.45
  + comment_perception_score * 0.25
  + evidence_completeness_score * 0.20
  + market_threat_score * 0.10
```

### 9.6 角色封顶任务

`RoleScoreCapper` 规则：

| 角色 | 封顶条件 |
| --- | --- |
| direct_fight | 无战场证据最高 0.45；无价格和尺寸证据最高 0.55；仅服务信号最高 0.30；M12 review_only 最高 0.50 |
| price_volume_pressure | 无价格优势且无销量优势最高 0.45；无市场证据最高 0.50；门槛卖点不足最高 0.65；仅任务相似最高 0.40 |
| benchmark_potential | 无参数或卖点优势最高 0.50；无战场重合最高 0.45；高价但无销额承接最高 0.65 |
| configuration_pressure | 无参数和卖点优势最高 0.35；价格跨度过大最高 0.55 |
| service_reference | 可高分，但不能提升产品核心角色 |

如果服务参考贡献进入产品核心角色，必须写 `service_over_weighted` issue。

### 9.7 总分和置信度任务

组件总分：

```text
component_total_score =
  base_comparability_score * 0.10
  + battlefield_fit_score * 0.16
  + task_overlap_score * 0.10
  + audience_overlap_score * 0.08
  + price_position_score * 0.10
  + size_fit_score * 0.06
  + channel_overlap_score * 0.06
  + param_similarity_score * 0.08
  + claim_confrontation_score * 0.12
  + market_threat_score * 0.10
  + comment_perception_score * 0.04
```

说明：

- 总分不包含 `service_reference_score`。
- 总分只用于 M14 辅助排序，不得单独作为业务结论。

综合置信度：

```text
confidence =
  min(key_component_confidences)
  * (0.60 + evidence_completeness_score * 0.40)
  * sample_status_factor
  * upstream_review_factor
```

因子：

| 因子 | 取值 |
| --- | --- |
| `sample_status=sufficient` | 1.00 |
| `sample_status=limited` | 0.80 |
| `sample_status=insufficient` | 0.55 |
| `sample_status=unknown` | 0.70 |
| 上游无 review | 1.00 |
| 上游 warning | 0.90 |
| 上游 review_required | 0.75 |
| 上游 blocker | 0.00 |

高分低置信触发：

- `component_total_score >= 0.70` 且 `confidence < 0.55`。
- 任一核心角色分 `>= 0.70` 且 `role_confidence < 0.55`。
- 角色分接近 M14 阈值但 evidence 完整度 `< 0.50`。

### 9.8 中文解释任务

`ComponentExplanationBuilder` 对 18 个组件全部输出中文解释。

模板：

战场：

```text
双方都围绕{战场中文名}竞争，目标该战场为{目标战场级别}，候选为{候选战场级别}，因此战场重合支撑较强。
```

价格：

```text
候选与目标处在{价格关系中文}，价格口径为 26W01-26W23 线上周均价，适合用于{正面对打/价格挤压/高端标杆}判断。
```

卖点：

```text
双方在{战场中文名}下的{卖点中文名}具备可比价值，候选为{候选层级中文}，目标为{目标层级中文}。
```

卖点缺失：

```text
目标缺结构化卖点记录，本组件以参数和评论补证，宣传证据置信度下降。
```

服务：

```text
该信号主要来自安装、配送或客服体验，只适合作为服务侧参考，不提升产品核心竞品角色分。
```

文案禁止：

- SQL、UUID、JSON。
- 英文字段名。
- “模型推理”“AI 判断”。
- 单独堆分数而没有业务含义。

### 9.9 复核任务

`ScoreReviewIssueBuilder` 触发条件：

1. `missing_feature_snapshot`：M12 入池但缺 pair 快照。
2. `missing_candidate_profile`：候选缺 M08 画像。
3. `no_market_evidence`：市场证据缺失但市场/价格角色分较高。
4. `no_semantic_evidence`：任务、客群、战场、卖点证据缺失但正面对打分较高。
5. `only_service_signal`：只有服务信号却出现高角色分。
6. `high_score_low_confidence`：角色分或总分高但置信度低。
7. `param_conflict`：高刷、HDMI、亮度、分区等关键参数冲突。
8. `claim_missing`：结构化卖点缺失导致卖点组件低置信。
9. `sample_insufficient`：样本不足但分数接近 M14 阈值。
10. `component_missing`：必要组件未输出解释。
11. `role_score_missing`：必要角色分缺失。
12. `service_over_weighted`：服务分影响产品核心角色分。
13. `same_family_duplicate_high_score`：同型号族候选高度重复且分数接近。

## 10. runner/API 任务

### 10.1 runner 入口

在 `component_scoring_runner.py` 实现：

```python
def run_m13_component_scoring(
    project_id: str,
    category_code: str,
    batch_id: str,
    target_sku_codes: list[str] | None = None,
    candidate_pair_ids: list[str] | None = None,
    force: bool = False,
    component_rule_version: str = "core3_mvp_real_data_v2_m13_component_v1",
    role_rule_version: str = "core3_mvp_real_data_v2_m13_role_v1",
    rule_version: str = "core3_mvp_real_data_v2_m13_v1",
) -> M13RunSummary:
    ...
```

`M13RunSummary` 字段：

| 字段 | 说明 |
| --- | --- |
| `input_pair_count` | M12 输入 pair 数 |
| `scored_pair_count` | 成功评分 pair 数 |
| `blocked_pair_count` | 阻塞 pair 数 |
| `component_score_count` | component score 记录数 |
| `role_score_count` | role score 记录数 |
| `explanation_count` | explanation 记录数 |
| `review_issue_count` | 复核问题数 |
| `high_score_low_confidence_count` | 高分低置信数量 |
| `service_over_weighted_count` | 服务过权重问题数量 |
| `changed_score_count` | 分数变化数量 |
| `downstream_invalidation_events` | 下游失效事件数 |

### 10.2 target scope

runner 支持：

| Scope | 含义 |
| --- | --- |
| `all_targets` | 批次内全部目标 |
| `target_sku_list` | 指定目标 |
| `candidate_pair_list` | 指定 pair |
| `changed_pairs` | M12/M08/M07/evidence 变化影响的 pair |

首版 API 可以只暴露 `target_sku_codes` 和 `candidate_pair_ids`，内部保留 scope 扩展位。

### 10.3 增量策略

Pair 级 `input_fingerprint`：

```text
hash(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  candidate_sku_code,
  candidate_pool_id,
  feature_snapshot_id,
  feature_snapshot_hash,
  target_profile_hash,
  candidate_profile_hash,
  evidence_revision,
  component_rule_version,
  role_rule_version,
  rule_version
)
```

`result_hash`：

```text
hash(
  component_scores_json,
  role_scores_json,
  component_total_score,
  confidence,
  risk_flags_json,
  review_required
)
```

变化传播：

| 变化来源 | M13 动作 | 下游影响 |
| --- | --- | --- |
| M12 候选新增 | 新增 pair 评分 | M14-M16 |
| M12 候选失效 | 当前 M13 评分置非 current | M14-M16 |
| M12 pair 快照变化 | 重算对应 pair | M14-M16 |
| M08 画像变化 | 通过 M12 快照变化触发；必要时校验重算 | M13-M16 |
| M09/M10/M11/M11.5 变化 | 通过 M12 快照变化触发；组件校验不一致时复核 | M13-M16 |
| M07 市场画像变化 | 重算价格、渠道、销量、趋势组件 | M13-M16 |
| M02 evidence 状态变化 | 重算证据完整度、解释和置信度 | M15-M16 |
| 评分规则变化 | 按新规则版本重算全部 current pair | M14-M16 |

### 10.4 API

在 v2 namespace 增加内部 API：

| API | 方法 | 用途 |
| --- | --- | --- |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/component-score/run` | POST | 触发目标候选评分 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/component-score/runs/{run_id}` | GET | 查看评分运行 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/score-audit` | GET | 查看候选组件分、角色分和复核问题 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/score-audit/{candidate_sku}` | GET | 查看单候选评分拆解 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/score-review-issues` | GET | 查询 M13 复核问题 |

API 约束：

- API 默认只查 `is_current=true`。
- 高层主屏不直接调用 M13 内部公式，由 M15 转中文。
- API 不返回原始评论全文大表。
- API 不暴露 SQL、UUID 列表、内部公式给高层页面。
- API 可以供运营追溯完整评分路径。

## 11. 测试任务

### 11.1 schema 和输入测试

`test_m13_component_scoring_schemas.py`：

- 18 个组件 code 完整。
- 5 个角色 code 完整。
- `component_total_score` 字段说明不是最终竞品结论。
- support_level、sample_status、issue_type 枚举完整。

`test_m13_input_loader.py`：

- 只加载 M12 current pair。
- 非 M12 pair 不评分。
- 缺 M12 snapshot 写 `missing_feature_snapshot` blocker。
- 不回读原始四表拼 snapshot。
- M12 `review_only` pair 可评分但降资格。

`test_m13_feature_normalizer.py`：

- 正确解析 `m13_component_input_json`。
- 缺部分组件输入时对应组件 missing。
- 价格 unknown 不当 lower。
- 参数 unknown 不当 false。

### 11.2 组件计算测试

`test_m13_base_comparability_calculator.py`：

- 同品类同尺寸同价同平台高分。
- 相邻尺寸/相邻价位中高分。
- 价格、尺寸、平台 unknown 降置信。

`test_m13_battlefield_fit_calculator.py`：

- 主主战场重合 1.00。
- 主次/次主中高分。
- 弱战场重合低分。
- 服务战场唯一重合标记 service_only。

`test_m13_task_audience_calculator.py`：

- 同主任务高分。
- 同主客群且同任务高分。
- 低置信客群降 confidence。
- 只有评论粗线索不得高分。

`test_m13_price_size_channel_calculator.py`：

- 价格 similar 高 price_position。
- lower 生成 price_advantage。
- higher 不生成 price_advantage。
- 线上平台只使用专业电商/平台电商。
- 不生成线下渠道判断。

`test_m13_param_calculator.py`：

- Mini LED、高亮、分区进入高端画质参数。
- 300HZ、HDMI2.1 进入游戏体育参数。
- unknown 不当 false。
- 参数冲突输出 conflict 和 `param_conflict` issue。

`test_m13_claim_value_calculator.py`：

- 同战场同绩效/溢价卖点提升 claim_confrontation。
- 候选卖点层级更强提升 claim_superiority。
- 目标弱感知而候选绩效/溢价生成配置拦截。
- 结构化卖点缺失不把卖点组件置 0，只降 confidence 并写 `claim_missing`。
- 服务卖点不提升产品核心 claim 分。

`test_m13_market_comment_calculator.py`：

- 同可比池销量/销额高提升 market_threat。
- 低价销量不弱提升价格挤压相关组件。
- 高价销额强提升标杆相关组件。
- 服务评论只进服务参考或风险。

`test_m13_evidence_completeness_calculator.py`：

- 市场、参数、卖点、评论、任务客群战场、召回 evidence 按权重计算。
- 结构化卖点缺失但参数/评论补证给 0.35-0.60。
- evidence 失效降低 confidence 或输出 issue。

### 11.3 角色、总分、解释和复核测试

`test_m13_role_score_calculator.py`：

- direct 按 0.22/0.18/0.14/0.10/0.12/0.08/0.08/0.08 计算。
- pressure 按 0.18/0.10/0.22/0.18/0.12/0.08/0.07/0.05 计算。
- benchmark 按 0.20/0.18/0.18/0.14/0.14/0.08/0.05/0.03 计算。
- configuration 和 service_reference 独立计算。

`test_m13_role_score_capper.py`：

- direct 无战场证据最高 0.45。
- pressure 无价格和销量优势最高 0.45。
- benchmark 无参数或卖点优势最高 0.50。
- M12 review_only 不能高置信自动入选。
- service_reference 不提升 direct/pressure/benchmark。

`test_m13_total_confidence_calculator.py`：

- component total 不包含 service_reference。
- 高分低证据写 `high_score_low_confidence`。
- sample_status 和 upstream review factor 影响 confidence。

`test_m13_explanation_builder.py`：

- 每个 pair 输出 18 条 explanation。
- missing 组件也输出解释。
- 中文解释不包含 SQL、UUID、JSON、英文字段名。
- 服务解释明确“只作服务侧参考”。

`test_m13_review_issue_builder.py`：

- 缺 snapshot 写 blocker。
- 无市场但价格挤压高写 review。
- 无语义但 direct 高写 review。
- 服务过权重写 `service_over_weighted`。
- 同型号族高分重复写 `same_family_duplicate_high_score`。

### 11.4 repository、runner、API 测试

`test_m13_repositories.py`：

- current 唯一索引生效。
- 重跑旧版本 `is_current=false`。
- 每个 pair 5 条 current role score。
- 每个 pair 18 条 current explanation。
- result hash 相同不重复插入业务版本。
- 事务失败不留下半成品。

`test_m13_runner.py`：

- 正常运行生成 component、role、explanation、issue。
- `force=false` 且 input hash 不变时跳过重算。
- M12 snapshot missing 时 blocked issue。
- M13 变化时发布 M14-M16 下游失效事件。

`test_m13_api.py`：

- POST run 返回运行摘要。
- GET score audit 返回候选组件分和角色分。
- 单候选 audit 返回 18 个组件解释和 5 个角色分。
- review issue API 支持 issue type 和 resolved status 过滤。
- API 默认 current。

## 12. 205/85E7Q fixture 验收

### 12.1 当前真实样例约束

必须用 fixture 固化 205 PostgreSQL 当前样例事实：

- `week_sales_data` 有 35 个量价型号。
- 当前品牌均为 `海信`。
- 周期为 `26W01` 到 `26W23`。
- 渠道只有线上。
- 平台为 `专业电商` 和 `平台电商`。
- 结构化卖点只覆盖 5 个型号。
- 评论有 33 个型号。
- 85E7Q `model_code=TV00029115`。
- 85E7Q 有 3621 行评论、1648 个去重评论 ID。
- 85E7Q 没有结构化卖点行。

### 12.2 85E7Q 关键评分断言

以 `TV00029115` / `85E7Q` 为目标，M13 必须验证：

| 场景 | 断言 |
| --- | --- |
| 同 85 寸候选 | 能输出正面对打、价格挤压或配置拦截分 |
| 75 寸候选 | 能输出降级替代或价格/销量挤压解释，不当同尺寸 |
| 100 寸候选 | 能输出升级替代或高端标杆解释，不当同尺寸 |
| Mini LED/高亮/分区 | 进入高端画质参数和卖点组件 |
| 300HZ/HDMI2.1 | 进入游戏体育参数组件 |
| 缺结构化卖点 | 卖点组件置信度降级，不判为卖点弱 |
| 服务评论 | 只影响服务参考或风险，不提升产品核心角色分 |
| 同品牌 | 海信候选正常评分，不降权、不排除 |
| 市场口径 | 使用 `26W01-26W23` 线上、专业电商/平台电商 |
| 中文解释 | 不出现 UUID、SQL、英文字段名、AI 过程话术 |

### 12.3 样例业务解释

对 85E7Q 的候选，M13 必须能输出类似解释：

- “双方都围绕高端画质战场竞争，且尺寸、价格和平台可比，因此具备正面对打基础。”
- “候选在亮度、分区或 Mini LED 等画质参数上更强，价格又处在相邻区间，因此具备配置拦截或高端标杆解释。”
- “候选价格低于 85E7Q，且销量表现不弱，同时门槛画质和大屏体验未明显断档，因此具备价格/销量挤压解释。”
- “目标缺结构化卖点记录，本组件以参数和评论补证，宣传证据置信度下降。”
- “服务或安装体验信号只作为服务侧参考，不提升产品核心竞品角色分。”

## 13. 完成标准

编码完成后必须满足：

1. 四张 M13 表 migration 可执行，downgrade 不影响 M00-M12 表。
2. 所有 M13 输出都有 `project_id`、`category_code`、`batch_id`、`run_id`、`module_run_id`。
3. M13 只评分 M12 current candidate pair。
4. M13 不直接读取原始四表。
5. M13 不对 M12 未召回的全量 SKU 评分。
6. 缺 M12 feature snapshot 时写 `missing_feature_snapshot` blocker，不回读散表补快照。
7. 每个成功评分 pair 有 1 条 current component score。
8. 每个成功评分 pair 有 5 条 current role score。
9. 每个成功评分 pair 有 18 条 current component explanation。
10. 18 个组件分全部有独立计算和测试。
11. direct、pressure、benchmark、configuration、service 五类角色分独立计算和测试。
12. `component_total_score` 只作辅助，不作为最终竞品结论。
13. `component_total_score` 不包含 `service_reference_score`。
14. 服务参考分不提升产品核心角色分。
15. 结构化卖点缺失不把卖点组件置 0，只降低置信并写缺口。
16. unknown 参数、价格、评论、市场不当 false。
17. 高分低置信写 `high_score_low_confidence`。
18. M14 可以直接消费 `core3_candidate_component_score` 和 `core3_candidate_role_score`。
19. M15 可以直接消费 `core3_candidate_component_explanation`。
20. 85E7Q 可以解释同尺寸正面对打、高端画质、游戏体育、价格挤压、卖点缺失和服务边界。
21. 中文解释不暴露 SQL、UUID、JSON、内部字段或 AI 过程文案。
22. runner 支持 `force=false` 的 input hash 跳过。
23. M13 结果变化时登记 M14-M16 下游失效事件。
24. pytest 覆盖 schema、input loader、18 组件、5 角色、封顶、置信度、解释、复核、repository、runner、API、85E7Q fixture。

建议最小验证命令：

```text
pytest apps/api-server/tests/core3_real_data/test_m13_input_loader.py
pytest apps/api-server/tests/core3_real_data/test_m13_component_score_calculator.py
pytest apps/api-server/tests/core3_real_data/test_m13_role_score_calculator.py
pytest apps/api-server/tests/core3_real_data/test_m13_role_score_capper.py
pytest apps/api-server/tests/core3_real_data/test_m13_explanation_builder.py
pytest apps/api-server/tests/core3_real_data/test_m13_runner.py
pytest apps/api-server/tests/core3_real_data/test_m13_api.py
pytest apps/api-server/tests/core3_real_data/test_m13_85e7q_fixture.py
```

## 14. 风险和回滚

### 14.1 主要风险

| 风险 | 表现 | 处理 |
| --- | --- | --- |
| M12 snapshot 缺失 | M13 想回读散表补特征 | 不补，写 `missing_feature_snapshot` blocker |
| M13 绕过 M12 评分 | 出现未召回候选分数 | repository 和测试禁止读取全量 SKU |
| 服务信号过权重 | 服务强导致 direct/pressure/benchmark 高 | `service_reference_score` 独立，写 `service_over_weighted` |
| 结构化卖点缺失误判 | 85E7Q 被判卖点弱 | 仅降宣传证据置信，不置 0 |
| 总分被误作结论 | M14/M15 直接按总分出结论 | 文档、schema、API 均标明总分仅辅助 |
| unknown 当 false | 参数或价格缺失被扣成能力弱 | 组件 calculator 明确 missing/unknown |
| 高分低证据 | M14 自动入选风险 | 写 `high_score_low_confidence` 并降低 auto_select_eligible |
| 中文解释技术化 | 页面出现字段、公式、AI 话术 | explanation builder 统一中文业务语言 |

### 14.2 回滚方式

代码回滚：

- 回退 M13 新增服务文件。
- 从 `runner.py` 移除 M13 注册。
- 从 API 移除 M13 路由。
- 不影响 M00-M12 运行。

数据库回滚：

- Alembic downgrade 删除 M13 四张表。
- 如果 M14-M16 已消费 M13，先标记下游结果失效或清理下游引用。

运行降级：

- M13 blocked 时，M14 不应自动选择该目标的三槽位。
- M13 缺 role score 时，M14 可以展示候选池但不能自动入选。
- M15 若缺 M13，只能展示 M12 召回轨迹，不能展示组件评分证据卡。

## 15. 下游依赖

### 15.1 M14 三槽位选择依赖

M14 必须以以下表为主输入：

- `core3_candidate_component_score`
- `core3_candidate_role_score`
- `core3_candidate_score_review_issue`

M14 使用：

- `direct_fight_score`
- `price_volume_pressure_score`
- `benchmark_potential_score`
- `configuration_pressure_score`
- `service_reference_score`
- `confidence`
- `evidence_completeness_score`
- `risk_flags_json`
- `auto_select_eligible`
- `auto_select_block_reason`
- unresolved review/blocker issues

M14 可以用 `component_total_score` 辅助排序，但不能用总分直接决定入选。M14 必须按 direct、pressure、benchmark 三个槽位分别选择，并结合 confidence、evidence、risk 和复核状态。

### 15.2 M15 报告依赖

M15 使用：

- `main_strengths_json`
- `main_gaps_json`
- `component_scores_json`
- `role_business_reason_cn`
- `role_business_reason_short_cn`
- `core3_candidate_component_explanation`
- evidence refs

M15 页面应把 M13 结果转成价格、渠道、参数、卖点、任务、销量、趋势的业务证据，不展示完整公式、内部英文枚举或技术字段。

### 15.3 M16 编排依赖

M16 需要：

- M13 runner status。
- component score 数量。
- role score 完整性。
- explanation 完整性。
- review issue 统计。
- high score low confidence 队列。
- service over weighted 队列。
- `input_fingerprint` 和 `result_hash`。

## 16. 子任务拆分建议

编码阶段不建议一个任务完成整个 M13。建议拆成以下小闭环：

| 子任务 | 内容 | 产物 |
| --- | --- | --- |
| D13-01 | Alembic migration | 四张表、索引、外键、downgrade |
| D13-02 | schema 和枚举 | 18 组件、5 角色、issue、runner summary |
| D13-03 | repository | M12 输入读取、M13 写入、current 版本 |
| D13-04 | input loader | pair、snapshot、profile、evidence 状态 |
| D13-05 | component calculators | 18 个组件计算 |
| D13-06 | role score calculators | 5 类角色分 |
| D13-07 | capper and confidence | 封顶、总分、综合置信度 |
| D13-08 | explanation builder | 18 个组件中文解释 |
| D13-09 | review issue builder | 复核问题 |
| D13-10 | service and runner | 编排、增量、运行摘要 |
| D13-11 | API | 运行和评分审计 API |
| D13-12 | tests and fixture | 单元、集成、85E7Q 回归 |

每个编码子任务完成后都要运行对应最小测试，不能等 M13 全部写完再测。

## 17. 下次任务

下一个开发任务文档应处理：

```text
docs/core3_mvp/real_data_v2/development/M14_development_tasks.md
```

M14 三槽位核心竞品选择模块必须以 `core3_candidate_component_score` 和 `core3_candidate_role_score` 为主输入。M14 可以使用 M13 的 `component_total_score` 辅助排序，但不能用总分直接决定入选；必须按 `direct_fight_score`、`price_volume_pressure_score`、`benchmark_potential_score` 三个槽位分别选择，并结合 `confidence`、`evidence_completeness_score`、`risk_flags_json` 和复核状态判断是否可自动入选。
