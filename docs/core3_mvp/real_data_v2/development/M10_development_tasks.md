# M10 目标客群开发任务

## 1. 模块目标

M10 的开发目标是基于 M09 用户任务、M08 SKU 综合信号画像和 M08 为 M10 裁剪的下游特征视图，推导每个 SKU 面向的主/次/弱目标客群，并输出客群候选、客群得分、关系等级、置信度、证据拆分和复核问题。

M10 要解决的工程问题：

1. 将“目标客群”从评论词、seed 默认映射和单一任务中解耦，改为由用户任务、评论客群线索、价格渠道适配、市场验证和服务侧面共同推导。
2. 对每个 SKU 和 9 个 TV MVP 目标客群都生成稳定 score 行，让 M11-M15 不需要猜测缺行是未计算还是不相关。
3. 保留候选阶段、最终得分、封顶降级、复核触发和中文业务解释，回答“这类人为什么可能买这个 SKU”。
4. 对 85E7Q 这类“85 寸、高端画质参数强、评论多、市场有、结构化卖点缺失”的 SKU，既要识别画质影音用户、家庭换新用户等强相关客群，也要避免把高端大屏误判为主性价比用户或卧室副屏用户。
5. 用 `profile_hash`、`feature_view_hash`、`task_score_fingerprint`、`target_group_seed_version`、`target_group_seed_hash`、`rule_version` 支撑增量重算、复核追溯和下游失效传播。
6. 输出可供 M15 高层报告使用的中文业务解释，但不输出内部 code、SQL、JSON、公式或“AI 判断”式过程语言。

M10 必须固化以下边界：

- M10 只消费 M08 `core3_sku_signal_profile`、`core3_sku_signal_evidence_matrix`、`core3_sku_downstream_feature_view where for_module='M10'`。
- M10 只消费 M09 `core3_sku_task_score`、`core3_sku_task_evidence_breakdown`、`core3_sku_task_review_issue`。
- M10 不直接读取原始 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data`。
- M10 不直接读取 M03、M04b、M05、M06、M07 散表做业务字段判断。
- M10 不重新推导用户任务。
- M10 不从原始评论文本直接生成客群结论。
- M10 不把“老人”“孩子”“游戏”“安装”等单个词直接等同目标客群。
- M10 不把 M09 seed 中的 `default_target_group_codes` 或 M10 seed 映射直接当成 SKU 客群结论。
- M10 不把服务安装评论泛化为产品购买人群。
- M10 不定义价值战场。
- M10 不做战场内卖点价值分层。
- M10 不召回候选 SKU。
- M10 不做竞品组件评分。
- M10 不选择核心三竞品。
- M10 不输出高层页最终报告。
- M10 不把 `unknown`、空值、`-` 或缺失值当成 false。
- M10 不按内部/外部品牌过滤，当前真实样例均为海信，海信 SKU 也可以参与后续竞品推导。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M10 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M10_target_group_requirements.md` |
| M10 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M10_target_group_design.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M08 任务 | `docs/core3_mvp/real_data_v2/development/M08_development_tasks.md` |
| M09 任务 | `docs/core3_mvp/real_data_v2/development/M09_development_tasks.md` |
| M08 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M08_sku_signal_profile_design.md` |
| M09 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M09_user_task_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 参考模块 | `cankao/catforge_sop_md/modules/M10_目标客群模块.md` |
| 目标客群 seed | `apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` |

编码前必须确认：

- M08 已输出 `core3_sku_signal_profile`，并包含 `profile_hash`、`profile_status`、`profile_confidence`、`domain_completeness_json`、`missing_signals_json`、`risk_signals_json`。
- M08 已输出 `core3_sku_signal_evidence_matrix`，并能按 SKU、证据域和 evidence refs 回溯。
- M08 已输出 `core3_sku_downstream_feature_view where for_module='M10'`，并包含 `feature_view_hash` 或 `view_hash`。
- M08 feature view 中已有客群所需的评论客群线索、价格感知、服务信号、市场画像、可比池、尺寸段、价格带和证据引用。
- M09 已输出 `core3_sku_task_score`，并覆盖 10 个用户任务的 current score。
- M09 已输出 `core3_sku_task_evidence_breakdown` 和 `core3_sku_task_review_issue`，M10 可继承任务侧复核风险。
- `tv_core3_mvp_seed_v0_2.json` 中 `target_groups` 正好覆盖 9 个 MVP 客群。
- INFRA 已提供 run context、hash 工具、runner 协议、复核 issue 约定、current 版本约定和测试 fixture 基础。

## 3. 本次范围

本次开发任务拆分覆盖 M10 的后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 4 张 M10 输出表 |
| model/schema | 新增客群 seed、M10 输入、候选、分域得分、客群得分、证据拆分、复核、runner、API schema |
| seed loader | 读取并校验真实 TV 目标客群 seed，保存 seed 版本和 hash |
| M08 input loader | 只读取 M08 profile、M10 feature view、evidence matrix |
| M09 input loader | 只读取 M09 task score、task evidence breakdown、task review issue |
| candidate builder | 对每个 SKU x 9 个客群生成候选、拒绝、复核或阻塞记录 |
| domain scorer | 分别计算任务、评论、价格渠道、市场、服务五类支撑分 |
| risk evaluator | 执行 only_comment、only_service、seed_hint_only、price_mismatch、task_review_inherited 等封顶和复核规则 |
| relation classifier | 输出 main、secondary、weak、insufficient、blocked 关系等级 |
| confidence calculator | 基于客群分、证据覆盖、M09 任务置信度、M08 画像置信度和证据质量计算置信度 |
| business reason builder | 生成业务化中文原因，禁止内部字段名和技术过程文案外露 |
| evidence breakdown | 输出任务、评论、价格渠道、市场、服务、风险、seed、profile 分域证据拆分 |
| review issue | 输出缺 M08 特征视图、缺 M09 任务结果、仅评论、仅服务、价格不适配、任务冲突、市场样本不足等复核问题 |
| invalidation | 客群结果变化时登记 M11-M16 下游影响 |
| runner/API | 运行入口、客群列表查询、客群详情查询、证据拆分查询、复核问题查询 |
| 测试 | 单元、集成、API、增量、边界、85E7Q fixture |

本次不做：

- 不实现 M11 价值战场。
- 不实现 M11.5 战场内卖点价值分层。
- 不实现 M12 候选池召回。
- 不实现 M13 竞品组件评分。
- 不实现 M14 核心三竞品选择。
- 不实现 M15 高层报告页。
- 不实现前端页面。
- 不部署到 205。
- 不修改目标客群 seed 内容，seed 只读校验。
- 不新增“服务敏感用户”等临时客群。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/target_group_schemas.py
apps/api-server/app/services/core3_real_data/target_group_repositories.py
apps/api-server/app/services/core3_real_data/target_group_seed_loader.py
apps/api-server/app/services/core3_real_data/m10_feature_view_loader.py
apps/api-server/app/services/core3_real_data/m09_task_result_loader.py
apps/api-server/app/services/core3_real_data/target_group_candidate_builder.py
apps/api-server/app/services/core3_real_data/target_group_domain_scorer.py
apps/api-server/app/services/core3_real_data/target_group_risk_evaluator.py
apps/api-server/app/services/core3_real_data/target_group_relation_classifier.py
apps/api-server/app/services/core3_real_data/target_group_confidence_calculator.py
apps/api-server/app/services/core3_real_data/target_group_business_reason_builder.py
apps/api-server/app/services/core3_real_data/target_group_evidence_breakdown_builder.py
apps/api-server/app/services/core3_real_data/target_group_review_issue_builder.py
apps/api-server/app/services/core3_real_data/target_group_invalidation_publisher.py
apps/api-server/app/services/core3_real_data/target_group_service.py
apps/api-server/app/services/core3_real_data/target_group_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `target_group_schemas.py` | M10 内部 typed contracts、枚举、runner summary |
| `target_group_repositories.py` | 读取 M08/M09 输入、写入 M10 输出、查询 current 结果 |
| `target_group_seed_loader.py` | 读取 `tv_core3_mvp_seed_v0_2.json.target_groups`、校验 9 个客群、生成 seed hash |
| `m10_feature_view_loader.py` | 加载并校验 M08 M10 feature view、profile、evidence matrix |
| `m09_task_result_loader.py` | 加载 M09 task score、task evidence breakdown、task review issue |
| `target_group_candidate_builder.py` | 生成 SKU x 客群候选、拒绝、阻塞和候选原因 |
| `target_group_domain_scorer.py` | 分别计算任务、评论、价格渠道、市场、服务支撑分和代表证据 |
| `target_group_risk_evaluator.py` | 计算风险扣分、封顶、复核原因 |
| `target_group_relation_classifier.py` | 根据得分、证据域覆盖和封顶结果输出关系等级 |
| `target_group_confidence_calculator.py` | 计算 M10 target group confidence |
| `target_group_business_reason_builder.py` | 生成业务中文解释和结构化中文解释片段 |
| `target_group_evidence_breakdown_builder.py` | 生成分域证据拆分记录 |
| `target_group_review_issue_builder.py` | 生成客群级和 SKU 级复核问题 |
| `target_group_invalidation_publisher.py` | M10 result hash 变化时登记 M11-M16 下游失效 |
| `target_group_service.py` | M10 编排 service |
| `target_group_runner.py` | M10 runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0017_core3_real_data_target_group.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0017_core3_real_data_target_group.py` | 新增 M10 4 张输出表、索引、唯一键、枚举约束 |
| `core3_real_data.py` schema | 导出 M10 运行、客群列表、客群详情、证据拆分和复核问题 response |
| `core3_real_data.py` API | 增加 M10 v2 API，不能影响旧接口 |
| `constants.py` | 补 M10 target group code、candidate status、relation level、evidence domain、review issue type |
| `runner.py` | 注册 M10 runner，不改变 M00-M09 逻辑 |
| `conftest.py` | 增加 M08/M09 输入 fixture、目标客群 seed fixture、85E7Q fixture |

