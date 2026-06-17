# M12 候选池召回开发任务

## 1. 模块目标

M12 的开发目标是围绕目标 SKU 生成可解释的竞品候选池。M12 只回答“哪些 SKU 值得进入后续竞品评分，为什么进入候选池”，不回答“最终三个竞品是谁”，也不输出最终排序。

M12 要从 M08-M11.5 已经形成的 SKU 画像、用户任务、目标客群、价值战场和战场内卖点价值中抽取目标召回锚点，再从全量清洗 SKU 中按多入口召回候选，最后输出目标-候选 pair、召回理由、M13 可消费的特征快照和复核问题。

M12 要解决的工程问题：

1. 将“候选召回”和“竞品评分/选择”拆开，避免直接在召回阶段输出核心三竞品。
2. 支持同品牌候选。当前 205 样例全部为海信，海信 SKU 可以互为竞品，不能按品牌内外过滤。
3. 使用多入口召回，而不是单一价格、尺寸、卖点或评论入口。
4. 保留同一候选的所有召回入口和关系类型，不能只保留最高分理由。
5. 输出 pair 级特征快照，M13 不需要重新从 M07-M11.5 拼接候选特征。
6. 对候选池过小、过大、单一来源、仅服务信号、缺市场证据、缺语义证据等情况生成复核问题。
7. 对 85E7Q `TV00029115` 这类有量价、参数、评论但无结构化卖点的目标，仍能通过参数、评论、市场、战场和卖点价值摘要召回候选。
8. 生成中文业务召回理由，能被 M15 转成领导可看的“为什么进入候选池”的推导，不暴露 SQL、UUID、JSON、内部字段或 AI 过程文案。

M12 必须固化以下边界：

- M12 不计算最终竞品分，M13 负责。
- M12 不选择核心三竞品，M14 负责。
- M12 不生成高层报告结论，M15 负责。
- M12 不直接读取原始 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data`。
- M12 不重新推导任务、客群、战场或卖点价值。
- M12 不重新计算 M11.5 的 PSI、SSI、SAI、CPI。
- M12 不按品牌排除候选。
- M12 不因为结构化卖点缺失就剔除 SKU。
- M12 不把候选池当成 TopN 排序。
- M12 不把单一评论、单一服务信号或单一低置信客群作为强召回。
- M12 不把 `recall_priority_score` 展示为最终竞品分。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M12 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M12_candidate_recall_requirements.md` |
| M12 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M12_candidate_recall_design.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M07 任务 | `docs/core3_mvp/real_data_v2/development/M07_development_tasks.md` |
| M08 任务 | `docs/core3_mvp/real_data_v2/development/M08_development_tasks.md` |
| M09 任务 | `docs/core3_mvp/real_data_v2/development/M09_development_tasks.md` |
| M10 任务 | `docs/core3_mvp/real_data_v2/development/M10_development_tasks.md` |
| M11 任务 | `docs/core3_mvp/real_data_v2/development/M11_development_tasks.md` |
| M11.5 任务 | `docs/core3_mvp/real_data_v2/development/M11_5_development_tasks.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 方法论 | `cankao/CatForge_竞品生成SOP_详细指导_v1.md` |
| SOP 参考模块 | `cankao/catforge_sop_md/modules/M12_候选池召回模块.md` |
| UI 规范 | `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md` |

编码前必须确认：

- M01 已输出 `core3_clean_sku`，且目标和候选 SKU 均可从清洗 SKU 主数据定位。
- M02 已输出可回溯 evidence，M12 可以保存 evidence refs 或明确缺失原因。
- M07 已输出 `core3_sku_market_profile`、`core3_comparable_pool_baseline`、`core3_market_pool_member` 或由 M08 汇总的等价市场/可比池视图。
- M08 已输出 `core3_sku_signal_profile`、`core3_sku_signal_evidence_matrix`、`core3_sku_downstream_feature_view where for_module='M12'`。
- M09 已输出 `core3_sku_task_score`。
- M10 已输出 `core3_sku_target_group_score`。
- M11 已输出 `core3_sku_battlefield_score` 和 `core3_sku_battlefield_portfolio`。
- M11.5 已输出 `core3_sku_claim_value_layer` 和 `core3_sku_battlefield_claim_value_summary`。
- M11.5 的 `m12_recall_hint_json`、`premium_claim_codes_json`、`competitive_claim_codes_json`、`basic_claim_codes_json`、`weak_claim_codes_json`、`insufficient_claim_codes_json` 可供 M12 消费。
- INFRA 已提供 run context、hash 工具、current 版本约定、runner 协议、复核 issue 约定和测试 fixture 基础。

## 3. 本次范围

本次开发任务拆分覆盖 M12 后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 5 张 M12 输出表、索引、唯一键、外键和 current 版本约束 |
| model/schema | 新增 run、pool、reason、feature snapshot、review issue、runner summary 和 API response contract |
| 输入读取 | 读取目标和候选 M08 画像、M07 市场、M09 任务、M10 客群、M11 战场、M11.5 卖点价值 |
| 目标锚点 | 生成目标主/次/机会战场、任务、客群、卖点价值、尺寸、价格、平台和市场锚点 |
| 候选全集 | 从 M01/M08 构建基础候选全集，不按品牌排除 |
| 多入口召回 | 实现 comparable_pool、battlefield、task、audience、claim_value、market_pressure、scenario_service 七个入口 |
| 关系类型 | 输出 direct_fight、price_volume_pressure、configuration_pressure、premium_benchmark、potential_downward_pressure、upgrade_substitute、downgrade_substitute、scenario_substitute、service_reference |
| pair 合并 | 同一 target-candidate pair 合并全部召回入口、关系类型、证据和中文理由 |
| 优先分 | 计算 `recall_priority_score`，仅用于候选池收敛，不作为最终竞品分 |
| 强度封顶 | 输出 strong/medium/weak/review_only，并处理仅服务、仅评论、无市场、无语义等封顶 |
| 规模控制 | 当前 35 型号样例下目标候选 8-20 合理，少于 3 或超过 25 复核 |
| M13 快照 | 输出 `core3_candidate_feature_snapshot`，让 M13 直接消费 pair 特征 |
| 复核问题 | 输出 empty_pool、too_small_pool、single_source_pool、only_service_signal 等复核问题 |
| 增量失效 | 用目标和候选 profile hash、市场 hash、任务/客群/战场/卖点价值 fingerprint、rule version 控制重算 |
| runner/API | 提供 M12 运行入口、运行摘要、候选池审计和单候选召回路径 API |
| 测试 | 单元、repository、service、API、增量、边界、85E7Q fixture |

本次不做：

- 不实现 M13 组件评分。
- 不实现 M14 三槽位选择。
- 不实现 M15 报告页。
- 不实现 M16 全链路编排。
- 不实现前端页面。
- 不部署到 205。
- 不修改 M07-M11.5 上游结果。
- 不在 M12 中补做清洗、参数抽取、评论抽取或卖点价值分层。
- 不对旧 `core3_mvp` 粗粒度页面做改造。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/candidate_recall_schemas.py
apps/api-server/app/services/core3_real_data/candidate_recall_repositories.py
apps/api-server/app/services/core3_real_data/candidate_target_anchor_builder.py
apps/api-server/app/services/core3_real_data/candidate_universe_builder.py
apps/api-server/app/services/core3_real_data/candidate_pair_feature_loader.py
apps/api-server/app/services/core3_real_data/candidate_comparable_pool_recaller.py
apps/api-server/app/services/core3_real_data/candidate_battlefield_recaller.py
apps/api-server/app/services/core3_real_data/candidate_task_recaller.py
apps/api-server/app/services/core3_real_data/candidate_audience_recaller.py
apps/api-server/app/services/core3_real_data/candidate_claim_value_recaller.py
apps/api-server/app/services/core3_real_data/candidate_market_pressure_recaller.py
apps/api-server/app/services/core3_real_data/candidate_scenario_service_recaller.py
apps/api-server/app/services/core3_real_data/candidate_recall_reason_merger.py
apps/api-server/app/services/core3_real_data/candidate_recall_priority_scorer.py
apps/api-server/app/services/core3_real_data/candidate_recall_strength_capper.py
apps/api-server/app/services/core3_real_data/candidate_pool_controller.py
apps/api-server/app/services/core3_real_data/candidate_feature_snapshot_builder.py
apps/api-server/app/services/core3_real_data/candidate_recall_business_reason_builder.py
apps/api-server/app/services/core3_real_data/candidate_recall_review_issue_builder.py
apps/api-server/app/services/core3_real_data/candidate_recall_invalidation_publisher.py
apps/api-server/app/services/core3_real_data/candidate_recall_service.py
apps/api-server/app/services/core3_real_data/candidate_recall_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `candidate_recall_schemas.py` | M12 枚举、typed contracts、runner summary、API internal schema |
| `candidate_recall_repositories.py` | 读取上游 current 结果，写入五张 M12 输出表 |
| `candidate_target_anchor_builder.py` | 从目标 SKU 上游结果生成召回锚点 |
| `candidate_universe_builder.py` | 构建候选基础全集，不按品牌排除 |
| `candidate_pair_feature_loader.py` | 加载目标-候选 pair 所需 M07-M11.5 特征 |
| `candidate_comparable_pool_recaller.py` | 可比池入口召回 |
| `candidate_battlefield_recaller.py` | 价值战场入口召回 |
| `candidate_task_recaller.py` | 用户任务入口召回 |
| `candidate_audience_recaller.py` | 目标客群入口召回 |
| `candidate_claim_value_recaller.py` | 战场内卖点价值入口召回 |
| `candidate_market_pressure_recaller.py` | 市场压力入口召回 |
| `candidate_scenario_service_recaller.py` | 场景与服务入口召回 |
| `candidate_recall_reason_merger.py` | reason 去重合并为 target-candidate pair |
| `candidate_recall_priority_scorer.py` | 计算召回组件分和优先分 |
| `candidate_recall_strength_capper.py` | 应用 strong/medium/weak/review_only 封顶 |
| `candidate_pool_controller.py` | 候选池规模控制和过小/过大复核 |
| `candidate_feature_snapshot_builder.py` | 生成 M13 可消费的 pair 特征快照 |
| `candidate_recall_business_reason_builder.py` | 生成中文业务召回理由 |
| `candidate_recall_review_issue_builder.py` | 生成运行级、目标级、pair 级复核问题 |
| `candidate_recall_invalidation_publisher.py` | M12 变化时登记 M13-M16 下游失效 |
| `candidate_recall_service.py` | M12 编排 service |
| `candidate_recall_runner.py` | M12 runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0020_core3_real_data_candidate_recall.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0020_core3_real_data_candidate_recall.py` | 新增 M12 五张表、索引、唯一键、外键和 downgrade |
| `core3_real_data.py` schema | 导出 M12 run、pool、reason、snapshot、review issue response |
| `core3_real_data.py` API | 增加 M12 v2 内部运行和审计 API |
| `constants.py` | 补 M12 recall source、relation type、strength、status、issue type |
| `runner.py` | 注册 M12 runner，不改变 M00-M11.5 逻辑 |
| `conftest.py` | 增加 M12 目标、候选、上游摘要、85E7Q fixture |

