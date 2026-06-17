# M11.5 战场内卖点价值分层开发任务

## 1. 模块目标

M11.5 的开发目标是基于 M11 已确定的 SKU 价值战场、M08 汇总后的 SKU 综合信号画像、M04b/M08 传递的最终卖点激活结果、M07/M08 传递的市场和可比池信息、M05/M06/M08 传递的去重评论信号，在每个 SKU 的每个价值战场内部判断标准卖点的业务价值层级。

M11.5 要回答的问题不是“这个 SKU 有哪些卖点”，而是：

1. 在某个价值战场内，哪些标准卖点值得拿来比较。
2. 每个卖点在该战场内属于基础门槛、竞争绩效、溢价倾向、弱感知、样本不足还是不适用。
3. 这个判断依赖参数、结构化卖点、评论、价格、销量、销额、战场可比池中的哪些证据。
4. 当前样本是否足够支撑强分层，还是只能输出方向性解释或复核问题。
5. 这个卖点价值结果如何交给 M12 候选池召回、M13 组件评分、M14 三槽位选择和 M15 高层报告使用。

M11.5 要解决的工程问题：

1. 将“卖点是否存在”与“卖点在战场内是否有价值”拆开，避免把参数命中直接写成高层业务结论。
2. 将“全局卖点分层”改成“SKU x 战场 x 卖点”的分层结果，每条结果必须带 `battlefield_code`。
3. 将候选卖点、最终层级、证据拆分、战场摘要和复核问题分表保存，方便后续复核和增量重算。
4. 将覆盖率、PSI、SSI、SAI、CPI 拆成独立计算，后续模块不再重复计算这些指标。
5. 对结构化卖点缺失、样本不足、服务卖点误用、评论不足、市场缺失等风险明确降置信和复核。
6. 对 85E7Q 这类参数强、评论多、市场有但结构化卖点缺失的 SKU，能解释 Mini LED、高亮 HDR、精细分区控光、大屏、高刷、HDMI 2.1、安装服务等卖点为什么是门槛、绩效、溢价、弱感知或样本不足。
7. 生成中文业务解释，供 M15 报告页使用，但不暴露内部字段、公式、SQL、JSON、UUID 或“AI 判断”过程文案。

M11.5 必须固化以下边界：

- M11.5 只在 M11 已给出的战场范围内做卖点价值分层。
- M11.5 不判断 SKU 是否进入某个价值战场，M11 负责。
- M11.5 不反向修改 M11 的 `relation_level`、战场分或 portfolio。
- M11.5 不做全局卖点分层，每条候选、分层、证据和摘要都必须有 `battlefield_code`。
- M11.5 不新增标准卖点，不修改 `standard_claims` seed。
- M11.5 不新增价值战场，不修改 `battlefields` seed。
- M11.5 不直接读取原始 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data`。
- M11.5 不直接读取 M03、M05、M06、M07 散表拼业务字段，只能通过 M08 特征视图和画像汇总消费这些结果。
- M11.5 不把 `unknown`、空值、`-` 或缺失值当成 false。
- M11.5 不把缺结构化卖点写成产品没有该能力，只能写成宣传证据缺失或结构化卖点缺失。
- M11.5 不把 PSI、SSI、SAI 写成因果证明，只能写成战场可比池内的相关性支撑。
- M11.5 不把服务类卖点用于画质、游戏、体育等产品核心战场。
- M11.5 不按内部/外部品牌过滤，当前真实样例均为海信，海信 SKU 也可以进入后续竞品推导。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M11.5 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M11_5_claim_value_layer_requirements.md` |
| M11.5 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M11_5_claim_value_layer_design.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M08 任务 | `docs/core3_mvp/real_data_v2/development/M08_development_tasks.md` |
| M11 任务 | `docs/core3_mvp/real_data_v2/development/M11_development_tasks.md` |
| M12 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M12_candidate_recall_requirements.md` |
| M12 下游任务 | `docs/core3_mvp/real_data_v2/development/M12_development_tasks.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 方法论 | `cankao/CatForge_竞品生成SOP_详细指导_v1.md` |
| SOP 参考模块 | `cankao/catforge_sop_md/modules/M11_5_战场内卖点价值分层模块.md` |
| UI 规范 | `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md` |
| TV seed | `apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` |

编码前必须确认：

- M11 已输出 `core3_sku_battlefield_score`、`core3_sku_battlefield_evidence_breakdown`、`core3_sku_battlefield_portfolio`。
- M11 输出中有 `battlefield_score_fingerprint` 或可稳定生成的 result hash 集合。
- M08 已输出 `core3_sku_signal_profile`、`core3_sku_signal_evidence_matrix`。
- M08 已输出 `core3_sku_downstream_feature_view where for_module='M11_5'`。
- M08 特征视图中能拿到最终卖点激活、参数支撑、评论支撑、市场画像、可比池摘要和 evidence refs。
- M04b 的最终卖点激活已经通过 M08 汇总字段传递，不由 M11.5 直接读取散表。
- M07 的市场价格、销量、销额、平台、周期和可比池基线已经通过 M08 传递。
- M05/M06 的去重评论、评论主题、卖点验证、服务信号已经通过 M08 传递。
- seed 中 `standard_claims` 正好覆盖 20 个标准卖点。
- seed 中 `battlefields` 正好覆盖 10 个 MVP 战场。
- INFRA 已提供 run context、hash 工具、current 版本约定、runner 协议、复核 issue 约定和测试 fixture 基础。

## 3. 本次范围

本次开发任务拆分覆盖 M11.5 的后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 5 张 M11.5 输出表、索引、唯一键、状态字段和审计字段 |
| model/schema | 新增候选、分层、证据拆分、战场摘要、复核问题、runner summary、API response 的 typed contract |
| seed loader | 读取并校验 20 个标准卖点、10 个战场、战场-卖点映射、seed 版本和 hash |
| M08 loader | 读取 M11.5 feature view、profile、evidence matrix、最终卖点激活摘要和市场/评论/可比池摘要 |
| M11 loader | 读取战场分、战场 evidence breakdown、portfolio 和 `battlefield_score_fingerprint` |
| 候选生成 | 按 SKU x 战场 x 卖点生成候选，保存触发来源、角色、初分、风险和状态 |
| 可比池构建 | 按同战场、同尺寸段、同价格带、同平台优先级构建 with/without claim 样本 |
| 指标计算 | 独立计算 `coverage_rate`、`PSI`、`SSI`、`SAI`、`CPI` 和样本充分性 |
| 价值评分 | 计算 `claim_value_score`、风险扣分和置信度 |
| 层级判定 | 输出 `basic_threshold`、`competitive_performance`、`premium_tendency`、`weak_perception`、`insufficient_sample`、`not_applicable`、`blocked` |
| 封顶规则 | 样本不足、仅参数、仅宣传、仅评论、结构化卖点缺失、服务误用等封顶 |
| 证据拆分 | 按 activation、param、promo、comment、price、sales、pool、market、service、risk、seed、profile 拆证据 |
| 战场摘要 | 生成战场内卖点价值组合摘要，供 M12/M13/M14/M15 消费 |
| 复核问题 | 输出输入缺失、样本不足、with/without 不足、promo 缺失、评论缺失、市场缺失、参数冲突、seed gap 等问题 |
| 增量失效 | 用 `profile_hash`、`feature_view_hash`、`battlefield_score_fingerprint`、seed hash、rule version 生成输入指纹和 result hash |
| runner/API | 提供 M11.5 运行入口、运行摘要查询、战场内卖点价值查询、证据查询、复核列表 |
| 测试 | 单元、repository、service、API、增量、边界、85E7Q fixture |

本次不做：

