# M16 增量任务编排、复核和验收开发任务

## 1. 模块目标

M16 的开发目标是把 M00-M15 的独立模块产物串成一条可重跑、可复用、可复核、可验收、可发布的真实数据生产线。M16 是生产线治理层，不是新的竞品算法层，也不是高层报告内容生成层。

M16 要回答的问题是：

1. 本次运行为什么触发，是数据变化、规则变化、人工刷新、复核返工，还是只做验收。
2. 哪些 SKU、目标报告和上游证据受影响。
3. 应该从哪个模块开始重算，哪些模块可以复用旧结果。
4. 每个模块实际运行状态、输入数量、输出数量、依赖 hash 和输出 hash 是什么。
5. M00-M15 产生了哪些复核问题，哪些会阻断发布，哪些可以带说明发布。
6. 单个目标 SKU 的 M15 报告是否可汇报、需复核、不可发布或已发布。
7. 当前 205 样例数据范围是否被正确说明，特别是 85E7Q 的同品牌样例、线上样例和宣传卖点数据缺口。
8. 后续原始表持续新增时，如何只处理增量并保持历史版本可追溯。

M16 要解决的工程问题：

1. 建立独立的 pipeline run、重算计划、模块运行、依赖快照、复核队列、复核决策、验收报告、发布门禁和水位表。
2. 按 M00-M15 的 DAG 生成可解释的运行计划。
3. 根据原始数据变化、规则变化、复核决策和目标刷新请求做影响扩散。
4. 调用或复用每个模块 runner，但不把 M00-M15 合并成一个大脚本。
5. 统一收敛各模块复核问题，并追加跨模块质量问题。
6. 对报告可发布性做门禁判断，阻断内部字段、UUID、SQL、AI 过程文案、低置信确定语气和无证据结论。
7. 生成分层验收报告，区分数据接入、模块链路、业务输出和高层展示。
8. 更新增量水位，支持失败恢复、单目标刷新和验收-only 运行。

M16 必须固化以下边界：

- M16 不重新清洗原始数据，M01 负责。
- M16 不生成 evidence，M02 负责。
- M16 不抽取参数、卖点、评论、任务、客群或价值战场，M03-M11.5 负责。
- M16 不召回、评分或选择竞品，M12-M14 负责。
- M16 不生成高层报告内容，M15 负责。
- M16 不直接读取原始四表生成业务结论；原始表只用于只读校验和水位摘要，且优先通过 M00 产物读取。
- M16 不把低置信、样本不足或空槽结果包装成确定结论。
- M16 不覆盖历史运行、历史报告或复核决策，只追加新版本。
- M16 不把 205 样例数据写成完整市场结论。
- M16 不实现前端页面，也不部署 205。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M16 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M16_incremental_review_acceptance_requirements.md` |
| M16 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M16_incremental_review_acceptance_design.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M15 任务 | `docs/core3_mvp/real_data_v2/development/M15_development_tasks.md` |
| M15 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M15_evidence_report_design.md` |
| M14 任务 | `docs/core3_mvp/real_data_v2/development/M14_development_tasks.md` |
| M12-M13 任务 | `docs/core3_mvp/real_data_v2/development/M12_development_tasks.md`、`docs/core3_mvp/real_data_v2/development/M13_development_tasks.md` |
| M00-M11.5 任务 | `docs/core3_mvp/real_data_v2/development/M00_development_tasks.md` 到 `M11_5_development_tasks.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 方法论 | `cankao/CatForge_竞品生成SOP_详细指导_v1.md` |
| SOP 参考模块 | `cankao/catforge_sop_md/modules/M16_增量任务编排、复核和验收模块.md` |
| UI 规范 | `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md` |

编码前必须确认：

- INFRA 已提供真实数据 v2 独立包、run context、hash 工具、runner 协议、枚举基线和测试 fixture 基础。
- M00 已输出批次、水位、行 hash、受影响 SKU 和原始表只读校验摘要。
- M01-M02 已输出清洗结果、质量问题和 evidence atom。
- M03-M11.5 已输出参数、卖点、评论、市场、SKU 画像、任务、客群、战场和卖点价值层结果及复核问题。
- M12-M14 已输出候选池、组件评分、三槽位选择、空槽原因和未选审计。
- M15 已输出证据卡、报告 payload、报告 section、导出和报告复核问题。
- M16 不依赖前端完成，也不要求 205 部署完成。

## 3. 本次范围

本次开发任务拆分覆盖 M16 后端治理实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 9 张 M16 治理表、索引、唯一键和回滚策略 |
| model/schema | 新增 run mode、module status、review、acceptance、release gate、watermark 等 typed contracts |
| 重算计划 | 根据数据变化、规则变化、复核返工、单目标刷新生成 recompute plan |
| DAG 编排 | 固化 M00-M15 模块依赖、拓扑顺序、失败传播和合法复用 |
| runner registry | 注册 M00-M15 runner，统一 runner 返回契约 |
| 依赖快照 | 为每个模块目标记录上游输出 hash、规则版本、模块版本和依赖状态 |
| 复核队列 | 汇总 M00-M15 复核问题，追加跨模块复核问题，写入统一队列 |
| 复核决策 | 记录 approve/reject/waive/request_data/rework_rule，并判断是否触发返工 |
| 验收报告 | 生成数据接入、模块链路、业务输出、高层展示四层验收 |
| 发布门禁 | 按目标 SKU 判断 not_ready、review_required、releasable、released、blocked |
| 水位管理 | 维护 source_table、module、target_sku 三类水位，支持增量和失败恢复 |
| runner/API | 提供 M16 内部运行入口、生产线状态 API、复核 API、验收 API 和门禁 API |
| 测试 | 单元、repository、service、API、集成、85E7Q fixture 和无原始表改写测试 |

本次不做：

- 不实现 API 聚合任务文档中的批量总览、报告聚合或前端专用视图。
- 不实现前端页面。
- 不部署到 205。
- 不修改 M00-M15 的业务算法。
- 不修改旧 `core3_mvp` 粗粒度实现。
- 不把 M00-M15 合并成一个脚本。
- 不调用外部 LLM。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/pipeline_schemas.py
apps/api-server/app/services/core3_real_data/pipeline_repositories.py
apps/api-server/app/services/core3_real_data/pipeline_dependency_graph.py
apps/api-server/app/services/core3_real_data/pipeline_recompute_planner.py
apps/api-server/app/services/core3_real_data/pipeline_impact_analyzer.py
apps/api-server/app/services/core3_real_data/pipeline_module_runner_registry.py
apps/api-server/app/services/core3_real_data/pipeline_execution_service.py
apps/api-server/app/services/core3_real_data/pipeline_review_aggregator.py
apps/api-server/app/services/core3_real_data/pipeline_review_service.py
apps/api-server/app/services/core3_real_data/pipeline_acceptance_service.py
apps/api-server/app/services/core3_real_data/pipeline_release_gate_service.py
apps/api-server/app/services/core3_real_data/pipeline_watermark_service.py
apps/api-server/app/services/core3_real_data/pipeline_snapshot_service.py
apps/api-server/app/services/core3_real_data/pipeline_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `pipeline_schemas.py` | M16 枚举、typed contracts、request/response DTO、runner result DTO |
| `pipeline_repositories.py` | 读 M00-M15 运行摘要和问题，写 M16 九张治理表 |
| `pipeline_dependency_graph.py` | 固化 M00-M15 DAG、模块顺序、必要依赖和可跳过条件 |
| `pipeline_recompute_planner.py` | 根据变化生成 `core3_recompute_plan` |
| `pipeline_impact_analyzer.py` | 处理数据域、规则域、目标 SKU 和候选池扩散 |
| `pipeline_module_runner_registry.py` | 注册 M00-M15 runner，校验 runner 返回契约 |
| `pipeline_execution_service.py` | 创建 run、执行计划、记录模块状态、失败传播、结束 run |
| `pipeline_review_aggregator.py` | 收集 M00-M15 复核问题和 M16 跨模块问题 |
| `pipeline_review_service.py` | 写复核队列、处理复核决策、触发返工建议 |
| `pipeline_acceptance_service.py` | 生成分层验收报告 |
| `pipeline_release_gate_service.py` | 计算目标级和运行级发布门禁 |
| `pipeline_watermark_service.py` | 读取、比较、更新 source/module/target 水位 |
| `pipeline_snapshot_service.py` | 计算 dependency hash、output hash、依赖快照和复用判断 |
| `pipeline_runner.py` | M16 runner 入口和命令式调用封装 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0024_core3_real_data_pipeline_governance.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0024_core3_real_data_pipeline_governance.py` | 新增 M16 九张表、索引、唯一键、downgrade |
| `core3_real_data.py` schema | 增加生产线运行、模块运行、复核、验收、门禁 response |
| `core3_real_data.py` API | 增加 M16 内部调度、复核、验收、门禁 API |
| `constants.py` | 增加 M16 run mode、状态、模块码、问题类型、门禁枚举 |
| `runner.py` | 注册 M16 runner 和 M00-M15 runner registry 入口，不改变上游 runner 行为 |
| `conftest.py` | 增加 pipeline、review、acceptance、release gate、85E7Q fixture |