如果 Alembic 当前最新编号不是 `0019`，编码时按最新编号顺延，但 migration 内容仍只能包含 M12 表、索引、约束。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m12_candidate_recall_schemas.py
apps/api-server/tests/core3_real_data/test_m12_target_anchor_builder.py
apps/api-server/tests/core3_real_data/test_m12_candidate_universe_builder.py
apps/api-server/tests/core3_real_data/test_m12_pair_feature_loader.py
apps/api-server/tests/core3_real_data/test_m12_comparable_pool_recaller.py
apps/api-server/tests/core3_real_data/test_m12_battlefield_recaller.py
apps/api-server/tests/core3_real_data/test_m12_task_recaller.py
apps/api-server/tests/core3_real_data/test_m12_audience_recaller.py
apps/api-server/tests/core3_real_data/test_m12_claim_value_recaller.py
apps/api-server/tests/core3_real_data/test_m12_market_pressure_recaller.py
apps/api-server/tests/core3_real_data/test_m12_scenario_service_recaller.py
apps/api-server/tests/core3_real_data/test_m12_reason_merger.py
apps/api-server/tests/core3_real_data/test_m12_priority_scorer.py
apps/api-server/tests/core3_real_data/test_m12_strength_capper.py
apps/api-server/tests/core3_real_data/test_m12_pool_controller.py
apps/api-server/tests/core3_real_data/test_m12_feature_snapshot_builder.py
apps/api-server/tests/core3_real_data/test_m12_business_reason_builder.py
apps/api-server/tests/core3_real_data/test_m12_review_issue_builder.py
apps/api-server/tests/core3_real_data/test_m12_repositories.py
apps/api-server/tests/core3_real_data/test_m12_runner.py
apps/api-server/tests/core3_real_data/test_m12_api.py
apps/api-server/tests/core3_real_data/test_m12_85e7q_fixture.py
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

不得在 M12 中改动或重写：

- M00-M11.5 已有 migration 的业务含义。
- M01 清洗 SKU 逻辑。
- M07 市场画像和可比池生成逻辑。
- M08 SKU 综合画像逻辑。
- M09 用户任务逻辑。
- M10 目标客群逻辑。
- M11 价值战场逻辑。
- M11.5 战场内卖点价值分层逻辑。
- M13 组件评分逻辑。
- M14 三槽位选择逻辑。
- M15 报告逻辑。

不得新增以下捷径：

- 直接读取原始四表来补召回结论。
- 写死 85E7Q 的候选结果。
- 只用价格或尺寸做候选池。
- 按品牌过滤掉海信候选。
- 把服务信号候选写成产品核心强候选。
- 把 `recall_priority_score` 命名或展示为竞品分。
- 丢弃同一个候选的多个召回入口。
- 在业务理由里展示 UUID、SQL、JSON、英文字段名或 AI 过程话术。

## 6. 数据库迁移任务

### 6.1 新增表

迁移文件建议为：

```text
apps/api-server/alembic/versions/0020_core3_real_data_candidate_recall.py
```

新增五张表：

```text
core3_candidate_recall_run
core3_candidate_pool
core3_candidate_recall_reason
core3_candidate_feature_snapshot
core3_candidate_recall_review_issue
```

### 6.2 `core3_candidate_recall_run`

用途：记录一次目标 SKU 候选召回运行，回答“本次从多少 SKU 中召回了多少候选，状态如何，是否需要复核”。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `project_id` | text/uuid | 必填 |
| `category_code` | text | 必填，MVP 为 `TV` |
| `batch_id` | text/uuid | 必填 |
| `run_id` | text/uuid | 必填 |
| `module_run_id` | text/uuid | 必填 |
| `target_sku_code` | text | 必填 |
| `target_model_name` | text | 必填 |
| `target_brand_name` | text | 可空 |
| `analysis_window_start` | text | 首版为 `26W01` |
| `analysis_window_end` | text | 首版为 `26W23` |
| `candidate_universe_count` | integer | 必填 |
| `candidate_selected_count` | integer | 必填 |
| `strong_candidate_count` | integer | 必填 |
| `medium_candidate_count` | integer | 必填 |
| `weak_candidate_count` | integer | 必填 |
| `review_candidate_count` | integer | 必填 |
| `blocked_reason` | text | 可空 |
| `recall_status` | text | success/limited/review_required/blocked/failed |
| `recall_summary_cn` | text | 中文摘要 |
| `target_anchor_json` | jsonb | 目标召回锚点 |
| `pool_control_json` | jsonb | 候选池规模控制 |
| `quality_flags_json` | jsonb | 运行级质量标记 |
| `target_profile_hash` | text | M08 目标画像 hash |
| `market_fingerprint` | text | M07 市场画像/可比池 hash |
| `task_fingerprint` | text | M09 任务摘要 |
| `audience_fingerprint` | text | M10 客群摘要 |
| `battlefield_fingerprint` | text | M11 战场摘要 |
| `claim_value_fingerprint` | text | M11.5 卖点价值摘要 |
| `candidate_universe_hash` | text | 候选全集 hash |
| `evidence_revision` | text | evidence 状态版本 |
| `rule_version` | text | 规则版本 |
| `input_fingerprint` | text | 输入 hash |
| `result_hash` | text | 输出 hash |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

唯一索引：

```sql
create unique index uq_core3_candidate_recall_run_current
on core3_candidate_recall_run(project_id, category_code, batch_id, target_sku_code, rule_version)
where is_current = true;
```

查询索引：

- `(project_id, category_code, batch_id, target_sku_code, recall_status)`
- `(project_id, category_code, batch_id, recall_status, created_at desc)`
- `(project_id, category_code, batch_id, input_fingerprint, rule_version)`

### 6.3 `core3_candidate_pool`

