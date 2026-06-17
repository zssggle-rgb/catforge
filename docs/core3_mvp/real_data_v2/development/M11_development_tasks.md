# M11 价值战场开发任务

## 1. 模块目标

M11 的开发目标是基于 M08 SKU 综合信号画像、M09 用户任务、M10 目标客群和 M08 为 M11 裁剪的下游特征视图，判断每个 SKU 参与哪些价值战场，并输出主战场、次战场、机会战场、弱战场、置信度、证据拆分、战场组合摘要和复核问题。

M11 要解决的工程问题：

1. 将“价值战场”从卖点列表、任务列表、客群标签中解耦，改为由任务、客群、卖点、参数、评论和市场共同推导出的竞品比较语境。
2. 对每个 SKU 和 10 个 TV MVP 价值战场都生成稳定 score 行，让 M11.5-M15 不需要猜测缺行是未计算还是不相关。
3. 分离语义分和市场分，避免只靠参数、评论、任务或 seed 映射生成高置信主战场。
4. 输出战场组合摘要，明确哪些战场可作为 M12/M14 的主筛选语境，哪些只是机会监控、服务风险或报告提示。
5. 对 85E7Q 这类“85 寸、高端画质参数强、评论多、市场有、结构化卖点缺失”的 SKU，既要识别高端画质、家庭观影升级等强支撑战场，也要避免把游戏体育、大屏性价比、影院音效或服务保障过度升为主战场。
6. 用 `profile_hash`、`feature_view_hash`、`task_score_fingerprint`、`target_group_score_fingerprint`、`battlefield_seed_version`、`battlefield_seed_hash`、`rule_version` 支撑增量重算、复核追溯和下游失效传播。
7. 输出可供 M15 高层报告使用的中文业务解释和竞品选择作用，但不输出内部 code、SQL、JSON、公式或“AI 判断”式过程语言。

M11 必须固化以下边界：

- M11 只消费 M08 `core3_sku_signal_profile`、`core3_sku_signal_evidence_matrix`、`core3_sku_downstream_feature_view where for_module='M11'`。
- M11 只消费 M09 `core3_sku_task_score`、`core3_sku_task_evidence_breakdown`、`core3_sku_task_review_issue`。
- M11 只消费 M10 `core3_sku_target_group_score`、`core3_sku_target_group_evidence_breakdown`、`core3_sku_target_group_review_issue`。
- M11 不直接读取原始 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data`。
- M11 不直接读取 M03、M04b、M05、M06、M07 散表做业务字段判断。
- M11 不重新推导用户任务。
- M11 不重新推导目标客群。
- M11 不把任务、客群、卖点、参数或评论任一单域直接等同战场结论。
- M11 不从原始评论文本直接生成战场标签。
- M11 不做战场内卖点价值分层，M11.5 负责。
- M11 不召回候选 SKU，M12 负责。
- M11 不做竞品组件评分，M13 负责。
- M11 不选择核心三竞品，M14 负责。
- M11 不输出高层页最终报告，M15 负责。
- M11 不把 `unknown`、空值、`-` 或缺失值当成 false。
- M11 不按内部/外部品牌过滤，当前真实样例均为海信，海信 SKU 也可以参与后续竞品推导。
- M11 不把 `BF_SERVICE_ASSURANCE` 默认作为产品核心筛选主线。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M11 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M11_battlefield_requirements.md` |
| M11 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M11_battlefield_design.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M08 任务 | `docs/core3_mvp/real_data_v2/development/M08_development_tasks.md` |
| M09 任务 | `docs/core3_mvp/real_data_v2/development/M09_development_tasks.md` |
| M10 任务 | `docs/core3_mvp/real_data_v2/development/M10_development_tasks.md` |
| M08 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M08_sku_signal_profile_design.md` |
| M09 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M09_user_task_design.md` |
| M10 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M10_target_group_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 参考模块 | `cankao/catforge_sop_md/modules/M11_价值战场模块.md` |
| 价值战场 seed | `apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` |

编码前必须确认：

- M08 已输出 `core3_sku_signal_profile`，并包含 `profile_hash`、`profile_status`、`profile_confidence`、`domain_completeness_json`、`missing_signals_json`、`risk_signals_json`。
- M08 已输出 `core3_sku_signal_evidence_matrix`，并能按 SKU、证据域和 evidence refs 回溯。
- M08 已输出 `core3_sku_downstream_feature_view where for_module='M11'`，并包含 `feature_view_hash` 或 `view_hash`。
- M08 feature view 中已有战场所需的参数能力、卖点激活、评论战场支撑、痛点风险、价格感知、服务信号、市场画像、可比池和证据引用。
- M09 已输出 `core3_sku_task_score`、`core3_sku_task_evidence_breakdown`、`core3_sku_task_review_issue`。
- M10 已输出 `core3_sku_target_group_score`、`core3_sku_target_group_evidence_breakdown`、`core3_sku_target_group_review_issue`。
- `tv_core3_mvp_seed_v0_2.json` 中 `battlefields` 正好覆盖 10 个 MVP 战场。
- INFRA 已提供 run context、hash 工具、runner 协议、复核 issue 约定、current 版本约定和测试 fixture 基础。

## 3. 本次范围

本次开发任务拆分覆盖 M11 的后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 5 张 M11 输出表 |
| model/schema | 新增战场 seed、M11 输入、候选、分域得分、战场得分、证据拆分、portfolio、复核、runner、API schema |
| seed loader | 读取并校验真实 TV 价值战场 seed，保存 seed 版本和 hash |
| M08 input loader | 只读取 M08 profile、M11 feature view、evidence matrix |
| M09 input loader | 只读取 M09 task score、task evidence breakdown、task review issue |
| M10 input loader | 只读取 M10 target group score、target group evidence breakdown、target group review issue |
| candidate builder | 对每个 SKU x 10 个战场生成候选、拒绝、复核或阻塞记录 |
| domain scorer | 分别计算任务、客群、卖点、参数、评论、市场、服务分域得分 |
| semantic/market scorer | 分离语义分、市场分和最终战场分 |
| risk evaluator | 执行 only_comment、only_service、market_missing、claim_missing、param_conflict、upstream_review、service_as_core_battlefield 等封顶和复核规则 |
| relation classifier | 输出 main、secondary、opportunity、weak、insufficient、blocked 关系等级 |
| role builder | 输出 primary_search_context、secondary_search_context、opportunity_monitoring、risk_or_service_context 等竞品筛选作用 |
| confidence calculator | 基于战场分、证据覆盖、M09/M10 置信度、M08 画像置信度和证据质量计算置信度 |
| business reason builder | 生成业务化中文原因和竞品选择作用说明 |
| evidence breakdown | 输出任务、客群、卖点、参数、评论、市场、服务、风险、seed、profile 分域证据拆分 |
| portfolio builder | 生成 SKU 战场组合摘要和 M12/M14 主筛选语境 |
| review issue | 输出缺 M08 特征视图、缺 M09/M10 结果、仅评论、仅服务、市场缺失、参数冲突、服务误作核心战场等复核问题 |
| invalidation | 战场结果或组合摘要变化时登记 M11.5-M16 下游影响 |
| runner/API | 运行入口、战场列表查询、战场详情查询、证据拆分查询、portfolio 查询、复核问题查询 |
| 测试 | 单元、集成、API、增量、边界、85E7Q fixture |

本次不做：