- 不实现 M12 候选池召回。
- 不实现 M13 竞品组件评分。
- 不实现 M14 核心三竞品选择。
- 不实现 M15 高层报告页面。
- 不实现 M16 全链路编排。
- 不实现前端页面。
- 不部署到 205。
- 不修改 M11 的战场结果。
- 不修改 `tv_core3_mvp_seed_v0_2.json`。
- 不新增临时卖点或临时战场。
- 不绕过 M08 直接回读原始表。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/claim_value_layer_schemas.py
apps/api-server/app/services/core3_real_data/claim_value_layer_repositories.py
apps/api-server/app/services/core3_real_data/claim_value_seed_loader.py
apps/api-server/app/services/core3_real_data/m11_5_feature_view_loader.py
apps/api-server/app/services/core3_real_data/m11_battlefield_result_loader.py
apps/api-server/app/services/core3_real_data/claim_activation_feature_loader.py
apps/api-server/app/services/core3_real_data/battlefield_claim_candidate_builder.py
apps/api-server/app/services/core3_real_data/battlefield_comparable_pool_builder.py
apps/api-server/app/services/core3_real_data/claim_coverage_calculator.py
apps/api-server/app/services/core3_real_data/claim_psi_calculator.py
apps/api-server/app/services/core3_real_data/claim_ssi_sai_calculator.py
apps/api-server/app/services/core3_real_data/claim_cpi_calculator.py
apps/api-server/app/services/core3_real_data/claim_value_layer_scorer.py
apps/api-server/app/services/core3_real_data/claim_value_layer_classifier.py
apps/api-server/app/services/core3_real_data/claim_value_risk_evaluator.py
apps/api-server/app/services/core3_real_data/claim_value_confidence_calculator.py
apps/api-server/app/services/core3_real_data/claim_value_business_reason_builder.py
apps/api-server/app/services/core3_real_data/claim_value_evidence_breakdown_builder.py
apps/api-server/app/services/core3_real_data/battlefield_claim_value_summary_builder.py
apps/api-server/app/services/core3_real_data/claim_value_review_issue_builder.py
apps/api-server/app/services/core3_real_data/claim_value_invalidation_publisher.py
apps/api-server/app/services/core3_real_data/claim_value_layer_service.py
apps/api-server/app/services/core3_real_data/claim_value_layer_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `claim_value_layer_schemas.py` | M11.5 内部枚举、typed contracts、runner summary、metric、risk、reason schema |
| `claim_value_layer_repositories.py` | 读取 M08/M11 输入，写入五张 M11.5 输出表，查询 current 结果 |
| `claim_value_seed_loader.py` | 加载和校验 `standard_claims`、`battlefields`、战场-卖点映射和 seed hash |
| `m11_5_feature_view_loader.py` | 读取并校验 M08 `for_module='M11_5'` 特征视图 |
| `m11_battlefield_result_loader.py` | 读取 M11 战场分、证据拆分、portfolio 和 fingerprint |
| `claim_activation_feature_loader.py` | 从 M08 视图中解析 M04b 最终卖点激活、证据和支撑来源 |
| `battlefield_claim_candidate_builder.py` | 生成 SKU x 战场 x 卖点候选和候选触发理由 |
| `battlefield_comparable_pool_builder.py` | 构建战场可比池和 with/without claim 样本 |
| `claim_coverage_calculator.py` | 计算战场池内卖点覆盖率和来源分布 |
| `claim_psi_calculator.py` | 计算价格支撑 PSI 和样本状态 |
| `claim_ssi_sai_calculator.py` | 计算销量支撑 SSI 和销额支撑 SAI |
| `claim_cpi_calculator.py` | 基于去重有效评论计算 CPI |
| `claim_value_layer_scorer.py` | 计算 `claim_value_score` 和分项 score |
| `claim_value_layer_classifier.py` | 判定价值层级和封顶结果 |
| `claim_value_risk_evaluator.py` | 识别样本不足、结构化卖点缺失、服务误用、参数冲突等风险 |
| `claim_value_confidence_calculator.py` | 计算 confidence 和 confidence_level |
| `claim_value_business_reason_builder.py` | 生成中文业务解释和分段解释 |
| `claim_value_evidence_breakdown_builder.py` | 生成分域证据拆分和代表证据 |
| `battlefield_claim_value_summary_builder.py` | 生成战场内卖点价值组合摘要 |
| `claim_value_review_issue_builder.py` | 生成复核问题 |
| `claim_value_invalidation_publisher.py` | M11.5 结果变化时登记 M12-M16 下游失效 |
| `claim_value_layer_service.py` | M11.5 编排 service |
| `claim_value_layer_runner.py` | M11.5 runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0019_core3_real_data_claim_value_layer.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0019_core3_real_data_claim_value_layer.py` | 新增 M11.5 五张输出表、索引、唯一键、枚举约束 |
| `core3_real_data.py` schema | 导出 M11.5 运行、分层列表、单卖点详情、证据、摘要和复核 response |
| `core3_real_data.py` API | 增加 M11.5 v2 API，不能影响旧接口 |
| `constants.py` | 补 M11.5 claim value layer、candidate source、evidence domain、review issue type |
| `runner.py` | 注册 M11.5 runner，不改变 M00-M11 逻辑 |
| `conftest.py` | 增加 M08/M11 输入 fixture、seed fixture、85E7Q fixture |

如果 Alembic 当前最新编号不是 `0018`，编码时按最新编号顺延，但 migration 内容仍只能包含 M11.5 表、索引、约束。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m11_5_seed_loader.py
apps/api-server/tests/core3_real_data/test_m11_5_feature_view_loader.py
apps/api-server/tests/core3_real_data/test_m11_5_battlefield_result_loader.py
apps/api-server/tests/core3_real_data/test_m11_5_claim_activation_feature_loader.py
apps/api-server/tests/core3_real_data/test_m11_5_candidate_builder.py
apps/api-server/tests/core3_real_data/test_m11_5_pool_builder.py
apps/api-server/tests/core3_real_data/test_m11_5_coverage_calculator.py
apps/api-server/tests/core3_real_data/test_m11_5_psi_calculator.py
apps/api-server/tests/core3_real_data/test_m11_5_ssi_sai_calculator.py
apps/api-server/tests/core3_real_data/test_m11_5_cpi_calculator.py
apps/api-server/tests/core3_real_data/test_m11_5_layer_scorer.py
apps/api-server/tests/core3_real_data/test_m11_5_layer_classifier.py
apps/api-server/tests/core3_real_data/test_m11_5_risk_evaluator.py
apps/api-server/tests/core3_real_data/test_m11_5_confidence_calculator.py
apps/api-server/tests/core3_real_data/test_m11_5_business_reason_builder.py
apps/api-server/tests/core3_real_data/test_m11_5_evidence_breakdown_builder.py
apps/api-server/tests/core3_real_data/test_m11_5_summary_builder.py
apps/api-server/tests/core3_real_data/test_m11_5_repositories.py
apps/api-server/tests/core3_real_data/test_m11_5_runner.py
apps/api-server/tests/core3_real_data/test_m11_5_api.py
apps/api-server/tests/core3_real_data/test_m11_5_85e7q_fixture.py
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

不得在 M11.5 中改动或重写：

- M00-M11 已有 migration 的业务含义。
- M03 参数抽取逻辑。
- M04a 基础卖点激活逻辑。
- M04b 评论验证增强逻辑。
- M05 评论基础证据逻辑。
- M06 评论下游信号逻辑。
- M07 市场画像逻辑。
- M08 SKU 综合画像逻辑。
- M09 用户任务逻辑。
- M10 目标客群逻辑。
- M11 价值战场逻辑。
- M12 候选池召回逻辑。

不得新增以下捷径：

- 直接读取原始四表来补 M11.5 结论。
- 在 M11.5 中临时写死 85E7Q 的分层结果。
- 将标准卖点列表复制成不可维护的业务常量而不校验 seed。
- 在 API 或页面 payload 主文案中暴露 `PSI`、`SSI`、`SAI`、`CPI` 的内部字段名。
- 把样本不足时的高 PSI 解释成明确溢价结论。
- 把结构化卖点缺失解释成“没有该能力”。

## 6. 数据库迁移任务

### 6.1 新增表

迁移文件建议为：

```text
apps/api-server/alembic/versions/0019_core3_real_data_claim_value_layer.py
```

如果当前最新 revision 已变化，按 Alembic 最新 revision 顺延。

新增五张表：

```text
core3_sku_battlefield_claim_candidate
core3_sku_claim_value_layer
core3_sku_claim_value_evidence_breakdown
core3_sku_battlefield_claim_value_summary
core3_sku_claim_value_review_issue
```

### 6.2 `core3_sku_battlefield_claim_candidate`

用途：保存 SKU 在某个战场内需要进行价值分层的卖点候选，候选不等于最终有强价值。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `sku_battlefield_claim_candidate_id` | uuid/text | 主键 |
| `project_id` | text | 必填 |
| `category_code` | text | 必填，MVP 为 `TV` |
| `batch_id` | text | 必填 |
| `run_id` | text | 必填 |
| `module_run_id` | text | 必填 |
| `sku_code` | text | 必填 |
| `model_code` | text | 可空 |
| `model_name` | text | 可空 |
| `battlefield_code` | text | 必填 |
| `claim_code` | text | 必填 |
| `candidate_status` | text | active/rejected/review_required/blocked |
| `candidate_source_json` | jsonb | 候选来源，可多来源 |
| `candidate_source_count` | integer | 来源数量 |
| `battlefield_relevance_role` | text | core/auxiliary/service/risk/not_applicable |
| `candidate_initial_score` | numeric | 初分 |
| `candidate_reason_cn` | text | 中文候选原因 |
| `source_evidence_refs_json` | jsonb | evidence refs |
| `profile_hash` | text | M08 profile hash |
| `feature_view_hash` | text | M08 M11.5 feature view hash |
| `battlefield_score_fingerprint` | text | M11 战场输入指纹 |
| `claim_seed_version` | text | seed 版本 |
| `battlefield_seed_version` | text | seed 版本 |
| `rule_version` | text | 规则版本 |
| `input_fingerprint` | text | 输入指纹 |
| `result_hash` | text | 结果 hash |
| `is_current` | boolean | current 版本 |
| `review_required` | boolean | 是否复核 |
| `review_status` | text | pending/approved/rejected/resolved |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

唯一键建议：

```sql
unique (
  project_id,
  category_code,
  batch_id,
  sku_code,
  battlefield_code,
  claim_code,
  profile_hash,
  feature_view_hash,
  battlefield_score_fingerprint,
  claim_seed_version,
  battlefield_seed_version,
  rule_version,
  result_hash
)
```

索引：

- `(project_id, category_code, batch_id, sku_code, battlefield_code, is_current)`
- `(project_id, category_code, batch_id, claim_code, is_current)`
- `(project_id, category_code, batch_id, candidate_status)`

### 6.3 `core3_sku_claim_value_layer`

用途：保存最终战场内卖点价值层级。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `sku_claim_value_layer_id` | uuid/text | 主键 |
| `sku_battlefield_claim_candidate_id` | uuid/text | 关联候选 |
| `project_id` | text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | text | 必填 |
| `run_id` | text | 必填 |
| `module_run_id` | text | 必填 |
| `sku_code` | text | 必填 |
| `battlefield_code` | text | 必填 |
| `claim_code` | text | 必填 |
| `claim_value_layer` | text | 枚举 |
| `claim_value_score` | numeric | 卖点价值分 |
| `confidence` | numeric | 0-1 |
| `confidence_level` | text | high/medium/low/unknown |
| `sample_sufficiency` | text | sufficient/limited/insufficient/unknown |
| `coverage_rate` | numeric | 可空 |
| `pool_sku_count` | integer | 可空 |
| `with_claim_count` | integer | 可空 |
| `without_claim_count` | integer | 可空 |
| `comment_effective_count` | integer | 可空 |
| `market_week_count` | integer | 可空 |
| `psi_value` | numeric | 可空 |
| `ssi_value` | numeric | 可空 |
| `sai_value` | numeric | 可空 |
| `cpi_value` | numeric | 可空 |
| `metric_validity_json` | jsonb | 各指标是否有效 |
| `score_parts_json` | jsonb | 分项得分 |
| `risk_flags_json` | jsonb | 风险旗标 |
| `cap_rules_json` | jsonb | 封顶规则 |
| `business_reason_cn` | text | 中文业务解释 |
| `business_reason_parts_json` | jsonb | 中文解释片段 |
| `representative_evidence_refs_json` | jsonb | 代表证据 |
| `profile_hash` | text | 必填 |
| `feature_view_hash` | text | 必填 |
| `battlefield_score_fingerprint` | text | 必填 |
| `claim_seed_version` | text | 必填 |
| `battlefield_seed_version` | text | 必填 |
| `claim_seed_hash` | text | 必填 |
| `battlefield_seed_hash` | text | 必填 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `processing_status` | text | completed/blocked/review_required/skipped |
| `review_required` | boolean | 必填 |
| `review_status` | text | pending/approved/rejected/resolved |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

`claim_value_layer` 枚举：

```text
basic_threshold
competitive_performance
premium_tendency
weak_perception
insufficient_sample
not_applicable
blocked
```

唯一键建议：

```sql
unique (
  project_id,
  category_code,
  batch_id,
  sku_code,
  battlefield_code,
  claim_code,
  profile_hash,
  feature_view_hash,
  battlefield_score_fingerprint,
  claim_seed_version,
  battlefield_seed_version,
  rule_version,
  result_hash
)
```

索引：

- `(project_id, category_code, batch_id, sku_code, battlefield_code, is_current)`
- `(project_id, category_code, batch_id, battlefield_code, claim_value_layer)`
- `(project_id, category_code, batch_id, claim_code, claim_value_layer)`
- `(project_id, category_code, batch_id, review_required, review_status)`

### 6.4 `core3_sku_claim_value_evidence_breakdown`

用途：保存每条分层的分域证据拆分，让 M15 可以展示证据卡，M16 可以做复核。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `sku_claim_value_evidence_breakdown_id` | uuid/text | 主键 |
| `sku_claim_value_layer_id` | uuid/text | 关联分层 |
| `project_id` | text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | text | 必填 |
| `sku_code` | text | 必填 |
| `battlefield_code` | text | 必填 |
| `claim_code` | text | 必填 |
| `evidence_domain` | text | activation/param/promo/comment/price/sales/pool/market/service/risk/seed/profile |
| `domain_score` | numeric | 可空 |
| `domain_confidence` | numeric | 可空 |
| `domain_status` | text | supported/missing/insufficient/conflicting/not_applicable |
| `domain_summary_cn` | text | 中文摘要 |
| `evidence_refs_json` | jsonb | evidence refs |
| `source_record_refs_json` | jsonb | 上游记录 refs |
| `metric_snapshot_json` | jsonb | 指标快照 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

索引：

- `(project_id, category_code, batch_id, sku_code, battlefield_code, claim_code, is_current)`
- `(project_id, category_code, batch_id, evidence_domain)`
- `(sku_claim_value_layer_id)`

### 6.5 `core3_sku_battlefield_claim_value_summary`

用途：按 SKU x 战场汇总该战场内各卖点的价值组合，供 M12/M13/M14/M15 直接消费。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `sku_battlefield_claim_value_summary_id` | uuid/text | 主键 |
| `project_id` | text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | text | 必填 |
| `run_id` | text | 必填 |
| `module_run_id` | text | 必填 |
| `sku_code` | text | 必填 |
| `battlefield_code` | text | 必填 |
| `premium_claim_codes_json` | jsonb | 溢价倾向卖点 |
| `competitive_claim_codes_json` | jsonb | 竞争绩效卖点 |
| `basic_claim_codes_json` | jsonb | 基础门槛卖点 |
| `weak_claim_codes_json` | jsonb | 弱感知卖点 |
| `insufficient_claim_codes_json` | jsonb | 样本不足卖点 |
| `not_applicable_claim_codes_json` | jsonb | 不适用卖点 |
| `top_claim_value_points_cn_json` | jsonb | 中文价值重点 |
| `risk_summary_cn_json` | jsonb | 风险摘要 |
| `battlefield_claim_value_strength` | numeric | 战场内卖点组合强度 |
| `battlefield_claim_value_confidence` | numeric | 摘要置信度 |
| `m12_recall_hint_json` | jsonb | 给 M12 的召回提示 |
| `m13_component_hint_json` | jsonb | 给 M13 的组件提示 |
| `m15_report_hint_json` | jsonb | 给 M15 的报告提示 |
| `profile_hash` | text | 必填 |
| `feature_view_hash` | text | 必填 |
| `battlefield_score_fingerprint` | text | 必填 |
| `claim_seed_version` | text | 必填 |
| `battlefield_seed_version` | text | 必填 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

唯一键：

```sql
unique (
  project_id,
  category_code,
  batch_id,
  sku_code,
  battlefield_code,
  profile_hash,
  feature_view_hash,
  battlefield_score_fingerprint,
  claim_seed_version,
  battlefield_seed_version,
  rule_version,
  result_hash
)
```

索引：

- `(project_id, category_code, batch_id, sku_code, is_current)`
- `(project_id, category_code, batch_id, battlefield_code, is_current)`

### 6.6 `core3_sku_claim_value_review_issue`

用途：保存 M11.5 输入缺失、样本不足、复核和阻塞问题。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `sku_claim_value_review_issue_id` | uuid/text | 主键 |
| `project_id` | text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | text | 必填 |
| `run_id` | text | 必填 |
| `module_run_id` | text | 必填 |
| `sku_code` | text | 必填 |
| `battlefield_code` | text | 可空，战场级问题可空 |
| `claim_code` | text | 可空，战场问题可空 |
| `issue_type` | text | 枚举 |
| `issue_level` | text | info/warning/blocker |
| `issue_reason_cn` | text | 中文原因 |
| `issue_detail_json` | jsonb | 详情 |
| `related_record_refs_json` | jsonb | 相关记录 |
| `resolved_status` | text | open/resolved/ignored |
| `resolution_note` | text | 处理说明 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

`issue_type` 枚举：

```text
missing_feature_view
missing_battlefield_result
missing_claim_activation
insufficient_pool
insufficient_with_claim
insufficient_without_claim
promo_missing
comment_missing
market_missing
param_conflict
service_misuse
seed_gap
profile_blocked
unknown
```

表达式唯一索引：

```sql
create unique index uq_core3_sku_claim_value_review_issue_result
on core3_sku_claim_value_review_issue (
  project_id,
  category_code,
  batch_id,
  sku_code,
  battlefield_code,
  coalesce(claim_code, ''),
  issue_type,
  input_fingerprint,
  result_hash
);
```

索引：

- `(project_id, category_code, batch_id, resolved_status, issue_level)`
- `(project_id, category_code, batch_id, sku_code, battlefield_code, claim_code)`
- `(project_id, category_code, batch_id, issue_type)`

### 6.7 回滚策略

`downgrade()` 只删除本 migration 新增的五张表和相关索引，不触碰 M00-M11 表。

回滚前提：

- M12-M16 未依赖 M11.5 表上线。
- 若已经有 M12-M16 结果，需要先清理或标记下游结果失效，不能只 drop M11.5 表。

## 7. model/schema 任务

### 7.1 枚举定义

在 `claim_value_layer_schemas.py` 或 `constants.py` 中定义：

```python
CLAIM_VALUE_LAYER_VALUES = (
    "basic_threshold",
    "competitive_performance",
    "premium_tendency",
    "weak_perception",
    "insufficient_sample",
    "not_applicable",
    "blocked",
)
```

其他枚举：

| 枚举 | 值 |
| --- | --- |
| candidate_status | active/rejected/review_required/blocked |
| candidate_source | battlefield_core_claim/claim_battlefield_mapping/claim_activation/param/comment/market/service/seed_gap |
| battlefield_relevance_role | core/auxiliary/service/risk/not_applicable |
| sample_sufficiency | sufficient/limited/insufficient/unknown |
| evidence_domain | activation/param/promo/comment/price/sales/pool/market/service/risk/seed/profile |
| review_issue_type | missing_feature_view/missing_battlefield_result/missing_claim_activation/insufficient_pool/insufficient_with_claim/insufficient_without_claim/promo_missing/comment_missing/market_missing/param_conflict/service_misuse/seed_gap/profile_blocked/unknown |

### 7.2 seed schema

`ClaimValueSeedLoader` 要输出：

```python
class ClaimValueSeedBundle(BaseModel):
    claim_seed_version: str
    battlefield_seed_version: str
    seed_file_version: str
    claim_seed_hash: str
    battlefield_seed_hash: str
    standard_claims: dict[str, StandardClaimSeed]
    battlefields: dict[str, BattlefieldSeed]
    battlefield_claim_map: dict[str, BattlefieldClaimScope]