如果 Alembic 当前最新编号不是 `0023`，编码时按最新编号顺延；migration 内容仍只能包含 M16 表、索引和约束。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m16_pipeline_schemas.py
apps/api-server/tests/core3_real_data/test_m16_dependency_graph.py
apps/api-server/tests/core3_real_data/test_m16_recompute_planner.py
apps/api-server/tests/core3_real_data/test_m16_impact_analyzer.py
apps/api-server/tests/core3_real_data/test_m16_module_runner_registry.py
apps/api-server/tests/core3_real_data/test_m16_pipeline_execution_service.py
apps/api-server/tests/core3_real_data/test_m16_review_aggregator.py
apps/api-server/tests/core3_real_data/test_m16_review_service.py
apps/api-server/tests/core3_real_data/test_m16_acceptance_service.py
apps/api-server/tests/core3_real_data/test_m16_release_gate_service.py
apps/api-server/tests/core3_real_data/test_m16_watermark_service.py
apps/api-server/tests/core3_real_data/test_m16_pipeline_repositories.py
apps/api-server/tests/core3_real_data/test_m16_runner.py
apps/api-server/tests/core3_real_data/test_m16_api.py
apps/api-server/tests/core3_real_data/test_m16_85e7q_fixture.py
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

- M00 原始数据批次和行登记逻辑。
- M01 清洗规则。
- M02 evidence 原子生成逻辑。
- M03-M11.5 抽取、画像、任务、客群、战场和卖点价值逻辑。
- M12 候选池召回逻辑。
- M13 组件评分逻辑。
- M14 三槽位选择逻辑。
- M15 报告内容生成和导出逻辑。
- 原始四表结构和真实数据导入脚本。

不得引入的行为：

- 用 M16 直接读取原始表拼业务结论。
- 用一个脚本顺序跑完 M00-M15 并绕过模块 runner。
- 覆盖历史 run、module run、review decision、acceptance report 或 release gate。
- 把待复核或低置信结果直接标记为可发布。
- 在高层页面或业务 payload 中暴露内部英文枚举、表名、字段名、UUID、SQL、JSON 大段或 AI 过程文案。
- 因为当前样例全是海信就过滤同品牌竞品。
- 因为 85E7Q 无结构化卖点就写成“产品无卖点”或“卖点弱”。
- 在测试中调用外部 LLM。

## 6. 数据库迁移任务

### 6.1 migration 文件

建议新增：

```text
apps/api-server/alembic/versions/0024_core3_real_data_pipeline_governance.py
```

新增九张表：

```text
core3_pipeline_run
core3_recompute_plan
core3_module_run
core3_module_dependency_snapshot
core3_review_queue
core3_review_decision
core3_acceptance_report
core3_release_gate
core3_pipeline_watermark
```

M16 migration 只包含生产线治理表。M00-M15 的业务结果表已经由各模块 migration 管理。

### 6.2 `core3_pipeline_run`

用途：记录一次真实数据 v2 生产线运行。

字段：

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `run_id` | uuid | 主键 |
| `parent_run_id` | uuid nullable | 返工或重试来源 run |
| `project_id` | varchar(64) | 项目 |
| `category_code` | varchar(32) | 品类，首版 TV |
| `run_mode` | varchar(32) | bootstrap_full/daily_incremental/ruleset_replay/single_target_refresh/review_rework/acceptance_only |
| `trigger_type` | varchar(32) | data_change/rule_change/manual/review/export_acceptance |
| `triggered_by` | varchar(128) | 触发人或系统 |
| `data_batch_id` | uuid nullable | M00 批次 |
| `target_scope_json` | jsonb | 目标范围 |
| `ruleset_version` | varchar(64) | 规则版本 |
| `module_version_json` | jsonb | M00-M16 模块版本 |
| `seed_version_json` | jsonb | seed 版本 |
| `input_watermark_json` | jsonb | 输入水位 |
| `status` | varchar(32) | pending/running/success/warning/review_required/blocked/failed |
| `release_status` | varchar(32) | not_ready/review_required/releasable/released/blocked |
| `output_summary_json` | jsonb | 输出摘要 |
| `quality_summary_json` | jsonb | 质量摘要 |
| `error_code` | varchar(64) nullable | 错误码 |
| `error_message_cn` | text nullable | 中文错误说明 |
| `started_at` | timestamptz nullable | 开始时间 |
| `finished_at` | timestamptz nullable | 结束时间 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

索引和约束：

```sql
alter table core3_pipeline_run
  add constraint pk_core3_pipeline_run primary key (run_id);

create index idx_core3_pipeline_run_project_status
on core3_pipeline_run(project_id, category_code, status, created_at desc);

create index idx_core3_pipeline_run_batch
on core3_pipeline_run(project_id, category_code, data_batch_id);
```

### 6.3 `core3_recompute_plan`

用途：记录本次运行每个模块、每个目标为什么运行、复用、跳过或阻断。

字段：

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `plan_id` | uuid | 主键 |
| `run_id` | uuid | 生产线运行 |
| `project_id` | varchar(64) | 项目 |
| `category_code` | varchar(32) | 品类 |
| `batch_id` | uuid nullable | 批次 |
| `module_code` | varchar(16) | M00-M16 |
| `target_type` | varchar(32) | batch/source_row/sku/target_sku/pair/report/global |
| `target_id` | varchar(128) | 目标标识 |
| `start_from_module` | varchar(16) | 变化影响的起始模块 |
| `change_domain` | varchar(32) | market/param/claim/comment/profile/rule/review/report/source |
| `change_reason_cn` | text | 中文重算原因 |
| `upstream_dependency_hash` | varchar(128) nullable | 上游依赖 hash |
| `previous_output_hash` | varchar(128) nullable | 上次输出 hash |
| `planned_action` | varchar(32) | run/reuse/block/skip |
| `priority` | integer | 执行优先级 |
| `related_targets_json` | jsonb | 扩散到的相关目标 |
| `plan_reason_json` | jsonb | 机器可读计划原因 |
| `created_at` | timestamptz | 创建时间 |

索引和约束：

```sql
alter table core3_recompute_plan
  add constraint pk_core3_recompute_plan primary key (plan_id);

create unique index uq_core3_recompute_plan_item
on core3_recompute_plan(run_id, module_code, target_type, target_id);

create index idx_core3_recompute_plan_module
on core3_recompute_plan(run_id, module_code, planned_action, priority);
```

### 6.4 `core3_module_run`

用途：记录每个模块在每个目标粒度上的运行或复用状态。