- 不实现 M11.5 战场内卖点价值分层。
- 不实现 M12 候选池召回。
- 不实现 M13 竞品组件评分。
- 不实现 M14 核心三竞品选择。
- 不实现 M15 高层报告页。
- 不实现前端页面。
- 不部署到 205。
- 不修改价值战场 seed 内容，seed 只读校验。
- 不新增临时价值战场。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/battlefield_schemas.py
apps/api-server/app/services/core3_real_data/battlefield_repositories.py
apps/api-server/app/services/core3_real_data/battlefield_seed_loader.py
apps/api-server/app/services/core3_real_data/m11_feature_view_loader.py
apps/api-server/app/services/core3_real_data/m11_task_result_loader.py
apps/api-server/app/services/core3_real_data/m11_target_group_result_loader.py
apps/api-server/app/services/core3_real_data/battlefield_candidate_builder.py
apps/api-server/app/services/core3_real_data/battlefield_domain_scorer.py
apps/api-server/app/services/core3_real_data/battlefield_semantic_market_scorer.py
apps/api-server/app/services/core3_real_data/battlefield_risk_evaluator.py
apps/api-server/app/services/core3_real_data/battlefield_relation_classifier.py
apps/api-server/app/services/core3_real_data/competitor_selection_role_builder.py
apps/api-server/app/services/core3_real_data/battlefield_confidence_calculator.py
apps/api-server/app/services/core3_real_data/battlefield_business_reason_builder.py
apps/api-server/app/services/core3_real_data/battlefield_evidence_breakdown_builder.py
apps/api-server/app/services/core3_real_data/battlefield_portfolio_builder.py
apps/api-server/app/services/core3_real_data/battlefield_review_issue_builder.py
apps/api-server/app/services/core3_real_data/battlefield_invalidation_publisher.py
apps/api-server/app/services/core3_real_data/battlefield_service.py
apps/api-server/app/services/core3_real_data/battlefield_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `battlefield_schemas.py` | M11 内部 typed contracts、枚举、runner summary |
| `battlefield_repositories.py` | 读取 M08/M09/M10 输入、写入 M11 输出、查询 current 结果 |
| `battlefield_seed_loader.py` | 读取 `tv_core3_mvp_seed_v0_2.json.battlefields`、校验 10 个战场、生成 seed hash |
| `m11_feature_view_loader.py` | 加载并校验 M08 M11 feature view、profile、evidence matrix |
| `m11_task_result_loader.py` | 加载 M09 task score、task evidence breakdown、task review issue |
| `m11_target_group_result_loader.py` | 加载 M10 target group score、breakdown、review issue |
| `battlefield_candidate_builder.py` | 生成 SKU x 战场候选、拒绝、阻塞和候选原因 |
| `battlefield_domain_scorer.py` | 计算任务、客群、卖点、参数、评论、市场、服务分域得分 |
| `battlefield_semantic_market_scorer.py` | 计算 semantic_score、market_score、raw_battlefield_score |
| `battlefield_risk_evaluator.py` | 计算风险扣分、封顶、复核原因 |
| `battlefield_relation_classifier.py` | 根据得分、证据域覆盖和封顶结果输出关系等级 |
| `competitor_selection_role_builder.py` | 生成竞品筛选作用和中文说明 |
| `battlefield_confidence_calculator.py` | 计算 M11 battlefield confidence |
| `battlefield_business_reason_builder.py` | 生成业务中文解释和结构化中文解释片段 |
| `battlefield_evidence_breakdown_builder.py` | 生成分域证据拆分记录 |
| `battlefield_portfolio_builder.py` | 生成 SKU 战场组合摘要 |
| `battlefield_review_issue_builder.py` | 生成战场级和 SKU 级复核问题 |
| `battlefield_invalidation_publisher.py` | M11 result hash 或 portfolio 变化时登记 M11.5-M16 下游失效 |
| `battlefield_service.py` | M11 编排 service |
| `battlefield_runner.py` | M11 runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0018_core3_real_data_battlefield.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0018_core3_real_data_battlefield.py` | 新增 M11 5 张输出表、索引、唯一键、枚举约束 |
| `core3_real_data.py` schema | 导出 M11 运行、战场列表、战场详情、证据拆分、portfolio 和复核问题 response |
| `core3_real_data.py` API | 增加 M11 v2 API，不能影响旧接口 |
| `constants.py` | 补 M11 battlefield code、candidate status、relation level、evidence domain、role、review issue type |
| `runner.py` | 注册 M11 runner，不改变 M00-M10 逻辑 |
| `conftest.py` | 增加 M08/M09/M10 输入 fixture、价值战场 seed fixture、85E7Q fixture |

如果 Alembic 当前最新编号不是 `0017`，编码时按最新编号顺延，但 migration 内容仍只能包含 M11 表、索引、约束。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m11_battlefield_seed_loader.py
apps/api-server/tests/core3_real_data/test_m11_feature_view_loader.py
apps/api-server/tests/core3_real_data/test_m11_task_result_loader.py
apps/api-server/tests/core3_real_data/test_m11_target_group_result_loader.py
apps/api-server/tests/core3_real_data/test_m11_candidate_builder.py
apps/api-server/tests/core3_real_data/test_m11_domain_scorer.py
apps/api-server/tests/core3_real_data/test_m11_semantic_market_scorer.py
apps/api-server/tests/core3_real_data/test_m11_risk_evaluator.py
apps/api-server/tests/core3_real_data/test_m11_relation_classifier.py
apps/api-server/tests/core3_real_data/test_m11_competitor_selection_role_builder.py
apps/api-server/tests/core3_real_data/test_m11_confidence_calculator.py
apps/api-server/tests/core3_real_data/test_m11_business_reason_builder.py
apps/api-server/tests/core3_real_data/test_m11_evidence_breakdown_builder.py
apps/api-server/tests/core3_real_data/test_m11_portfolio_builder.py
apps/api-server/tests/core3_real_data/test_m11_review_issue_builder.py
apps/api-server/tests/core3_real_data/test_m11_repositories.py
apps/api-server/tests/core3_real_data/test_m11_runner.py
apps/api-server/tests/core3_real_data/test_m11_api.py
apps/api-server/tests/core3_real_data/test_m11_no_business_outputs.py
apps/api-server/tests/core3_real_data/test_m11_85e7q_fixture.py
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

不得在 M11 中改动或重写：

- M00-M10 已有 migration 的业务含义。
- M06 评论战场支撑和痛点抽取逻辑。
- M07 市场画像和可比池逻辑。
- M08 SKU 画像和 feature view 口径。
- M09 用户任务推导逻辑。
- M10 目标客群推导逻辑。
- 205 部署脚本或 nginx 配置。

如果发现 M08 M11 特征不够、M09 任务结果缺失或 M10 客群结果缺失，M11 只输出 `blocked` 或 `review_required`，不能在本模块绕过上游重新拼装散表。

## 6. 数据库迁移任务

### 6.1 新增 migration

新增：

```text
apps/api-server/alembic/versions/0018_core3_real_data_battlefield.py
```

新增 5 张表：

| 表 | 粒度 | 用途 |
| --- | --- | --- |
| `core3_sku_battlefield_candidate` | SKU + battlefield + input fingerprint | 记录为什么进入候选、被拒绝、阻塞或需复核 |
| `core3_sku_battlefield_score` | SKU + battlefield + rule version | 记录语义分、市场分、战场分、关系等级、竞品选择作用和中文解释 |
| `core3_sku_battlefield_evidence_breakdown` | SKU + battlefield + evidence domain | 记录任务、客群、卖点、参数、评论、市场、服务、风险分域证据 |
| `core3_sku_battlefield_portfolio` | SKU + rule version | 记录战场组合摘要和竞品筛选主语境 |
| `core3_sku_battlefield_review_issue` | SKU + battlefield 或 SKU 级 issue | 记录战场推断复核问题 |

### 6.2 通用字段

5 张输出表都必须保留：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid/text | 是 | 主键，实际可用模块专属 ID 字段 |
| `project_id` | text | 是 | 项目 ID |
| `category_code` | text | 是 | MVP 为 `TV` |
| `batch_id` | text | 是 | 批次 ID |
| `run_id` | text | 否 | 全链路运行 ID |
| `module_run_id` | text | 否 | M11 模块运行 ID |
| `sku_code` | text | 是 | SKU 编号 |
| `model_code` | text | 否 | 真实样例中如 `TV00029115` |
| `model_name` | text | 否 | 真实样例中如 `85E7Q` |
| `brand_name` | text | 否 | 当前样例为海信 |
| `rule_version` | text | 是 | 默认 `core3_mvp_real_data_v2_m11_v1` |
| `battlefield_seed_version` | text | 是 | 默认 `tv_core3_mvp_seed_v0_2` |
| `battlefield_seed_file_version` | text | 是 | seed 文件内 `core3-mvp-0.2.0` |
| `battlefield_seed_hash` | text | 是 | seed 文件内容 hash |
| `profile_hash` | text | 是 | M08 SKU profile hash |
| `feature_view_hash` | text | 是 | M08 M11 view hash |
| `task_score_fingerprint` | text | 是 | M09 task score、breakdown、review issue 指纹 |
| `target_group_score_fingerprint` | text | 是 | M10 target group score、breakdown、review issue 指纹 |
| `input_fingerprint` | text | 是 | 输入指纹 |
| `result_hash` | text | 是 | 输出内容 hash |
| `is_current` | boolean | 是 | 是否当前版本 |
| `processing_status` | text | 是 | `success`、`warning`、`review_required`、`blocked`、`failed` |
| `review_required` | boolean | 是 | 是否需要复核 |
| `review_status` | text | 是 | `auto_pass`、`review_required`、`approved`、`rejected`、`waived` |
| `review_reason_json` | jsonb | 是 | 复核原因 |
| `created_at` | timestamptz | 是 | 创建时间 |
| `updated_at` | timestamptz | 是 | 更新时间 |

### 6.3 `core3_sku_battlefield_candidate`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sku_battlefield_candidate_id` | uuid | 是 | 主键 |
| `sku_signal_profile_id` | uuid | 是 | M08 profile ID |
| `sku_downstream_feature_view_id` | uuid | 是 | M08 M11 feature view ID |
| `battlefield_code` | text | 是 | 10 个 seed 战场之一 |
| `battlefield_name_cn` | text | 是 | 中文业务名 |
| `battlefield_definition_cn` | text | 是 | 战场定义 |
| `candidate_status` | text | 是 | `active`、`rejected`、`review_required`、`blocked` |
| `candidate_source_json` | jsonb | 是 | task、target_group、claim、param、comment、market、service、seed_hint、seed_gap |
| `candidate_source_count` | integer | 是 | 有效来源数 |
| `source_task_codes_json` | jsonb | 是 | 来源任务、关系等级、任务分 |
| `source_target_group_codes_json` | jsonb | 是 | 来源客群、关系等级、客群分 |
| `candidate_initial_score` | numeric | 是 | 候选初始分 |
| `candidate_reason_cn` | text | 是 | 中文候选原因 |
| `reject_reason_json` | jsonb | 是 | 被拒绝原因 |
| `missing_signals_json` | jsonb | 是 | 缺失信号 |
| `risk_flags_json` | jsonb | 是 | 风险 |
| `evidence_ids` | uuid[] | 是 | 候选代表 evidence |
| `evidence_matrix_refs_json` | jsonb | 是 | M08 evidence matrix refs |