```

必须校验 20 个标准卖点：

```text
CLAIM_LARGE_SCREEN_IMMERSION
CLAIM_MINI_LED_BACKLIGHT
CLAIM_OLED_SELF_LIT
CLAIM_QLED_WIDE_COLOR
CLAIM_HIGH_BRIGHTNESS_HDR
CLAIM_FINE_LOCAL_DIMMING
CLAIM_HIGH_REFRESH_RATE
CLAIM_GAMING_LOW_LATENCY
CLAIM_HDMI_2_1_GAMING
CLAIM_SPORTS_MOTION_SMOOTH
CLAIM_EYE_CARE_COMFORT
CLAIM_ELDER_FRIENDLY_SMART
CLAIM_SMART_VOICE_EASE
CLAIM_NO_AD_OR_CLEAN_SYSTEM
CLAIM_IMMERSIVE_AUDIO
CLAIM_DOLBY_CINEMA_AUDIO
CLAIM_THIN_DESIGN
CLAIM_ENERGY_SAVING
CLAIM_VALUE_FOR_MONEY
CLAIM_INSTALLATION_SERVICE_ASSURANCE
```

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

### 7.3 战场-卖点范围 schema

首版必须在 seed loader 输出显式映射，不在业务逻辑中散落 if/else：

| 战场 | 核心卖点 |
| --- | --- |
| `BF_PREMIUM_PICTURE` | `CLAIM_MINI_LED_BACKLIGHT`、`CLAIM_OLED_SELF_LIT`、`CLAIM_QLED_WIDE_COLOR`、`CLAIM_HIGH_BRIGHTNESS_HDR`、`CLAIM_FINE_LOCAL_DIMMING` |
| `BF_FAMILY_VIEWING_UPGRADE` | `CLAIM_LARGE_SCREEN_IMMERSION`、`CLAIM_HIGH_BRIGHTNESS_HDR`、`CLAIM_IMMERSIVE_AUDIO`、`CLAIM_DOLBY_CINEMA_AUDIO` |
| `BF_GAMING_SPORTS` | `CLAIM_HIGH_REFRESH_RATE`、`CLAIM_GAMING_LOW_LATENCY`、`CLAIM_HDMI_2_1_GAMING`、`CLAIM_SPORTS_MOTION_SMOOTH` |
| `BF_LARGE_SCREEN_VALUE` | `CLAIM_LARGE_SCREEN_IMMERSION`、`CLAIM_VALUE_FOR_MONEY`、`CLAIM_ENERGY_SAVING` |
| `BF_FAMILY_EYE_CARE` | `CLAIM_EYE_CARE_COMFORT` |
| `BF_SENIOR_EASE_OF_USE` | `CLAIM_ELDER_FRIENDLY_SMART`、`CLAIM_SMART_VOICE_EASE`、`CLAIM_NO_AD_OR_CLEAN_SYSTEM` |
| `BF_SMART_SYSTEM_EXPERIENCE` | `CLAIM_SMART_VOICE_EASE`、`CLAIM_NO_AD_OR_CLEAN_SYSTEM`、`CLAIM_ELDER_FRIENDLY_SMART` |
| `BF_CINEMA_AUDIO_IMMERSION` | `CLAIM_IMMERSIVE_AUDIO`、`CLAIM_DOLBY_CINEMA_AUDIO` |
| `BF_DESIGN_HOME_FIT` | `CLAIM_THIN_DESIGN`、`CLAIM_INSTALLATION_SERVICE_ASSURANCE`、`CLAIM_LARGE_SCREEN_IMMERSION` |
| `BF_SERVICE_ASSURANCE` | `CLAIM_INSTALLATION_SERVICE_ASSURANCE` |

### 7.4 输入 schema

需要定义：

- `M115FeatureView`
- `M11BattlefieldResult`
- `ClaimActivationFeature`
- `BattlefieldClaimCandidate`
- `BattlefieldComparablePool`
- `ClaimValueMetrics`
- `ClaimValueScoreParts`
- `ClaimValueRiskResult`
- `ClaimValueLayerDecision`
- `ClaimValueBusinessReason`
- `ClaimValueEvidenceBreakdown`
- `BattlefieldClaimValueSummary`
- `M11_5RunSummary`

字段必须包含：

- `project_id`
- `category_code`
- `batch_id`
- `sku_code`
- `battlefield_code`
- `claim_code`
- `profile_hash`
- `feature_view_hash`
- `battlefield_score_fingerprint`
- `claim_seed_version`
- `battlefield_seed_version`
- `rule_version`

### 7.5 API schema

在 `apps/api-server/app/schemas/core3_real_data.py` 增加：

- `RunM115ClaimValueLayerRequest`
- `M115ClaimValueLayerRunResponse`
- `M115ClaimValueLayerListResponse`
- `M115ClaimValueLayerDetailResponse`
- `M115ClaimValueEvidenceResponse`
- `M115BattlefieldClaimValueSummaryResponse`
- `M115ClaimValueReviewIssueResponse`

API response 中允许保留内部 `claim_code` 和 `battlefield_code` 作为隐藏标识，但高层中文字段必须同时提供：

- `claim_name_cn`
- `battlefield_name_cn`
- `claim_value_layer_cn`
- `business_reason_cn`
- `evidence_summary_cn`
- `sample_status_cn`
- `review_points_cn`

## 8. repository 任务

### 8.1 输入读取边界

`ClaimValueRepository` 只允许读取：

```text
core3_sku_signal_profile
core3_sku_signal_evidence_matrix
core3_sku_downstream_feature_view
core3_sku_battlefield_score
core3_sku_battlefield_evidence_breakdown
core3_sku_battlefield_portfolio
```

不得直接读取：

```text
week_sales_data
attribute_data
selling_points_data
comment_data
core3_param_*
core3_comment_*
core3_market_*
```

如果确实需要 M03/M04b/M05/M06/M07 结果，必须要求 M08 feature view 补字段，而不是在 M11.5 repository 中绕过 M08。

### 8.2 读取方法

需要实现：

```python
get_m115_feature_views(project_id, category_code, batch_id, sku_codes=None) -> list[M115FeatureView]
get_signal_profile(project_id, category_code, batch_id, sku_code) -> SkuSignalProfile
get_signal_evidence_matrix(project_id, category_code, batch_id, sku_code) -> SignalEvidenceMatrix
get_current_battlefield_scores(project_id, category_code, batch_id, sku_code) -> list[M11BattlefieldResult]
get_current_battlefield_portfolio(project_id, category_code, batch_id, sku_code) -> M11BattlefieldPortfolio | None
get_current_claim_value_layers(project_id, category_code, batch_id, sku_code, battlefield_code=None) -> list[ClaimValueLayerRecord]
find_current_by_input_fingerprint(project_id, category_code, batch_id, sku_code, battlefield_code, claim_code, input_fingerprint) -> ClaimValueLayerRecord | None
```

### 8.3 写入方法

需要实现：

```python
upsert_claim_candidate(candidate: BattlefieldClaimCandidateRecord) -> None
upsert_claim_value_layer(layer: ClaimValueLayerRecord) -> None
upsert_evidence_breakdown(items: list[ClaimValueEvidenceBreakdownRecord]) -> None
upsert_battlefield_claim_value_summary(summary: BattlefieldClaimValueSummaryRecord) -> None
upsert_review_issues(issues: list[ClaimValueReviewIssueRecord]) -> None
mark_previous_versions_not_current(scope: ClaimValueWriteScope) -> None
```

写入规则：

- 新结果与当前 `result_hash` 相同：复用 current 结果，不插重复业务版本。
- 新结果与 current `result_hash` 不同：旧记录 `is_current=false`，插入新版本。
- candidate、layer、breakdown、summary、review issue 必须共享同一 `input_fingerprint`。
- 部分写入失败必须回滚当前 SKU x 战场事务，不能留下候选有而分层缺的半成品。

### 8.4 查询方法

API 需要：

```python
list_claim_value_layers(project_id, category_code, batch_id, sku_code, battlefield_code) -> list[ClaimValueLayerRecord]
get_claim_value_layer_detail(project_id, category_code, batch_id, sku_code, battlefield_code, claim_code) -> ClaimValueLayerRecord | None
list_claim_value_evidence(project_id, category_code, batch_id, sku_code, battlefield_code, claim_code) -> list[ClaimValueEvidenceBreakdownRecord]
get_battlefield_claim_value_summary(project_id, category_code, batch_id, sku_code, battlefield_code) -> BattlefieldClaimValueSummaryRecord | None
list_claim_value_review_issues(project_id, category_code, batch_id, filters) -> list[ClaimValueReviewIssueRecord]
```

## 9. service 任务

### 9.1 编排服务

`ClaimValueLayerService` 负责主流程：

```python
class ClaimValueLayerService:
    def run(self, request: M115RunRequest) -> M11_5RunSummary:
        seed = self.seed_loader.load(request.claim_seed_version, request.battlefield_seed_version)
        feature_views = self.feature_view_loader.load_ready_views(request)
        for view in feature_views:
            self.process_sku(view, seed, request)
        return self.build_run_summary()