用途：保存目标-候选 SKU pair，是 M13 的主输入。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `candidate_recall_run_id` | uuid/text | 外键到 run |
| `project_id` | text/uuid | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | text/uuid | 必填 |
| `run_id` | text/uuid | 必填 |
| `module_run_id` | text/uuid | 必填 |
| `target_sku_code` | text | 必填 |
| `target_model_name` | text | 必填 |
| `target_brand_name` | text | 可空 |
| `candidate_sku_code` | text | 必填 |
| `candidate_model_name` | text | 必填 |
| `candidate_brand_name` | text | 可空 |
| `same_brand_flag` | boolean | 必填，只标记不排除 |
| `model_family_key` | text | 可空 |
| `hard_filter_pass` | boolean | 必填 |
| `hard_filter_reason` | text | 可空 |
| `relation_types_json` | jsonb | 全部关系类型 |
| `candidate_role_hints_json` | jsonb | direct/pressure/benchmark/potential/configuration/scenario/service |
| `recall_sources_json` | jsonb | 全部召回入口 |
| `matched_battlefields_json` | jsonb | 战场重合和差异 |
| `matched_tasks_json` | jsonb | 任务重合和替代链 |
| `matched_audiences_json` | jsonb | 客群重合和置信度 |
| `matched_claim_layers_json` | jsonb | 战场内卖点层级重合和差异 |
| `price_relation` | text | lower/similar/higher/unknown |
| `price_gap_pct` | numeric | 候选相对目标价格差 |
| `target_price_wavg` | numeric | 可空 |
| `candidate_price_wavg` | numeric | 可空 |
| `size_relation` | text | same/adjacent_larger/adjacent_smaller/larger_cross/smaller_cross/unknown |
| `target_size_inch` | numeric | 可空 |
| `candidate_size_inch` | numeric | 可空 |
| `platform_overlap_score` | numeric | 必填 |
| `market_relation_json` | jsonb | 销量、销额、趋势、平台压力 |
| `base_comparability_score` | numeric | 必填 |
| `battlefield_recall_score` | numeric | 必填 |
| `task_audience_recall_score` | numeric | 必填 |
| `claim_value_recall_score` | numeric | 必填 |
| `market_pressure_recall_score` | numeric | 必填 |
| `evidence_quality_score` | numeric | 必填 |
| `recall_priority_score` | numeric | 召回优先分，不是竞品分 |
| `recall_strength` | text | strong/medium/weak/review_only |
| `sample_status` | text | sufficient/limited/insufficient/unknown |
| `data_quality_flags_json` | jsonb | 数据质量风险 |
| `business_reason_cn` | text | 中文业务召回理由 |
| `business_reason_short_cn` | text | 高层页短理由 |
| `review_required` | boolean | 必填 |
| `review_reason` | text | 可空 |
| `evidence_ids` | jsonb/array | 代表 evidence |
| `missing_evidence_reasons_json` | jsonb | 缺失原因 |
| `target_profile_hash` | text | 必填 |
| `candidate_profile_hash` | text | 必填 |
| `pair_feature_hash` | text | 必填 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

唯一索引：