当前版本唯一索引：

```text
ux_m11_battlefield_candidate_current(project_id, category_code, batch_id, sku_code, battlefield_code, battlefield_seed_version, rule_version)
  where is_current = true
```

查询索引：

- `(project_id, category_code, batch_id, sku_code, is_current)`
- `(project_id, category_code, batch_id, battlefield_code, candidate_status, is_current)`
- `(project_id, category_code, batch_id, review_required, is_current)`
- `(project_id, category_code, batch_id, input_fingerprint)`
- GIN `candidate_source_json`

### 6.4 `core3_sku_battlefield_score`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sku_battlefield_score_id` | uuid | 是 | 主键 |
| `sku_signal_profile_id` | uuid | 是 | M08 profile ID |
| `sku_downstream_feature_view_id` | uuid | 是 | M08 M11 feature view ID |
| `battlefield_code` | text | 是 | 10 个 seed 战场之一 |
| `battlefield_name_cn` | text | 是 | 中文业务名 |
| `battlefield_definition_cn` | text | 是 | 战场定义 |
| `candidate_id` | uuid | 否 | 对应 candidate |
| `semantic_score` | numeric | 是 | 语义分 |
| `market_score` | numeric | 是 | 市场分 |
| `core_task_score` | numeric | 是 | M09 核心任务支撑分 |
| `target_group_score` | numeric | 是 | M10 客群支撑分 |
| `core_claim_combo_score` | numeric | 是 | 核心卖点组合分 |
| `core_param_capability_score` | numeric | 是 | 参数能力分 |
| `comment_support_score` | numeric | 是 | 评论战场支撑分 |
| `pain_point_risk_score` | numeric | 是 | 痛点风险分 |
| `price_position_score` | numeric | 是 | 价格位置分 |
| `sales_validation_score` | numeric | 是 | 销量验证分 |
| `sales_amount_validation_score` | numeric | 是 | 销额验证分 |
| `channel_fit_score` | numeric | 是 | 渠道/平台适配分 |
| `trend_signal_score` | numeric | 是 | 趋势分 |
| `comparable_pool_strength` | numeric | 是 | 可比池强度 |
| `raw_battlefield_score` | numeric | 是 | 风险修正前战场分 |
| `risk_penalty` | numeric | 是 | 风险扣分 |
| `battlefield_score` | numeric | 是 | 最终战场分 |
| `relation_level` | text | 是 | `main`、`secondary`、`opportunity`、`weak`、`insufficient`、`blocked` |
| `relation_reason_json` | jsonb | 是 | 关系等级判定原因 |
| `competitor_selection_role` | text | 是 | `primary_search_context`、`secondary_search_context`、`opportunity_monitoring`、`risk_or_service_context`、`not_for_core_search` |
| `competitor_selection_role_cn` | text | 是 | 对后续竞品选择的中文作用 |
| `sample_sufficiency` | text | 是 | `sufficient`、`limited`、`insufficient`、`unknown` |
| `confidence` | numeric | 是 | 置信度 |
| `confidence_level` | text | 是 | `high`、`medium`、`low`、`unknown` |
| `evidence_domain_count` | integer | 是 | 有效证据域数量 |
| `effective_domain_json` | jsonb | 是 | 哪些域有效 |
| `score_breakdown_json` | jsonb | 是 | 权重、原始分、封顶、风险 |
| `cap_rule_applied_json` | jsonb | 是 | 触发的封顶规则 |
| `missing_signals_json` | jsonb | 是 | 缺失信号 |
| `risk_flags_json` | jsonb | 是 | 风险 |
| `business_reason_cn` | text | 是 | 中文业务解释摘要 |
| `business_reason_parts_json` | jsonb | 是 | 任务、客群、产品价值、用户感知、市场验证、竞品作用、复核点 |
| `next_module_payload_json` | jsonb | 是 | M11.5-M15 可消费精简 payload |
| `evidence_ids` | uuid[] | 是 | 核心 evidence |
| `evidence_matrix_refs_json` | jsonb | 是 | M08 evidence matrix refs |

MVP 建议每个有效 SKU 对 10 个战场都生成一行 score。未命中的战场 `relation_level='insufficient'`，缺关键输入时 `relation_level='blocked'`。

当前版本唯一索引：

```text
ux_m11_battlefield_score_current(project_id, category_code, batch_id, sku_code, battlefield_code, battlefield_seed_version, rule_version)
  where is_current = true
```

查询索引：

- `(project_id, category_code, batch_id, sku_code, relation_level, battlefield_score desc)`
- `(project_id, category_code, batch_id, battlefield_code, relation_level, is_current)`
- `(project_id, category_code, batch_id, sku_code, competitor_selection_role, battlefield_score desc)`
- `(project_id, category_code, batch_id, profile_hash, task_score_fingerprint, target_group_score_fingerprint, battlefield_seed_version, rule_version)`
- GIN `score_breakdown_json`
- GIN `cap_rule_applied_json`
- GIN `next_module_payload_json`

### 6.5 `core3_sku_battlefield_evidence_breakdown`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sku_battlefield_evidence_breakdown_id` | uuid | 是 | 主键 |
| `sku_battlefield_score_id` | uuid | 是 | 对应 score |
| `battlefield_code` | text | 是 | 战场 code |
| `evidence_domain` | text | 是 | `task`、`target_group`、`claim`、`param`、`comment`、`market`、`service`、`risk`、`seed`、`profile` |
| `support_level` | text | 是 | `strong`、`medium`、`weak`、`missing`、`conflict`、`not_applicable` |
| `support_score` | numeric | 是 | 分域原始分 |
| `domain_weight` | numeric | 是 | 该域权重 |
| `weighted_contribution` | numeric | 是 | 加权贡献 |
| `support_summary_cn` | text | 是 | 中文证据摘要 |
| `source_signal_codes_json` | jsonb | 是 | 来源任务、客群、卖点、参数、评论主题、市场信号或 seed 信号 |
| `source_values_json` | jsonb | 是 | 命中的具体值和强度 |
| `representative_evidence_ids` | uuid[] | 是 | 代表 evidence |
| `evidence_matrix_refs_json` | jsonb | 是 | M08 evidence matrix refs |
| `missing_reason_code` | text | 否 | 缺失原因 |
| `risk_flags_json` | jsonb | 是 | 风险 |
| `confidence` | numeric | 是 | 分域置信度 |

每个 score 至少输出以下域记录：

```text
task
target_group
claim
param
comment
market
service
risk
```

缺失域也要输出 `support_level='missing'` 或 `not_applicable`，避免下游误判没有计算。

唯一键：

```text
ux_m11_battlefield_breakdown_current(project_id, category_code, batch_id, sku_code, battlefield_code, evidence_domain, battlefield_seed_version, rule_version)
  where is_current = true
```

索引：

- `(sku_battlefield_score_id, evidence_domain)`
- `(project_id, category_code, batch_id, sku_code, battlefield_code, is_current)`
- `(project_id, category_code, batch_id, evidence_domain, support_level, is_current)`
- GIN `representative_evidence_ids`
- GIN `source_signal_codes_json`

### 6.6 `core3_sku_battlefield_portfolio`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sku_battlefield_portfolio_id` | uuid | 是 | 主键 |
| `sku_signal_profile_id` | uuid | 是 | M08 profile ID |
| `main_battlefields_json` | jsonb | 是 | 主战场列表，按分数排序 |
| `secondary_battlefields_json` | jsonb | 是 | 次战场列表 |
| `opportunity_battlefields_json` | jsonb | 是 | 机会战场列表 |
| `weak_battlefields_json` | jsonb | 是 | 弱战场列表 |
| `insufficient_battlefields_json` | jsonb | 是 | 证据不足战场列表 |
| `primary_competitor_search_context_cn` | text | 是 | 竞品筛选主语境中文摘要 |
| `primary_search_battlefield_codes_json` | jsonb | 是 | M12/M14 主召回战场，最多 3 个 |
| `secondary_search_battlefield_codes_json` | jsonb | 是 | M12/M14 辅助召回战场 |
| `opportunity_monitoring_codes_json` | jsonb | 是 | 机会监控战场 |
| `risk_or_service_context_json` | jsonb | 是 | 服务和风险上下文 |
| `portfolio_confidence` | numeric | 是 | 组合置信度 |
| `portfolio_risk_flags_json` | jsonb | 是 | 组合风险 |
| `battlefield_score_refs_json` | jsonb | 是 | 关联 score ID 和 hash |
| `evidence_ids` | uuid[] | 是 | 核心 evidence |

portfolio 规则：