```

处理顺序：

1. 加载并校验 seed。
2. 读取 M08 M11.5 feature view。
3. 读取 M11 current battlefield score 和 portfolio。
4. 校验 profile、feature view、战场结果、卖点激活、市场、评论和 evidence refs。
5. 按 M11 relation level 选择需要分层的战场。
6. 生成战场内卖点候选。
7. 构建战场可比池和 with/without claim 样本。
8. 计算 coverage、PSI、SSI、SAI、CPI。
9. 计算 value score、风险、置信度。
10. 判定 layer 和封顶。
11. 生成中文业务解释。
12. 生成证据拆分。
13. 生成战场内卖点价值摘要。
14. 生成复核问题。
15. 版本化写入。
16. 发布下游 M12-M16 失效事件。

### 9.2 M11 战场范围规则

M11.5 必须按 M11 的战场关系确定范围：

| M11 relation | M11.5 行为 |
| --- | --- |
| main | 对战场核心卖点和已激活映射卖点完整分层 |
| secondary | 对战场核心卖点和已激活映射卖点完整分层 |
| opportunity | 对核心卖点、已激活卖点、有评论/市场信号卖点分层 |
| weak | 只对已激活或有明确评论/市场证据的卖点分层 |
| insufficient | 不做正常分层，写 `insufficient_sample` 或 review issue |
| blocked | 不做正常分层，写 `blocked` 和 review issue |

M11.5 不得把一个 M11 没有进入范围的战场强行加入分层。若用户或 API 指定了 M11 不存在的 `battlefield_code`，返回 blocked 或 review issue。

### 9.3 候选生成任务

`BattlefieldClaimCandidateBuilder` 输入：

- `M115FeatureView`
- `M11BattlefieldResult`
- `ClaimValueSeedBundle`
- `ClaimActivationFeature`
- `SignalEvidenceMatrix`

候选触发来源：

| 来源 | 条件 |
| --- | --- |
| `battlefield_core_claim` | `claim_code` 属于该战场核心卖点 |
| `claim_battlefield_mapping` | SKU 已激活卖点映射到该战场 |
| `claim_activation` | M04b/M08 汇总后该卖点有效激活 |
| `param` | 参数强支撑可映射到标准卖点 |
| `comment` | 评论验证或战场支撑命中该卖点主题 |
| `market` | 市场/可比池中可计算 with/without 差异 |
| `service` | 服务信号命中服务保障或家居美学服务侧 |
| `seed_gap` | 真实数据高频卖点无法映射到现有 seed |

候选初分：

```text
candidate_initial_score =
  max(core_claim_score, activation_score, param_hint_score, comment_hint_score, market_hint_score)
  + min(candidate_source_count * 0.04, 0.16)
  - candidate_risk_penalty