如果 Alembic 当前最新编号不是 `0016`，编码时按最新编号顺延，但 migration 内容仍只能包含 M10 表、索引、约束。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m10_target_group_seed_loader.py
apps/api-server/tests/core3_real_data/test_m10_feature_view_loader.py
apps/api-server/tests/core3_real_data/test_m10_m09_task_result_loader.py
apps/api-server/tests/core3_real_data/test_m10_candidate_builder.py
apps/api-server/tests/core3_real_data/test_m10_domain_scorer.py
apps/api-server/tests/core3_real_data/test_m10_risk_evaluator.py
apps/api-server/tests/core3_real_data/test_m10_relation_classifier.py
apps/api-server/tests/core3_real_data/test_m10_confidence_calculator.py
apps/api-server/tests/core3_real_data/test_m10_business_reason_builder.py
apps/api-server/tests/core3_real_data/test_m10_evidence_breakdown_builder.py
apps/api-server/tests/core3_real_data/test_m10_review_issue_builder.py
apps/api-server/tests/core3_real_data/test_m10_repositories.py
apps/api-server/tests/core3_real_data/test_m10_runner.py
apps/api-server/tests/core3_real_data/test_m10_api.py
apps/api-server/tests/core3_real_data/test_m10_no_business_outputs.py
apps/api-server/tests/core3_real_data/test_m10_85e7q_fixture.py
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

不得在 M10 中改动或重写：

- M00-M09 已有 migration 的业务含义。
- M06 评论客群线索抽取逻辑。
- M07 市场画像和可比池逻辑。
- M08 SKU 画像和 feature view 口径。
- M09 用户任务推导逻辑。
- 205 部署脚本或 nginx 配置。

如果发现 M08 M10 特征不够或 M09 任务结果缺失，M10 只输出 `blocked` 或 `review_required`，不能在本模块绕过上游重新拼装散表。

## 6. 数据库迁移任务

### 6.1 新增 migration

新增：

```text
apps/api-server/alembic/versions/0017_core3_real_data_target_group.py
```

新增 4 张表：

| 表 | 粒度 | 用途 |
| --- | --- | --- |
| `core3_sku_target_group_candidate` | SKU + target group + input fingerprint | 记录为什么进入候选、被拒绝、阻塞或需复核 |
| `core3_sku_target_group_score` | SKU + target group + rule version | 记录客群分、关系等级、置信度和中文解释 |
| `core3_sku_target_group_evidence_breakdown` | SKU + target group + evidence domain | 记录任务、评论、价格渠道、市场、服务、风险分域证据 |
| `core3_sku_target_group_review_issue` | SKU + target group 或 SKU 级 issue | 记录客群推断复核问题 |

### 6.2 通用字段

4 张输出表都必须保留：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid/text | 是 | 主键，实际可用模块专属 ID 字段 |
| `project_id` | text | 是 | 项目 ID |
| `category_code` | text | 是 | MVP 为 `TV` |
| `batch_id` | text | 是 | 批次 ID |
| `run_id` | text | 否 | 全链路运行 ID |
| `module_run_id` | text | 否 | M10 模块运行 ID |
| `sku_code` | text | 是 | SKU 编号 |
| `model_code` | text | 否 | 真实样例中如 `TV00029115` |
| `model_name` | text | 否 | 真实样例中如 `85E7Q` |
| `brand_name` | text | 否 | 当前样例为海信 |
| `rule_version` | text | 是 | 默认 `core3_mvp_real_data_v2_m10_v1` |
| `target_group_seed_version` | text | 是 | 默认 `tv_core3_mvp_seed_v0_2` |
| `target_group_seed_file_version` | text | 是 | seed 文件内 `core3-mvp-0.2.0` |
| `target_group_seed_hash` | text | 是 | seed 文件内容 hash |
| `profile_hash` | text | 是 | M08 SKU profile hash |
| `feature_view_hash` | text | 是 | M08 M10 view hash |
| `task_score_fingerprint` | text | 是 | M09 task score、breakdown、review issue 指纹 |
| `input_fingerprint` | text | 是 | 输入指纹 |
| `result_hash` | text | 是 | 输出内容 hash |
| `is_current` | boolean | 是 | 是否当前版本 |
| `processing_status` | text | 是 | `success`、`warning`、`review_required`、`blocked`、`failed` |
| `review_required` | boolean | 是 | 是否需要复核 |
| `review_status` | text | 是 | `auto_pass`、`review_required`、`approved`、`rejected`、`waived` |
| `review_reason_json` | jsonb | 是 | 复核原因 |
| `created_at` | timestamptz | 是 | 创建时间 |
| `updated_at` | timestamptz | 是 | 更新时间 |