- `main_battlefields_json` 按 `battlefield_score desc, confidence desc` 排序。
- 如果没有 main，用最高 secondary 作为主筛选语境，但标记 `no_main_battlefield`。
- `primary_search_battlefield_codes_json` 默认取 main 战场，最多 3 个。
- `BF_SERVICE_ASSURANCE` 默认进入 `risk_or_service_context_json`，不进入主召回战场。

当前版本唯一索引：

```text
ux_m11_battlefield_portfolio_current(project_id, category_code, batch_id, sku_code, battlefield_seed_version, rule_version)
  where is_current = true
```

索引：

- `(project_id, category_code, batch_id, sku_code, is_current)`
- `(project_id, category_code, batch_id, portfolio_confidence desc, review_required, is_current)`
- GIN `primary_search_battlefield_codes_json`
- GIN `risk_or_service_context_json`

### 6.7 `core3_sku_battlefield_review_issue`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sku_battlefield_review_issue_id` | uuid | 是 | 主键 |
| `battlefield_code` | text | 否 | 为空表示 SKU 级问题 |
| `issue_type` | text | 是 | 复核类型 |
| `issue_level` | text | 是 | `warning`、`blocker` |
| `issue_message_cn` | text | 是 | 中文复核说明 |
| `issue_context_json` | jsonb | 是 | 结构化复核详情 |
| `related_score_id` | uuid | 否 | 关联战场分 |
| `related_candidate_id` | uuid | 否 | 关联候选 |
| `source_task_score_ids` | uuid[] | 是 | 来源 M09 任务记录 |
| `source_target_group_score_ids` | uuid[] | 是 | 来源 M10 客群记录 |
| `evidence_ids` | uuid[] | 是 | 相关证据 |
| `resolved_status` | text | 是 | `open`、`resolved`、`ignored` |
| `resolved_by` | text | 否 | 处理人 |
| `resolved_at` | timestamptz | 否 | 处理时间 |
| `resolution_note` | text | 否 | 处理说明 |

`issue_type` 至少覆盖：

```text
missing_feature_view
missing_task_score
missing_target_group_score
only_comment
only_service
market_missing
market_limited
claim_missing
param_conflict
upstream_review
seed_gap
profile_blocked
high_score_contradiction
service_as_core_battlefield
seed_hint_only
unknown_input
comparable_pool_insufficient
```

表达式唯一索引：

```text
ux_m11_battlefield_review_issue_current(project_id, category_code, batch_id, sku_code, coalesce(battlefield_code, ''), issue_type, input_fingerprint)
  where is_current = true
```

索引：

- `(project_id, category_code, batch_id, resolved_status, issue_level, is_current)`
- `(project_id, category_code, batch_id, sku_code, battlefield_code, is_current)`
- `(project_id, category_code, batch_id, issue_type, is_current)`

## 7. model/schema 任务

### 7.1 枚举

在 `battlefield_schemas.py` 和必要的 API schema 中定义：

```text
BattlefieldCandidateStatus = active | rejected | review_required | blocked
BattlefieldCandidateSource = task | target_group | claim | param | comment | market | service | seed_hint | seed_gap
BattlefieldRelationLevel = main | secondary | opportunity | weak | insufficient | blocked
BattlefieldEvidenceDomain = task | target_group | claim | param | comment | market | service | risk | seed | profile
BattlefieldSupportLevel = strong | medium | weak | missing | conflict | not_applicable
CompetitorSelectionRole = primary_search_context | secondary_search_context | opportunity_monitoring | risk_or_service_context | not_for_core_search
BattlefieldReviewIssueType = missing_feature_view | missing_task_score | missing_target_group_score | only_comment | only_service | market_missing | market_limited | claim_missing | param_conflict | upstream_review | seed_gap | profile_blocked | high_score_contradiction | service_as_core_battlefield | seed_hint_only | unknown_input | comparable_pool_insufficient
```

### 7.2 seed schema

新增 typed contracts：

| schema | 关键字段 |
| --- | --- |
| `BattlefieldSeedSet` | `category_code`、`file_version`、`battlefield_seed_version`、`battlefield_seed_hash`、`battlefields` |
| `BattlefieldSeed` | `battlefield_code`、`battlefield_name_cn`、`definition_cn`、`aliases`、`keywords` |
| `BattlefieldSignalRule` | `core_task_codes`、`core_claim_codes`、`core_param_codes`、`comment_topic_codes` |
| `BattlefieldSemanticMarketWeights` | `semantic`、`market` |
| `BattlefieldMarketScoreRule` | `signals`、可识别市场信号、unknown 信号 |
| `BattlefieldEntryThresholds` | `main`、`secondary`、`weak`，以及默认 opportunity 推导阈值 |

必须校验 10 个战场：

```text
BF_PREMIUM_PICTURE
BF_FAMILY_VIEWING_UPGRADE
BF_GAMING_SPORTS
BF_LARGE_SCREEN_VALUE
BF_FAMILY_EYE_CARE
BF_SENIOR_EASE_OF_USE
BF_SMART_SYSTEM_EXPERIENCE
BF_CINEMA_AUDIO_IMMERSION
BF_DESIGN_HOME_FIT
BF_SERVICE_ASSURANCE
```

M11 必须以真实 seed 的 10 个战场为准，不能使用旧 SOP 参考中的过时代码，也不能临时新增战场。

seed 校验要求：

- `category_code='TV'`。
- `battlefields` 正好覆盖 10 个 MVP battlefield_code。
- 每个战场有中文名称、定义、核心任务、语义/市场权重和进入阈值。
- `core_task_codes` 均存在于 M09 10 个任务 seed。
- `core_claim_codes`、`core_param_codes`、`comment_topic_codes` 可识别；无法观测的信号标记为 unknown，不当负向。
- `semantic_market_weights.semantic + semantic_market_weights.market = 1.0`。
- `entry_thresholds` 顺序合理。
- battlefield_code 无重复。
- seed hash 可稳定计算。

### 7.3 M08/M09/M10 输入 schema

新增：

| schema | 用途 |
| --- | --- |
| `M11FeatureViewInput` | 承载 M08 `for_module='M11'` 特征包 |
| `M11SkuProfileInput` | 承载 M08 SKU profile 摘要、状态和 `profile_hash` |
| `M11EvidenceMatrixInput` | 承载 M08 分域 evidence matrix |
| `M11TaskScoreInput` | 承载 M09 task score |
| `M11TaskBreakdownInput` | 承载 M09 task evidence breakdown |
| `M11TargetGroupScoreInput` | 承载 M10 target group score |
| `M11TargetGroupBreakdownInput` | 承载 M10 target group evidence breakdown |
| `M11UpstreamReviewInput` | 承载 M09/M10 open review issue 摘要 |
| `M11BattlefieldFeatureBundle` | 合并 M08/M09/M10 后的单 SKU 输入 |

输入 schema 必须表达：

- `profile_status`
- `profile_hash`
- `feature_view_hash`
- `task_score_fingerprint`
- `target_group_score_fingerprint`
- `input_fingerprint`
- M09 task score、relation level、confidence、review_required
- M10 target group score、relation level、confidence、review_required
- M08 参数能力、卖点激活、评论战场支撑、痛点风险、价格感知、服务信号、市场画像、可比池
- M08 evidence refs and evidence matrix refs
- M08 missing/risk/domain completeness

### 7.4 输出 schema

新增：

| schema | 用途 |
| --- | --- |
| `BattlefieldCandidateRecord` | 对应 `core3_sku_battlefield_candidate` |
| `BattlefieldDomainScore` | 任务、客群、卖点、参数、评论、市场、服务单域评分 |
| `BattlefieldSemanticMarketScore` | 语义分、市场分、raw score |
| `BattlefieldRiskDecision` | 风险扣分、封顶和复核 |
| `BattlefieldScoreRecord` | 对应 `core3_sku_battlefield_score` |
| `BattlefieldEvidenceBreakdownRecord` | 对应 `core3_sku_battlefield_evidence_breakdown` |
| `BattlefieldPortfolioRecord` | 对应 `core3_sku_battlefield_portfolio` |
| `BattlefieldReviewIssueRecord` | 对应 `core3_sku_battlefield_review_issue` |
| `M11RunRequest` | runner/API 请求 |
| `M11RunSummary` | 运行汇总 |
| `SkuBattlefieldListResponse` | SKU 战场列表 API 返回 |
| `SkuBattlefieldDetailResponse` | 单战场详情 API 返回 |
| `SkuBattlefieldEvidenceResponse` | 证据拆分 API 返回 |
| `SkuBattlefieldPortfolioResponse` | 战场组合摘要 API 返回 |

输出 schema 必须避免把内部调试字段直接暴露给前端高层页面。API 可以返回机器字段，但业务页面消费时必须有中文业务字段。

## 8. repository 任务

### 8.1 读取职责

`BattlefieldRepository` 只允许读取：