```sql
create unique index uq_core3_candidate_pool_current
on core3_candidate_pool(
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

- `(project_id, category_code, batch_id, target_sku_code, recall_strength, recall_priority_score desc)`
- `(project_id, category_code, batch_id, candidate_sku_code)`
- `(project_id, category_code, batch_id, review_required, review_reason)`
- GIN `candidate_role_hints_json`
- GIN `relation_types_json`

### 6.4 `core3_candidate_recall_reason`

用途：保存每个 pair 的多条召回理由。一个入池 pair 至少有一条 reason。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `candidate_pool_id` | uuid/text | 外键到 pool |
| `candidate_recall_run_id` | uuid/text | 外键到 run |
| `project_id` | text/uuid | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | text/uuid | 必填 |
| `run_id` | text/uuid | 必填 |
| `module_run_id` | text/uuid | 必填 |
| `target_sku_code` | text | 必填 |
| `candidate_sku_code` | text | 必填 |
| `reason_type` | text | comparable_pool/battlefield/task/audience/claim_value/market_pressure/scenario_service |
| `relation_type` | text | 关系类型 |
| `source_module` | text | M07/M08/M09/M10/M11/M11.5 |
| `source_table` | text | 可空 |
| `source_record_ids_json` | jsonb | 来源记录 |
| `support_score` | numeric | 支撑分 |
| `support_level` | text | strong/medium/weak/missing |
| `confidence` | numeric | 置信度 |
| `cap_applied` | text | 可空 |
| `business_reason_cn` | text | 中文理由 |
| `source_payload_json` | jsonb | 结构化来源 |
| `risk_flags_json` | jsonb | 风险 |
| `evidence_ids` | jsonb/array | evidence |
| `missing_evidence_reasons_json` | jsonb | 缺失原因 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

唯一索引：

```sql
create unique index uq_core3_candidate_recall_reason_current
on core3_candidate_recall_reason(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  candidate_sku_code,
  reason_type,
  relation_type,
  source_module,
  result_hash,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, target_sku_code, candidate_sku_code)`
- `(project_id, category_code, batch_id, reason_type, relation_type, support_level)`
- GIN `evidence_ids`

### 6.5 `core3_candidate_feature_snapshot`

用途：保存 M13 评分所需 pair 特征快照。M13 可以归一化这些 raw 值，但不能绕过 M12 重新召回候选。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `candidate_pool_id` | uuid/text | 外键到 pool |
| `candidate_recall_run_id` | uuid/text | 外键到 run |
| `project_id` | text/uuid | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | text/uuid | 必填 |
| `run_id` | text/uuid | 必填 |
| `module_run_id` | text/uuid | 必填 |
| `target_sku_code` | text | 必填 |
| `candidate_sku_code` | text | 必填 |
| `battlefield_overlap_json` | jsonb | M11/M12 |
| `task_overlap_json` | jsonb | M09/M12 |
| `audience_overlap_json` | jsonb | M10/M12 |
| `claim_value_overlap_json` | jsonb | M11.5/M12 |
| `price_feature_json` | jsonb | M07/M12 |
| `channel_feature_json` | jsonb | M07/M12 |
| `size_feature_json` | jsonb | M03/M08/M12 |
| `market_feature_json` | jsonb | M07/M12 |
| `param_feature_json` | jsonb | M03/M08/M12 |
| `quality_feature_json` | jsonb | M08/M12 |
| `m13_component_input_json` | jsonb | M13 直接输入 |
| `evidence_ids` | jsonb/array | 代表 evidence |
| `feature_hash` | text | 快照 hash |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

`m13_component_input_json` 必须覆盖：

- price_similarity
- price_advantage
- channel_overlap
- size_similarity
- param_similarity
- claim_similarity
- task_similarity
- target_group_similarity
- battlefield_similarity
- sales_strength
- param_superiority
- claim_superiority
- price_drop_signal
- recent_sales_growth
- evidence_quality

唯一索引：

```sql
create unique index uq_core3_candidate_feature_snapshot_current
on core3_candidate_feature_snapshot(
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

- `(project_id, category_code, batch_id, target_sku_code, candidate_sku_code)`
- `(project_id, category_code, batch_id, feature_hash)`
- GIN `m13_component_input_json`

### 6.6 `core3_candidate_recall_review_issue`

用途：保存 M12 运行级、目标级、pair 级和 snapshot 级复核问题。

关键字段：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `candidate_recall_run_id` | uuid/text | 外键到 run |
| `candidate_pool_id` | uuid/text | 可空 |
| `project_id` | text/uuid | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | text/uuid | 必填 |
| `run_id` | text/uuid | 必填 |
| `module_run_id` | text/uuid | 必填 |
| `target_sku_code` | text | 必填 |
| `candidate_sku_code` | text | 可空 |
| `issue_scope` | text | run/target/pair/reason/snapshot |
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
missing_target_profile
missing_target_battlefield
empty_pool
too_small_pool
too_large_pool
single_source_pool
all_candidates_insufficient_sample
no_market_evidence
no_semantic_evidence
only_service_signal
weak_audience_signal
structured_claim_missing
model_family_overcrowded
feature_snapshot_missing
duplicate_reason
feature_missing
unknown
```

表达式唯一索引：

```sql
create unique index uq_core3_candidate_recall_review_issue_current
on core3_candidate_recall_review_issue(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
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
- `(project_id, category_code, batch_id, target_sku_code, candidate_sku_code)`

### 6.7 回滚策略

`downgrade()` 只删除 M12 五张表和相关索引，不触碰 M00-M11.5 表。

如果 M13-M16 已消费 M12 结果，回滚前必须先标记下游结果失效，避免 M13/M14 悬空引用。

## 7. model/schema 任务

### 7.1 枚举

在 `candidate_recall_schemas.py` 或 `constants.py` 中定义：

```python
RECALL_SOURCE_VALUES = (
    "comparable_pool",
    "battlefield",
    "task",
    "audience",
    "claim_value",
    "market_pressure",
    "scenario_service",
)
```

其他枚举：

| 枚举 | 值 |
| --- | --- |
| relation_type | direct_fight/price_volume_pressure/configuration_pressure/premium_benchmark/potential_downward_pressure/upgrade_substitute/downgrade_substitute/scenario_substitute/service_reference |
| recall_strength | strong/medium/weak/review_only |
| price_relation | lower/similar/higher/unknown |
| size_relation | same/adjacent_larger/adjacent_smaller/larger_cross/smaller_cross/unknown |
| recall_status | success/limited/review_required/blocked/failed |
| sample_status | sufficient/limited/insufficient/unknown |
| support_level | strong/medium/weak/missing |
| issue_scope | run/target/pair/reason/snapshot |
| issue_level | warning/review/blocker |

### 7.2 typed contracts

需要定义：

- `CandidateRecallRunContext`
- `CandidateRecallTargetScope`
- `TargetRecallAnchor`
- `CandidateUniverseItem`
- `PairFeatureBundle`
- `CandidateRecallReasonDraft`
- `CandidatePairDraft`
- `CandidatePoolRecord`
- `CandidateFeatureSnapshotRecord`
- `CandidateRecallReviewIssueRecord`
- `CandidateRecallRunSummary`

所有 pair 级 contract 必须包含：

- `project_id`
- `category_code`
- `batch_id`
- `target_sku_code`
- `candidate_sku_code`
- `target_profile_hash`
- `candidate_profile_hash`
- `rule_version`
- `input_fingerprint`
- `result_hash`

### 7.3 目标锚点 schema

`TargetRecallAnchor` 必须包含：

- `primary_battlefields`
- `secondary_battlefields`
- `opportunity_battlefields`
- `primary_tasks`
- `secondary_tasks`
- `primary_audiences`
- `secondary_audiences`
- `focus_claims`
- `basic_claims`
- `weak_or_insufficient_claims`
- `size_inch`
- `size_segment`
- `price_wavg`
- `price_band`
- `platforms`
- `market_window`
- `market_strength_summary`
- `risk_flags`
- `missing_domains`

### 7.4 API schema

在 `apps/api-server/app/schemas/core3_real_data.py` 增加：

- `RunM12CandidateRecallRequest`
- `M12CandidateRecallRunResponse`
- `M12CandidatePoolListResponse`
- `M12CandidatePoolItemResponse`
- `M12CandidateRecallReasonResponse`
- `M12CandidateFeatureSnapshotResponse`
- `M12CandidateAuditResponse`
- `M12CandidateRecallReviewIssueResponse`

API response 中内部 code 可以保留为 hidden key，但必须提供中文展示字段：

- `relation_type_cn`
- `recall_strength_cn`
- `recall_source_cn`
- `business_reason_cn`
- `business_reason_short_cn`
- `candidate_role_hint_cn`
- `sample_status_cn`
- `review_reason_cn`

## 8. repository 任务

### 8.1 输入读取边界

`CandidateRecallRepository` 允许读取：

```text
core3_clean_sku
core3_evidence_atom
core3_sku_market_profile
core3_comparable_pool_baseline
core3_market_pool_member
core3_sku_signal_profile
core3_sku_signal_evidence_matrix
core3_sku_downstream_feature_view
core3_sku_task_score
core3_sku_target_group_score
core3_sku_battlefield_score
core3_sku_battlefield_portfolio
core3_sku_claim_value_layer
core3_sku_battlefield_claim_value_summary
```

不得直接读取：

```text
week_sales_data
attribute_data
selling_points_data
comment_data
M13 scoring tables
M14 selection tables
M15 report tables
```

### 8.2 读取方法

需要实现：

```python
get_clean_sku(project_id, category_code, batch_id, sku_code) -> CleanSku | None
list_clean_skus(project_id, category_code, batch_id) -> list[CleanSku]
get_m12_feature_view(project_id, category_code, batch_id, sku_code) -> M12FeatureView | None
get_signal_profile(project_id, category_code, batch_id, sku_code) -> SignalProfile | None
get_market_profile(project_id, category_code, batch_id, sku_code) -> MarketProfile | None
get_comparable_pool_members(project_id, category_code, batch_id, target_sku_code) -> list[PoolMember]
get_task_scores(project_id, category_code, batch_id, sku_code) -> list[TaskScore]
get_target_group_scores(project_id, category_code, batch_id, sku_code) -> list[TargetGroupScore]
get_battlefield_scores(project_id, category_code, batch_id, sku_code) -> list[BattlefieldScore]
get_battlefield_portfolio(project_id, category_code, batch_id, sku_code) -> BattlefieldPortfolio | None
get_claim_value_layers(project_id, category_code, batch_id, sku_code) -> list[ClaimValueLayer]
get_claim_value_summary(project_id, category_code, batch_id, sku_code) -> list[ClaimValueSummary]
get_signal_evidence_matrix(project_id, category_code, batch_id, sku_code) -> EvidenceMatrix | None
```

### 8.3 写入方法

需要实现：

```python
upsert_recall_run(run: CandidateRecallRunRecord) -> None
upsert_candidate_pool_items(items: list[CandidatePoolRecord]) -> None
upsert_recall_reasons(items: list[CandidateRecallReasonRecord]) -> None
upsert_feature_snapshots(items: list[CandidateFeatureSnapshotRecord]) -> None
upsert_review_issues(items: list[CandidateRecallReviewIssueRecord]) -> None
mark_previous_versions_not_current(scope: CandidateRecallWriteScope) -> None
```

写入规则：

- 目标级运行、pair、reason、snapshot、review issue 使用同一目标级 `input_fingerprint`。
- pair 和 snapshot 另有 `pair_feature_hash` 或 `feature_hash`。
- `result_hash` 相同不得重复插入业务版本。
- `result_hash` 变化时旧记录 `is_current=false`，新记录写入。
- 同一事务内写 run、pool、reason、snapshot、issue，避免有 pair 无 reason 或无 snapshot 的半成品。
- 如果 snapshot 生成失败，pair 可以保留但必须 `review_required=true` 并写 `feature_snapshot_missing`。

### 8.4 查询方法

API 需要：

```python
get_recall_run(project_id, category_code, batch_id, target_sku_code, run_id) -> CandidateRecallRunRecord | None
list_candidate_pool(project_id, category_code, batch_id, target_sku_code, filters) -> list[CandidatePoolRecord]
get_candidate_pool_item(project_id, category_code, batch_id, target_sku_code, candidate_sku_code) -> CandidatePoolRecord | None
list_recall_reasons(project_id, category_code, batch_id, target_sku_code, candidate_sku_code) -> list[CandidateRecallReasonRecord]
get_feature_snapshot(project_id, category_code, batch_id, target_sku_code, candidate_sku_code) -> CandidateFeatureSnapshotRecord | None
list_review_issues(project_id, category_code, batch_id, target_sku_code, filters) -> list[CandidateRecallReviewIssueRecord]
```

## 9. service 任务

### 9.1 编排服务

`CandidateRecallService` 负责主流程：

```python
class CandidateRecallService:
    def run(self, request: CandidateRecallRunRequest) -> CandidateRecallRunSummary:
        targets = self.resolve_targets(request)
        for target_sku_code in targets:
            self.run_for_target(request, target_sku_code)
        return self.build_summary()
```

处理顺序：

1. 读取 run context。
2. 读取目标 M08 画像和 M11 战场组合。
3. 缺 M08 或 M11 时写 blocked run 和 blocker issue，停止该目标。
4. 读取目标 M07、M09、M10、M11.5 当前结果。
5. 生成目标召回锚点。
6. 从 M01/M08 构建候选基础全集。
7. 对每个候选加载 M07-M11.5 pair 特征。
8. 执行七个召回入口。
9. 合并 reason 为 pair。
10. 计算价格关系、尺寸关系、平台重合、市场关系。
11. 计算召回优先分和召回强度。
12. 应用强度封顶。
13. 应用候选池规模控制。
14. 生成中文业务理由。
15. 生成 M13 feature snapshot。
16. 生成复核问题。
17. 版本化写入。
18. 发布 M13-M16 失效事件。

### 9.2 目标锚点生成

`TargetAnchorBuilder` 输入：

- M08 target feature view。
- M07 market profile。
- M09 task score。
- M10 target group score。
- M11 battlefield portfolio。
- M11.5 claim value summary。

锚点字段：

| 锚点 | 来源 | 用途 |
| --- | --- | --- |
| 主战场 | M11 portfolio | 强召回主条件 |
| 次战场 | M11 portfolio | 辅助召回 |
| 机会战场 | M11 battlefield score | 扩展召回，需要市场或价格压力 |
| 主任务 | M09 | 任务重合 |
| 次任务 | M09 | 场景替代 |
| 主客群 | M10 | 客群重合 |
| 重点卖点 | M11.5 summary 中绩效/溢价/门槛卖点 | 卖点价值召回 |
| 尺寸 | M08/M03 标准尺寸 | 同尺寸、相邻尺寸 |
| 价格 | M07 加权均价和价格带 | 同价、低价、高价、潜在下探 |
| 平台 | M07 平台份额 | 平台重合 |
| 市场 | M07 销量、销额、趋势 | 压力召回 |

缺失处理：

- 缺目标 M08：blocked。
- 缺目标 M11：blocked。
- 缺 M12 feature view：review_required，可回退到 profile 摘要。
- 缺 M07：市场入口不可用，强度最高 medium。
- 缺 M09/M10：对应入口不可用。
- 缺 M11.5：卖点价值入口不可用，但可继续弱召回。

### 9.3 候选全集构建

`CandidateUniverseBuilder` 硬过滤：

1. `category_code='TV'` 或清洗品类已映射到 TV。
2. `candidate_sku_code != target_sku_code`。
3. 候选存在 `core3_clean_sku is_current=true`。
4. 候选存在 M08 画像，或存在可解释画像缺失 issue。
5. 候选至少有一个 evidence 或一个当前上游推断结果。

不得因为以下原因直接剔除：

- 同品牌。
- 结构化卖点缺失。
- 评论不足。
- 市场证据局部缺失。
- 客群或任务低置信。

软过滤：

| 缺失 | 不可用入口 | 其他入口 |
| --- | --- | --- |
| 价格缺失 | 可比池同价、价格压力、潜在下探 | 战场、任务、客群、卖点价值仍可弱召回 |
| 尺寸缺失 | 同尺寸、相邻尺寸 | 战场、任务、客群仍可弱召回 |
| 平台缺失 | 平台重合 | 战场、任务、客群仍可弱召回 |
| 市场缺失 | 销量/销额/趋势压力 | 最高 medium |
| 语义缺失 | 任务/客群/战场/卖点价值 | 最高 weak |

### 9.4 PairFeatureLoader

`PairFeatureLoader` 要一次性加载目标和候选的：

- clean sku。
- M08 profile 和 M12 feature view。
- M07 market profile。
- M07 comparable pool membership。
- M09 task scores。
- M10 target group scores。
- M11 battlefield scores 和 portfolio。
- M11.5 claim value layer 和 summary。
- evidence refs 和 evidence quality。

输出 `PairFeatureBundle`，供七个 recaller 共享，避免每个入口重复查询。

### 9.5 七个召回入口

#### 9.5.1 可比池召回

`ComparablePoolRecaller` 来源：

- `core3_comparable_pool_baseline`
- `core3_market_pool_member`
- M08 `comparable_pool_summary`

规则：

| 条件 | 关系类型 |
| --- | --- |
| 同尺寸 + 同价位 + 平台重合 | `direct_fight` |
| 同尺寸 + 更低价 + 销量不弱 | `price_volume_pressure` |
| 相邻大尺寸 + 更高价 + 战场重合 | `upgrade_substitute` 或 `premium_benchmark` |
| 相邻小尺寸 + 更低价 + 任务重合 | `downgrade_substitute` |
| 同价位但关键参数强于目标 | `configuration_pressure` |

首版阈值：

- 平台重合度 `>= 0.30`。
- 同价位：价格差在正负 8% 内。
- 相邻价位：价格差在正负 30% 内。
- 销量不弱：候选销量分位不低于目标分位 - 0.15。
- 相邻尺寸：75/85/100 等相邻档。

#### 9.5.2 价值战场召回

`BattlefieldRecaller` 来源：

- `core3_sku_battlefield_score`
- `core3_sku_battlefield_portfolio`

规则：

| 条件 | 支撑 |
| --- | --- |
| 目标主战场 = 候选主战场 | strong |
| 目标主战场 = 候选次战场 | medium |
| 目标次战场 = 候选主战场 | medium |
| 目标机会战场 = 候选主战场，且价格或销量有压力 | medium |
| 只重合弱战场 | weak 或不召回 |

`BF_SERVICE_ASSURANCE` 不能作为产品核心正面对打主线。若服务战场是唯一重合，只能生成 `service_reference` 或 `scenario_service`，强度封顶为 `review_only`。

#### 9.5.3 用户任务召回

`TaskRecaller` 来源：

- `core3_sku_task_score`

规则：

| 条件 | 关系类型 |
| --- | --- |
| 同一主任务 | `direct_fight` 或 `scenario_substitute` |
| 目标主任务 = 候选次任务 | `scenario_substitute` |
| 任务组合相似 | `scenario_substitute` |
| 大屏换新与性价比购买替代链 | `downgrade_substitute` 或 `price_volume_pressure` |
| 高端画质影音与客厅影院观影组合 | `direct_fight` 或 `premium_benchmark` |

M12 不能从评论粗标签重新抽任务，只能使用 M09 已确认结果。

#### 9.5.4 目标客群召回

`AudienceRecaller` 来源：

- `core3_sku_target_group_score`

规则：

| 条件 | 处理 |
| --- | --- |
| 同一主客群且高置信 | medium 到 strong，但不能单独 strong |
| 目标主客群 = 候选次客群 | medium |
| 客群不同但任务和价格压力强 | 场景替代辅助 |
| 客群低置信 | reason 标记 `weak_audience_signal` |

客群入口不能独立形成 strong，必须有任务、战场、市场或卖点价值入口支撑。

#### 9.5.5 战场内卖点价值召回

`ClaimValueRecaller` 来源：

- `core3_sku_claim_value_layer`
- `core3_sku_battlefield_claim_value_summary`

规则：

| 条件 | 关系类型 |
| --- | --- |
| 同战场同绩效卖点或同溢价卖点 | `direct_fight` |
| 候选在目标弱感知卖点上更强 | `configuration_pressure` |
| 候选拥有相同门槛卖点但价格更低 | `price_volume_pressure` |
| 候选在目标主战场卖点层级整体更强且价格更高 | `premium_benchmark` |
| 高端候选卖点更强且价格趋势下探 | `potential_downward_pressure` |
| 目标或候选卖点样本不足但参数强 | weak 并复核 |

M12 不重新计算 M11.5 的 PSI、SSI、SAI、CPI，只使用 layer、score、summary、hint 和 evidence。

#### 9.5.6 市场压力召回

`MarketPressureRecaller` 来源：

- `core3_sku_market_profile`
- M08 市场摘要

规则：

| 条件 | 关系类型 |
| --- | --- |
| 同价位高销量 | `price_volume_pressure` |
| 同价位高销额 | `direct_fight` 或 `price_volume_pressure` |
| 更低价 + 销量不弱 | `price_volume_pressure` |
| 更高价 + 销额不弱 + 主战场重合 | `premium_benchmark` |
| 更高价 + 近期价格下行 + 主战场重合 | `potential_downward_pressure` |
| 相邻尺寸价格每英寸更低 | `downgrade_substitute` 或 `price_volume_pressure` |

市场口径必须保留：

- 周期：`26W01-26W23`。
- 渠道：线上。
- 平台：`专业电商`、`平台电商`。
- 价格：加权均价或最近有效均价。

不得写成 12 个月、全渠道或线下。

#### 9.5.7 场景与服务召回

`ScenarioServiceRecaller` 来源：

- M09/M10 场景任务和客群。
- M11 服务保障、家居美学、智能系统等辅助战场。
- M11.5 服务类卖点价值。

边界：

- 服务保障只作为服务侧比较或风险提示。
- 新家装修、安装服务、家居美学可以作为场景替代辅助入口。
- 仅服务信号召回时 `recall_strength='review_only'`。
- 仅场景服务召回的候选不挤占产品核心候选名额。

### 9.6 reason 合并任务

`RecallReasonMerger` 合并规则：

- 同一 `target_sku_code + candidate_sku_code + rule_version` 只生成一条当前 pool。
- `relation_types_json` 汇总全部关系类型。
- `recall_sources_json` 汇总全部召回入口。
- `matched_battlefields_json` 合并战场重合。
- `matched_tasks_json` 合并任务重合。
- `matched_audiences_json` 合并客群重合。
- `matched_claim_layers_json` 合并卖点层级重合与差异。
- `evidence_ids` 去重，最多保留代表 evidence，完整 evidence 留在 reason 级。
- `business_reason_cn` 选最重要 2-3 条理由组织成中文解释。
- `recall_priority_score` 使用综合组件分，不简单取最高入口分。

### 9.7 召回优先分任务

`RecallPriorityScorer` 首版公式：

```text
recall_priority_score =
  base_comparability_score * 0.20
  + battlefield_recall_score * 0.25
  + task_audience_recall_score * 0.15
  + claim_value_recall_score * 0.15
  + market_pressure_recall_score * 0.20
  + evidence_quality_score * 0.05
```

组件规则：

| 组件 | 首版规则 |
| --- | --- |
| `base_comparability_score` | 同品类 0.25，同尺寸 0.25，同/邻价 0.25，平台重合 0.25 |
| `battlefield_recall_score` | 主主重合 1.0，主次/次主 0.75，机会主且市场压力 0.55 |
| `task_audience_recall_score` | 任务 60%，客群 40%，低置信客群按 0.5 折减 |
| `claim_value_recall_score` | 同绩效/溢价 1.0，候选更强 0.85，同门槛 0.55，样本不足 0.30 |
| `market_pressure_recall_score` | 低价高销 1.0，同价高销 0.85，高端标杆 0.70，市场缺失 0 |
| `evidence_quality_score` | 证据域覆盖、样本充分、缺失折减 |

### 9.8 强度封顶任务

`RecallStrengthCapper` 初判：

- 命中入口数 `>=3` 且包含战场或市场入口：strong。
- 命中入口数 `>=2`：medium。
- 命中入口数 `=1`：weak。
- `recall_priority_score < 0.25`：最高 weak。
- `recall_priority_score >= 0.70` 且未触发封顶：可为 strong。

封顶规则：

| 情况 | 强度上限 |
| --- | --- |
| 仅评论入口 | weak |
| 仅服务入口 | review_only |
| 无市场证据 | medium |
| 无语义证据 | weak |
| 候选画像缺失严重 | weak |
| 客群低置信且无其他强入口 | weak |
| 结构化卖点缺失但参数/评论可补证 | 不封顶，但降低 `claim_value_recall_score` |

### 9.9 候选池规模控制任务

`CandidatePoolController` 首版规模：

| 数据规模 | 合理候选规模 |
| --- | --- |
| 当前 35 型号样例 | 8-20 个 |
| 100-500 SKU | 15-40 个 |
| 1000+ SKU | 20-80 个 |

当前 35 型号样例规则：

- 候选少于 3：`too_small_pool`。
- 候选 3-7：`limited`，可继续 M13。
- 候选 8-20：合理。
- 候选超过 25：检查过滤过松或同型号族过密。
- 不能为了凑够 8 个候选伪造弱理由。

收敛顺序：

1. 保留所有 strong 候选。
2. 每个目标主战场至少保留 direct、pressure、benchmark/potential 类型候选。
3. 保留价格/销量压力明显候选。
4. 保留高端标杆或潜在下探候选。
5. 弱召回只保留有明确业务增量的候选。
6. 仅服务信号候选进入复核，不挤占产品核心候选名额。

### 9.10 中文业务理由任务

`CandidateRecallBusinessReasonBuilder` 生成：

- `business_reason_cn`
- `business_reason_short_cn`
- reason 级 `business_reason_cn`
- review issue 中文说明

模板：

正面对打：

```text
该候选与目标同处{主战场中文名}，尺寸同段、价格带接近，且在{卖点中文名}等核心卖点上具备同类支撑，适合作为正面对打候选。
```

价格/销量挤压：

```text
该候选承接相近的{任务中文名}需求，价格低于目标且销量表现不弱，可能在同平台形成价格/销量挤压。
```

配置拦截：

```text
该候选在{参数或卖点中文名}上强于目标，价格又处在相邻区间，适合作为配置拦截候选。
```

高端标杆：

```text
该候选在{战场中文名}上与目标重合，但价格和卖点价值更高，可作为上探标杆观察。
```

潜在下探：

```text
该候选当前价格高于目标，但与目标主战场重合且存在价格下行信号，需要关注其下探后对目标价格空间的挤压。
```

服务参考：

```text
该候选主要因服务或安装体验信号进入参考池，只适合做服务侧对比，不应直接作为产品核心竞品。
```

85E7Q 结构化卖点缺失说明：

```text
目标缺结构化卖点记录，本次以标准参数、评论验证和市场表现补充判断，卖点价值相关召回置信度已降级。
```

禁止文案：

- “目标宣传 Mini LED 卖点强”，除非 M04a/M04b 有真实宣传 evidence。
- “AI 判断该候选是竞品”。
- “recall_priority_score 为 0.72，因此是核心竞品”。

### 9.11 M13 快照任务

`CandidateFeatureSnapshotBuilder` 对每个入池 pair 生成一条 current snapshot。

必须输出：

- `battlefield_overlap_json`
- `task_overlap_json`
- `audience_overlap_json`
- `claim_value_overlap_json`
- `price_feature_json`
- `channel_feature_json`
- `size_feature_json`
- `market_feature_json`
- `param_feature_json`
- `quality_feature_json`
- `m13_component_input_json`

M13 直接使用 `m13_component_input_json`，不能再从全量 SKU 召回候选。

### 9.12 复核任务

`CandidateRecallReviewIssueBuilder` 触发条件：

1. `missing_target_profile`：目标缺 M08 画像。
2. `missing_target_battlefield`：目标缺 M11 战场。
3. `empty_pool`：候选全集或结果候选为空。
4. `too_small_pool`：当前 35 型号样例候选少于 3。
5. `too_large_pool`：候选过多或原因重复。
6. `single_source_pool`：候选全部来自单一入口。
7. `all_candidates_insufficient_sample`：候选全部样本不足。
8. `no_market_evidence`：候选或目标缺市场证据。
9. `no_semantic_evidence`：候选缺任务、客群、战场、卖点价值语义证据。
10. `only_service_signal`：候选只因服务信号进入。
11. `weak_audience_signal`：低置信客群被用于召回。
12. `structured_claim_missing`：结构化卖点缺失导致卖点价值入口降级。
13. `model_family_overcrowded`：同型号族候选过多，业务增量不足。
14. `feature_snapshot_missing`：候选已入池但 M13 快照缺失。
15. `duplicate_reason`：同一入口重复生成等价理由。

## 10. runner/API 任务

### 10.1 runner 入口

在 `candidate_recall_runner.py` 实现：

```python
def run_m12_candidate_recall(
    project_id: str,
    category_code: str,
    batch_id: str,
    target_sku_codes: list[str] | None = None,
    force: bool = False,
    rule_version: str = "core3_mvp_real_data_v2_m12_v1",
) -> M12CandidateRecallRunSummary:
    ...
```

`M12CandidateRecallRunSummary` 字段：

| 字段 | 说明 |
| --- | --- |
| `target_count` | 本次目标 SKU 数 |
| `blocked_target_count` | 阻塞目标数 |
| `candidate_universe_count` | 候选全集累计数量 |
| `candidate_selected_count` | 入池候选累计数量 |
| `strong_candidate_count` | 强召回数量 |
| `medium_candidate_count` | 中召回数量 |
| `weak_candidate_count` | 弱召回数量 |
| `review_candidate_count` | 仅复核数量 |
| `reason_count` | 召回理由数量 |
| `snapshot_count` | M13 快照数量 |
| `review_issue_count` | 复核问题数量 |
| `changed_pair_count` | 变化 pair 数 |
| `downstream_invalidation_events` | 下游失效事件数 |

### 10.2 target scope

runner 支持：

| Scope | 含义 |
| --- | --- |
| `all_targets` | 批次内所有目标 SKU |
| `target_sku_list` | 指定目标 SKU |
| `changed_targets` | 上游变化影响的目标 |
| `changed_pairs` | 候选画像变化影响的 pair |

首版 API 可以只暴露 `target_sku_codes`，内部保留 scope 扩展位。

### 10.3 增量策略

目标级 `input_fingerprint`：

```text
hash(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  target_profile_hash,
  target_m07_market_hash,
  target_m09_task_fingerprint,
  target_m10_audience_fingerprint,
  target_m11_battlefield_fingerprint,
  target_m115_claim_value_fingerprint,
  candidate_universe_hash,
  evidence_revision,
  rule_version
)
```

Pair 级 `pair_feature_hash`：

```text
hash(
  target_profile_hash,
  candidate_profile_hash,
  target_market_hash,
  candidate_market_hash,
  battlefield_overlap_payload,
  task_overlap_payload,
  audience_overlap_payload,
  claim_value_overlap_payload,
  price_feature_payload,
  channel_feature_payload,
  size_feature_payload,
  rule_version
)
```

变化传播：

| 变化来源 | M12 动作 | 下游影响 |
| --- | --- | --- |
| M01 SKU 新增/失效 | 更新候选全集 | M12-M16 |
| M02 evidence 状态变化 | 更新证据和复核状态 | M12-M16 |
| M07 市场画像变化 | 重算可比池、价格、销量、趋势召回 | M12-M16 |
| M08 目标画像变化 | 重算该目标全部候选 | M12-M16 |
| M08 候选画像变化 | 重算涉及该候选的 pair | M12-M16 |
| M09 任务变化 | 重算任务入口和快照 | M12-M16 |
| M10 客群变化 | 重算客群入口和快照 | M12-M16 |
| M11 战场变化 | 重算战场入口和角色提示 | M12-M16 |
| M11.5 卖点价值变化 | 重算卖点价值入口和配置/标杆关系 | M12-M16 |
| 召回规则变化 | 按新 `rule_version` 全量重算 | M12-M16 |

### 10.4 API

在 v2 namespace 增加内部 API：

| API | 方法 | 用途 |
| --- | --- | --- |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/candidate-recall/run` | POST | 触发指定目标召回 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/candidate-recall/runs/{run_id}` | GET | 查看召回运行 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/candidate-audit` | GET | 查询候选池、召回理由和复核问题 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/candidate-audit/{candidate_sku}` | GET | 查询单候选召回路径 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/candidate-recall-review-issues` | GET | 查询 M12 复核问题 |

API 约束：

- API 默认只查 `is_current=true`。
- 高层主屏不直接调用 M12 内部枚举，由 M15 转中文。
- API 不返回原始评论全文大表。
- API 不暴露 SQL、UUID 列表、内部公式给高层页面。
- API 可以供运营追溯完整召回路径。

## 11. 测试任务

### 11.1 schema 和 builder 测试

`test_m12_candidate_recall_schemas.py`：

- 枚举值完整。
- `recall_priority_score` 字段不命名为 final score。
- relation type 支持 9 类关系。
- `same_brand_flag` 只标记，不用于过滤。

`test_m12_target_anchor_builder.py`：

- 目标主/次/机会战场来自 M11。
- 重点卖点来自 M11.5 summary。
- 缺 M11.5 时卖点价值入口不可用但不 blocked。
- 缺 M08 或 M11 时 blocked。

`test_m12_candidate_universe_builder.py`：

- 同品牌不排除。
- 候选 SKU 不等于目标 SKU。
- 结构化卖点缺失不剔除。
- 市场缺失不直接剔除。
- 候选全集小于 3 生成复核。

`test_m12_pair_feature_loader.py`：

- 加载目标和候选 M07-M11.5 摘要。
- 不读取原始四表。
- 缺价格时 price relation 为 unknown。
- 缺尺寸时 size relation 为 unknown。

### 11.2 七入口测试

`test_m12_comparable_pool_recaller.py`：

- 同尺寸同价同平台生成 `direct_fight`。
- 同尺寸更低价销量不弱生成 `price_volume_pressure`。
- 相邻大尺寸更高价战场重合生成 `upgrade_substitute` 或 `premium_benchmark`。
- 相邻小尺寸更低价任务重合生成 `downgrade_substitute`。

`test_m12_battlefield_recaller.py`：

- 主战场重合生成 strong battlefield reason。
- 主次/次主重合生成 medium reason。
- 只重合 weak 战场不强召回。
- `BF_SERVICE_ASSURANCE` 唯一重合时封顶 `review_only`。

`test_m12_task_recaller.py`：

- 同主任务生成 direct 或 scenario reason。
- 任务替代链生成 downgrade 或 price pressure。
- 不从评论粗标签重新推导任务。

`test_m12_audience_recaller.py`：

- 高置信主客群重合生成 audience reason。
- 低置信客群打 `weak_audience_signal`。
- 客群入口不能单独 strong。

`test_m12_claim_value_recaller.py`：

- 同战场同绩效/溢价卖点生成 direct reason。
- 候选在目标弱感知卖点更强生成 `configuration_pressure`。
- 同门槛卖点但候选低价生成 `price_volume_pressure`。
- M12 不重新计算 PSI、SSI、SAI、CPI。

`test_m12_market_pressure_recaller.py`：

- 同价高销量生成 market pressure。
- 低价销量不弱生成 price pressure。
- 高价销额不弱且战场重合生成 benchmark。
- 高价下行且战场重合生成 potential downward pressure。
- 市场口径固定 `26W01-26W23`、线上、专业电商/平台电商。

`test_m12_scenario_service_recaller.py`：

- 新家装修/家居美学生成 scenario auxiliary。
- 仅服务信号最高 `review_only`。
- 服务信号不挤占产品核心候选名额。

### 11.3 合并、评分、规模和文案测试

`test_m12_reason_merger.py`：

- 同一 pair 多入口合并为一条 pool。
- 所有 sources 和 relation types 保留。
- evidence 去重。
- 业务理由保留最重要 2-3 个原因。

`test_m12_priority_scorer.py`：

- 按 0.20/0.25/0.15/0.15/0.20/0.05 权重计算。
- `recall_priority_score` 不作为最终竞品分。
- 价格未知不当更低价。

`test_m12_strength_capper.py`：

- 仅服务入口封顶 `review_only`。
- 无市场证据最高 `medium`。
- 无语义证据最高 `weak`。
- 低分 pair 最高 `weak`。

`test_m12_pool_controller.py`：

- 当前 35 型号样例 8-20 合理。
- 少于 3 触发 `too_small_pool`。
- 超过 25 检查 `too_large_pool` 或 `model_family_overcrowded`。
- 不为了凑数伪造 weak reason。

`test_m12_business_reason_builder.py`：

- 中文理由不包含 SQL、UUID、JSON、英文字段名。
- 不出现“AI 判断”“模型认为”。
- 85E7Q 缺结构化卖点时使用降级说明。
- 仅服务候选写成服务侧参考，不写产品核心竞品。

### 11.4 repository、runner、API 测试

`test_m12_feature_snapshot_builder.py`：

- 每个入池 pair 生成 snapshot。
- snapshot 包含 `m13_component_input_json`。
- snapshot 缺失时 pair 复核并写 `feature_snapshot_missing`。

`test_m12_review_issue_builder.py`：

- 缺目标画像写 `missing_target_profile`。
- 缺目标战场写 `missing_target_battlefield`。
- 空池写 `empty_pool`。
- 单一来源写 `single_source_pool`。
- 结构化卖点缺失写 `structured_claim_missing`。

`test_m12_repositories.py`：

- current 唯一索引生效。
- 重跑旧版本 `is_current=false`。
- reason 和 snapshot 外键关联 pool。
- result hash 相同不重复插入业务版本。
- 事务失败不留下半成品。

`test_m12_runner.py`：

- 正常运行生成 run、pool、reason、snapshot、issue。
- `force=false` 且 input hash 不变时跳过重算。
- M08 missing 时 blocked。
- M11 missing 时 blocked。
- M12 变化时发布 M13-M16 下游失效事件。

`test_m12_api.py`：

- POST run 返回运行摘要。
- GET run 返回候选数量和状态。
- candidate audit 返回候选池和召回理由。
- 单候选 audit 返回召回路径和 snapshot。
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

### 12.2 85E7Q 候选范围

`test_m12_85e7q_fixture.py` 必须验证，以 `TV00029115` / `85E7Q` 为目标时至少检查：

同 85 寸候选：

```text
85E8Q
85E5S-PRO
85E5Q-PRO
85E5Q
85E52S-PRO
85E52Q
85E3Q
85D30QD
```

相邻尺寸候选：

- 75 寸候选用于降级替代、价格/销量挤压和大屏性价比判断。
- 100 寸候选用于升级替代、高端标杆和大屏换新判断。

同价位与相邻价位：

- 同价位高销量候选。
- 更低价但任务/战场相同候选。
- 更高价但卖点价值更强候选。
- 高端候选是否存在潜在下探压力。

### 12.3 85E7Q 重点召回断言

| 语境 | 断言 |
| --- | --- |
| 高端画质 | Mini LED、高亮、分区、画质评论和同战场得分参与召回 |
| 家庭观影升级 | 85 寸、大屏、画质、音效、家庭观影任务参与召回 |
| 游戏体育 | 300HZ、HDMI2.1、看球或游戏体验参与召回 |
| 大屏性价比 | 价格每英寸、销量、销额、价格价值评论参与召回 |
| 智能系统与服务 | 只作为辅助召回或复核，不替代产品核心战场 |
| 结构化卖点缺失 | 85E7Q 不因缺卖点被剔除，卖点价值入口降置信 |
| 同品牌候选 | 海信候选可以进入候选池 |
| 业务理由 | 不出现 UUID、SQL、英文字段名、AI 过程话术 |

### 12.4 样例业务解释

对 85E7Q 的候选，M12 必须能输出类似解释：

- “该候选与 85E7Q 同处高端画质战场，尺寸同段、价格带接近，且在 Mini LED、高亮或分区控光等画质卖点上具备同类支撑，适合作为正面对打候选。”
- “该候选价格低于 85E7Q 且销量表现不弱，同时承接相近的大屏家庭观影需求，可能形成价格/销量挤压。”
- “该候选当前价格高于 85E7Q，但与目标主战场重合且卖点价值更高，可作为高端标杆或潜在下探候选观察。”
- “该候选主要因服务或安装体验信号进入参考池，只适合作为服务侧对比，不应直接作为产品核心候选。”

## 13. 完成标准

编码完成后必须满足：

1. 五张 M12 表 migration 可执行，downgrade 不影响 M00-M11.5 表。
2. 所有 M12 输出都有 `project_id`、`category_code`、`batch_id`、`run_id`、`module_run_id`。
3. `core3_candidate_pool` 中同一 target-candidate pair 当前只有一条 `is_current=true`。
4. 每个入池 pair 至少有一条 `core3_candidate_recall_reason`。
5. 每个入池 pair 有一条 current `core3_candidate_feature_snapshot`，缺失时必须复核。
6. M12 不直接读取原始四表。
7. M12 不按品牌排除候选。
8. 结构化卖点缺失不剔除候选。
9. 价格、尺寸、市场缺失保留 unknown/limited，不当 false。
10. direct、pressure、configuration、benchmark、potential、upgrade、downgrade、scenario、service 九类关系可表达。
11. 七个召回入口均有单元测试。
12. 同一 pair 多入口命中时保留全部 source 和 relation type。
13. `recall_priority_score` 只作为召回优先分，不作为最终竞品分。
14. 仅服务入口封顶 `review_only`。
15. 无市场证据最高 `medium`。
16. 无语义证据最高 `weak`。
17. 当前 35 型号样例候选池少于 3 或超过 25 触发复核。
18. M13 可以直接消费 `core3_candidate_pool` 和 `core3_candidate_feature_snapshot`，不需要重新召回。
19. 85E7Q 可以召回同 85 寸、相邻 75/100 寸、同价位/相邻价位候选。
20. 85E7Q 不因缺结构化卖点被剔除。
21. 中文业务理由不暴露 SQL、UUID、JSON、内部字段或 AI 过程文案。
22. runner 支持 `force=false` 的 input hash 跳过。
23. M12 结果变化时登记 M13-M16 下游失效事件。
24. pytest 覆盖 schema、anchor、universe、pair feature、七入口、merge、score、cap、pool controller、reason、snapshot、review、repository、runner、API、85E7Q fixture。

建议最小验证命令：

```text
pytest apps/api-server/tests/core3_real_data/test_m12_target_anchor_builder.py
pytest apps/api-server/tests/core3_real_data/test_m12_candidate_universe_builder.py
pytest apps/api-server/tests/core3_real_data/test_m12_comparable_pool_recaller.py
pytest apps/api-server/tests/core3_real_data/test_m12_claim_value_recaller.py
pytest apps/api-server/tests/core3_real_data/test_m12_reason_merger.py
pytest apps/api-server/tests/core3_real_data/test_m12_runner.py
pytest apps/api-server/tests/core3_real_data/test_m12_api.py
pytest apps/api-server/tests/core3_real_data/test_m12_85e7q_fixture.py
```

## 14. 风险和回滚

### 14.1 主要风险

| 风险 | 表现 | 处理 |
| --- | --- | --- |
| M08 M12 feature view 不足 | M12 想回读原始表补字段 | 不回读原始表，先补 M08 或降级召回 |
| M11 战场缺失 | 无法形成目标主语境 | blocked，不强行召回 |
| M11.5 缺失 | 卖点价值入口不可用 | 可继续弱召回，写缺失质量标记 |
| 当前样例全海信 | 错误排除同品牌后无候选 | same_brand 只标记不排除 |
| 候选池过小 | M13 无法评分 | 写 too_small_pool，不伪造候选 |
| 候选池过大 | M13 成本高且重复 | pool controller 按角色和战场收敛 |
| 仅服务候选误作核心竞品 | 高层报告误导 | 封顶 review_only，服务不挤占产品核心名额 |
| 价格/尺寸缺失误判 | unknown 被当 lower 或不可比 | 缺失保留 unknown，只影响对应入口 |
| M13 重复拼特征 | 上游逻辑分散 | snapshot 输出 M13 直接输入 |
| 文案过技术化 | 出现字段名、公式、AI 过程 | business reason builder 统一约束 |

### 14.2 回滚方式

代码回滚：

- 回退 M12 新增服务文件。
- 从 `runner.py` 移除 M12 注册。
- 从 API 移除 M12 路由。
- 不影响 M00-M11.5 运行。

数据库回滚：

- Alembic downgrade 删除 M12 五张表。
- 如果 M13-M16 已消费 M12，先标记下游结果失效或清理下游引用。

运行降级：

- M12 blocked 时，M13/M14 不应继续该目标评分。
- M11.5 缺失时，M12 可以基于 M07/M08/M09/M10/M11 形成弱候选池，但必须标记缺卖点价值入口。
- M15 若缺 M12，只能展示上游画像，不能展示竞品召回轨迹。

## 15. 下游依赖

### 15.1 M13 组件评分依赖

M13 必须以以下表为主输入：

- `core3_candidate_pool`
- `core3_candidate_feature_snapshot`
- `core3_candidate_recall_reason`

M13 使用：

- `candidate_role_hints_json`
- `relation_types_json`
- `recall_sources_json`
- `matched_battlefields_json`
- `matched_tasks_json`
- `matched_audiences_json`
- `matched_claim_layers_json`
- `price_feature_json`
- `market_feature_json`
- `m13_component_input_json`

M13 不应绕过 M12 重新从全量 SKU 召回候选。

### 15.2 M14 三槽位选择依赖

M14 使用 M12 的角色提示，但不受 M12 最终裁决：

- direct 角色可进入正面对打槽位。
- pressure 角色可进入价格/销量挤压槽位。
- benchmark 或 potential 角色可进入高端标杆/潜在下探槽位。
- service 角色只能作为服务侧参考，不默认进入核心三槽位。

M14 最终选择基于 M13 评分和 M14 槽位规则，不由 M12 直接决定。

### 15.3 M15 报告依赖

M15 使用：

- `business_reason_cn`
- `business_reason_short_cn`
- reason 级 `business_reason_cn`
- `relation_type_cn`
- `candidate_role_hint_cn`
- evidence refs

M15 页面应展示“为什么先进入候选池”的推导轨迹，但不展示完整候选池大表，不展示内部英文枚举。

### 15.4 M16 编排依赖

M16 需要：

- M12 run status。
- 候选池规模。
- review issue 统计。
- 下游失效事件。
- `input_fingerprint` 和 `result_hash`。
- `too_small_pool`、`too_large_pool`、`single_source_pool`、`only_service_signal` 等复核队列。

## 16. 子任务拆分建议

编码阶段不建议一个任务完成整个 M12。建议拆成以下小闭环：

| 子任务 | 内容 | 产物 |
| --- | --- | --- |
| D12-01 | Alembic migration | 五张表、索引、外键、downgrade |
| D12-02 | schema 和枚举 | typed contract、API schema、runner summary |
| D12-03 | repository | 上游读取、M12 写入、current 版本 |
| D12-04 | target anchor builder | 目标召回锚点 |
| D12-05 | candidate universe builder | 候选基础全集 |
| D12-06 | pair feature loader | 目标-候选特征加载 |
| D12-07 | seven recallers | 七个入口 reason draft |
| D12-08 | reason merge | pair 合并和多理由保留 |
| D12-09 | scorer and capper | 优先分、强度、封顶 |
| D12-10 | pool controller | 规模控制和复核 |
| D12-11 | business reason | 中文业务召回理由 |
| D12-12 | feature snapshot | M13 快照 |
| D12-13 | review and invalidation | 复核问题、下游失效 |
| D12-14 | service and runner | 编排、增量、运行摘要 |
| D12-15 | API | 运行和审计 API |
| D12-16 | tests and fixture | 单元、集成、85E7Q 回归 |

每个编码子任务完成后都要运行对应最小测试，不能等 M12 全部写完再测。

## 17. 下次任务

下一个开发任务文档应处理：

```text
docs/core3_mvp/real_data_v2/development/M13_development_tasks.md
```

M13 必须以 `core3_candidate_pool` 和 `core3_candidate_feature_snapshot` 为主输入，对 M12 召回的候选逐项计算价格、渠道、尺寸、参数、卖点、任务、客群、战场、市场、风险等组件分。M13 可以使用 M12 的 `candidate_role_hints_json` 区分正面对打、价格/销量挤压、高端标杆、潜在下探等角色，但不得重新召回全量候选，也不得直接选择核心三竞品。