### 6.3 `core3_sku_target_group_candidate`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sku_target_group_candidate_id` | uuid | 是 | 主键 |
| `sku_signal_profile_id` | uuid | 是 | M08 profile ID |
| `sku_downstream_feature_view_id` | uuid | 是 | M08 M10 feature view ID |
| `target_group_code` | text | 是 | 9 个 seed 客群之一 |
| `target_group_name_cn` | text | 是 | 中文业务名 |
| `target_group_definition_cn` | text | 是 | 客群定义 |
| `candidate_status` | text | 是 | `active`、`rejected`、`review_required`、`blocked` |
| `candidate_source_json` | jsonb | 是 | task、comment、price_channel、market、service、seed_hint、seed_gap |
| `candidate_source_count` | integer | 是 | 有效来源数 |
| `source_task_codes_json` | jsonb | 是 | 来源任务、关系等级、任务分 |
| `candidate_initial_score` | numeric | 是 | 候选初始分 |
| `candidate_reason_cn` | text | 是 | 中文候选原因 |
| `reject_reason_json` | jsonb | 是 | 被拒绝原因 |
| `missing_signals_json` | jsonb | 是 | 缺失信号 |
| `risk_flags_json` | jsonb | 是 | 风险 |
| `evidence_ids` | uuid[] | 是 | 候选代表 evidence |
| `evidence_matrix_refs_json` | jsonb | 是 | M08 evidence matrix refs |

当前版本唯一索引：

```text
ux_m10_target_group_candidate_current(project_id, category_code, batch_id, sku_code, target_group_code, target_group_seed_version, rule_version)
  where is_current = true
```

查询索引：

- `(project_id, category_code, batch_id, sku_code, is_current)`
- `(project_id, category_code, batch_id, target_group_code, candidate_status, is_current)`
- `(project_id, category_code, batch_id, review_required, is_current)`
- `(project_id, category_code, batch_id, input_fingerprint)`
- GIN `candidate_source_json`

### 6.4 `core3_sku_target_group_score`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sku_target_group_score_id` | uuid | 是 | 主键 |
| `sku_signal_profile_id` | uuid | 是 | M08 profile ID |
| `sku_downstream_feature_view_id` | uuid | 是 | M08 M10 feature view ID |
| `target_group_code` | text | 是 | 9 个 seed 客群之一 |
| `target_group_name_cn` | text | 是 | 中文业务名 |
| `target_group_definition_cn` | text | 是 | 客群定义 |
| `candidate_id` | uuid | 否 | 对应 candidate |
| `task_support_score` | numeric | 是 | M09 任务支撑分 |
| `comment_group_signal_score` | numeric | 是 | 评论客群线索分 |
| `price_channel_fit_score` | numeric | 是 | 价格渠道适配分 |
| `market_validation_score` | numeric | 是 | 市场验证分 |
| `service_side_score` | numeric | 是 | 服务侧面分，只可作为侧证 |
| `raw_target_group_score` | numeric | 是 | 风险修正前分 |
| `risk_penalty` | numeric | 是 | 风险扣分 |
| `target_group_score` | numeric | 是 | 最终客群分 |
| `relation_level` | text | 是 | `main`、`secondary`、`weak`、`insufficient`、`blocked` |
| `relation_reason_json` | jsonb | 是 | 关系等级判定原因 |
| `confidence` | numeric | 是 | 置信度 |
| `confidence_level` | text | 是 | `high`、`medium`、`low`、`unknown` |
| `evidence_domain_count` | integer | 是 | 有效证据域数量 |
| `effective_domain_json` | jsonb | 是 | 哪些域有效 |
| `source_task_scores_json` | jsonb | 是 | 来源任务及得分 |
| `score_breakdown_json` | jsonb | 是 | 权重、原始分、封顶、风险 |
| `cap_rule_applied_json` | jsonb | 是 | 触发的封顶规则 |
| `missing_signals_json` | jsonb | 是 | 缺失信号 |
| `risk_flags_json` | jsonb | 是 | 风险 |
| `business_reason_cn` | text | 是 | 中文业务解释摘要 |
| `business_reason_parts_json` | jsonb | 是 | 购买任务、用户线索、价格渠道、市场验证、待复核点 |
| `next_module_payload_json` | jsonb | 是 | M11-M15 可消费精简 payload |
| `evidence_ids` | uuid[] | 是 | 核心 evidence |
| `evidence_matrix_refs_json` | jsonb | 是 | M08 evidence matrix refs |

MVP 建议每个有效 SKU 对 9 个目标客群都生成一行 score。未命中的客群 `relation_level='insufficient'`，缺关键输入时 `relation_level='blocked'`。

当前版本唯一索引：

```text
ux_m10_target_group_score_current(project_id, category_code, batch_id, sku_code, target_group_code, target_group_seed_version, rule_version)
  where is_current = true
```

查询索引：

- `(project_id, category_code, batch_id, sku_code, relation_level, target_group_score desc)`
- `(project_id, category_code, batch_id, target_group_code, relation_level, is_current)`
- `(project_id, category_code, batch_id, sku_code, target_group_score desc, confidence desc)`
- `(project_id, category_code, batch_id, profile_hash, task_score_fingerprint, target_group_seed_version, rule_version)`
- GIN `score_breakdown_json`
- GIN `cap_rule_applied_json`
- GIN `next_module_payload_json`

### 6.5 `core3_sku_target_group_evidence_breakdown`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sku_target_group_evidence_breakdown_id` | uuid | 是 | 主键 |
| `sku_target_group_score_id` | uuid | 是 | 对应 score |
| `target_group_code` | text | 是 | 客群 code |
| `evidence_domain` | text | 是 | `task`、`comment`、`price_channel`、`market`、`service`、`risk`、`seed`、`profile` |
| `support_level` | text | 是 | `strong`、`medium`、`weak`、`missing`、`conflict`、`not_applicable` |
| `support_score` | numeric | 是 | 分域原始分 |
| `domain_weight` | numeric | 是 | 该域权重 |
| `weighted_contribution` | numeric | 是 | 加权贡献 |
| `support_summary_cn` | text | 是 | 中文证据摘要 |
| `source_signal_codes_json` | jsonb | 是 | 来源任务、评论主题、市场信号或 seed 信号 |
| `source_values_json` | jsonb | 是 | 命中的具体值和强度 |
| `representative_evidence_ids` | uuid[] | 是 | 代表 evidence |
| `evidence_matrix_refs_json` | jsonb | 是 | M08 evidence matrix refs |
| `missing_reason_code` | text | 否 | 缺失原因 |
| `risk_flags_json` | jsonb | 是 | 风险 |
| `confidence` | numeric | 是 | 分域置信度 |

每个 score 至少输出以下域记录：

```text
task
comment
price_channel
market
service
risk
```

缺失域也要输出 `support_level='missing'` 或 `not_applicable`，避免下游误判没有计算。

唯一键：

```text
ux_m10_target_group_breakdown_current(project_id, category_code, batch_id, sku_code, target_group_code, evidence_domain, target_group_seed_version, rule_version)
  where is_current = true
```