| 来源 | 查询 |
| --- | --- |
| M08 profile | `core3_sku_signal_profile where is_current=true` |
| M08 feature view | `core3_sku_downstream_feature_view where for_module='M11' and is_current=true` |
| M08 evidence matrix | `core3_sku_signal_evidence_matrix where is_current=true` |
| M09 task score | `core3_sku_task_score where is_current=true` |
| M09 task evidence breakdown | `core3_sku_task_evidence_breakdown where is_current=true` |
| M09 task review issue | `core3_sku_task_review_issue where is_current=true` |
| M10 target group score | `core3_sku_target_group_score where is_current=true` |
| M10 target group evidence breakdown | `core3_sku_target_group_evidence_breakdown where is_current=true` |
| M10 target group review issue | `core3_sku_target_group_review_issue where is_current=true` |
| M02 evidence atom | 仅按 M08/M09/M10 evidence refs 批量回溯，不做业务扫描 |
| M11 历史输出 | 查询可复用 current 记录和旧版本失效 |

不得增加以下 repository 查询：

- 直接查 `week_sales_data`。
- 直接查 `attribute_data`。
- 直接查 `selling_points_data`。
- 直接查 `comment_data`。
- 直接查 M03/M04b/M05/M06/M07 散表做业务判断。

### 8.2 写入职责

`BattlefieldRepository` 必须支持：

1. `mark_previous_records_not_current(...)`
2. `bulk_insert_candidates(...)`
3. `bulk_insert_scores(...)`
4. `bulk_insert_evidence_breakdowns(...)`
5. `upsert_portfolios(...)`
6. `bulk_insert_review_issues(...)`
7. `get_current_battlefield_scores(...)`
8. `get_battlefield_detail(...)`
9. `get_battlefield_evidence_breakdown(...)`
10. `get_battlefield_portfolio(...)`
11. `list_review_issues(...)`

写入约定：

- 同一 SKU、battlefield、rule、seed hash 的新结果写入前，旧 current 记录必须置为 `is_current=false`。
- 写入 candidate、score、breakdown、portfolio、review issue 必须在同一事务内完成。
- 任一 SKU feature view 缺失、M09 task score 缺失或 M10 target group score 缺失时，该 SKU 的 10 个战场应写 `blocked` score 或复核问题，不能静默跳过。
- repository 不计算业务分，只负责持久化和查询。

### 8.3 查询返回顺序

SKU 战场列表默认排序：

1. `relation_level` 按 main、secondary、opportunity、weak、insufficient、blocked。
2. `battlefield_score desc`。
3. `confidence desc`。
4. seed 中战场顺序。

战场详情必须返回：

- 战场中文名。
- 关系等级。
- 语义分、市场分、最终分和置信度。
- 任务、客群、卖点、参数、评论、市场、服务分域得分。
- 竞品选择作用。
- 业务解释。
- 分域证据拆分。
- 复核问题。

## 9. service 任务

### 9.1 编排流程

`BattlefieldService.run(...)` 按以下步骤执行：

1. 构建 run context 和 `module_run_id`。
2. 加载并校验价值战场 seed。
3. 读取 SKU 范围内 M08 profile、M11 feature view、evidence matrix。
4. 读取 SKU 范围内 M09 task score、task evidence breakdown、task review issue。
5. 读取 SKU 范围内 M10 target group score、target group evidence breakdown、target group review issue。
6. 对缺失 M08 feature view 的 SKU 生成 `missing_feature_view` 阻塞问题。
7. 对缺失 M09 task score 的 SKU 生成 `missing_task_score` 阻塞问题。
8. 对缺失 M10 target group score 的 SKU 生成 `missing_target_group_score` 阻塞问题。
9. 对每个有效 SKU 遍历 10 个 seed 战场。
10. `BattlefieldCandidateBuilder` 生成候选、拒绝、复核或阻塞。
11. `BattlefieldDomainScorer` 计算任务、客群、卖点、参数、评论、市场、服务分域支撑分。
12. `BattlefieldSemanticMarketScorer` 计算语义分、市场分和 raw score。
13. `BattlefieldRiskEvaluator` 应用风险扣分、封顶和复核规则。
14. `BattlefieldRelationClassifier` 输出关系等级。
15. `CompetitorSelectionRoleBuilder` 输出竞品筛选作用。
16. `BattlefieldConfidenceCalculator` 输出置信度。
17. `BattlefieldBusinessReasonBuilder` 生成中文业务解释。
18. `BattlefieldEvidenceBreakdownBuilder` 生成分域证据拆分。
19. `BattlefieldPortfolioBuilder` 生成 SKU 战场组合摘要。
20. `BattlefieldReviewIssueBuilder` 生成复核问题。
21. 计算 `result_hash`，判断是否需要写入或复用。
22. 事务写入 5 张输出表。
23. `BattlefieldInvalidationPublisher` 登记 M11.5-M16 下游失效。
24. 返回 `M11RunSummary`。

### 9.2 候选生成规则

候选遍历粒度必须是 SKU x 10 个 seed 战场。进入候选的条件满足任一即可：

| 触发来源 | 条件 |
| --- | --- |
| 任务触发 | M09 命中战场 `core_task_codes`，且任务不是 `insufficient` |
| 客群触发 | M10 命中与战场相关的目标客群，且客群不是 `insufficient` |
| 卖点触发 | M08 最终卖点命中战场 `core_claim_codes` |
| 参数触发 | M08 参数画像命中战场 `core_param_codes`，且不是 `unknown` |
| 评论触发 | M08 `battlefield_support` 命中战场主题 |
| 市场触发 | M08 市场画像命中战场 `market_score_rule.signals` |
| 服务触发 | 服务信号只可触发 `BF_SERVICE_ASSURANCE` 或 `BF_DESIGN_HOME_FIT` |

候选初始分建议：

```text
candidate_initial_score =
  max(task_candidate_score, group_candidate_score, claim_candidate_score, param_candidate_score, comment_candidate_score, market_candidate_score)
  + min(candidate_source_count * 0.04, 0.16)
  - candidate_risk_penalty
```

约束：

- 仅评论命中可进入候选，但最终关系等级最高 `weak`。
- 仅 seed 映射命中不能进入 active，必须有真实任务、客群、卖点、参数、评论或市场信号。
- 仅服务信号只可触发服务保障或家居美学候选。
- `BF_SERVICE_ASSURANCE` 默认不进入 `primary_search_context`。
- 无法映射到 10 个 seed 战场的高频价值竞争线索写 `seed_gap`，不能新增临时战场。

### 9.3 分域评分规则

语义分：

```text
semantic_score =
  core_task_score * 0.30
  + target_group_score * 0.15
  + core_claim_combo_score * 0.25
  + core_param_capability_score * 0.20
  + comment_support_score * 0.10
```

市场分：

```text
market_score =
  price_position_score * 0.25
  + sales_validation_score * 0.25
  + sales_amount_validation_score * 0.15
  + channel_fit_score * 0.10
  + trend_signal_score * 0.10
  + comparable_pool_strength * 0.15
```

最终战场分：

```text
raw_battlefield_score =
  semantic_score * seed.semantic_weight
  + market_score * seed.market_weight

battlefield_score = clamp(raw_battlefield_score - risk_penalty, 0, 1)
```

分域要求：

| 域 | 输入 | 评分要求 |
| --- | --- | --- |
| 任务 | M09 task score、relation level、confidence、breakdown | 主任务强支撑，复核任务传递封顶；游戏体育需区分游戏和体育来源 |
| 客群 | M10 target group score、relation level、confidence、breakdown | 主客群强支撑，但不能单独生成主战场 |
| 卖点 | M08 final claim activation | 结构化卖点缺失不能伪造；`param_only` 可支撑但降置信 |
| 参数 | M08 param profile | unknown 不当 false；关键参数冲突进入复核 |
| 评论 | M08 battlefield_support 和 pain_point | 必须使用去重评论和有效句；仅评论最高 weak |
| 市场 | M08/M07 市场画像、可比池 | 主战场必须有市场验证；样本不足降级或复核 |
| 服务 | M08 service_signal | 只支撑服务保障或家居服务侧面，不替代产品核心战场 |

### 9.4 封顶和复核规则

必须实现以下封顶：

| 条件 | 处理 |
| --- | --- |
| `market_missing` | 没有市场支撑时，最高 `secondary`，不能作为高置信主战场 |
| `only_comment` | 仅评论命中时，最高 `weak`，如果接近 secondary 阈值则复核 |
| `seed_hint_only` | 仅 seed 映射命中时，`insufficient`，不能成为结论 |
| `only_service` | 仅服务信号命中时，最高 `weak`，只支撑服务保障或家居服务侧面 |
| `claim_missing` | 结构化卖点缺失但战场高度依赖卖点表达时，最高 `secondary` 并复核 |
| `param_conflict` | 关键参数冲突时，最高 `secondary` 并复核 |
| `upstream_review` | M09/M10 上游结果复核时，相关战场最高 `secondary` 并继承原因 |
| `market_limited` | 市场样本不足或可比池不足时，最高 `secondary` 并复核 |
| `service_as_core_battlefield` | 服务保障战场被作为产品核心战场使用时，复核并移入风险/服务上下文 |
| `missing_feature_view` | 缺 M08 M11 feature view 时，关系等级 `blocked` |
| `missing_task_score` | 缺 M09 任务结果时，关系等级 `blocked` |
| `missing_target_group_score` | 缺 M10 客群结果时，关系等级 `blocked` |
| `profile_blocked` | M08 profile blocked 时，关系等级 `blocked` |

`unknown`、空值和 `-` 只能降低完整度或触发 `unknown_input`，不能生成负向结论。