字段：

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `module_run_id` | uuid | 主键 |
| `run_id` | uuid | 生产线运行 |
| `plan_id` | uuid nullable | 重算计划 |
| `project_id` | varchar(64) | 项目 |
| `category_code` | varchar(32) | 品类 |
| `batch_id` | uuid nullable | 批次 |
| `module_code` | varchar(16) | M00-M16 |
| `module_name_cn` | varchar(128) | 中文模块名 |
| `target_type` | varchar(32) | batch/sku/target_sku/pair/report/global |
| `target_id` | varchar(128) | 目标 |
| `status` | varchar(32) | pending/running/success/warning/review_required/blocked/failed/skipped_reused/skipped_by_dependency |
| `input_count` | integer | 输入数量 |
| `changed_input_count` | integer | 变化输入数量 |
| `output_count` | integer | 输出数量 |
| `warning_count` | integer | 警告数 |
| `review_issue_count` | integer | 复核问题数 |
| `dependency_hash` | varchar(128) nullable | 当前依赖 hash |
| `output_hash` | varchar(128) nullable | 当前输出 hash |
| `hash_version` | varchar(32) | hash 算法版本 |
| `rule_version` | varchar(64) | 规则版本 |
| `module_version` | varchar(64) | 实现版本 |
| `seed_version` | varchar(64) nullable | seed 版本 |
| `reused_from_module_run_id` | uuid nullable | 复用来源 |
| `run_summary_json` | jsonb | 运行摘要 |
| `error_code` | varchar(64) nullable | 错误码 |
| `error_message_cn` | text nullable | 中文错误说明 |
| `started_at` | timestamptz nullable | 开始时间 |
| `finished_at` | timestamptz nullable | 结束时间 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

索引和约束：

```sql
alter table core3_module_run
  add constraint pk_core3_module_run primary key (module_run_id);

create unique index uq_core3_module_run_target
on core3_module_run(run_id, module_code, target_type, target_id);

create index idx_core3_module_run_status
on core3_module_run(project_id, category_code, run_id, status);

create index idx_core3_module_run_reuse
on core3_module_run(module_code, target_type, target_id, dependency_hash, rule_version, module_version);
```

### 6.5 `core3_module_dependency_snapshot`

用途：记录模块运行依赖了哪些上游模块、上游目标和上游输出 hash。

字段：

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `snapshot_id` | uuid | 主键 |
| `run_id` | uuid | 生产线运行 |
| `module_run_id` | uuid | 当前模块运行 |
| `project_id` | varchar(64) | 项目 |
| `category_code` | varchar(32) | 品类 |
| `batch_id` | uuid nullable | 批次 |
| `module_code` | varchar(16) | 当前模块 |
| `target_type` | varchar(32) | 当前目标类型 |
| `target_id` | varchar(128) | 当前目标 |
| `upstream_module_code` | varchar(16) | 上游模块 |
| `upstream_target_id` | varchar(128) | 上游目标 |
| `upstream_module_run_id` | uuid nullable | 上游模块运行 |
| `upstream_output_hash` | varchar(128) nullable | 上游输出 hash |
| `upstream_rule_version` | varchar(64) nullable | 上游规则版本 |
| `upstream_module_version` | varchar(64) nullable | 上游模块版本 |
| `dependency_status` | varchar(32) | valid/missing/failed/reused/invalid |
| `dependency_reason_cn` | text nullable | 中文说明 |
| `created_at` | timestamptz | 创建时间 |

索引和约束：

```sql
alter table core3_module_dependency_snapshot
  add constraint pk_core3_module_dependency_snapshot primary key (snapshot_id);

create index idx_core3_dependency_snapshot_current
on core3_module_dependency_snapshot(run_id, module_code, target_type, target_id);

create index idx_core3_dependency_snapshot_upstream
on core3_module_dependency_snapshot(upstream_module_run_id, dependency_status);
```

### 6.6 `core3_review_queue`

用途：统一汇总 M00-M15 复核问题，并追加 M16 跨模块问题。

字段：

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `review_id` | uuid | 主键 |
| `run_id` | uuid | 生产线运行 |
| `source_module_run_id` | uuid nullable | 来源模块运行 |
| `project_id` | varchar(64) | 项目 |
| `category_code` | varchar(32) | 品类 |
| `batch_id` | uuid nullable | 批次 |
| `module_code` | varchar(16) | 来源模块 |
| `target_type` | varchar(32) | 目标类型 |
| `target_id` | varchar(128) | 目标 |
| `target_sku_code` | varchar(64) nullable | 目标 SKU |
| `candidate_sku_code` | varchar(64) nullable | 候选 SKU |
| `object_type` | varchar(64) | 问题对象 |
| `object_id` | varchar(128) nullable | 对象标识 |
| `issue_type` | varchar(64) | 问题类型 |
| `severity` | varchar(16) | blocker/high/medium/low |
| `issue_title_cn` | varchar(256) | 中文标题 |
| `issue_detail_cn` | text | 中文说明 |
| `evidence_ids` | jsonb | 相关 evidence |
| `risk_flags_json` | jsonb | 风险标记 |
| `suggested_action_cn` | text | 建议动作 |
| `review_status` | varchar(32) | pending/approved/rejected/waived/resolved |
| `reviewer` | varchar(128) nullable | 复核人 |
| `reviewed_at` | timestamptz nullable | 复核时间 |
| `resolution_note_cn` | text nullable | 处理说明 |
| `is_blocking_release` | boolean | 是否阻断发布 |
| `source_issue_table` | varchar(128) nullable | 来源问题表 |
| `source_issue_id` | varchar(128) nullable | 来源问题编号 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

索引和约束：

```sql
alter table core3_review_queue
  add constraint pk_core3_review_queue primary key (review_id);

create unique index uq_core3_review_queue_issue
on core3_review_queue(run_id, module_code, target_type, target_id, issue_type, coalesce(object_id, ''));

create index idx_core3_review_queue_pending
on core3_review_queue(project_id, category_code, review_status, severity);

create index idx_core3_review_queue_target
on core3_review_queue(project_id, category_code, batch_id, target_sku_code);
```

### 6.7 `core3_review_decision`

用途：记录人工复核动作。决策只追加，不覆盖来源事实。

字段：

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `decision_id` | uuid | 主键 |
| `review_id` | uuid | 复核问题 |
| `run_id` | uuid | 生产线运行 |
| `decision_type` | varchar(32) | approve/reject/waive/request_data/rework_rule |
| `decision_reason_cn` | text | 中文原因 |
| `impact_scope_json` | jsonb | 影响范围 |
| `need_recompute` | boolean | 是否需要重算 |
| `recompute_mode` | varchar(32) nullable | review_rework/ruleset_replay/single_target_refresh |
| `created_followup_run_id` | uuid nullable | 触发的新 run |
| `decided_by` | varchar(128) | 处理人 |
| `decided_at` | timestamptz | 处理时间 |

索引和约束：

```sql
alter table core3_review_decision
  add constraint pk_core3_review_decision primary key (decision_id);

create index idx_core3_review_decision_review
on core3_review_decision(review_id, decided_at desc);

create index idx_core3_review_decision_recompute
on core3_review_decision(run_id, need_recompute, recompute_mode);
```

### 6.8 `core3_acceptance_report`

用途：记录一次运行是否达到 MVP 可用标准。