索引：

- `(sku_target_group_score_id, evidence_domain)`
- `(project_id, category_code, batch_id, sku_code, target_group_code, is_current)`
- `(project_id, category_code, batch_id, evidence_domain, support_level, is_current)`
- GIN `representative_evidence_ids`
- GIN `source_signal_codes_json`

### 6.6 `core3_sku_target_group_review_issue`

字段任务：

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sku_target_group_review_issue_id` | uuid | 是 | 主键 |
| `target_group_code` | text | 否 | 为空表示 SKU 级问题 |
| `issue_type` | text | 是 | 复核类型 |
| `issue_level` | text | 是 | `warning`、`blocker` |
| `issue_message_cn` | text | 是 | 中文复核说明 |
| `issue_context_json` | jsonb | 是 | 结构化复核详情 |
| `related_score_id` | uuid | 否 | 关联客群分 |
| `related_candidate_id` | uuid | 否 | 关联候选 |
| `source_task_score_ids` | uuid[] | 是 | 来源 M09 任务记录 |
| `evidence_ids` | uuid[] | 是 | 相关证据 |
| `resolved_status` | text | 是 | `open`、`resolved`、`ignored` |
| `resolved_by` | text | 否 | 处理人 |
| `resolved_at` | timestamptz | 否 | 处理时间 |
| `resolution_note` | text | 否 | 处理说明 |

`issue_type` 至少覆盖：

```text
missing_feature_view
missing_task_score
only_comment
only_service
price_mismatch
market_limited
task_conflict
task_review_inherited
comment_quality_risk
seed_gap
profile_blocked
high_score_contradiction
seed_hint_only
unknown_input
bedroom_size_mismatch
value_price_mismatch
```

表达式唯一索引：

```text
ux_m10_target_group_review_issue_current(project_id, category_code, batch_id, sku_code, coalesce(target_group_code, ''), issue_type, input_fingerprint)
  where is_current = true
```

索引：

- `(project_id, category_code, batch_id, resolved_status, issue_level, is_current)`
- `(project_id, category_code, batch_id, sku_code, target_group_code, is_current)`
- `(project_id, category_code, batch_id, issue_type, is_current)`

## 7. model/schema 任务

### 7.1 枚举

在 `target_group_schemas.py` 和必要的 API schema 中定义：

```text
TargetGroupCandidateStatus = active | rejected | review_required | blocked
TargetGroupCandidateSource = task | comment | price_channel | market | service | seed_hint | seed_gap
TargetGroupRelationLevel = main | secondary | weak | insufficient | blocked
TargetGroupEvidenceDomain = task | comment | price_channel | market | service | risk | seed | profile
TargetGroupSupportLevel = strong | medium | weak | missing | conflict | not_applicable
TargetGroupReviewIssueType = missing_feature_view | missing_task_score | only_comment | only_service | price_mismatch | market_limited | task_conflict | task_review_inherited | comment_quality_risk | seed_gap | profile_blocked | high_score_contradiction | seed_hint_only | unknown_input | bedroom_size_mismatch | value_price_mismatch
```

### 7.2 seed schema

新增 typed contracts：

| schema | 关键字段 |
| --- | --- |
| `TargetGroupSeedSet` | `category_code`、`file_version`、`target_group_seed_version`、`target_group_seed_hash`、`target_groups` |
| `TargetGroupSeed` | `target_group_code`、`target_group_name_cn`、`definition_cn`、`aliases`、`keywords`、`source_task_codes` |
| `TargetGroupMarketFitRule` | `signals`、可识别市场信号、unknown 信号 |
| `TargetGroupEvidenceRequirement` | 客群需要的最低证据类型 |
| `TargetGroupMappingRule` | 来源任务、市场适配、战场提示 |

必须校验 9 个客群：

```text
TG_FAMILY_UPGRADE
TG_AV_QUALITY_SEEKER
TG_GAMER
TG_SPORTS_FAN
TG_SENIOR_FAMILY
TG_CHILD_FAMILY
TG_VALUE_BUYER
TG_NEW_HOME_DECORATOR
TG_BEDROOM_SECOND_TV
```

M10 必须以真实 seed 的 9 个客群为准，不能使用旧 SOP 参考中的 `GROUP_*` 代码，也不能临时新增“服务敏感用户”。

seed 校验要求：

- `category_code='TV'`。
- `target_groups` 正好覆盖 9 个 MVP target_group_code。
- 每个客群有中文名称、定义、`source_task_codes`。
- `source_task_codes` 均存在于 M09 10 个任务 seed。
- `market_fit_rule.signals` 可识别；无法观测的信号标记为 unknown，不当负向。
- `mapped_battlefield_codes` 只作为 M11 提示，不影响 M10 结论。
- target_group_code 无重复。
- seed hash 可稳定计算。

### 7.3 M08/M09 输入 schema

新增：

| schema | 用途 |
| --- | --- |
| `M10FeatureViewInput` | 承载 M08 `for_module='M10'` 特征包 |
| `M10SkuProfileInput` | 承载 M08 SKU profile 摘要、状态和 `profile_hash` |
| `M10EvidenceMatrixInput` | 承载 M08 分域 evidence matrix |
| `M09TaskScoreInput` | 承载 M09 task score |
| `M09TaskBreakdownInput` | 承载 M09 task evidence breakdown |
| `M09TaskReviewIssueInput` | 承载 M09 task review issue |
| `M10TargetGroupFeatureBundle` | 合并 M08/M09 后的单 SKU 输入 |

输入 schema 必须表达：

- `profile_status`
- `profile_hash`
- `feature_view_hash`
- `task_score_fingerprint`
- `input_fingerprint`
- M09 task score、relation level、confidence、review_required
- M09 task evidence domain coverage
- M09 open review issue summary
- M08 `target_group_cue_comment_signals`
- M08 `price_perception_signals`
- M08 `service_signal`
- M08 market summary and comparable pool summary
- M08 evidence refs and evidence matrix refs
- M08 missing/risk/domain completeness

### 7.4 输出 schema

新增：

| schema | 用途 |
| --- | --- |
| `TargetGroupCandidateRecord` | 对应 `core3_sku_target_group_candidate` |
| `TargetGroupDomainScore` | 任务、评论、价格渠道、市场、服务单域评分 |
| `TargetGroupRiskDecision` | 风险扣分、封顶和复核 |
| `TargetGroupScoreRecord` | 对应 `core3_sku_target_group_score` |
| `TargetGroupEvidenceBreakdownRecord` | 对应 `core3_sku_target_group_evidence_breakdown` |
| `TargetGroupReviewIssueRecord` | 对应 `core3_sku_target_group_review_issue` |
| `M10RunRequest` | runner/API 请求 |
| `M10RunSummary` | 运行汇总 |
| `SkuTargetGroupListResponse` | SKU 客群列表 API 返回 |
| `SkuTargetGroupDetailResponse` | 单客群详情 API 返回 |
| `SkuTargetGroupEvidenceResponse` | 证据拆分 API 返回 |

输出 schema 必须避免把内部调试字段直接暴露给前端高层页面。API 可以返回机器字段，但业务页面消费时必须有中文业务字段。

## 8. repository 任务

### 8.1 读取职责

`TargetGroupRepository` 只允许读取：

| 来源 | 查询 |
| --- | --- |
| M08 profile | `core3_sku_signal_profile where is_current=true` |
| M08 feature view | `core3_sku_downstream_feature_view where for_module='M10' and is_current=true` |
| M08 evidence matrix | `core3_sku_signal_evidence_matrix where is_current=true` |
| M09 task score | `core3_sku_task_score where is_current=true` |
| M09 task evidence breakdown | `core3_sku_task_evidence_breakdown where is_current=true` |
| M09 task review issue | `core3_sku_task_review_issue where is_current=true` |
| M02 evidence atom | 仅按 M08/M09 evidence refs 批量回溯，不做业务扫描 |
| M10 历史输出 | 查询可复用 current 记录和旧版本失效 |

不得增加以下 repository 查询：

- 直接查 `week_sales_data`。
- 直接查 `attribute_data`。
- 直接查 `selling_points_data`。
- 直接查 `comment_data`。
- 直接查 M03/M04b/M05/M06/M07 散表做业务判断。

### 8.2 写入职责

`TargetGroupRepository` 必须支持：

1. `mark_previous_records_not_current(...)`
2. `bulk_insert_candidates(...)`
3. `bulk_insert_scores(...)`
4. `bulk_insert_evidence_breakdowns(...)`
5. `bulk_insert_review_issues(...)`
6. `get_current_target_group_scores(...)`
7. `get_target_group_detail(...)`
8. `get_target_group_evidence_breakdown(...)`
9. `list_review_issues(...)`

写入约定：

- 同一 SKU、target_group、rule、seed hash 的新结果写入前，旧 current 记录必须置为 `is_current=false`。
- 写入 candidate、score、breakdown、review issue 必须在同一事务内完成。
- 任一 SKU feature view 缺失或 M09 task score 缺失时，该 SKU 的 9 个客群应写 `blocked` score 或复核问题，不能静默跳过。
- repository 不计算业务分，只负责持久化和查询。

### 8.3 查询返回顺序

SKU 客群列表默认排序：

1. `relation_level` 按 main、secondary、weak、insufficient、blocked。
2. `target_group_score desc`。
3. `confidence desc`。
4. seed 中客群顺序。

客群详情必须返回：

- 客群中文名。
- 关系等级。
- 分数和置信度。
- 任务、评论、价格渠道、市场、服务分域得分。
- 业务解释。
- 分域证据拆分。
- 复核问题。

## 9. service 任务

### 9.1 编排流程

`TargetGroupService.run(...)` 按以下步骤执行：

1. 构建 run context 和 `module_run_id`。
2. 加载并校验目标客群 seed。
3. 读取 SKU 范围内 M08 profile、M10 feature view、evidence matrix。
4. 读取 SKU 范围内 M09 task score、task evidence breakdown、task review issue。
5. 对缺失 M08 feature view 的 SKU 生成 `missing_feature_view` 阻塞问题。
6. 对缺失 M09 task score 的 SKU 生成 `missing_task_score` 阻塞问题。
7. 对每个有效 SKU 遍历 9 个 seed 客群。
8. `TargetGroupCandidateBuilder` 生成候选、拒绝、复核或阻塞。
9. `TargetGroupDomainScorer` 计算任务、评论、价格渠道、市场、服务五域支撑分。
10. `TargetGroupRiskEvaluator` 应用风险扣分、封顶和复核规则。
11. `TargetGroupRelationClassifier` 输出关系等级。
12. `TargetGroupConfidenceCalculator` 输出置信度。
13. `TargetGroupBusinessReasonBuilder` 生成中文业务解释。
14. `TargetGroupEvidenceBreakdownBuilder` 生成分域证据拆分。
15. `TargetGroupReviewIssueBuilder` 生成复核问题。
16. 计算 `result_hash`，判断是否需要写入或复用。
17. 事务写入 4 张输出表。
18. `TargetGroupInvalidationPublisher` 登记 M11-M16 下游失效。
19. 返回 `M10RunSummary`。

### 9.2 候选生成规则

候选遍历粒度必须是 SKU x 9 个 seed 客群。进入候选的条件满足任一即可：

| 触发来源 | 条件 |
| --- | --- |
| 任务触发 | M09 命中客群 `source_task_codes`，且任务关系不是 `insufficient` |
| 评论触发 | M08 汇总的 `target_group_cue` 命中客群别名、关键词、家庭结构或购买动机 |
| 价格渠道触发 | 价格带、尺寸段、平台与客群市场适配规则匹配 |
| 市场触发 | 可比池、销量、销额或价格分位支持该客群购买语境 |
| 服务触发 | 服务信号命中新家装修、安装省心相关场景 |
| seed 提示触发 | M09 任务 seed 的默认客群命中，但只能形成候选，不能直接得高分 |

候选初始分建议：

```text
candidate_initial_score =
  max(task_candidate_score, comment_candidate_score, price_channel_candidate_score, market_candidate_score)
  + min(candidate_source_count * 0.05, 0.15)
  - candidate_risk_penalty