### 9.5 关系等级

优先读取 seed `entry_thresholds`，首版默认：

| relation_level | 条件 | 下游用途 |
| --- | --- | --- |
| `main` | `battlefield_score >= 0.75`，语义和市场均有效，至少 3 类证据支撑 | M12/M13/M14 核心筛选主线 |
| `secondary` | `0.55 <= battlefield_score < 0.75`，语义强但市场中等，或市场强但语义成立 | 正面对打或辅助筛选 |
| `opportunity` | `0.45 <= battlefield_score < 0.55`，有能力或市场机会但证据不完整 | 机会监控或报告提示 |
| `weak` | `0.35 <= battlefield_score < 0.45`，有线索但不足以形成竞品主线 | 不作为核心筛选主线 |
| `insufficient` | `< 0.35`，证据不足 | 不进入后续召回主条件 |
| `blocked` | 关键输入缺失 | 复核 |

被封顶规则覆盖时，以更低等级为准。

### 9.6 竞品筛选作用

`CompetitorSelectionRoleBuilder` 必须输出：

| role | 说明 |
| --- | --- |
| `primary_search_context` | 可作为 M12/M14 主筛选语境 |
| `secondary_search_context` | 可作为辅助筛选语境 |
| `opportunity_monitoring` | 用于机会监控、价格挤压或报告提示 |
| `risk_or_service_context` | 服务保障或风险上下文，不默认召回核心候选 |
| `not_for_core_search` | 不进入核心筛选 |

默认规则：

- 高端画质、家庭观影升级、大屏性价比在证据充分时可进入主筛选。
- 游戏体育在任务、参数、评论和市场证据充分时可进入主筛选，否则多为辅助。
- 家庭护眼、长辈易用、智能系统、影院音效多为辅助或机会，除非证据极强。
- 家居美学多为机会或服务/装修侧面。
- 服务保障默认 `risk_or_service_context`。

### 9.7 置信度

置信度建议公式：

```text
confidence =
  battlefield_score * 0.30
  + evidence_domain_coverage_score * 0.25
  + upstream_task_group_confidence * 0.20
  + m08_profile_confidence * 0.10
  + evidence_quality_score * 0.15
  - confidence_risk_penalty
```

置信等级：

| 等级 | 条件 |
| --- | --- |
| `high` | `confidence >= 0.80`，且无关键复核 |
| `medium` | `0.60 <= confidence < 0.80` |
| `low` | `0.35 <= confidence < 0.60` |
| `unknown` | `< 0.35` 或 `blocked` |

置信度必须受以下因素影响：

- M09 来源任务置信度。
- M10 来源客群置信度。
- M08 profile confidence。
- evidence domain 覆盖数量。
- evidence refs 是否可回溯。
- 评论去重质量和有效句数量。
- 市场样本状态和可比池充分性。
- 结构化卖点缺失对卖点组合证据的影响。
- 服务保障是否被误作产品核心战场。

### 9.8 中文业务解释

`BattlefieldBusinessReasonBuilder` 输出：

```text
business_reason_parts_json.task_basis_cn
business_reason_parts_json.target_group_cn
business_reason_parts_json.product_value_cn
business_reason_parts_json.user_perception_cn
business_reason_parts_json.market_validation_cn
business_reason_parts_json.competitor_selection_role_cn
business_reason_parts_json.review_points_cn
business_reason_cn
```

业务解释要求：

- 使用业务语言说明“为什么按这个战场找竞品”。
- 先说任务基础和目标人群，再说产品价值、用户感知、市场验证、竞品选择作用，最后说待复核点。
- 不出现 SQL、JSON、字段名、公式、内部 code、`battlefield_support`、`profile_hash`、`task_score_fingerprint`、“AI 判断”等字样。
- 对 85E7Q 的高端画质战场，要说明 Mini LED、5200 亮度、3500 分区、高端画质任务、画质影音用户、画质评论和市场共同支撑，同时提示结构化卖点缺失。
- 对 85E7Q 的游戏体育战场，要说明高刷和 HDMI2.1 只是能力候选，缺低延迟或游戏评论时不能写成主战场。
- 对服务保障战场，要说明它是服务风险/保障对比，不替代产品核心战场。

## 10. runner/API 任务

### 10.1 runner

新增 runner：

```python
run_m11_battlefield(
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_codes: list[str] | None = None,
    battlefield_codes: list[str] | None = None,
    force: bool = False,
    battlefield_seed_version: str = "tv_core3_mvp_seed_v0_2",
    rule_version: str = "core3_mvp_real_data_v2_m11_v1",
) -> M11RunSummary
```

runner 要求：

- 默认处理 batch 内所有有 M08 profile 或 M08 M11 feature view 或 M09/M10 current 结果的 SKU。
- `battlefield_codes` 不传时必须遍历 10 个 seed 战场。
- `force=false` 时复用 hash 未变化的历史 current 结果。
- `force=true` 时重算并写新版本。
- seed 校验阻塞时本次 run 标记 failed 或 blocked，不写半成品业务结论。
- 单 SKU 缺 M08 feature view、M09 task score 或 M10 target group score 时只阻塞该 SKU，不影响其他 SKU。
- 每个有效 SKU 对 10 个战场都应有 score 行，并生成 1 条 portfolio 行。

### 10.2 API

新增 v2 API：

```text
POST /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/runs/m11-battlefield
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/runs/{run_id}/m11
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields/{battlefield_code}
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields/{battlefield_code}/evidence
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefield-portfolio
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/battlefield-review-issues
```

API response 要求：

- 支持按 `relation_level`、`battlefield_code`、`competitor_selection_role`、`review_required`、`processing_status` 过滤。
- SKU 战场列表默认只返回 current 结果。
- 战场详情返回中文战场名、关系等级、语义分、市场分、分域得分、竞品选择作用、业务解释、证据拆分和复核点。
- portfolio 接口返回主/次/机会/弱战场列表和竞品筛选主语境。
- 证据接口返回 M08/M09/M10/M02 refs，不重新读取原始表。
- API 不应直接作为高层页文案；高层页最终呈现由 M15/FRONTEND 设计转换。

## 11. 增量策略

### 11.1 输入指纹

`input_fingerprint` 至少包含：

```text
project_id
category_code
batch_id
sku_code
battlefield_code
profile_hash
feature_view_hash
M08 evidence matrix result_hash
M09 task score result_hash set
M09 task evidence breakdown result_hash set
M09 open review issue summary hash
M10 target group score result_hash set
M10 target group evidence breakdown result_hash set
M10 open review issue summary hash
battlefield_seed_hash
battlefield_seed_version
battlefield_seed_file_version
rule_version
threshold_version
cap_rule_version
portfolio_rule_version
business_reason_template_version
```

### 11.2 可复用条件

历史结果可复用必须同时满足：

- M08 `profile_hash` 未变化。
- M08 M11 `feature_view_hash` 未变化。
- M08 evidence matrix 相关 `result_hash` 未变化。
- M09 current task scores 的 result hash 集合未变化。
- M09 task evidence breakdown 的 result hash 集合未变化。
- M09 open review issue 摘要未变化。
- M10 current target group scores 的 result hash 集合未变化。
- M10 target group evidence breakdown 的 result hash 集合未变化。
- M10 open review issue 摘要未变化。
- `battlefield_seed_hash` 未变化。
- `battlefield_seed_version` 未变化。
- `rule_version`、阈值版本、封顶规则版本、portfolio 规则版本、业务解释模板版本未变化。
- 历史记录 `is_current=true`。
- 历史记录 `processing_status` 不是 `failed` 或 `blocked`。

### 11.3 下游失效

M11 任一 SKU 的 battlefield score、relation level、competitor_selection_role、portfolio、confidence、review status、business payload 或 evidence refs 变化时，必须登记下游影响：

```text
M11.5 claim value layer
M12 candidate recall
M13 component scoring
M14 core3 selection
M15 evidence report
M16 review acceptance
```

失效 payload 至少包含：

- `changed_sku_code`
- `changed_battlefield_codes`
- `old_result_hash`
- `new_result_hash`
- `portfolio_changed`
- `affected_modules`
- `reason="m11_battlefield_changed"`

只有 evidence 代表集变化但 battlefield_score 未变化时，也要通知 M15 更新证据卡。

## 12. 真实数据和 fixture 验收

### 12.1 样例数据约束

开发测试必须体现真实样例数据约束：

- 市场窗口为 `26W01` 到 `26W23`，不能出现 12 月口径。
- 当前样例市场模型约 35 个，参数约 35 个，评论约 33 个，结构化卖点约 5 个。
- 当前样例均为海信品牌，不能按内部/外部品牌过滤。
- 当前市场数据主要是线上，含专业电商、平台电商；不能推导线下战场。
- 评论存在重复、拆句和通用好评，必须依赖 M05/M06/M08 的去重和有效句口径。
- 参数缺失、卖点缺失、评论缺失、价格或市场信号 unknown 只表示证据不足，不能当 false。

### 12.2 85E7Q 验收样例

85E7Q fixture 必须包含：