字段：

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `acceptance_id` | uuid | 主键 |
| `run_id` | uuid | 生产线运行 |
| `project_id` | varchar(64) | 项目 |
| `category_code` | varchar(32) | 品类 |
| `data_batch_id` | uuid nullable | 批次 |
| `processed_sku_count` | integer | 已处理 SKU 数 |
| `processed_target_count` | integer | 已处理目标数 |
| `report_ready_count` | integer | 可用报告数 |
| `high_confidence_report_count` | integer | 高置信报告数 |
| `medium_confidence_report_count` | integer | 中置信报告数 |
| `limited_report_count` | integer | 数据受限但可说明数量 |
| `blocked_report_count` | integer | 阻断报告数 |
| `avg_competitor_count` | numeric(6,3) | 平均核心竞品数量 |
| `direct_slot_fill_rate` | numeric(6,4) | 正面对打填充率 |
| `pressure_slot_fill_rate` | numeric(6,4) | 压力槽位填充率 |
| `benchmark_slot_fill_rate` | numeric(6,4) | 标杆槽位填充率 |
| `evidence_coverage_rate` | numeric(6,4) | 证据覆盖率 |
| `review_pending_count` | integer | 待复核数 |
| `blocker_count` | integer | blocker 数 |
| `warning_count` | integer | warning 数 |
| `acceptance_status` | varchar(32) | passed/passed_with_warning/failed |
| `acceptance_summary_cn` | text | 中文验收摘要 |
| `data_scope_note_cn` | text | 数据范围说明 |
| `module_status_summary_json` | jsonb | 模块状态摘要 |
| `report_status_summary_json` | jsonb | 报告状态摘要 |
| `quality_gate_json` | jsonb | 质量门禁明细 |
| `acceptance_detail_json` | jsonb | 四层验收明细 |
| `created_at` | timestamptz | 创建时间 |

索引和约束：

```sql
alter table core3_acceptance_report
  add constraint pk_core3_acceptance_report primary key (acceptance_id);

create unique index uq_core3_acceptance_report_run
on core3_acceptance_report(run_id);

create index idx_core3_acceptance_report_status
on core3_acceptance_report(project_id, category_code, acceptance_status, created_at desc);
```

### 6.9 `core3_release_gate`

用途：按目标 SKU 判断 M15 报告是否可汇报、需复核、带说明可发布、已发布或必须阻断。

字段：

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `release_gate_id` | uuid | 主键 |
| `run_id` | uuid | 生产线运行 |
| `project_id` | varchar(64) | 项目 |
| `category_code` | varchar(32) | 品类 |
| `batch_id` | uuid nullable | 批次 |
| `target_sku_code` | varchar(64) | 目标 SKU |
| `report_payload_id` | uuid nullable | M15 报告 |
| `selection_run_id` | uuid nullable | M14 选择运行 |
| `gate_status` | varchar(32) | not_ready/review_required/releasable/released/blocked |
| `gate_reason_cn` | text | 中文门禁原因 |
| `required_review_ids` | jsonb | 必须处理的复核 |
| `warning_review_ids` | jsonb | 可带说明发布的问题 |
| `data_scope_note_cn` | text | 数据范围说明 |
| `display_badges_json` | jsonb | 高层页面徽标 |
| `gate_check_json` | jsonb | 门禁检查明细 |
| `released_by` | varchar(128) nullable | 发布人 |
| `released_at` | timestamptz nullable | 发布时间 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

索引和约束：

```sql
alter table core3_release_gate
  add constraint pk_core3_release_gate primary key (release_gate_id);

create unique index uq_core3_release_gate_target
on core3_release_gate(run_id, target_sku_code);

create index idx_core3_release_gate_status
on core3_release_gate(project_id, category_code, gate_status, updated_at desc);

create index idx_core3_release_gate_target_lookup
on core3_release_gate(project_id, category_code, batch_id, target_sku_code);
```

### 6.10 `core3_pipeline_watermark`

用途：记录原始表、模块和目标 SKU 的处理水位，支持增量和失败恢复。

字段：

| 字段 | 类型建议 | 说明 |
| --- | --- | --- |
| `watermark_id` | uuid | 主键 |
| `project_id` | varchar(64) | 项目 |
| `category_code` | varchar(32) | 品类 |
| `watermark_type` | varchar(32) | source_table/module/target_sku |
| `source_table` | varchar(64) nullable | 原始表 |
| `module_code` | varchar(16) nullable | 模块 |
| `target_id` | varchar(128) nullable | SKU 或目标 |
| `last_source_pk` | varchar(128) nullable | 已处理最大来源主键 |
| `last_write_time` | timestamptz nullable | 已处理最大写入时间 |
| `last_row_hash_snapshot` | varchar(128) nullable | 行 hash 快照 |
| `last_success_run_id` | uuid nullable | 上次成功运行 |
| `last_success_module_run_id` | uuid nullable | 上次成功模块运行 |
| `last_output_hash` | varchar(128) nullable | 上次输出 hash |
| `watermark_json` | jsonb | 扩展水位 |
| `updated_at` | timestamptz | 更新时间 |

索引和约束：

```sql
alter table core3_pipeline_watermark
  add constraint pk_core3_pipeline_watermark primary key (watermark_id);

create unique index uq_core3_pipeline_watermark_scope
on core3_pipeline_watermark(
  project_id,
  category_code,
  watermark_type,
  coalesce(source_table, ''),
  coalesce(module_code, ''),
  coalesce(target_id, '')
);

create index idx_core3_pipeline_watermark_run
on core3_pipeline_watermark(last_success_run_id, last_success_module_run_id);
```

### 6.11 downgrade 要求

`downgrade()` 只删除 M16 九张治理表和相关索引，不触碰 M00-M15 业务结果表，不触碰原始四表。

如果 M16 已经生成 release gate 或 acceptance report，回滚前必须确认前端和 API 不再读取 M16 治理表，避免展示悬空状态。

## 7. model/schema 任务

### 7.1 枚举

新增或扩展以下枚举：

```text
PipelineRunMode = bootstrap_full / daily_incremental / ruleset_replay / single_target_refresh / review_rework / acceptance_only
PipelineTriggerType = data_change / rule_change / manual / review / export_acceptance
PipelineStatus = pending / running / success / warning / review_required / blocked / failed
ModuleCode = M00-M16
ModuleRunStatus = pending / running / success / warning / review_required / blocked / failed / skipped_reused / skipped_by_dependency
TargetType = batch / source_row / sku / target_sku / pair / report / global
ChangeDomain = market / param / claim / comment / profile / rule / review / report / source
PlannedAction = run / reuse / block / skip
DependencyStatus = valid / missing / failed / reused / invalid
ReviewSeverity = blocker / high / medium / low
ReviewStatus = pending / approved / rejected / waived / resolved
ReviewDecisionType = approve / reject / waive / request_data / rework_rule
AcceptanceStatus = passed / passed_with_warning / failed
ReleaseGateStatus = not_ready / review_required / releasable / released / blocked
WatermarkType = source_table / module / target_sku
```

### 7.2 Pydantic DTO

必须新增以下 typed contracts：

| DTO | 用途 |
| --- | --- |
| `PipelineRunRequest` | 启动 M16 运行 |
| `PipelineRunContext` | 服务内部上下文 |
| `PipelineRunRecord` | `core3_pipeline_run` 读写对象 |
| `TargetScope` | 全量、单目标、目标列表、受影响目标 |
| `RecomputePlanItem` | 单个重算计划项 |
| `ModuleTargetScope` | 传给模块 runner 的目标范围 |
| `ModuleRunRequest` | 调用 runner 的标准请求 |
| `ModuleRunResult` | runner 返回标准结果 |
| `DependencySnapshotItem` | 单条依赖快照 |
| `ReviewQueueItem` | 统一复核问题 |
| `ReviewDecisionInput` | 复核决策请求 |
| `AcceptanceReportSummary` | 验收报告摘要 |
| `ReleaseGateResult` | 目标级门禁结果 |
| `WatermarkSnapshot` | 水位快照 |
| `PipelineRunResponse` | 运行状态 API 返回 |
| `PipelineModuleRunResponse` | 模块运行 API 返回 |
| `ReviewQueueResponse` | 复核队列 API 返回 |
| `AcceptanceReportResponse` | 验收 API 返回 |
| `ReleaseGateResponse` | 门禁 API 返回 |