```

约束：

- 单评论命中可进入候选，但最终关系等级最高 `weak`。
- 单服务信号只允许触发 `TG_NEW_HOME_DECORATOR` 候选。
- 单 seed 默认映射只能触发候选，不可成为客群结论。
- `TG_BEDROOM_SECOND_TV` 必须校验尺寸和价格语境。
- 无法映射到 9 个 seed 客群的高频人群线索写 `seed_gap`，不能新增临时客群。

### 9.3 分域评分规则

首版综合得分：

```text
raw_target_group_score =
  task_support_score * 0.55
  + comment_group_signal_score * 0.20
  + price_channel_fit_score * 0.15
  + market_validation_score * 0.10

target_group_score = clamp(raw_target_group_score - risk_penalty, 0, 1)
```

`service_side_score` 不独立进入主公式，默认通过评论和风险表达；对 `TG_NEW_HOME_DECORATOR` 可在 rule version 中将服务侧面纳入评论域内部。

分域要求：

| 域 | 输入 | 评分要求 |
| --- | --- | --- |
| 任务 | M09 task score、relation level、confidence、breakdown | main 强支撑，secondary 中支撑，weak 只形成弱线索，M09 review 继承复核 |
| 评论 | M08 M10 view 的 target_group_cue、去重评论、有效句 | 评论不能单独生成高置信主客群；低价值评论降置信 |
| 价格渠道 | M08 price_band、size_segment、platform、价格分位、可比池 | 性价比、卧室副屏、新家装修等必须有价格或尺寸语境 |
| 市场 | M08/M07 市场画像、可比池、销量、销额、样本状态 | 样本不足不否定客群，只降置信和复核 |
| 服务 | M08 service_signal | 只增强新家装修或服务侧面，不能替代产品人群 |

### 9.4 封顶和复核规则

必须实现以下封顶：

| 条件 | 处理 |
| --- | --- |
| `only_comment` | 仅评论命中时，最高 `weak`，如果接近 secondary 阈值则复核 |
| `only_service` | 仅服务信号命中时，最高 `weak`，且只允许影响新家装修用户侧面 |
| `seed_hint_only` | 仅 seed 默认映射命中时，最高 `weak`，不能成为结论 |
| `task_review_inherited` | 来源 M09 任务 `review_required=true` 时，相关客群最高 `secondary` 并继承复核原因 |
| `price_mismatch` | 价格渠道明显不适配时，最高 `weak` |
| `value_price_mismatch` | 高价 SKU 被判为性价比用户且缺少低价分位或促销证据，最高 `weak` 并复核 |
| `bedroom_size_mismatch` | 大尺寸高端 SKU 被判为卧室副屏用户，最高 `weak` 并复核 |
| `comment_quality_risk` | 评论有效样本不足或低价值占比高，最高 `secondary` 并降置信 |
| `market_limited` | 市场样本或可比池不足，最高 `secondary` 并复核 |
| `missing_feature_view` | 缺 M08 M10 feature view 时，关系等级 `blocked` |
| `missing_task_score` | 缺 M09 任务结果时，关系等级 `blocked` |
| `profile_blocked` | M08 profile blocked 时，关系等级 `blocked` |

`unknown`、空值和 `-` 只能降低完整度或触发 `unknown_input`，不能生成负向结论。

### 9.5 关系等级

默认判定：

| relation_level | 条件 |
| --- | --- |
| `main` | `target_group_score >= 0.75`，至少 2 类证据有效，且任务或市场必须有效 |
| `secondary` | `0.60 <= target_group_score < 0.75`，至少 2 类证据有效，或一个强任务支撑加一个弱验证 |
| `weak` | `0.40 <= target_group_score < 0.60`，或被封顶到 weak |
| `insufficient` | `target_group_score < 0.40`，证据不足 |
| `blocked` | 缺 M08 feature view、缺 M09 task score、profile blocked 或 seed 校验阻塞 |

被封顶规则覆盖时，以更低等级为准。

### 9.6 置信度

置信度建议公式：

```text
confidence =
  target_group_score * 0.35
  + evidence_domain_coverage_score * 0.25
  + m09_task_confidence_score * 0.20
  + m08_profile_confidence * 0.10
  + evidence_quality_score * 0.10
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
- M08 profile confidence。
- evidence domain 覆盖数量。
- evidence refs 是否可回溯。
- 评论去重质量和有效句数量。
- 市场样本状态和可比池充分性。
- 结构化卖点缺失对画质影音等客群的宣传证据影响。
- 价格渠道是否与客群购买语境一致。