```

候选规则：

- 仅 seed 核心卖点但 SKU 无真实激活、参数、评论或市场信号，可以进入候选，但最终通常是 `not_applicable` 或 `insufficient_sample`。
- `BF_SERVICE_ASSURANCE` 的服务候选只能支撑服务保障战场。
- `CLAIM_INSTALLATION_SERVICE_ASSURANCE` 出现在 `BF_PREMIUM_PICTURE`、`BF_GAMING_SPORTS` 等产品核心战场时必须触发 `service_misuse`。
- M11 战场为 weak 时，候选需更严格，不能把 20 个标准卖点全部扩散。

### 9.4 战场可比池任务

`BattlefieldComparablePoolBuilder` 输入：

- 目标 SKU 画像。
- 当前战场。
- 当前 claim。
- M08 市场画像摘要。
- M08 可比池摘要。
- M11 战场结果。
- M11.5 候选列表。

池优先级：

| 优先级 | 池定义 | 用途 |
| --- | --- | --- |
| 1 | 同战场、同尺寸段、同价格带、同平台 | 可支撑强分层 |
| 2 | 同战场、同尺寸段、同平台 | 样本不足时放宽 |
| 3 | 同战场、相邻尺寸段、同价格带 | 大屏或尺寸段样本不足时放宽 |
| 4 | 同战场、同品类线上样本 | 仅方向性参考 |

样本门槛：

| 指标 | 门槛 | 处理 |
| --- | --- | --- |
| `pool_sku_count` | `>=8` 可方向性分层，`>=30` 可强溢价判断 | 低于 8 标记 `insufficient_pool` |
| `with_claim_count` | `>=3` | 低于 3 不输出强 PSI/SSI |
| `without_claim_count` | `>=3` | 低于 3 不输出强 PSI/SSI |
| `comment_effective_count` | `>=20` 或 M06 样本状态 sufficient | 低于门槛 CPI 只作弱证据 |
| `market_week_count` | 使用 `26W01`-`26W23` 有效周 | 有效周不足降置信 |

with/without claim 来源必须分开：

- `promo_supported`
- `param_supported`
- `comment_supported`
- `market_supported`

85E7Q 无结构化卖点时，可以进入 `param_supported`，不能伪造成 `promo_supported`。

### 9.5 指标计算任务

`ClaimCoverageCalculator`：

```text
coverage_rate =
  战场可比池中该卖点有效激活 SKU 数 / 战场可比池 SKU 数
```

要求：

- `param_supported`、`promo_supported`、`comment_supported`、`market_supported` 分别计数。
- missing、unknown、空值、`-` 不当 false。
- 样本不足时 coverage 只作方向性参考。

`ClaimPsiCalculator`：

```text
PSI = median(price_with_claim) / median(price_without_claim) - 1
```

要求：

- 价格优先使用 M07/M08 加权均价，缺失时可降级到最新均价并标注。
- `with_claim_count` 或 `without_claim_count` 不足时，不输出强 PSI。
- PSI 为相关性，不是因果证明。

`ClaimSsiSaiCalculator`：

```text
SSI = median(volume_with_claim) / median(volume_without_claim) - 1
SAI = median(sales_amount_with_claim) / median(sales_amount_without_claim) - 1
```

要求：

- 销量和销额来自 M07/M08 市场画像。
- 市场有效周数不足时降低置信度。
- 大屏性价比战场必须参考价格每英寸、价格分位和销量，不能只看绝对价格。

`ClaimCpiCalculator`：

```text
CPI = positive_mention_rate - negative_mention_rate
positive_mention_rate = positive_claim_mentions / effective_comment_count
negative_mention_rate = negative_claim_mentions / effective_comment_count
```

要求：

- 必须使用 M05/M06/M08 汇总后的去重有效评论口径。
- 通用好评、默认评论、纯物流评论不能支撑产品卖点 CPI。
- 服务类 CPI 只用于 `BF_SERVICE_ASSURANCE` 和 `BF_DESIGN_HOME_FIT` 服务侧。
- 评论不足时输出 `comment_missing` 或低置信，不能强判弱感知。

### 9.6 价值评分任务

`ClaimValueLayerScorer` 首版公式：

```text
claim_value_score =
  claim_activation_score * 0.25
  + battlefield_relevance_score * 0.20
  + coverage_position_score * 0.15
  + price_support_score * 0.15
  + sales_support_score * 0.15
  + comment_perception_score * 0.10
  - risk_penalty