### 7.3 runner 返回契约

所有 M00-M15 runner 必须返回同一结构：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `status` | 是 | success/warning/review_required/blocked/failed |
| `input_count` | 是 | 输入数量 |
| `changed_input_count` | 是 | 变化输入数量 |
| `output_count` | 是 | 输出数量 |
| `output_hash` | 条件 | 成功、warning、review_required 时必填 |
| `warnings` | 是 | 警告列表 |
| `review_issues` | 是 | 复核问题列表 |
| `downstream_impacts` | 是 | 下游影响模块 |
| `summary_json` | 是 | 模块摘要 |

禁止 runner 返回自由格式 dict 后由 M16 猜字段。

## 8. repository 任务

新增 `PipelineRepository`，也可以按现有风格拆成多个 repository，但必须保持读写边界清晰。

### 8.1 写入方法

必须实现：

```text
create_pipeline_run(context) -> PipelineRunRecord
mark_pipeline_running(run_id) -> None
finish_pipeline_run(run_id, status, release_status, summary) -> None
fail_pipeline_run(run_id, error_code, error_message_cn) -> None

insert_recompute_plan(run_id, items) -> list[RecomputePlanItem]
list_recompute_plan(run_id, filters) -> list[RecomputePlanItem]

create_module_run(module_run) -> ModuleRunRecord
update_module_run_status(module_run_id, status, summary) -> None
find_reusable_module_run(module_code, target_type, target_id, dependency_hash, rule_version, module_version) -> ModuleRunRecord | None
insert_dependency_snapshots(module_run_id, snapshots) -> None

upsert_review_queue(items) -> list[ReviewQueueItem]
insert_review_decision(decision) -> ReviewDecisionRecord
update_review_status(review_id, status, reviewer, note) -> None

write_acceptance_report(report) -> AcceptanceReportRecord
write_release_gate(gate) -> ReleaseGateRecord
mark_release_gate_released(gate_id, released_by) -> ReleaseGateRecord
upsert_watermark(snapshot) -> WatermarkSnapshot
```

### 8.2 读取方法

必须实现：

```text
get_pipeline_run(run_id) -> PipelineRunRecord
get_latest_success_run(project_id, category_code) -> PipelineRunRecord | None
get_current_watermarks(project_id, category_code) -> list[WatermarkSnapshot]
get_m00_batch_summary(batch_id) -> SourceBatchSummary
get_m00_impacted_skus(batch_id) -> list[ImpactedSku]
get_m00_source_hash_summary(batch_id) -> SourceHashSummary

list_module_runs(run_id, filters) -> list[ModuleRunRecord]
list_dependency_snapshots(run_id, filters) -> list[DependencySnapshotItem]
list_open_reviews(run_id, filters) -> list[ReviewQueueItem]
list_target_reviews(run_id, target_sku_code) -> list[ReviewQueueItem]
get_acceptance_report(run_id) -> AcceptanceReportRecord | None
list_release_gates(run_id, filters) -> list[ReleaseGateRecord]
get_target_release_gate(run_id, target_sku_code) -> ReleaseGateRecord | None
```

### 8.3 来源问题读取边界

M16 可以读取 M00-M15 的复核问题表或等价 issue 输出：

| 模块 | 读取对象 |
| --- | --- |
| M00 | 原始表只读、批次、水位、行 hash、受影响 SKU 问题 |
| M01 | 清洗质量问题、有效 SKU 异常下降、字段规范化问题 |
| M02 | evidence 缺失、证据失效、证据覆盖不足 |
| M03-M11.5 | 参数、卖点、评论、市场、画像、任务、客群、战场复核问题 |
| M12 | 候选池过小、召回来源不足、同品牌过滤风险 |
| M13 | 分数接近阈值、组件证据不足 |
| M14 | 空槽、角色选择复核、未选原因异常 |
| M15 | 证据卡缺失、主屏内部字段、UUID、语气和数据范围问题 |

M16 不允许直接修改来源模块 issue，只能汇总进 `core3_review_queue` 并追加 `core3_review_decision`。

### 8.4 事务和幂等

- 创建 run、写 plan、写 module run、写 dependency snapshot 应按运行阶段分事务。
- 单个模块目标失败不能回滚已成功模块 run。
- 同一 run/module/target 的 plan 和 module run 必须幂等，不重复插入。
- review queue 以 run/module/target/issue/object 去重。
- acceptance report 每个 run 只能有一份。
- release gate 每个 run + target 只能有一份。
- watermark 只有在 run 达到 success/warning/review_required 且没有原始表只读违规时更新。

## 9. service 任务

### 9.1 `PipelineExecutionService`

主流程：

1. 校验 `PipelineRunRequest`。
2. 读取规则版本、模块版本、seed 版本和当前水位。
3. 创建 `core3_pipeline_run`，状态 `pending`。
4. 标记 run `running`。
5. 如果不是 `acceptance_only`，读取或触发 M00 批次摘要。
6. 调用 `RecomputePlanner` 生成计划并写入 `core3_recompute_plan`。
7. 按 `PipelineDependencyGraph` 拓扑顺序执行计划。
8. 每个模块目标先计算 dependency hash，再判断是否复用。
9. 复用时写 `skipped_reused`，并记录 `reused_from_module_run_id`。
10. 上游失败或阻断时，下游写 `skipped_by_dependency`。
11. 需要运行时，通过 `ModuleRunnerRegistry` 调用对应 runner。
12. 写入 `core3_module_run` 和 `core3_module_dependency_snapshot`。
13. 调用 `ReviewAggregator` 汇总复核问题。
14. 调用 `AcceptanceService` 生成验收报告。
15. 调用 `ReleaseGateService` 生成目标级门禁和总发布状态。
16. 成功或带复核结束时更新水位。
17. 结束 run。

伪代码：

```python
def run_pipeline(request: PipelineRunRequest) -> PipelineRunResponse:
    context = build_context(request)
    run = repo.create_pipeline_run(context)
    try:
        repo.mark_pipeline_running(run.run_id)
        plan = planner.build_plan(context)
        repo.insert_recompute_plan(run.run_id, plan.items)
        execution_summary = execute_plan(context, plan)
        reviews = review_aggregator.collect(context, execution_summary)
        review_service.upsert_queue(context, reviews)
        acceptance = acceptance_service.build_report(context)
        gates = release_gate_service.evaluate_all(context)
        final_status = derive_final_status(acceptance, gates)
        watermark_service.update_on_success(context, final_status)
        repo.finish_pipeline_run(run.run_id, final_status.pipeline_status, final_status.release_status, final_status.summary)
        return build_response(run.run_id)
    except Exception as exc:
        repo.fail_pipeline_run(run.run_id, normalize_error_code(exc), to_cn_message(exc))
        raise
```

### 9.2 `RecomputePlanner`

必须支持六种运行模式：

| run mode | 处理 |
| --- | --- |
| `bootstrap_full` | 从 M00 开始全链路运行目标范围内模块 |
| `daily_incremental` | 根据 M00 水位和 row hash 只重算受影响链路 |
| `ruleset_replay` | 按规则影响表扩散到对应模块和下游 |
| `single_target_refresh` | 只刷新指定目标 SKU 及其候选相关链路 |
| `review_rework` | 根据复核决策从指定模块或规则点返工 |
| `acceptance_only` | 不调用业务 runner，只重建复核、验收和门禁 |

数据变化扩散规则：

| 变化来源 | 首个重算模块 | 必须继续影响 | 可复用模块 |
| --- | --- | --- | --- |
| `week_sales_data` | M01/M02/M07 | M08-M15 | 参数、卖点、评论基础层可复用 |
| `attribute_data` | M01/M02/M03 | M04a、M08-M15 | 评论基础层、市场画像可复用 |
| `selling_points_data` | M01/M02/M04a | M04b、M08-M15 | 市场和评论基础层可复用 |
| `comment_data` | M01/M02/M05 | M06、M04b、M08-M15 | 参数抽取和市场画像可复用 |
| 原始行失效 | M00-M02 | 依赖该 evidence 的所有下游 | 必须按 evidence 状态判断 |