| 项 | 值 |
| --- | --- |
| `model_code` | `TV00029115` |
| `model_name` | `85E7Q` |
| 参数 | 85 英寸、4K、300HZ、Mini LED、5200 亮度、3500 分区、HDMI2.1、4GB/64GB、海信星海 |
| 评论 | 原始评论约 3621 条，去重评论 ID 可覆盖 `1648` |
| 市场 | `26W01` 到 `26W23`，线上，专业电商、平台电商 |
| 结构化卖点 | 缺失或不足，必须继承 `claim_missing` 或 `missing_structured_claim` 风险 |

85E7Q 战场预期：

| 战场 | 预期 |
| --- | --- |
| 高端画质战场 | Mini LED、5200 亮度、3500 分区、高端画质任务、画质影音用户、画质评论和高端价格带共同支撑；结构化卖点缺失降低卖点组合置信但不否定参数能力 |
| 家庭观影升级战场 | 85 寸、客厅影院观影、大屏换新、家庭换新用户、画质/尺寸评论和市场表现共同支撑；音效证据不足时不能把影院音效写成强证据 |
| 游戏体育战场 | 高刷、HDMI2.1、游戏/体育任务或看球评论可支撑；缺低延迟或游戏评论时不应作为主战场 |
| 大屏性价比战场 | 85 寸、价格每英寸、销量、价格感知和大屏换新任务支撑；如果价格不低或销量验证不足，只能是机会或弱战场 |
| 家庭护眼战场 | 需要护眼参数、儿童护眼任务、儿童/护眼评论；无明确护眼或儿童信号时不高分 |
| 长辈易用战场 | 需要长辈易用任务、语音、长辈评论和系统易用；无明确爸妈/老人线索时不高分 |
| 智能系统体验战场 | 4GB/64GB、星海大模型、语音/系统评论可支撑；仅参数存在但评论缺失时不应高置信 |
| 影院音效战场 | 需要音响功率、杜比/音效卖点和音质评论；音效证据不足时最多弱或机会 |
| 家居美学战场 | 新家装修任务、尺寸空间、外观、挂装和安装评论支撑；服务安装不能替代外观和装修适配 |
| 服务保障战场 | 安装、送货、售后评论和服务保障卖点可支撑；作为服务侧风险/保障对比，不替代产品核心战场 |

## 13. 测试任务

### 13.1 seed loader 测试

`test_m11_battlefield_seed_loader.py`：

- `test_battlefield_seed_has_10_battlefields`
- `test_battlefield_seed_rejects_missing_required_battlefield`
- `test_battlefield_seed_rejects_battlefield_task_not_in_m09_seed`
- `test_battlefield_seed_rejects_weight_sum_not_one`
- `test_battlefield_seed_rejects_bad_threshold_order`
- `test_battlefield_seed_hash_is_stable`
- `test_battlefield_seed_uses_real_bf_codes_not_old_reference_codes`

### 13.2 M08/M09/M10 input loader 测试

`test_m11_feature_view_loader.py`、`test_m11_task_result_loader.py`、`test_m11_target_group_result_loader.py`：

- `test_m11_loads_only_m08_feature_view`
- `test_m11_blocks_without_feature_view`
- `test_m11_blocks_without_m09_scores`
- `test_m11_blocks_without_m10_scores`
- `test_m11_does_not_query_raw_tables`
- `test_m11_does_not_query_m03_m04b_m06_m07_scatter_tables`
- `test_profile_blocked_becomes_battlefield_blocked`
- `test_task_score_fingerprint_is_stable`
- `test_target_group_score_fingerprint_is_stable`
- `test_unknown_input_preserved_as_unknown`

### 13.3 candidate builder 测试

`test_m11_candidate_builder.py`：

- `test_candidate_created_by_task_trigger`
- `test_candidate_created_by_target_group_trigger`
- `test_candidate_created_by_claim_trigger`
- `test_candidate_created_by_param_trigger`
- `test_candidate_created_by_comment_trigger_with_dedup_threshold`
- `test_candidate_created_by_market_trigger`
- `test_service_signal_only_limited_to_service_or_design_battlefield`
- `test_seed_hint_only_not_active_candidate`
- `test_unmapped_pattern_creates_seed_gap_review_issue`
- `test_candidate_and_score_separated`

### 13.4 scorer 和 risk 测试

`test_m11_domain_scorer.py`、`test_m11_semantic_market_scorer.py`、`test_m11_risk_evaluator.py`：

- `test_main_task_strongly_supports_mapped_battlefield_but_not_direct_main`
- `test_target_group_alone_cannot_make_main_battlefield`
- `test_semantic_and_market_scores_are_separate`
- `test_comment_only_capped_to_weak`
- `test_service_only_not_core_product_battlefield`
- `test_no_market_caps_main_battlefield`
- `test_missing_structured_claim_does_not_zero_battlefield`
- `test_param_conflict_caps_secondary`
- `test_upstream_review_caps_secondary`
- `test_market_limited_caps_secondary`
- `test_unknown_param_not_false`
- `test_service_assurance_not_primary_search_context_by_default`

### 13.5 relation、role 和 confidence 测试

`test_m11_relation_classifier.py`、`test_m11_competitor_selection_role_builder.py`、`test_m11_confidence_calculator.py`：

- `test_main_requires_semantic_market_and_three_domains`
- `test_secondary_for_semantic_strong_market_medium`
- `test_opportunity_for_incomplete_but_meaningful_signal`
- `test_weak_for_low_score_or_cap`
- `test_blocked_for_missing_feature_view_task_or_group`
- `test_primary_role_for_strong_picture_or_family_viewing`
- `test_service_assurance_role_is_risk_or_service_context`
- `test_confidence_uses_m09_m10_confidence`
- `test_confidence_uses_m08_profile_confidence`
- `test_confidence_penalizes_low_evidence_quality`

### 13.6 business reason 和 portfolio 测试

`test_m11_business_reason_builder.py`、`test_m11_portfolio_builder.py`、`test_m11_no_business_outputs.py`：

- `test_business_reason_cn_no_internal_tokens`
- `test_business_reason_does_not_say_ai_judgement`
- `test_business_reason_does_not_expose_sql_json_formula`
- `test_business_reason_does_not_expose_battlefield_support_or_hash`
- `test_business_reason_mentions_competitor_selection_role`
- `test_portfolio_builds_primary_secondary_opportunity_weak_lists`
- `test_portfolio_filters_service_from_primary`
- `test_portfolio_uses_best_secondary_when_no_main`
- `test_portfolio_marks_no_main_battlefield`

### 13.7 repository、runner、API 测试

`test_m11_repositories.py`、`test_m11_runner.py`、`test_m11_api.py`：

- `test_repository_marks_previous_current_false`
- `test_repository_writes_five_output_tables_in_transaction`
- `test_runner_writes_10_scores_per_valid_sku`
- `test_runner_writes_one_portfolio_per_valid_sku`
- `test_runner_skips_when_input_fingerprint_unchanged`
- `test_runner_force_recomputes`
- `test_runner_invalidates_m11_5_to_m16_on_result_hash_change`
- `test_api_runs_m11`
- `test_api_lists_sku_battlefields_sorted_by_relation_and_score`
- `test_api_returns_battlefield_evidence_breakdown`
- `test_api_returns_battlefield_portfolio`
- `test_api_lists_review_issues`

### 13.8 85E7Q fixture 测试

`test_m11_85e7q_fixture.py`：

- `test_85e7q_premium_picture_supported_by_params_tasks_group_comments_market`
- `test_85e7q_family_viewing_supported_by_size_tasks_group_and_market`
- `test_85e7q_gaming_sports_not_main_without_game_or_latency_evidence`
- `test_85e7q_large_screen_value_requires_price_per_inch_and_sales_validation`
- `test_85e7q_eye_care_not_high_without_eye_care_evidence`
- `test_85e7q_senior_ease_not_high_without_senior_cue`
- `test_85e7q_smart_system_not_high_from_params_only`
- `test_85e7q_cinema_audio_not_high_without_audio_evidence`
- `test_85e7q_service_assurance_not_product_core_battlefield`
- `test_85e7q_portfolio_prioritizes_picture_family_and_large_screen_contexts`

## 14. 开发子任务拆分

### M11-1 迁移和 schema

目标：

- 创建 `0018_core3_real_data_battlefield.py`。
- 创建 `battlefield_schemas.py`。
- 在 API schema 中暴露必要 response。

验收：

- 5 张表、唯一键、索引存在。
- battlefield seed、candidate、score、breakdown、portfolio、review issue schema 可实例化。
- enum 覆盖全部设计值。

### M11-2 seed loader

目标：

- 实现 `BattlefieldSeedLoader`。
- 校验 `tv_core3_mvp_seed_v0_2.json.battlefields` 中 10 个真实战场。
- 校验 `core_task_codes` 与 M09 10 个任务 seed 对齐。
- 生成 `battlefield_seed_hash`。

验收：

- seed 版本、文件版本、hash 可写入输出。
- 缺战场、重复战场、source task 不存在、权重不为 1、阈值顺序异常均阻塞。
- 旧参考战场代码不能通过校验。

### M11-3 M08/M09/M10 输入加载

目标：