### 9.7 中文业务解释

`TargetGroupBusinessReasonBuilder` 输出：

```text
business_reason_parts_json.purchase_task_cn
business_reason_parts_json.user_cue_cn
business_reason_parts_json.price_channel_cn
business_reason_parts_json.market_validation_cn
business_reason_parts_json.review_points_cn
business_reason_cn
```

业务解释要求：

- 使用业务语言说明“这类人为什么可能买这个 SKU”。
- 先说购买任务，再说用户线索、价格渠道、市场验证，最后说待复核点。
- 不出现 SQL、JSON、字段名、公式、内部 code、`target_group_cue`、`profile_hash`、`task_score_fingerprint`、“AI 判断”等字样。
- 对 85E7Q 的画质影音用户，要说明高端画质任务、Mini LED/亮度/分区、画质评论和高端价格带支撑，同时提示结构化卖点缺失需要复核。
- 对 85E7Q 的性价比用户，要说明需要价格分位、销量和价格价值评论共同支撑；高端价格带时不能写成主客群。
- 对服务信号命中的新家装修用户，要说明服务只是安装/交付侧面，不能替代产品购买人群判断。

## 10. runner/API 任务

### 10.1 runner

新增 runner：

```python
run_m10_target_group(
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_codes: list[str] | None = None,
    target_group_codes: list[str] | None = None,
    force: bool = False,
    target_group_seed_version: str = "tv_core3_mvp_seed_v0_2",
    rule_version: str = "core3_mvp_real_data_v2_m10_v1",
) -> M10RunSummary
```

runner 要求：

- 默认处理 batch 内所有有 M08 profile 或 M08 M10 feature view 或 M09 task score 的 SKU。
- `target_group_codes` 不传时必须遍历 9 个 seed 客群。
- `force=false` 时复用 hash 未变化的历史 current 结果。
- `force=true` 时重算并写新版本。
- seed 校验阻塞时本次 run 标记 failed 或 blocked，不写半成品业务结论。
- 单 SKU 缺 M08 feature view 或 M09 task score 时只阻塞该 SKU，不影响其他 SKU。
- 每个有效 SKU 对 9 个客群都应有 score 行。

### 10.2 API

新增 v2 API：

```text
POST /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/runs/m10-target-group
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/runs/{run_id}/m10
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/target-groups
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/target-groups/{target_group_code}
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/target-groups/{target_group_code}/evidence
GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/target-group-review-issues
```

API response 要求：

- 支持按 `relation_level`、`target_group_code`、`review_required`、`processing_status` 过滤。
- SKU 客群列表默认只返回 current 结果。
- 客群详情返回中文客群名、关系等级、五域得分、业务解释、证据拆分和复核点。
- 证据接口返回 M08/M09/M02 refs，不重新读取原始表。
- API 不应直接作为高层页文案；高层页最终呈现由 M15/FRONTEND 设计转换。

## 11. 增量策略

### 11.1 输入指纹

`input_fingerprint` 至少包含：

```text
project_id
category_code
batch_id
sku_code
target_group_code
profile_hash
feature_view_hash
M08 evidence matrix result_hash
M09 task score result_hash set
M09 task evidence breakdown result_hash set
M09 open review issue summary hash
target_group_seed_hash
target_group_seed_version
target_group_seed_file_version
rule_version
threshold_version
cap_rule_version
business_reason_template_version
```

### 11.2 可复用条件

历史结果可复用必须同时满足：

- M08 `profile_hash` 未变化。
- M08 M10 `feature_view_hash` 未变化。
- M08 evidence matrix 相关 `result_hash` 未变化。
- M09 current task scores 的 result hash 集合未变化。
- M09 task evidence breakdown 的 result hash 集合未变化。
- M09 open review issue 摘要未变化。
- `target_group_seed_hash` 未变化。
- `target_group_seed_version` 未变化。
- `rule_version`、阈值版本、封顶规则版本、业务解释模板版本未变化。
- 历史记录 `is_current=true`。
- 历史记录 `processing_status` 不是 `failed` 或 `blocked`。

### 11.3 下游失效

M10 任一 SKU 的 target group score、relation level、confidence、review status、business payload 或 evidence refs 变化时，必须登记下游影响：