规则变化扩散规则：

| 变化来源 | 重算范围 |
| --- | --- |
| 参数 seed 或解析规则 | M03-M15 |
| 卖点 seed 或激活规则 | M04a、M04b、M08-M15 |
| 评论规则 | M05、M06、M04b、M08-M15 |
| 市场价格带或渠道规则 | M07-M15 |
| SKU 画像合并规则 | M08-M15 |
| 用户任务 seed 或推导规则 | M09、M11-M15 |
| 目标客群 seed 或推导规则 | M10-M15 |
| 价值战场 seed 或推导规则 | M11-M15 |
| 战场内卖点价值规则 | M11.5-M15 |
| 候选召回规则 | M12-M15 |
| 组件评分规则 | M13-M15 |
| 三槽位选择规则 | M14-M15 |
| 报告展示和语言规则 | M15 |
| 验收门禁规则 | M16 `acceptance_only` |

目标扩散规则：

1. 直接受影响 SKU：M00 标出的受影响 SKU。
2. 可比池受影响目标：与变化 SKU 在尺寸、价格带、渠道、主战场或候选池中有关的目标。
3. 已发布或演示目标：从 `core3_release_gate`、演示配置或用户指定目标中读取，首版必须覆盖 85E7Q。

示例：85E7Q 本身未变，但同尺寸同价位 SKU 的周销或价格变化可能影响 85E7Q 的压力槽位，需要从 M12 或 M13 开始重算 85E7Q 报告。

### 9.3 `PipelineDependencyGraph`

首版 DAG：

```text
M00 -> M01 -> M02
M02 -> M03
M02 -> M04a
M02 -> M05 -> M06
M03 + M04a + M05 + M06 -> M04b
M02 -> M07
M03 + M04a + M04b + M06 + M07 -> M08
M04a + M04b + M05 + M07 + M08 -> M09
M04a + M04b + M05 + M07 + M08 -> M10
M09 + M10 + M08 -> M11
M04a + M04b + M11 -> M11.5
M08 + M09 + M10 + M11 + M11.5 + M07 -> M12
M12 + M08 + M09 + M10 + M11 + M11.5 + M07 -> M13
M13 + M12 -> M14
M14 + M13 + M12 + M08-M11.5 + M02 -> M15
M00-M15 -> M16
```

服务必须提供：

- `topological_order(plan) -> list[ModulePlanGroup]`
- `required_upstream(module_code) -> list[ModuleCode]`
- `downstream_modules(module_code) -> list[ModuleCode]`
- `can_reuse(module_code, dependency_status, planned_action) -> bool`
- `must_block_downstream(module_status) -> bool`

### 9.4 `PipelineSnapshotService`

dependency hash 组成：

1. 上游模块输出 hash。
2. 当前模块规则版本。
3. 当前模块实现版本。
4. 相关 seed 版本。
5. 目标范围。
6. evidence 状态。
7. 会影响重算的复核决策。

要求：

- JSON key 固定排序。
- null、空字符串、`unknown`、`-` 保持不同语义。
- evidence 状态变化必须进入 hash。
- 复用旧结果必须记录 `reused_from_module_run_id`。
- 缺 dependency hash 的 M08-M15 结果必须进入 blocker 复核问题。

### 9.5 `ModuleRunnerRegistry`

职责：

1. 注册 M00-M15 runner。
2. 校验每个 runner 暴露 `module_code`。
3. 校验 runner 返回 `ModuleRunResult`。
4. runner 缺失时写 `failed`，不得静默跳过。
5. `acceptance_only` 不调用业务 runner。

首版可以用 mock runner 做集成测试，但真实编码时必须通过 registry 接入各模块 runner，避免 M16 import 每个模块 service 后硬编码调用。

### 9.6 `ReviewAggregator` 和 `ReviewService`

复核问题来源：

```text
review_required
review_status
review_reason
risk_flags
missing_signals_json
evidence_ids
confidence
confidence_level
sample_status
```

M16 追加跨模块问题：

| 场景 | 级别 | 触发条件 |
| --- | --- | --- |
| 下游无依赖 hash | blocker | M08-M15 输出存在但没有 dependency snapshot |
| 复用旧结果但规则已变 | blocker | `skipped_reused` 且 rule_version 不一致 |
| 同一目标同规则重复发布不同结果 | blocker | 当前 released 结果冲突 |
| 主屏出现内部字段 | blocker | M15 section 或 export 命中禁用词 |
| 主屏出现 UUID/hash | blocker | 命中 UUID/hash 正则 |
| 85E7Q 卖点缺失未说明 | high | `TV00029115` 无结构化卖点且 M15 无限制说明 |
| 海信内部竞品被过滤 | high | 候选池因 same_brand 被排除 |
| 服务体验被当成产品核心卖点 | medium | M06 服务信号支撑 M15 核心卖点 |
| 当前线上样例被写成全市场结论 | high | 报告无线上范围限定 |

复核决策语义：

| 决策 | 行为 |
| --- | --- |
| `approve` | 认可模块结论，不触发重算 |
| `reject` | 不认可结论，按影响范围触发 `review_rework` |
| `waive` | 带说明豁免，不触发重算，但门禁保留说明 |
| `request_data` | 等待补充数据，新数据进入后触发 `daily_incremental` |
| `rework_rule` | 规则或 seed 需要修订，触发 `ruleset_replay` |

### 9.7 `AcceptanceService`

验收报告必须分四层：

| 层级 | 必查项 |
| --- | --- |
| 数据接入 | 原始表只读、M00 批次、水位、行 hash、受影响 SKU、M01 清洗、M02 evidence |
| 模块链路 | DAG 正确、每个计划模块有 module run、依赖快照完整、复用合法、失败传播 |
| 业务输出 | M12 候选池、M13 组件分、M14 三槽位、M15 报告顺序、低置信处理 |
| 高层展示 | 30 秒理解、中文业务语言、短证据编号、无 AI 过程文案、数据范围清楚 |

`acceptance_status` 规则：

| 状态 | 条件 |
| --- | --- |
| `passed` | 无 blocker、无 high 待处理、关键报告可发布 |
| `passed_with_warning` | 无 blocker，有样例范围、卖点缺失、空槽或评论重复等说明 |
| `failed` | 原始表改写、关键模块失败、无 evidence 报告、主屏出现内部字段等 |

### 9.8 `ReleaseGateService`

目标级门禁至少检查：

1. M00-M15 必要模块状态为 `success`、`warning` 或合法 `skipped_reused`。
2. 没有未处理 blocker。
3. high 问题已处理、豁免或进入 `review_required`。
4. M14 至少有 1 个可解释核心竞品；不足 3 个时 M15 有空槽原因。
5. 核心竞品有证据卡和 evidence 回溯。
6. M15 报告主屏不出现 UUID、内部字段、SQL、JSON 大段和 AI 过程文案。
7. 样例数据范围已经说明。
8. 当前同品牌样例不被误写成外部品牌市场结论。

可带说明发布的场景：

| 场景 | 必须说明 |
| --- | --- |
| 只有海信品牌 | 竞品关系是样例数据内的核心竞争关系 |
| 只有线上渠道 | 不能做线下门店判断 |
| 85E7Q 无结构化卖点 | 宣传卖点数据缺口，不等于产品无卖点 |
| 评论重复或服务类较多 | 评论仅作为用户感知补充 |
| 未选满 3 个槽位 | 空槽原因和后续补数建议 |

必须阻断的场景：