```

分项要求：

- `claim_activation_score` 来自 M04b/M08 最终卖点激活。
- `battlefield_relevance_score` 来自战场-卖点映射和 M11 战场关系。
- `coverage_position_score` 不是越高越好，要区分行业门槛和差异卖点。
- `price_support_score` 来自 PSI。
- `sales_support_score` 来自 SSI/SAI。
- `comment_perception_score` 来自 CPI。
- `risk_penalty` 来自样本不足、结构化卖点缺失、参数冲突、评论负向、服务误用等。

### 9.7 层级判定任务

`ClaimValueLayerClassifier` 输出：

| 层级 | 业务含义 | 首版规则 |
| --- | --- | --- |
| `basic_threshold` | 战场中多数 SKU 都具备，缺了会吃亏，有了未必拉开差距 | coverage >= 0.70 且 PSI/SSI/CPI 无明显正向，或 seed required signal 已行业普及 |
| `competitive_performance` | 能形成体验差异或销量支撑 | coverage 0.20-0.70，参数可量化，SSI/SAI 或 CPI 有正向支撑 |
| `premium_tendency` | 可能支撑更高价格或高端定位 | 样本充分，PSI >= 0.05，SSI 不明显负向，参数/宣传/评论至少两类证据成立 |
| `weak_perception` | 卖点被激活或宣传存在，但用户/市场感知弱或证据缺口明显 | 激活分低、CPI 弱或负向、PSI/SSI 无支撑、结构化卖点缺失且无评论补强 |
| `insufficient_sample` | 可比池或评论样本不足 | pool、with/without、市场周数或评论样本低于门槛 |
| `not_applicable` | 与该战场无业务关系 | 非战场核心、非映射卖点且无真实信号 |
| `blocked` | 缺 M11/M08 关键输入 | 无法自动分层 |

封顶规则：

| 条件 | 最高层级 | 复核 |
| --- | --- | --- |
| 样本不足 | `insufficient_sample` | 是 |
| 仅参数支撑，缺宣传/评论/市场 | `competitive_performance` | 视战场重要性 |
| 仅宣传支撑，缺参数/评论/市场 | `weak_perception` | 是 |
| 仅评论支撑，缺参数或卖点激活 | `weak_perception` | 是 |
| 结构化卖点缺失 | 不否定技术卖点，但不能强宣传支撑 | 是 |
| 服务类卖点在产品核心战场 | `not_applicable` 或 `weak_perception` | 是 |
| 可比池所有 SKU 都具备且价格/销量无差异 | `basic_threshold` | 否 |
| PSI 正但 SSI 显著负向 | 最高 `premium_tendency` 且低置信，或 `insufficient_sample` | 是 |

必须有测试证明：样本不足不能输出 `premium_tendency`。

### 9.8 置信度任务

`ClaimValueConfidenceCalculator` 首版公式：

```text
confidence =
  claim_value_score * 0.30
  + sample_sufficiency_score * 0.25
  + evidence_domain_coverage_score * 0.20
  + m08_claim_confidence * 0.15
  + market_and_comment_quality_score * 0.10
  - confidence_risk_penalty
```

置信等级：

| 等级 | 条件 |
| --- | --- |
| high | `confidence >= 0.80`，且样本充分、无关键复核 |
| medium | `0.60 <= confidence < 0.80` |
| low | `0.35 <= confidence < 0.60` |
| unknown | `< 0.35` 或 `blocked` |

### 9.9 业务解释任务

`ClaimValueBusinessReasonBuilder` 生成：

- `business_reason_cn`
- `business_reason_parts_json`
- `sample_status_cn`
- `review_points_cn`
- `m12_hint_cn`
- `m15_report_sentence_cn`

解释片段结构：

```json
{
  "battlefield_relevance_cn": "战场相关性：该卖点是高端画质战场核心卖点。",
  "activation_basis_cn": "激活依据：由 Mini LED 参数和高亮分区参数支撑，结构化宣传证据缺失。",
  "pool_status_cn": "可比池表现：同战场同尺寸可比池样本有限，覆盖率仅作方向性参考。",
  "price_support_cn": "价格支撑：带该卖点样本价格更高，但样本不足，不能强判溢价。",
  "sales_support_cn": "销量支撑：销量方向可参考，但不足以单独形成竞争绩效。",
  "comment_perception_cn": "评论感知：画质评论有正向线索，暗场/分区感知还需更多样本。",
  "review_points_cn": "待复核点：结构化卖点缺失，with/without claim 样本不足。"
}
```

文案约束：

- 必须是中文业务语言。
- 不展示内部 code、SQL、JSON、字段名或公式。
- 不写“AI 判断”“模型认为”“系统推理”等过程性话术。
- 不把 PSI/SSI/SAI 写成因果证明。
- 不把样本不足写成负向能力。
- 不把缺结构化卖点写成产品没有该能力。

### 9.10 证据拆分任务

`ClaimValueEvidenceBreakdownBuilder` 对每条 layer 生成多条 domain breakdown。

必须覆盖的 domain：

```text
activation
param
promo
comment
price
sales
pool
market
service
risk
seed
profile
```

每个 domain 要包含：

- `domain_status`
- `domain_score`
- `domain_confidence`
- `domain_summary_cn`
- `evidence_refs_json`
- `source_record_refs_json`
- `metric_snapshot_json`

证据规则：

- 优先引用 M08 evidence matrix 的 evidence refs。
- 若 evidence refs 缺失，写 review issue，不能生成无来源强结论。
- 代表证据最多选 3-5 条，不能把全部原始评论塞进输出。
- 评论证据必须使用去重有效评论结果，不使用原始重复评论。

### 9.11 战场摘要任务

`BattlefieldClaimValueSummaryBuilder` 按 SKU x battlefield 汇总：

- premium tendency 卖点。
- competitive performance 卖点。
- basic threshold 卖点。
- weak perception 卖点。
- insufficient sample 卖点。
- not applicable 卖点。
- 给 M12 的召回提示。
- 给 M13 的组件评分提示。
- 给 M15 的报告提示。

摘要必须能让 M12 回答：

- 同战场内应该优先找哪些卖点对打。
- 哪些卖点是门槛，适合寻找低价挤压候选。
- 哪些卖点是高端上探参照。
- 哪些卖点样本不足，不应作为强召回理由。

### 9.12 复核任务

`ClaimValueReviewIssueBuilder` 对以下情况写入 `core3_sku_claim_value_review_issue`：

1. `missing_feature_view`：M08 未生成 M11.5 特征视图。
2. `missing_battlefield_result`：M11 没有相关战场结果。
3. `missing_claim_activation`：M04b 最终卖点激活缺失或处于复核状态。
4. `insufficient_pool`：战场可比池样本不足。
5. `insufficient_with_claim`：with claim 样本不足。
6. `insufficient_without_claim`：without claim 样本不足。
7. `promo_missing`：结构化卖点缺失但参数强，容易被误解为宣传证据充分。
8. `comment_missing`：评论有效样本不足。
9. `market_missing`：市场价格、销量、销额或有效周缺失。
10. `param_conflict`：刷新率、亮度、分区、HDMI、护眼等参数口径冲突。
11. `service_misuse`：服务类卖点被用于画质、游戏、体育等产品核心战场。
12. `seed_gap`：真实数据高频卖点无法映射到 20 个标准卖点或 10 个战场。
13. `unknown`：未归类异常。

## 10. runner/API 任务

### 10.1 runner 入口

在 `claim_value_layer_runner.py` 实现：

```python
def run_m11_5_claim_value_layer(
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_codes: list[str] | None = None,
    battlefield_codes: list[str] | None = None,
    claim_codes: list[str] | None = None,
    force: bool = False,
    claim_seed_version: str = "tv_core3_mvp_seed_v0_2",
    battlefield_seed_version: str = "tv_core3_mvp_seed_v0_2",
    rule_version: str = "core3_mvp_real_data_v2_m11_5_v1",
) -> M11_5RunSummary:
    ...