```text
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
- `changed_target_group_codes`
- `old_result_hash`
- `new_result_hash`
- `affected_modules`
- `reason="m10_target_group_changed"`

只有 evidence 代表集变化但 target_group_score 未变化时，也要通知 M15 更新证据卡。

## 12. 真实数据和 fixture 验收

### 12.1 样例数据约束

开发测试必须体现真实样例数据约束：

- 市场窗口为 `26W01` 到 `26W23`，不能出现 12 月口径。
- 当前样例市场模型约 35 个，参数约 35 个，评论约 33 个，结构化卖点约 5 个。
- 当前样例均为海信品牌，不能按内部/外部品牌过滤。
- 当前市场数据主要是线上，含专业电商、平台电商；不能推导线下客群。
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
| 结构化卖点 | 缺失或不足，必须继承 M09 `missing_structured_claim` 风险 |

85E7Q 客群预期：

| 客群 | 预期 |
| --- | --- |
| 画质影音用户 | 由高端画质影音任务、Mini LED、亮度、分区、画质评论和高端价格带支撑；缺结构化卖点需降低宣传证据置信度 |
| 家庭换新用户 | 由客厅影院观影、大屏换新任务、85 寸、家庭观影/尺寸评论和市场表现支撑；要区分家庭观影和单纯大尺寸参数 |
| 体育观看用户 | 由体育赛事观看任务、看球评论、高刷和运动画面证据支撑；不能只因高刷默认主客群 |
| 游戏用户 | 由游戏娱乐任务、高刷、HDMI2.1 和游戏评论支撑；缺游戏评论或低延迟时应为候选或弱客群 |
| 性价比用户 | 需要性价比购买任务、价格分位、销量和价格价值评论；高端价格带时不能高置信判为主客群 |
| 新家装修用户 | 由新家装修搭配任务、尺寸空间、外观、安装评论支撑；纯安装服务好评只能支撑侧面 |
| 儿童家庭用户 | 需要儿童护眼任务、护眼参数、儿童/孩子评论；无明确儿童/护眼信号时不高分 |
| 长辈家庭用户 | 需要长辈易用任务、语音/简单操作、爸妈/老人评论；无明确人群线索时不高分 |
| 卧室副屏用户 | 85E7Q 默认不应作为主客群，除非有非常强的卧室/副屏语境且仍需复核 |

## 13. 测试任务

### 13.1 seed loader 测试

`test_m10_target_group_seed_loader.py`：

- `test_target_group_seed_has_9_groups`
- `test_target_group_seed_rejects_missing_required_group`
- `test_target_group_seed_rejects_group_source_task_not_in_m09_seed`
- `test_target_group_seed_hash_is_stable`
- `test_target_group_seed_uses_real_tg_codes_not_old_group_codes`
- `test_service_sensitive_user_not_added_as_temporary_group`

### 13.2 M08/M09 input loader 测试

`test_m10_feature_view_loader.py`、`test_m10_m09_task_result_loader.py`：

- `test_m10_loads_only_m08_feature_view`
- `test_m10_blocks_without_feature_view`
- `test_m10_blocks_without_m09_scores`
- `test_m10_does_not_query_raw_tables`
- `test_m10_does_not_query_m06_or_m07_scatter_tables`
- `test_profile_blocked_becomes_target_group_blocked`
- `test_task_score_fingerprint_is_stable`
- `test_unknown_input_preserved_as_unknown`

### 13.3 candidate builder 测试

`test_m10_candidate_builder.py`：

- `test_candidate_created_by_task_trigger`
- `test_candidate_created_by_comment_trigger_with_dedup_threshold`
- `test_candidate_created_by_price_channel_trigger`
- `test_candidate_created_by_market_trigger`
- `test_service_signal_only_limited_to_new_home_decorator`
- `test_seed_hint_only_creates_candidate_not_conclusion`
- `test_unmapped_pattern_creates_seed_gap_review_issue`
- `test_candidate_and_score_separated`

### 13.4 scorer 和 risk 测试

`test_m10_domain_scorer.py`、`test_m10_risk_evaluator.py`：

- `test_main_task_strongly_supports_mapped_group`
- `test_weak_task_only_forms_weak_group_signal`
- `test_comment_only_capped_to_weak`
- `test_service_only_limited_to_new_home`
- `test_seed_hint_only_not_final_group`
- `test_price_mismatch_caps_value_buyer`
- `test_large_screen_not_bedroom_second_tv`
- `test_task_review_inherited_caps_secondary`
- `test_market_limited_caps_secondary`
- `test_unknown_not_false`

### 13.5 relation 和 confidence 测试

`test_m10_relation_classifier.py`、`test_m10_confidence_calculator.py`：

- `test_main_requires_two_domains_and_task_or_market`
- `test_secondary_requires_two_domains_or_strong_task_with_weak_validation`
- `test_weak_for_low_score_or_cap`
- `test_blocked_for_missing_feature_view_or_task_score`
- `test_confidence_uses_m09_task_confidence`
- `test_confidence_uses_m08_profile_confidence`
- `test_confidence_penalizes_comment_low_quality`
- `test_confidence_penalizes_market_limited`

### 13.6 business reason 测试

`test_m10_business_reason_builder.py`、`test_m10_no_business_outputs.py`：

- `test_business_reason_cn_no_internal_tokens`
- `test_business_reason_does_not_say_ai_judgement`
- `test_business_reason_does_not_expose_sql_json_formula`
- `test_business_reason_does_not_expose_target_group_cue_or_hash`
- `test_value_buyer_reason_mentions_price_evidence_requirement`
- `test_service_only_reason_is_side_signal_not_product_group`

### 13.7 repository、runner、API 测试

`test_m10_repositories.py`、`test_m10_runner.py`、`test_m10_api.py`：

- `test_repository_marks_previous_current_false`
- `test_repository_writes_four_output_tables_in_transaction`
- `test_runner_writes_9_scores_per_valid_sku`
- `test_runner_skips_when_input_fingerprint_unchanged`
- `test_runner_force_recomputes`
- `test_runner_invalidates_m11_to_m16_on_result_hash_change`
- `test_api_runs_m10`
- `test_api_lists_sku_target_groups_sorted_by_relation_and_score`
- `test_api_returns_target_group_evidence_breakdown`
- `test_api_lists_review_issues`

### 13.8 85E7Q fixture 测试

`test_m10_85e7q_fixture.py`：

- `test_85e7q_av_quality_seeker_supported_with_missing_claim_review`
- `test_85e7q_family_upgrade_supported_by_living_room_and_large_screen_tasks`
- `test_85e7q_sports_and_gaming_distinguished`
- `test_85e7q_gamer_not_main_without_game_specific_evidence`
- `test_85e7q_value_buyer_not_main_when_price_band_high`
- `test_85e7q_new_home_decorator_service_is_side_signal`
- `test_85e7q_child_family_not_high_without_child_or_eye_care_evidence`
- `test_85e7q_senior_family_not_high_without_senior_cue`
- `test_85e7q_bedroom_second_tv_not_main_for_85_inch`
- `test_85e7q_comment_count_and_dedup_refs_preserved`

## 14. 开发子任务拆分

### M10-1 迁移和 schema

目标：

- 创建 `0017_core3_real_data_target_group.py`。
- 创建 `target_group_schemas.py`。
- 在 API schema 中暴露必要 response。

验收：

- 4 张表、唯一键、索引存在。
- target group seed、candidate、score、breakdown、review issue schema 可实例化。
- enum 覆盖全部设计值。

### M10-2 seed loader

目标：

- 实现 `TargetGroupSeedLoader`。
- 校验 `tv_core3_mvp_seed_v0_2.json.target_groups` 中 9 个真实客群。
- 校验 source task codes 与 M09 10 个任务 seed 对齐。
- 生成 `target_group_seed_hash`。

验收：

- seed 版本、文件版本、hash 可写入输出。
- 缺客群、重复客群、source task 不存在均阻塞。
- 旧 `GROUP_*` 代码不能通过校验。

### M10-3 M08/M09 输入加载

目标：

- 实现 `M10FeatureViewLoader`。
- 实现 `M09TaskResultLoader`。
- 只读取 M08 profile、M10 feature view、evidence matrix 和 M09 任务输出。

验收：

- 缺 M08 M10 feature view 输出 `missing_feature_view`。
- 缺 M09 task score 输出 `missing_task_score`。
- profile blocked 输出 blocked。
- 单元测试证明不直接读取原始表和上游散表。

### M10-4 候选生成

目标：

- 实现 `TargetGroupCandidateBuilder`。
- 对 SKU x 9 客群生成 active、rejected、review_required、blocked。

验收：

- 任务、评论、价格渠道、市场、服务、seed hint 触发均可覆盖。
- 服务信号只触发新家装修用户侧面。
- seed hint 只能生成候选，不能成为最终主客群。
- 候选和最终得分分离。

### M10-5 分域评分

目标：

- 实现 `TargetGroupDomainScorer`。
- 输出 task、comment、price_channel、market、service 五域分。

验收：

- M09 main/secondary/weak 任务对客群支撑不同。
- 评论必须使用去重评论和有效句。
- 性价比和卧室副屏必须校验价格和尺寸语境。
- 市场样本不足不生成负向结论。
- unknown 不当 false。

### M10-6 风险、关系、置信度

目标：

- 实现 `TargetGroupRiskEvaluator`、`TargetGroupRelationClassifier`、`TargetGroupConfidenceCalculator`。

验收：

- `only_comment` 最高 weak。
- `only_service` 最高 weak。
- `seed_hint_only` 不能成为结论。
- `task_review_inherited` 最高 secondary。
- `price_mismatch` 最高 weak。
- main 必须至少 2 域有效且任务或市场有效。

### M10-7 业务解释和证据拆分

目标：

- 实现 `TargetGroupBusinessReasonBuilder`。
- 实现 `TargetGroupEvidenceBreakdownBuilder`。
- 实现 `TargetGroupReviewIssueBuilder`。

验收：

- 中文解释不出现内部字段、SQL、JSON、公式或 AI 过程性语言。
- 分域证据可以回溯 M08/M09/M02 refs。
- 复核 issue 覆盖阻塞、封顶、缺失、冲突、样本不足、seed gap。

### M10-8 repository、runner、API

目标：

- 实现 `TargetGroupRepository`。
- 实现 `TargetGroupService` 和 `run_m10_target_group`。
- 注册 v2 API。

验收：

- 事务写入 4 张表。
- 每个有效 SKU 对 9 个客群有 score 行。
- `force=false` 可按 input fingerprint 跳过。
- result hash 变化登记 M11-M16 下游失效。
- API 可查询 SKU 客群列表、客群详情、证据拆分、复核问题。

### M10-9 真实 fixture 和回归测试

目标：

- 构造 85E7Q fixture。
- 覆盖真实样例数据约束。

验收：

- 85E7Q 画质影音用户、家庭换新用户能用真实证据解释。
- 体育观看用户和游戏用户可区分。
- 性价比用户不因价格评论单独升为 main。
- 新家装修用户不因纯安装服务单独升为产品主客群。
- 儿童家庭、长辈家庭、卧室副屏无证据不高分。

## 15. 完成标准

M10 开发完成必须满足：

- migration 可升级和回滚。
- 所有新增 schema 有单元测试。
- seed loader 使用真实 `tv_core3_mvp_seed_v0_2.json.target_groups` 并覆盖 9 个 MVP 客群。
- M10 不直接读取原始四表，不直接读取 M03/M04b/M05/M06/M07 散表做业务字段判断。
- M10 不重新推导 M09 用户任务。
- 每个有效 SKU x 9 客群都有 score 行；候选、score、breakdown、review issue 分表保存。
- `only_comment`、`only_service`、`seed_hint_only`、`price_mismatch`、`value_price_mismatch`、`bedroom_size_mismatch`、`task_review_inherited`、`market_limited` 等规则可测试。
- `unknown`、空值、`-` 不被当 false。
- `profile_hash`、`feature_view_hash`、`task_score_fingerprint`、`target_group_seed_version`、`target_group_seed_hash`、`rule_version` 全部落库。
- result hash 支持增量跳过和下游失效。
- 85E7Q fixture 验收通过。
- API 返回客群列表、客群详情、证据拆分和复核问题。
- 中文业务解释不包含内部字段、SQL、JSON、公式或 AI 过程性语言。
- 测试不依赖外部 LLM。

建议运行：

```text
pytest apps/api-server/tests/core3_real_data/test_m10_*.py
pytest apps/api-server/tests/core3_real_data/test_m09_*.py apps/api-server/tests/core3_real_data/test_m10_*.py
```

## 16. 风险和回滚

| 风险 | 处理 |
| --- | --- |
| M08 M10 feature view 缺字段 | M10 输出 `missing_feature_view` 或 `missing_feature`，不绕过 M08 读散表 |
| M09 任务结果缺失 | M10 输出 `missing_task_score`，不重新推导任务 |
| seed 与详细设计不一致 | 以真实 seed 9 个 `TG_*` 客群为准，测试锁定 target group code |
| 评论词导致客群过度泛化 | 评论单域最高 weak，并要求去重评论和有效句阈值 |
| seed 默认映射直接变结论 | `seed_hint_only` 只能候选，不可 main |
| 服务/物流评论污染产品人群 | `only_service` 仅可侧面支撑新家装修用户 |
| 高端 SKU 被误判性价比主客群 | `value_price_mismatch` 降级和复核 |
| 85 寸大屏被误判卧室副屏 | `bedroom_size_mismatch` 降级和复核 |
| 市场样本不足 | `market_limited` 降级和复核 |
| 业务解释像算法日志 | business reason 单测禁止内部 tokens |
| 增量跳过错误 | input fingerprint 覆盖 M08 hash、M09 hash、seed hash、rule version |

回滚方式：

- Alembic downgrade 删除 M10 4 张表。
- API 注册可按路由开关临时关闭。
- runner 注册可移除 M10，不影响 M00-M09。
- M10 输出是下游输入，回滚前需确认 M11-M16 没有依赖当前 M10 新表；若已依赖，先停止下游 runner。

## 17. 下游依赖

M11 价值战场将消费：

- `core3_sku_target_group_score`
- `core3_sku_target_group_evidence_breakdown`
- 主/次客群、客群证据和风险。
- 任务、客群、卖点、评论和市场共同推导战场；客群不直接等于战场。

M12 候选召回将消费：

- SKU 客群向量。
- 客群关系等级。
- 客群置信度。
- 客群证据缺口。
- 候选召回不得只按客群相同召回。

M13 竞品组件评分将消费：

- 目标 SKU 和候选 SKU 的客群重合度。
- 客群关系等级差异。
- 客群证据完整度。
- 客群相似只是组件之一。

M15 高层报告将消费：

- 业务化客群解释。
- 客群证据拆分。
- 复核提示。
- 不能直接展示内部 hash、JSON、SQL、公式或 `only_comment` 等技术标签。

## 18. 下次任务

M10 完成后，下一个开发任务文档是：

```text
docs/core3_mvp/real_data_v2/development/M11_development_tasks.md
```

M11 需要基于 M09 用户任务、M10 目标客群、M08 卖点/评论/市场画像继续推导价值战场，不能提前在 M10 中生成战场结论。