| 场景 | 门禁 |
| --- | --- |
| 核心竞品无 evidence | blocked |
| 报告结论与 M14 不一致 | blocked |
| 低置信写成确定结论 | blocked 或 review_required |
| 主屏出现 UUID、内部字段、SQL | blocked |
| 关键上游失败但报告仍正式生成 | blocked |
| 原始表被清洗流程覆盖 | blocked |

### 9.9 `WatermarkService`

水位类型：

| 类型 | 粒度 |
| --- | --- |
| `source_table` | `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data` |
| `module` | module_code + target_id |
| `target_sku` | 目标 SKU 当前可发布结果 |

原始表水位字段：

| 原始表 | 水位字段 |
| --- | --- |
| `week_sales_data` | `id`、`write_time`、row_hash |
| `attribute_data` | `id`、`write_time`、row_hash |
| `selling_points_data` | `id`、`write_time`、row_hash |
| `comment_data` | `id`、`write_time`、`comment_id`、正文 hash、分句 hash |

更新规则：

- `failed` run 不更新全局 source 水位。
- 单模块失败时，已成功模块可写 module 水位，但不能写 target release 水位。
- `review_required` 可写模块水位，但 release gate 维持需复核。
- 原始表只读校验失败时，整次运行 `failed` 且不更新任何水位。

## 10. runner/API 任务

### 10.1 runner

新增 `pipeline_runner.py`：

```text
run_pipeline(request: PipelineRunRequest) -> PipelineRunResponse
run_acceptance_only(run_id_or_scope) -> PipelineRunResponse
refresh_single_target(target_sku_code, include_related_targets=True) -> PipelineRunResponse
rework_from_review(review_id, decision) -> PipelineRunResponse | None
```

runner 必须：

- 使用 `PipelineExecutionService`，不直接写表。
- 支持 pytest 内 mock runner 注入。
- 对外返回中文错误摘要，不暴露堆栈。
- 保留 `run_id`，方便 API 和前端查询状态。

### 10.2 API

M16 API 是生产线状态和治理 API，不是高层报告页面 API。建议新增：

| API | 方法 | 用途 |
| --- | --- | --- |
| `/api/mvp/core3/v2/pipeline/runs` | POST | 启动运行 |
| `/api/mvp/core3/v2/pipeline/runs/{run_id}` | GET | 查看运行状态 |
| `/api/mvp/core3/v2/pipeline/runs/{run_id}/modules` | GET | 查看模块运行 |
| `/api/mvp/core3/v2/pipeline/runs/{run_id}/recompute-plan` | GET | 查看重算计划 |
| `/api/mvp/core3/v2/pipeline/runs/{run_id}/reviews` | GET | 查看复核队列 |
| `/api/mvp/core3/v2/pipeline/reviews/{review_id}/decisions` | POST | 提交复核决策 |
| `/api/mvp/core3/v2/pipeline/runs/{run_id}/acceptance` | GET | 查看验收报告 |
| `/api/mvp/core3/v2/pipeline/runs/{run_id}/release-gates` | GET | 查看门禁列表 |
| `/api/mvp/core3/v2/pipeline/release-gates/{gate_id}/release` | POST | 标记发布 |

请求示例：

```json
{
  "project_id": "core3_mvp",
  "category_code": "TV",
  "run_mode": "single_target_refresh",
  "trigger_type": "manual",
  "target_scope": {
    "scope_type": "target_sku_list",
    "sku_codes": ["TV00029115"],
    "include_related_targets": true
  },
  "ruleset_version": "core3-real-data-v2-1.0.0"
}
```

API 返回边界：

- 生产线状态页可以展示模块状态、复核数量、验收摘要和门禁状态。
- 高层报告页只读取门禁中文结果、数据版本、更新时间和是否需复核。
- API 不向高层业务页面返回完整 M00-M16 技术链路、内部字段、UUID、SQL、异常堆栈或任务队列细节。

## 11. 测试任务

### 11.1 schema 测试

`test_m16_pipeline_schemas.py`：

- 合法 run mode 通过。
- 非法 run mode 拒绝。
- `TargetScope` 支持全量、单目标和目标列表。
- `ModuleRunResult` 缺 output_hash 时按状态校验。
- null、空字符串、`unknown`、`-` 不被 schema 合并。

### 11.2 dependency graph 测试

`test_m16_dependency_graph.py`：

- M00-M15 拓扑顺序稳定。
- M04b 同时依赖参数、卖点、评论信号。
- M15 依赖 M14/M13/M12/M08-M11.5/M02。
- 上游 failed 时下游应 `skipped_by_dependency`。

### 11.3 recompute planner 测试

`test_m16_recompute_planner.py`：

- 周销变化从 M07 扩散到 M15。
- 参数变化从 M03 扩散到 M15。
- 评论变化触发 M05、M06、M04b、M08-M15。
- 任务 seed 变化触发 M09、M11-M15。
- 报告规则变化只触发 M15 和 M16 验收。
- `acceptance_only` 不生成业务 runner plan。
- `single_target_refresh` 能覆盖 85E7Q 及相关候选。

### 11.4 impact analyzer 测试

`test_m16_impact_analyzer.py`：

- 直接受影响 SKU 正确映射。
- 同尺寸、同价格带、同渠道候选变化能影响相关目标。
- 已发布或演示目标必须纳入影响分析。
- 同品牌候选不能因品牌相同被过滤。

### 11.5 runner registry 测试

`test_m16_module_runner_registry.py`：

- 注册 M00-M15 runner 成功。
- 缺 runner 返回 failed，不静默跳过。
- runner 返回自由 dict 时校验失败。
- mock runner 可在测试中替换真实 runner。

### 11.6 execution service 测试

`test_m16_pipeline_execution_service.py`：

- `bootstrap_full` 生成 M00-M15 plan 和 module run。
- 依赖不变时生成 `skipped_reused`。
- 上游 failed 时下游 `skipped_by_dependency`。
- 单目标失败不阻断其他目标。
- run 失败时写 `error_code` 和中文错误。

### 11.7 review 测试

`test_m16_review_aggregator.py` 和 `test_m16_review_service.py`：

- M15 UUID 暴露生成 blocker。
- M12 候选池过小生成 high。
- 85E7Q 卖点缺失未说明生成 high。
- 复核 queue 去重。
- `waive` 不触发重算但保留门禁说明。
- `reject` 或 `rework_rule` 能生成返工建议。

### 11.8 acceptance 和 release gate 测试

`test_m16_acceptance_service.py`：

- 原始表只读通过时数据接入 passed。
- dependency snapshot 缺失时模块链路 failed。
- M15 报告顺序不符合时业务输出 failed 或 review_required。
- 当前样例只有线上和同品牌时 `passed_with_warning`。

`test_m16_release_gate_service.py`：

- 未处理 blocker 时 `blocked`。
- high 待处理时 `review_required`。
- 只有 warning 且说明完整时 `releasable`。
- 标记发布后 `released`。
- M14 选择和 M15 报告不一致时 `blocked`。

### 11.9 watermark 和 repository 测试

`test_m16_watermark_service.py`：

- source_table 水位 upsert 幂等。
- failed run 不更新全局 source 水位。
- review_required 可更新 module 水位但不标记 target released。
- comment_data 使用 `comment_id` 和正文 hash 区分增量。

`test_m16_pipeline_repositories.py`：

- 九张表主键、唯一键和查询索引生效。
- review decision 追加，不覆盖 review queue。
- release gate 每个 run + target 唯一。
- acceptance report 每个 run 唯一。

### 11.10 API 测试

`test_m16_api.py`：

- `POST /pipeline/runs` schema、非法模式、单目标刷新。
- `GET /pipeline/runs/{run_id}` 返回状态、错误和中文摘要。
- `GET /pipeline/runs/{run_id}/modules` 支持模块过滤。
- `GET /pipeline/runs/{run_id}/reviews` 支持级别、目标、分页。
- `POST /pipeline/reviews/{review_id}/decisions` 校验决策类型和重算字段。
- `GET /pipeline/runs/{run_id}/acceptance` 返回四层验收。
- `GET /pipeline/runs/{run_id}/release-gates` 不返回内部堆栈。