- 实现 `M11FeatureViewLoader`。
- 实现 `M11TaskResultLoader`。
- 实现 `M11TargetGroupResultLoader`。
- 只读取 M08 profile、M11 feature view、evidence matrix、M09 任务输出和 M10 客群输出。

验收：

- 缺 M08 M11 feature view 输出 `missing_feature_view`。
- 缺 M09 task score 输出 `missing_task_score`。
- 缺 M10 target group score 输出 `missing_target_group_score`。
- profile blocked 输出 blocked。
- 单元测试证明不直接读取原始表和上游散表。

### M11-4 候选生成

目标：

- 实现 `BattlefieldCandidateBuilder`。
- 对 SKU x 10 战场生成 active、rejected、review_required、blocked。

验收：

- 任务、客群、卖点、参数、评论、市场、服务、seed hint 触发均可覆盖。
- 服务信号只触发服务保障或家居美学侧面。
- seed hint 不能单独进入 active 候选。
- 候选和最终得分分离。

### M11-5 分域评分和语义/市场分

目标：

- 实现 `BattlefieldDomainScorer`。
- 实现 `BattlefieldSemanticMarketScorer`。
- 输出 task、target_group、claim、param、comment、market、service 分域分，并计算 semantic_score、market_score、raw_battlefield_score。

验收：

- 任务和客群不能单独生成主战场。
- 结构化卖点缺失不归零，但降置信和复核。
- 参数 unknown 不当 false。
- 评论必须使用去重评论和有效句。
- 市场分独立保存，主战场必须有市场验证。

### M11-6 风险、关系、角色、置信度

目标：

- 实现 `BattlefieldRiskEvaluator`。
- 实现 `BattlefieldRelationClassifier`。
- 实现 `CompetitorSelectionRoleBuilder`。
- 实现 `BattlefieldConfidenceCalculator`。

验收：

- `only_comment` 最高 weak。
- `only_service` 不支撑产品核心战场。
- `market_missing` 最高 secondary。
- `claim_missing` 最高 secondary 并复核。
- `param_conflict` 最高 secondary 并复核。
- `upstream_review` 最高 secondary。
- `BF_SERVICE_ASSURANCE` 默认 `risk_or_service_context`。
- main 必须语义和市场均有效，且至少 3 类证据支撑。

### M11-7 业务解释、证据拆分和 portfolio

目标：

- 实现 `BattlefieldBusinessReasonBuilder`。
- 实现 `BattlefieldEvidenceBreakdownBuilder`。
- 实现 `BattlefieldPortfolioBuilder`。
- 实现 `BattlefieldReviewIssueBuilder`。

验收：

- 中文解释不出现内部字段、SQL、JSON、公式或 AI 过程性语言。
- 分域证据可以回溯 M08/M09/M10/M02 refs。
- portfolio 能输出主/次/机会/弱战场和主筛选语境。
- 服务保障默认进入风险/服务上下文，不进入主筛选语境。
- 复核 issue 覆盖阻塞、封顶、缺失、冲突、样本不足、seed gap。

### M11-8 repository、runner、API

目标：

- 实现 `BattlefieldRepository`。
- 实现 `BattlefieldService` 和 `run_m11_battlefield`。
- 注册 v2 API。

验收：

- 事务写入 5 张表。
- 每个有效 SKU 对 10 个战场有 score 行，并有 1 条 portfolio 行。
- `force=false` 可按 input fingerprint 跳过。
- result hash 或 portfolio 变化登记 M11.5-M16 下游失效。
- API 可查询 SKU 战场列表、战场详情、证据拆分、portfolio、复核问题。

### M11-9 真实 fixture 和回归测试

目标：

- 构造 85E7Q fixture。
- 覆盖真实样例数据约束。

验收：

- 85E7Q 高端画质战场、家庭观影升级战场能用真实证据解释。
- 游戏体育战场不因高刷/HDMI2.1 单独升为 main。
- 大屏性价比战场必须结合价格每英寸、销量和价格感知。
- 影院音效、护眼、长辈、智能系统无充分证据时不高分。
- 服务保障不替代产品核心战场。
- portfolio 优先体现高端画质、家庭观影、大屏价值等真实支撑强的战场语境。

## 15. 完成标准

M11 开发完成必须满足：

- migration 可升级和回滚。
- 所有新增 schema 有单元测试。
- seed loader 使用真实 `tv_core3_mvp_seed_v0_2.json.battlefields` 并覆盖 10 个 MVP 战场。
- M11 不直接读取原始四表，不直接读取 M03/M04b/M05/M06/M07 散表做业务字段判断。
- M11 不重新推导 M09 用户任务或 M10 目标客群。
- 每个有效 SKU x 10 战场都有 score 行；candidate、score、breakdown、portfolio、review issue 分表保存。
- `semantic_score`、`market_score`、`battlefield_score` 分别保存并可解释。
- `only_comment`、`only_service`、`seed_hint_only`、`market_missing`、`market_limited`、`claim_missing`、`param_conflict`、`upstream_review`、`service_as_core_battlefield` 等规则可测试。
- `unknown`、空值、`-` 不被当 false。
- `profile_hash`、`feature_view_hash`、`task_score_fingerprint`、`target_group_score_fingerprint`、`battlefield_seed_version`、`battlefield_seed_hash`、`rule_version` 全部落库。
- result hash 支持增量跳过和下游失效。
- portfolio 能给 M12/M14 提供主筛选语境。
- 85E7Q fixture 验收通过。
- API 返回战场列表、战场详情、证据拆分、portfolio 和复核问题。
- 中文业务解释不包含内部字段、SQL、JSON、公式或 AI 过程性语言。
- 测试不依赖外部 LLM。

建议运行：

```text
pytest apps/api-server/tests/core3_real_data/test_m11_*.py
pytest apps/api-server/tests/core3_real_data/test_m09_*.py apps/api-server/tests/core3_real_data/test_m10_*.py apps/api-server/tests/core3_real_data/test_m11_*.py
```

## 16. 风险和回滚

| 风险 | 处理 |
| --- | --- |
| M08 M11 feature view 缺字段 | M11 输出 `missing_feature_view` 或 `missing_feature`，不绕过 M08 读散表 |
| M09 任务结果缺失 | M11 输出 `missing_task_score`，不重新推导任务 |
| M10 客群结果缺失 | M11 输出 `missing_target_group_score`，不重新推导客群 |
| seed 与详细设计不一致 | 以真实 seed 10 个 `BF_*` 战场为准，测试锁定 battlefield code |
| 单任务或单客群被误当主战场 | 任务/客群只能支撑分，主战场需语义和市场共同成立 |
| 评论线索导致战场过度泛化 | 评论单域最高 weak，并要求去重评论和有效句阈值 |
| seed 默认映射直接变结论 | `seed_hint_only` 不能 active，不能成为结论 |
| 结构化卖点缺失被误判无能力 | `claim_missing` 降置信和复核，不否定参数能力 |
| 市场缺失仍输出主战场 | `market_missing` 最高 secondary |
| 服务保障污染产品核心战场 | `service_as_core_battlefield` 复核并移入风险/服务上下文 |
| 业务解释像算法日志 | business reason 单测禁止内部 tokens |
| 增量跳过错误 | input fingerprint 覆盖 M08 hash、M09 hash、M10 hash、seed hash、rule version |

回滚方式：

- Alembic downgrade 删除 M11 5 张表。
- API 注册可按路由开关临时关闭。
- runner 注册可移除 M11，不影响 M00-M10。
- M11 输出是下游输入，回滚前需确认 M11.5-M16 没有依赖当前 M11 新表；若已依赖，先停止下游 runner。

## 17. 下游依赖

M11.5 战场内卖点价值分层将消费：

- `core3_sku_battlefield_score`
- `core3_sku_battlefield_evidence_breakdown`
- 主/次/机会战场和战场上下文。
- M11.5 只在战场内判断卖点价值层级，不反向修改 M11 战场结果。

M12 候选召回将消费：

- `core3_sku_battlefield_portfolio`
- `primary_search_battlefield_codes_json`
- `secondary_search_battlefield_codes_json`
- opportunity 战场作为扩展条件。
- 弱战场不作为核心召回主条件。

M13 竞品组件评分将消费：

- 目标 SKU 和候选 SKU 的战场相似度。
- 战场关系等级差异。
- 市场验证和可比池状态。
- 战场相似只是组件之一，还要看价格、渠道、参数、任务。

M14 三槽位选择将消费：

- 战场组合。
- 竞品选择作用。
- 主/次/机会战场的差异。
- 三槽位不是简单取战场得分最高。

M15 高层报告将消费：

- 业务化战场解释。
- 竞品选择作用。
- 战场证据拆分。
- 复核提示。
- 不能直接展示内部 hash、JSON、SQL、公式或 `only_comment` 等技术标签。

## 18. 下次任务

M11 完成后，下一个开发任务文档是：

```text
docs/core3_mvp/real_data_v2/development/M11_5_development_tasks.md
```

M11.5 需要基于 M11 的主/次/机会战场上下文，结合 M08 的最终卖点、评论验证和 M07/M08 市场可比池，判断每个战场内卖点属于基础门槛、竞争绩效、溢价倾向还是弱感知，不能反向修改 M11 战场结果。