```

`M11_5RunSummary` 字段：

| 字段 | 说明 |
| --- | --- |
| `total_sku_count` | 本次扫描 SKU 数 |
| `battlefield_scope_count` | 进入分层的战场数 |
| `candidate_count` | 卖点候选数 |
| `layer_count` | 分层记录数 |
| `premium_tendency_count` | 溢价倾向数 |
| `competitive_performance_count` | 竞争绩效数 |
| `basic_threshold_count` | 基础门槛数 |
| `weak_perception_count` | 弱感知数 |
| `insufficient_sample_count` | 样本不足数 |
| `not_applicable_count` | 不适用数 |
| `blocked_count` | 阻塞数 |
| `summary_count` | 战场摘要数 |
| `review_issue_count` | 复核问题数 |
| `changed_layer_count` | 分层变化数 |
| `downstream_invalidation_events` | 下游失效事件数 |

### 10.2 增量策略

`input_fingerprint` 必须包含：

- M11 battlefield score result hash 集合。
- M11 portfolio result hash。
- M08 `profile_hash`。
- M08 M11.5 feature view `feature_view_hash`。
- M08 evidence matrix 中 claim/comment/market/pool 相关域 hash。
- M08 最终卖点激活摘要 hash。
- M08 市场画像和可比池摘要 hash。
- `standard_claims` seed hash。
- `battlefields` seed hash。
- M11.5 样本门槛、PSI/SSI/SAI/CPI 公式、层级规则版本。
- 业务解释模板版本。

变化传播：

| 变化来源 | M11.5 动作 | 下游影响 |
| --- | --- | --- |
| M11 战场结果变化 | 重算对应 SKU 对应战场内全部卖点分层 | M12-M16 |
| M04b 卖点激活变化，经 M08 传递 | 重算对应 SKU 相关卖点分层 | M11.5-M16 |
| M08 `profile_hash` 变化 | 重算对应 SKU 分层和摘要 | M11.5-M16 |
| M07 市场画像或可比池变化，经 M08 传递 | 重算 PSI/SSI/SAI、样本状态和层级 | M11.5-M16 |
| M06 评论信号变化，经 M08 传递 | 重算 CPI、评论风险和弱感知判断 | M11.5-M16 |
| standard_claims 或 battlefields seed 变化 | 按版本重算受影响卖点或战场 | M11.5-M16 |
| M11.5 评分规则变化 | 重算层级和置信度 | M12-M16 |
| M02 evidence 状态变化 | 通过 M08/M11 变化传递后更新代表证据 | M15/M16 |

### 10.3 API

在 v2 namespace 增加内部 API：

| API | 方法 | 用途 |
| --- | --- | --- |
| `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/runs/m11-5-claim-value-layer` | POST | 触发 M11.5 |
| `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/runs/{run_id}/m11-5` | GET | 查询 M11.5 运行摘要 |
| `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields/{battlefield_code}/claim-value-layers` | GET | 查询战场内卖点价值层级 |
| `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields/{battlefield_code}/claims/{claim_code}/value-layer` | GET | 查询单卖点分层详情 |
| `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields/{battlefield_code}/claims/{claim_code}/value-evidence` | GET | 查询单卖点证据拆分 |
| `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields/{battlefield_code}/claim-value-summary` | GET | 查询战场内卖点价值摘要 |
| `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/claim-value-review-issues` | GET | 查询复核问题 |

API 约束：

- API 不返回原始评论全文大表。
- API 不返回 SQL。
- API 不返回内部计算公式给高层页面。
- API 可返回内部 code 供前端 hidden key 使用，但必须同时返回中文展示字段。
- API 查询必须默认 `is_current=true`。

## 11. 测试任务

### 11.1 seed loader 测试

`test_m11_5_seed_loader.py`：

- `test_claim_seed_has_20_claims`：seed 正好 20 个标准卖点。
- `test_battlefield_seed_has_10_battlefields`：seed 正好 10 个战场。
- `test_battlefield_claim_mapping_valid`：所有战场核心卖点都存在于标准卖点。
- `test_seed_hash_is_stable`：同 seed hash 稳定。
- `test_seed_gap_generates_review_issue`：无法映射的高频卖点触发 `seed_gap`。

### 11.2 输入 loader 测试

`test_m11_5_feature_view_loader.py`：

- 只读取 `for_module='M11_5'`。
- 缺 `profile_hash` 或 `feature_view_hash` 时 blocked。
- 缺市场摘要时标记 `market_missing`，不崩溃。
- 缺评论摘要时标记 `comment_missing`，不崩溃。

`test_m11_5_battlefield_result_loader.py`：

- M11 missing 时写 `missing_battlefield_result`。
- M11 weak 战场只允许严格候选。
- M11 blocked 战场输出 blocked，不正常分层。

`test_m11_5_claim_activation_feature_loader.py`：

- 结构化卖点缺失不等于卖点不存在。
- 参数支撑和宣传支撑分开。
- `promo_supported` 不得由参数伪造。

### 11.3 候选和可比池测试

`test_m11_5_candidate_builder.py`：

- `BF_PREMIUM_PICTURE` 生成 Mini LED、高亮 HDR、精细分区控光等核心候选。
- `BF_GAMING_SPORTS` 生成高刷新率、HDMI 2.1、低延迟、体育流畅候选。
- `CLAIM_INSTALLATION_SERVICE_ASSURANCE` 不得作为画质核心候选。
- M11 weak 战场不扩散全量 20 个卖点。

`test_m11_5_pool_builder.py`：

- 优先同战场、同尺寸段、同价格带、同平台。
- 样本不足时按规则放宽。
- `pool_sku_count < 8` 时输出 `insufficient_pool`。
- with/without claim 低于 3 时不强算 PSI/SSI。

### 11.4 指标测试

`test_m11_5_coverage_calculator.py`：

- coverage 分母是战场可比池 SKU 数。
- `param_supported` 和 `promo_supported` 分开计数。
- unknown 不当 false。

`test_m11_5_psi_calculator.py`：

- `PSI = median(price_with_claim) / median(price_without_claim) - 1`。
- with/without 样本不足时 PSI invalid。
- PSI 正不等于溢价因果。

`test_m11_5_ssi_sai_calculator.py`：

- `SSI` 使用销量中位数。
- `SAI` 使用销额中位数。
- 市场周数不足降低置信度。

`test_m11_5_cpi_calculator.py`：

- CPI 使用去重有效评论。
- 重复评论不重复计数。
- 纯物流评论不支撑产品卖点。
- 服务评论只进入服务保障或家居美学服务侧。

### 11.5 分层和风险测试

`test_m11_5_layer_scorer.py`：

- 分项权重稳定。
- risk penalty 正确扣分。
- coverage 高但 PSI/SSI/CPI 无正向时倾向 `basic_threshold`。

`test_m11_5_layer_classifier.py`：

- `basic_threshold`：coverage >= 0.70 且无显著正向。
- `competitive_performance`：参数可量化且 SSI/SAI 或 CPI 正向。
- `premium_tendency`：样本充分、PSI >= 0.05、至少两类证据。
- `weak_perception`：证据弱或结构化卖点缺失且无补强。
- `insufficient_sample`：样本门槛不足。
- `not_applicable`：卖点与战场无关。
- `blocked`：关键输入缺失。

`test_m11_5_risk_evaluator.py`：

- `sample_insufficient_blocks_premium`：样本不足不能输出 `premium_tendency`。
- `only_param_caps_layer`：仅参数强，最高 `competitive_performance`。
- `only_promo_caps_weak`：仅宣传有，最高 `weak_perception`。
- `only_comment_caps_weak`：仅评论支撑，最高 `weak_perception`。
- `service_misuse_blocked`：服务卖点误入产品核心战场时复核。
- `missing_structured_claim_not_false`：结构化卖点缺失不否定技术能力。

### 11.6 解释、摘要和 repository 测试

`test_m11_5_business_reason_builder.py`：

- 输出中文业务语言。
- 不包含 SQL、JSON、UUID、大段字段名。
- 不出现“AI 判断”“模型认为”。
- 不把 PSI/SSI 写成因果。
- 不把样本不足写成能力弱。

`test_m11_5_evidence_breakdown_builder.py`：

- 每条 layer 生成至少 seed/profile/risk 或支撑域证据。
- 参数、评论、市场证据引用 evidence refs。
- 代表证据数量受控。

`test_m11_5_summary_builder.py`：

- summary 汇总 premium、competitive、basic、weak、insufficient。
- summary 生成 M12/M13/M15 hint。
- 样本不足卖点不作为强召回提示。

`test_m11_5_repositories.py`：

- current 版本写入和旧版本失效。
- `input_fingerprint` 相同不重复插入业务版本。
- result hash 变化时插入新版本。
- 事务失败不留下半成品。

### 11.7 runner/API 测试

`test_m11_5_runner.py`：

- 正常运行生成候选、分层、证据、摘要、复核。
- `force=false` 且 input hash 不变时跳过重算。
- M11 missing 时生成 blocked。
- seed hash 变化时重算。
- M11.5 变化时发布 M12-M16 下游失效事件。

`test_m11_5_api.py`：

- POST runner 返回 run summary。
- GET list 默认只返回 current。
- 单卖点详情包含中文展示字段。
- evidence API 不暴露原始大表。
- review issue API 支持 issue type 和 resolved status 过滤。

## 12. 205/85E7Q fixture 验收

### 12.1 当前真实样例约束

必须用 fixture 固化 205 PostgreSQL 当前样例事实：

- 市场有 35 个型号。
- 市场周期为 `26W01` 到 `26W23`。
- 参数有 35 个型号，unknown/空值/`-` 比例较高。
- 结构化卖点只覆盖 5 个型号。
- 评论有 33 个型号，存在重复和拆行。
- 85E7Q 评论原始约 3621 条，去重评论 ID 约 1648。
- 当前所有品牌均为海信，不区分内部外部。
- 当前渠道只有线上。
- 当前渠道来源主要是 `专业电商` 和 `平台电商`。
- 85E7Q 型号编码为 `TV00029115`，业务名称为 `85E7Q`。

### 12.2 85E7Q 关键断言

`test_m11_5_85e7q_fixture.py` 必须覆盖：

| 战场 | 卖点 | 断言 |
| --- | --- | --- |
| `BF_PREMIUM_PICTURE` | `CLAIM_MINI_LED_BACKLIGHT` | Mini LED 参数可支撑候选；结构化宣传缺失必须产生 `promo_missing` 或降低 promo support |
| `BF_PREMIUM_PICTURE` | `CLAIM_HIGH_BRIGHTNESS_HDR` | 5200 亮度可形成强参数支撑；样本不足时不得强判 `premium_tendency` |
| `BF_PREMIUM_PICTURE` | `CLAIM_FINE_LOCAL_DIMMING` | 3500 分区可形成参数支撑；评论不足时置信降低 |
| `BF_FAMILY_VIEWING_UPGRADE` | `CLAIM_LARGE_SCREEN_IMMERSION` | 85 寸可形成大屏候选；在 85 寸池内可能是 `basic_threshold`，不默认差异 |
| `BF_FAMILY_VIEWING_UPGRADE` | `CLAIM_IMMERSIVE_AUDIO` | 音效证据不足时为 `weak_perception` 或 `insufficient_sample` |
| `BF_GAMING_SPORTS` | `CLAIM_HIGH_REFRESH_RATE` | 300HZ 可形成游戏体育候选；缺游戏评论时不强判溢价 |
| `BF_GAMING_SPORTS` | `CLAIM_HDMI_2_1_GAMING` | HDMI2.1 仅参数命中时最高 `competitive_performance`，置信有限 |
| `BF_LARGE_SCREEN_VALUE` | `CLAIM_VALUE_FOR_MONEY` | 必须参考价格每英寸、价格分位、销量和价格评论；高端价格不能强判性价比 |
| `BF_SMART_SYSTEM_EXPERIENCE` | `CLAIM_SMART_VOICE_EASE` | 可由 4GB/64GB、星海大模型和语音/系统评论支撑；仅参数时低置信 |
| `BF_SERVICE_ASSURANCE` | `CLAIM_INSTALLATION_SERVICE_ASSURANCE` | 只作为服务侧价值，不替代产品核心卖点 |

### 12.3 业务解释验收

对 85E7Q 必须能输出类似业务解释：

- “在高端画质战场，Mini LED、高亮和分区控光属于核心画质卖点，当前主要由参数支撑；由于结构化宣传卖点缺失，宣传侧证据不足，需要在报告中表达为参数能力支撑，而不是宣传卖点已充分验证。”
- “在游戏体育战场，高刷新率和 HDMI 2.1 可以形成性能对打线索，但如果游戏评论和低延迟证据不足，不应直接判为溢价倾向。”
- “在服务保障战场，安装服务只能作为服务体验参考，不能替代画质、游戏或大屏等产品核心卖点。”

## 13. 完成标准

编码完成后必须满足：

1. 五张 M11.5 表 migration 可执行，downgrade 不影响 M00-M11 表。
2. 所有 M11.5 输出记录都有 `project_id`、`category_code`、`batch_id`、`run_id`、`module_run_id`。
3. 所有 candidate、layer、breakdown、summary 都有 `battlefield_code`，不存在全局卖点分层。
4. M11.5 不反向修改 M11。
5. M11.5 不直接读取原始四表。
6. seed loader 校验 20 个标准卖点和 10 个战场。
7. 候选与最终分层分表保存。
8. coverage、PSI、SSI、SAI、CPI 独立计算，并在样本不足时标记 invalid 或降低置信。
9. `basic_threshold`、`competitive_performance`、`premium_tendency`、`weak_perception`、`insufficient_sample`、`not_applicable`、`blocked` 全部有测试。
10. 样本不足不能输出 `premium_tendency`。
11. 仅参数支撑不得高置信输出溢价。
12. 结构化卖点缺失不被当成能力不存在。
13. 服务类卖点不能增强画质、游戏、体育等产品核心战场。
14. `business_reason_cn` 为中文业务语言，不暴露内部 code、SQL、JSON、UUID、公式或 AI 过程文案。
15. summary 能被 M12 直接消费，不要求 M12 重新计算卖点价值。
16. runner 支持 `force=false` 的 input hash 跳过。
17. result hash 变化时旧版本 `is_current=false`，新版本写入。
18. M11.5 结果变化时登记 M12-M16 下游失效事件。
19. 85E7Q fixture 能解释 Mini LED、高亮、分区、大屏、高刷、HDMI、性价比、服务等卖点的价值层级和证据缺口。
20. pytest 覆盖 M11.5 seed、loader、candidate、pool、metrics、classifier、risk、reason、summary、repository、runner、API、85E7Q fixture。

建议最小验证命令：

```text
pytest apps/api-server/tests/core3_real_data/test_m11_5_seed_loader.py
pytest apps/api-server/tests/core3_real_data/test_m11_5_candidate_builder.py
pytest apps/api-server/tests/core3_real_data/test_m11_5_pool_builder.py
pytest apps/api-server/tests/core3_real_data/test_m11_5_layer_classifier.py
pytest apps/api-server/tests/core3_real_data/test_m11_5_runner.py
pytest apps/api-server/tests/core3_real_data/test_m11_5_api.py
pytest apps/api-server/tests/core3_real_data/test_m11_5_85e7q_fixture.py
```

## 14. 风险和回滚

### 14.1 主要风险

| 风险 | 表现 | 处理 |
| --- | --- | --- |
| M08 M11.5 特征视图不足 | M11.5 想回读原始表补字段 | 不回读原始表，先补 M08 需求或写 `missing_feature_view` |
| M11 战场缺失 | 无法确定分层范围 | 写 `missing_battlefield_result`，不强行分层 |
| 结构化卖点稀疏 | 85E7Q 等 SKU 缺宣传证据 | 区分 `param_supported` 和 `promo_supported` |
| 战场可比池样本少 | PSI/SSI 不稳定 | 输出 `insufficient_sample` 或低置信方向性解释 |
| 评论重复 | CPI 被重复评论放大 | 只用 M05/M06 去重有效评论 |
| 服务卖点误用 | 服务保障增强画质或游戏结论 | 触发 `service_misuse`，封顶或不适用 |
| 高层文案过技术化 | 暴露 PSI、field、code、AI 过程 | reason builder 和 API schema 双重约束 |
| 下游重复计算 | M12/M13 重新算 PSI/SSI/CPI | summary 和 layer 输出指标快照，下游只读 |

### 14.2 回滚方式

代码回滚：

- 回退 M11.5 新增服务文件。
- 从 `runner.py` 移除 M11.5 注册。
- 从 API 移除 M11.5 路由。
- 不影响 M00-M11 运行。

数据库回滚：

- Alembic downgrade 删除 M11.5 五张表。
- 如果 M12-M16 已消费 M11.5，必须先标记或清理下游结果，避免悬空引用。

运行降级：

- M11.5 阻塞时，M12 可以暂时只用 M11 战场和 M09/M10 召回，但必须降低置信并提示缺 M11.5。
- M15 报告若缺 M11.5，只能展示战场和任务证据，不展示战场内卖点价值分层。

## 15. 下游依赖

### 15.1 M12 候选池召回依赖

M12 需要从 M11.5 读取：

- `core3_sku_claim_value_layer`
- `core3_sku_battlefield_claim_value_summary`
- `premium_claim_codes_json`
- `competitive_claim_codes_json`
- `basic_claim_codes_json`
- `weak_claim_codes_json`
- `insufficient_claim_codes_json`
- `m12_recall_hint_json`
- `business_reason_cn`
- `representative_evidence_refs_json`

M12 不应重新计算 PSI、SSI、SAI 或 CPI。

M12 使用方式：

- 同战场内绩效或溢价卖点相同：正面对打或配置拦截。
- 目标是门槛卖点、候选价格更低且销量不弱：价格/销量挤压。
- 候选溢价卖点更强且价格更高：高端标杆或升级替代。
- 样本不足卖点：只作为弱召回提示，不作为强召回依据。

### 15.2 M13 竞品组件评分依赖

M13 使用 M11.5 的 layer 和 metric snapshot：

- 同卖点层级差异。
- 目标与候选在同战场内的卖点强弱。
- 参数强但宣传缺失的风险。
- 服务类卖点边界。

M13 不重新计算 layer，只做目标-候选对比评分。

### 15.3 M14 三槽位选择依赖

M14 使用 M11.5 支撑：

- 正面对打槽位优先同战场同绩效或溢价卖点。
- 价格挤压槽位关注门槛卖点满足且价格/销量更强。
- 高端标杆槽位关注溢价倾向和高端价值支撑。

### 15.4 M15 报告依赖

M15 使用：

- `business_reason_cn`
- `business_reason_parts_json`
- `top_claim_value_points_cn_json`
- `risk_summary_cn_json`
- evidence breakdown

M15 页面必须把这些转换成业务高层可读语言，不展示内部枚举和过程字段。

### 15.5 M16 编排依赖

M16 需要：

- M11.5 runner status。
- review issue 统计。
- 下游失效事件。
- 样本不足和结构化卖点缺失复核队列。
- `input_fingerprint` 和 `result_hash` 变化记录。

## 16. 子任务拆分建议

编码阶段不建议一个任务完成整个 M11.5。建议拆成以下小闭环：

| 子任务 | 内容 | 产物 |
| --- | --- | --- |
| D11.5-01 | Alembic migration | 五张表、索引、约束、downgrade |
| D11.5-02 | schema 和枚举 | typed contract、API schema、runner summary |
| D11.5-03 | seed loader | 20 卖点、10 战场、映射、hash |
| D11.5-04 | input loaders | M08 feature view、M11 battlefield、claim activation |
| D11.5-05 | candidate builder | SKU x 战场 x 卖点候选 |
| D11.5-06 | pool builder | 战场可比池和 with/without 样本 |
| D11.5-07 | metric calculators | coverage、PSI、SSI、SAI、CPI |
| D11.5-08 | scorer/classifier/risk | value score、layer、封顶、risk |
| D11.5-09 | confidence/reason | 置信度和中文业务解释 |
| D11.5-10 | evidence/summary/review | 证据拆分、战场摘要、复核问题 |
| D11.5-11 | repository/service/runner | 版本写入、增量、运行摘要 |
| D11.5-12 | API | 查询和运行接口 |
| D11.5-13 | tests and fixture | 单元、集成、85E7Q 回归 |

每个编码子任务完成后都要运行对应最小测试，不能等 M11.5 全部写完再测。

## 17. 下次任务

下一个开发任务文档应处理：

```text
docs/core3_mvp/real_data_v2/development/M12_development_tasks.md
```

M12 必须以 M11 的战场组合和 M11.5 的战场内卖点价值摘要为主输入，在同战场中优先召回拥有相同绩效/溢价卖点的候选，或召回具备门槛卖点但形成价格挤压的候选。M12 不应重新计算 PSI、SSI、SAI、CPI，也不应绕过 M11.5 直接拼卖点价值证据。