## 12. 205/85E7Q fixture 验收

当前 205 PostgreSQL 样例数据首版验收基线：

| 数据事实 | M16 处理要求 |
| --- | --- |
| 35 个型号 | 不按完整市场使用，只按样例 SKU 集合分析 |
| 周销约 1326 行 | 可做 `26W01-26W23` 线上样例周期判断 |
| 属性约 2843 行 | 可支撑参数画像和可比判断 |
| 卖点约 65 行且只覆盖少量型号 | 必须识别为宣传卖点数据覆盖不足 |
| 评论约 62426 行 | 可做用户感知、场景和服务边界判断 |
| 品牌全部为海信 | 海信 SKU 可以互为竞品，不能过滤同品牌 |
| 渠道为专业电商、平台电商 | 只能写线上平台样例，不能写线下门店 |
| 85E7Q / `TV00029115` 无结构化卖点 | 门禁必须显示宣传卖点数据缺口 |

`test_m16_85e7q_fixture.py` 必须覆盖：

- `single_target_refresh` 可运行 `TV00029115`。
- 85E7Q 的市场、参数、评论覆盖正常。
- 85E7Q 无结构化卖点时，release gate 不是误判产品无卖点，而是显示“宣传卖点数据缺口”。
- 候选中海信内部 SKU 不被 same_brand 过滤。
- 当前数据范围显示 `26W01-26W23` 和线上平台样例。
- 服务体验和物流安装类评论不能作为产品核心竞争力证据。
- 不足 3 个高置信竞品时，门禁允许带空槽原因，而不是硬凑。
- 主屏 payload 检查无内部字段、UUID、SQL、JSON 大段和 AI 过程文案。

## 13. 完成标准

M16 开发完成必须满足：

| 标准 | 要求 |
| --- | --- |
| 表结构 | 9 张 M16 治理表、索引、唯一键和 downgrade 完整 |
| 模块独立 | M16 不改 M00-M15 业务逻辑 |
| 编排 | 支持 M00-M15 DAG、运行、复用、跳过和失败传播 |
| 增量 | 支持 `bootstrap_full`、`daily_incremental`、`ruleset_replay`、`single_target_refresh`、`review_rework`、`acceptance_only` |
| 依赖 | M08-M15 必须有 dependency snapshot 和 dependency hash |
| 复核 | M00-M15 问题能汇总到统一 queue，人工 decision 可追溯 |
| 验收 | 能生成四层 acceptance report |
| 门禁 | 能生成目标级 release gate 并阻断不合格报告 |
| 水位 | 支持 source/module/target 三类 watermark |
| 样例 | 85E7Q 数据限制、同品牌样例和卖点缺口识别正确 |
| 语言边界 | 高层可见字段无内部英文枚举、UUID、SQL、AI 过程文案 |
| 测试 | M16 单元、repository、service、API、fixture 测试通过 |
| 历史 | 不覆盖历史 run、module run、review decision、acceptance report、release gate |

## 14. 风险和回滚

| 风险 | 处理 |
| --- | --- |
| M16 过度耦合上游模块 | 通过 runner registry 和 repository 读摘要，禁止直接调用内部实现 |
| 一个大脚本替代模块化 | 编码时按 service 拆分，测试必须覆盖 registry 和 per-module run |
| dependency hash 不稳定 | 固定排序、固定 null 语义、单测覆盖重复运行一致性 |
| 增量影响漏掉相关目标 | impact analyzer 覆盖直接 SKU、可比池和已发布/演示目标 |
| 复核豁免被当成事实修改 | decision 只影响门禁和后续重算，不改上游事实表 |
| 低质量报告误发布 | blocker/high 规则、M15 guardrail 和 release gate 三层阻断 |
| 水位更新过早 | 只有 run 达到允许状态且原始表只读校验通过才更新 |
| 205 样例被写成全市场 | acceptance 和 release gate 固定样例范围说明 |

回滚策略：

1. migration downgrade 删除 M16 九张治理表，不触碰 M00-M15 业务表。
2. API 可关闭 M16 路由，不影响 M15 报告内容生成。
3. runner registry 可临时禁用 M16 自动调度，只保留 M00-M15 手工运行。
4. 已生成的 M15 报告不因 M16 回滚被删除，但前端应隐藏发布门禁状态或显示“未验收”。

## 15. 下游依赖

API 聚合任务依赖 M16 输出：

- `core3_pipeline_run`：生产线运行和状态。
- `core3_module_run`：模块进度和失败定位。
- `core3_review_queue`：待复核数量和问题列表。
- `core3_acceptance_report`：批量总览和验收摘要。
- `core3_release_gate`：单品报告是否可展示、需复核或阻断。
- `core3_pipeline_watermark`：数据更新时间和增量范围。

前端任务依赖 M16 输出：

- 批量总览页读取可发布报告数、待复核数、阻断数。
- 单品报告页读取门禁状态和中文数据范围说明。
- 生产线状态页读取 run、module run、review、acceptance、release gate。
- 高层主屏不得直接展示 M16 内部运行明细。

全链路验收任务依赖 M16 输出：

- 判断真实数据 v2 是否达到 MVP 可演示和可部署。
- 验证 85E7Q 样例是否可解释、可追溯、可带限制说明发布。
- 验证新增原始数据后是否可用 `daily_incremental` 转换到清洗表、证据表、抽取表、画像表、结果表和治理表。

## 16. 子任务拆分

| 子任务 | 内容 | 主要产物 |
| --- | --- | --- |
| D16-01 | 建 M16 表迁移 | `0024_core3_real_data_pipeline_governance.py` |
| D16-02 | 建 M16 SQLAlchemy model 和 Pydantic schema | `pipeline_schemas.py`、model 定义 |
| D16-03 | 实现 `PipelineRepository` | 九张表读写、M00-M15 摘要读取 |
| D16-04 | 实现 `PipelineDependencyGraph` | DAG、上下游、跳过和阻断规则 |
| D16-05 | 实现 `RecomputePlanner` | 六种 run mode 和变化扩散 |
| D16-06 | 实现 `PipelineImpactAnalyzer` | SKU、候选池、已发布目标扩散 |
| D16-07 | 实现 `PipelineSnapshotService` | dependency hash、output hash、复用判断 |
| D16-08 | 实现 `ModuleRunnerRegistry` | runner 注册、校验、mock 注入 |
| D16-09 | 实现 `PipelineExecutionService` | run 主流程、状态、失败恢复 |
| D16-10 | 实现 `ReviewAggregator` 和 `ReviewService` | 统一复核队列和决策 |
| D16-11 | 实现 `AcceptanceService` | 四层验收报告 |
| D16-12 | 实现 `ReleaseGateService` | 目标级门禁和发布标记 |
| D16-13 | 实现 `WatermarkService` | source/module/target 水位 |
| D16-14 | 实现 `pipeline_runner.py` 和 M16 API | 调度、复核、验收、门禁接口 |
| D16-15 | 建 mock runner 和 85E7Q fixture | 可确定性集成测试 |
| D16-16 | 完成单元、repository、service、API 和 fixture 测试 | M16 测试通过 |

编码时如果单个子任务仍然过大，应继续拆分；每次编码只做一个可测试闭环。

## 17. 下次任务

完成 M16 开发任务文档后，下一个文档是：

```text
docs/core3_mvp/real_data_v2/development/API_development_tasks.md
```

API 任务应基于 M00-M16 已定义的后端产物，设计真实数据 v2 的批量总览、单品报告、证据卡、复核和生产线状态接口，不重新设计 M16 的治理表。
