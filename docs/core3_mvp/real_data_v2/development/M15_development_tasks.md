# M15 证据卡与高层报告开发任务

## 1. 模块目标

M15 的开发目标是把 M14 的三槽位核心竞品选择结果，转换成业务高层可读、可追溯、可导出、可验收的证据卡和单 SKU 竞品报告 payload。M15 是报告生成层，不是算法调试层。

M15 要回答的问题是：

1. 当前目标 SKU 识别出几个核心竞品，分别是谁。
2. 每个核心竞品代表什么竞争压力：正面对打、价格/销量挤压、高端标杆/潜在下探。
3. 为什么这些 SKU 是竞品，而不是普通相似 SKU。
4. 结论背后的价格、渠道、参数、卖点、任务、客群、战场、市场和评论证据是什么。
5. 哪些证据不足，需要业务复核。
6. 报告是否适合给高层展示、导出和持续追踪。

M15 的汇报顺序必须固化为：

1. 先说核心竞品是谁。
2. 再说每个竞品代表什么竞争压力。
3. 再解释为什么这些 SKU 是竞品。
4. 再展示关键证据、差异和策略含义。
5. 最后提供可展开的 SOP 推导轨迹、候选池未选原因和数据质量说明。

M15 要解决的工程问题：

1. 建立 M15 独立报告结果表，不把报告 payload 混在 M14 选择表、前端页面或旧 MVP 结果里。
2. 生成每个入选竞品的证据卡。
3. 生成单 SKU 高层报告聚合 payload。
4. 生成页面 section，前端按 section 渲染，不在前端重拼业务结论。
5. 生成 JSON、Markdown、汇报摘要和证据卡导出内容。
6. 把 evidence UUID 转成业务短证据编号，主屏不展示 UUID。
7. 对主屏 payload 做质量护栏检查：内部字段、UUID、SQL、AI 过程文案、低置信确定语气、数据范围缺失。
8. 对报告问题输出复核 issue，供 M16 编排和验收。
9. 对 85E7Q 等真实样例，正确表达同品牌样例范围、线上时间窗口、宣传卖点数据缺口和服务评论边界。

M15 必须固化以下边界：

- M15 不重新选择竞品，M14 负责。
- M15 不重新计算 M13 组件分或 M14 槽位选择分。
- M15 不直接读取原始 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data`。
- M15 不添加没有 evidence 或缺失原因支撑的事实。
- M15 不把低置信结论写成确定语气。
- M15 不把所有候选 TopN 作为主屏内容。
- M15 不在主屏展示内部英文枚举、表名、字段名、UUID、SQL、JSON 大段结构。
- M15 不展示“AI 认为”“模型判断”“生成过程”“正在思考”等非业务语言。
- M15 不把服务体验证据包装成产品核心竞争结论。
- M15 不把结构化卖点缺失写成“卖点弱”，只能写成“宣传卖点数据缺口”。
- M15 不写全市场、全渠道或 12 个月结论；当前样例只能写 `26W01-26W23` 线上样例数据。
- M15 不实现前端页面，但必须输出前端可直接消费的中文业务 payload。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M15 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M15_evidence_report_requirements.md` |
| M15 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M15_evidence_report_design.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M14 任务 | `docs/core3_mvp/real_data_v2/development/M14_development_tasks.md` |
| M14 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M14_core3_selection_design.md` |
| M13 任务 | `docs/core3_mvp/real_data_v2/development/M13_development_tasks.md` |
| M13 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M13_component_scoring_design.md` |
| M12 任务 | `docs/core3_mvp/real_data_v2/development/M12_development_tasks.md` |
| M08-M11.5 任务 | `docs/core3_mvp/real_data_v2/development/M08_development_tasks.md` 到 `M11_5_development_tasks.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 方法论 | `cankao/CatForge_竞品生成SOP_详细指导_v1.md` |
| SOP 参考模块 | `cankao/catforge_sop_md/modules/M15_证据卡与高层报告模块.md` |
| UI 规范 | `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md` |

编码前必须确认：

- M14 已输出 current `core3_competitor_selection_run`。
- M14 已输出 current `core3_competitor_selection`。
- M14 已输出 current `core3_competitor_slot_decision`。
- M14 已输出 current `core3_competitor_selection_audit`。
- M14 已输出 current `core3_competitor_selection_review_issue`。
- M13 已输出组件分、角色分和组件解释。
- M12 已输出候选池和召回理由。
- M08-M11.5 已输出目标和竞品的 SKU 画像、用户任务、目标客群、价值战场、卖点价值分层摘要。
- M02 evidence atom 可用于证据短编号和回溯。
- INFRA 已提供 run context、hash 工具、current 版本约定、runner 协议、复核 issue 约定和测试 fixture 基础。

## 3. 本次范围

本次开发任务拆分覆盖 M15 后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 5 张 M15 输出表、索引、唯一键、外键和 current 版本约束 |
| model/schema | 新增 evidence card、report payload、report section、export、review issue、短证据编号、护栏结果等 schema |
| 输入读取 | 读取 M14 选择、M13 评分解释、M12 候选、M08-M11.5 画像推导、M02 evidence |
| 证据短编号 | 把 evidence_id 转成业务短证据编号，主屏不展示 UUID |
| 证据卡 | 为每个入选竞品生成一张核心证据卡 |
| 报告 section | 生成 executive、target_profile、competitor_cards、why_competitor、evidence_matrix、strategy、candidate_audit、sop_trace、data_quality、export 等 section |
| 报告 payload | 聚合单 SKU 高层报告 payload，前端直接消费 |
| 导出 | 生成 JSON、Markdown、汇报摘要、证据卡集合导出 |
| 主屏护栏 | 检查内部字段、UUID/hash、SQL、AI 过程文案、语气和数据范围 |
| 复核问题 | 输出 missing selection、all slots empty、missing evidence、internal field exposed、uuid exposed、tone mismatch 等问题 |
| 增量失效 | 用 M14/M13/M12/M08-M11.5/evidence/rule fingerprint 控制重算，并登记 M16 下游验收影响 |
| runner/API | 提供 M15 运行入口和业务展示 API、导出 API、短证据回溯 API |
| 测试 | 单元、repository、service、API、导出一致性、护栏、85E7Q fixture |

本次不做：

- 不实现 M16 增量编排和验收。
- 不实现前端页面。
- 不部署到 205。
- 不修改 M14 三槽位选择逻辑。
- 不修改 M13 组件评分逻辑。
- 不修改 M12 候选池逻辑。
- 不修改 M08-M11.5 上游画像和推导逻辑。
- 不对旧 `core3_mvp` 粗粒度页面做改造。
- 不在 M15 内调用真实 LLM。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/evidence_report_schemas.py
apps/api-server/app/services/core3_real_data/evidence_report_repositories.py
apps/api-server/app/services/core3_real_data/evidence_report_input_loader.py
apps/api-server/app/services/core3_real_data/evidence_short_ref_service.py
apps/api-server/app/services/core3_real_data/evidence_card_builder.py
apps/api-server/app/services/core3_real_data/report_section_builder.py
apps/api-server/app/services/core3_real_data/target_report_payload_builder.py
apps/api-server/app/services/core3_real_data/report_export_builder.py
apps/api-server/app/services/core3_real_data/report_guardrail_checker.py
apps/api-server/app/services/core3_real_data/report_review_issue_builder.py
apps/api-server/app/services/core3_real_data/evidence_report_invalidation_publisher.py
apps/api-server/app/services/core3_real_data/evidence_report_service.py
apps/api-server/app/services/core3_real_data/evidence_report_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `evidence_report_schemas.py` | M15 枚举、typed contracts、input/output DTO |
| `evidence_report_repositories.py` | 读取 M14/M13/M12/M08-M11.5/M02，写入 M15 五张表 |
| `evidence_report_input_loader.py` | 加载目标报告所需上游 bundle |
| `evidence_short_ref_service.py` | evidence UUID 到短证据编号映射和回溯 |
| `evidence_card_builder.py` | 生成核心竞品证据卡 |
| `report_section_builder.py` | 生成页面 section |
| `target_report_payload_builder.py` | 聚合单 SKU 高层报告 payload |
| `report_export_builder.py` | 生成 JSON、Markdown、汇报摘要、证据卡导出 |
| `report_guardrail_checker.py` | 检查内部字段、UUID、SQL、AI 文案、语气、数据范围 |
| `report_review_issue_builder.py` | 生成 M15 报告复核问题 |
| `evidence_report_invalidation_publisher.py` | M15 结果变化时登记 M16 验收影响 |
| `evidence_report_service.py` | M15 编排 service |
| `evidence_report_runner.py` | M15 runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0023_core3_real_data_evidence_report.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0023_core3_real_data_evidence_report.py` | 新增 M15 五张表、索引、唯一键、外键和 downgrade |
| `core3_real_data.py` schema | 导出 report、card、section、export、quality response |
| `core3_real_data.py` API | 增加 M15 v2 报告、证据卡、section、导出和质量 API |
| `constants.py` | 补 M15 section、export type、readiness、issue type、guardrail code |
| `runner.py` | 注册 M15 runner，不改变 M00-M14 逻辑 |
| `conftest.py` | 增加 M15 report fixture、short evidence fixture、85E7Q report fixture |

如果 Alembic 当前最新编号不是 `0022`，编码时按最新编号顺延，但 migration 内容仍只能包含 M15 表、索引、约束。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m15_evidence_report_schemas.py
apps/api-server/tests/core3_real_data/test_m15_report_input_loader.py
apps/api-server/tests/core3_real_data/test_m15_evidence_short_ref_service.py
apps/api-server/tests/core3_real_data/test_m15_evidence_card_builder.py
apps/api-server/tests/core3_real_data/test_m15_report_section_builder.py
apps/api-server/tests/core3_real_data/test_m15_target_report_payload_builder.py
apps/api-server/tests/core3_real_data/test_m15_report_export_builder.py
apps/api-server/tests/core3_real_data/test_m15_report_guardrail_checker.py
apps/api-server/tests/core3_real_data/test_m15_report_review_issue_builder.py
apps/api-server/tests/core3_real_data/test_m15_evidence_report_repositories.py
apps/api-server/tests/core3_real_data/test_m15_evidence_report_service.py
apps/api-server/tests/core3_real_data/test_m15_runner.py
apps/api-server/tests/core3_real_data/test_m15_api.py
apps/api-server/tests/core3_real_data/test_m15_85e7q_fixture.py
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

- M14 三槽位选择逻辑。
- M13 组件分、角色分和证据解释逻辑。
- M12 候选池召回逻辑。
- M08-M11.5 画像、任务、客群、战场、卖点价值逻辑。
- M02 evidence 原子生成逻辑。
- 原始四表结构。
- 旧 `core3_mvp` 页面或 API。

不得引入的行为：

- 从原始四表直接取数补报告。
- 从全量 SKU 中补选 M14 未入选竞品。
- 在报告层重算竞品选择或分数。
- 生成无 evidence 或无缺失说明的事实。
- 在业务展示 payload 中返回 UUID、内部字段名、SQL、公式、英文枚举。
- 在业务展示 payload 中返回 AI 过程文案。
- 把低置信、样本不足、空槽写成确定结论。
- 把服务评论写成产品核心竞争力。
- 在测试中调用外部 LLM。

## 6. 数据库迁移任务

### 6.1 migration 文件

建议新增：

```text
apps/api-server/alembic/versions/0023_core3_real_data_evidence_report.py
```

新增五张表：

```text
core3_evidence_card
core3_target_report_payload
core3_report_section
core3_report_export
core3_report_review_issue
```

M15 不单独设计全局任务表。运行状态由 M16 `core3_module_run` 管理；M15 结果表通过 `run_id`、`selection_run_id`、`input_fingerprint`、`result_hash` 和 `rule_version` 追溯。

### 6.2 `core3_evidence_card`

用途：每个入选核心竞品生成一张证据卡。证据卡是 M15 面向业务高层的最小可信结论单元。

若 M14 入选数量为 0，则不生成入选竞品证据卡，但必须生成 `core3_target_report_payload`、空槽 section、data quality section 和 review issue。

字段：

| 字段 | 类型建议 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `card_id` | text | 可展示卡片 ID |
| `selection_run_id` | uuid/text | 外键到 M14 selection run |
| `selection_id` | uuid/text | 外键到 M14 selection |
| `component_score_id` | uuid/text | 可空，外键到 M13 component score |
| `candidate_pool_id` | uuid/text | 可空，外键到 M12 pair |
| `project_id` | uuid/text | 必填 |
| `category_code` | text | 必填，MVP 为 `TV` |
| `batch_id` | uuid/text | 必填 |
| `run_id` | uuid/text | 必填 |
| `module_run_id` | uuid/text | 可空，关联 M16 run |
| `target_sku_code` | text | 必填 |
| `target_model_name` | text | 必填 |
| `target_display_name_cn` | text | 必填 |
| `competitor_sku_code` | text | 必填 |
| `competitor_model_name` | text | 必填 |
| `competitor_brand_name` | text | 可空 |
| `competitor_display_name_cn` | text | 必填 |
| `slot_code` | text | 必填 |
| `slot_name_cn` | text | 必填 |
| `primary_battlefield_code` | text | 可空，主屏隐藏 |
| `primary_battlefield_name_cn` | text | 必填 |
| `pressure_level_cn` | text | 必填 |
| `readiness_level` | text | ready/review_required/insufficient |
| `confidence_label_cn` | text | 高/中/低/需复核 |
| `headline_cn` | text | 结论标题 |
| `summary_cn` | text | 业务摘要 |
| `one_sentence_reason_cn` | text | 一句话理由 |
| `price_evidence_cn` | text | 可空 |
| `channel_evidence_cn` | text | 可空 |
| `param_evidence_cn` | text | 可空 |
| `claim_value_evidence_cn` | text | 可空 |
| `task_audience_evidence_cn` | text | 可空 |
| `market_evidence_cn` | text | 可空 |
| `comment_evidence_cn` | text | 可空 |
| `evidence_matrix_json` | jsonb | 必填 |
| `key_difference_cn` | text | 必填 |
| `target_advantage_cn` | text | 必填 |
| `competitor_advantage_cn` | text | 必填 |
| `strategy_implication_cn` | text | 必填 |
| `risk_note_cn` | text | 可空 |
| `short_evidence_refs_json` | jsonb | 必填 |
| `evidence_ids` | text[]/jsonb | 必填，业务 API 默认隐藏 |
| `display_payload_json` | jsonb | 前端卡片 payload，不含 UUID 和内部字段 |
| `export_payload_json` | jsonb | 导出 payload |
| `selection_result_hash` | text | M14 入选结果 hash |
| `rule_version` | text | 必填，默认 `m15_evidence_report_v1` |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

约束：

```sql
create unique index uq_core3_evidence_card_current
on core3_evidence_card(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  competitor_sku_code,
  slot_code,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, target_sku_code, slot_code)`
- `(selection_run_id, selection_id)`
- `(project_id, category_code, batch_id, readiness_level)`
- `evidence_ids` GIN，若使用 jsonb 则对 jsonb 建 GIN。

### 6.3 `core3_target_report_payload`

用途：保存单 SKU 高层报告聚合 payload。前端报告 API 默认读取该表，不在前端重新拼业务结论。

字段：

| 字段 | 类型建议 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `project_id` | uuid/text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | uuid/text | 必填 |
| `run_id` | uuid/text | 必填 |
| `module_run_id` | uuid/text | 可空 |
| `target_sku_code` | text | 必填 |
| `target_display_name_cn` | text | 必填 |
| `report_title_cn` | text | 必填 |
| `executive_conclusion_cn` | text | 高层结论 |
| `readiness_level` | text | ready/review_required/insufficient |
| `confidence_label_cn` | text | 高/中/低/需复核 |
| `data_scope_note_cn` | text | 数据覆盖范围说明 |
| `target_profile_summary_cn` | text | 目标 SKU 摘要 |
| `selection_run_id` | uuid/text | 外键到 M14 selection run |
| `selected_count` | integer | M14 入选数量 |
| `empty_slot_count` | integer | M14 空槽数量 |
| `battlefield_summary_json` | jsonb | 战场摘要 |
| `task_group_summary_json` | jsonb | 任务客群摘要 |
| `target_signal_cards_json` | jsonb | 目标信号卡 |
| `core_competitors_json` | jsonb | 0-3 个核心竞品卡摘要 |
| `empty_slots_json` | jsonb | 空槽说明 |
| `why_competitor_logic_json` | jsonb | 为什么是竞品的业务推导 |
| `evidence_matrix_json` | jsonb | 证据矩阵 |
| `key_difference_json` | jsonb | 关键差异 |
| `strategy_hint_json` | jsonb | 策略提示 |
| `sop_trace_json` | jsonb | 7 步推导轨迹 |
| `candidate_pool_summary_json` | jsonb | 候选池和未选原因 |
| `review_questions_json` | jsonb | 需业务确认问题 |
| `data_quality_note_cn` | text | 数据质量说明 |
| `short_evidence_map_json` | jsonb | 短证据编号映射 |
| `export_payload_json` | jsonb | 导出结构 |
| `ui_guardrail_result_json` | jsonb | 主屏质量检查结果 |
| `m14_selection_fingerprint` | text | M14 选择结果指纹 |
| `evidence_revision` | text | 可空 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

约束：

```sql
create unique index uq_core3_target_report_payload_current
on core3_target_report_payload(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  selection_run_id,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, target_sku_code, readiness_level)`
- `(project_id, category_code, batch_id, selection_run_id)`
- `core_competitors_json` GIN。
- `sop_trace_json` GIN。

### 6.4 `core3_report_section`

用途：把报告拆成可渲染 section，前端按 section 顺序展示。页面不需要理解算法表，只需要渲染中文业务 payload。

字段：

| 字段 | 类型建议 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `target_report_payload_id` | uuid/text | 外键到 report payload |
| `project_id` | uuid/text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | uuid/text | 必填 |
| `run_id` | uuid/text | 必填 |
| `target_sku_code` | text | 必填 |
| `selection_run_id` | uuid/text | 必填 |
| `section_code` | text | 见 section 枚举 |
| `section_title_cn` | text | 中文标题 |
| `section_order` | integer | 展示顺序 |
| `section_payload_json` | jsonb | 区域结构化内容 |
| `display_status` | text | visible/collapsed/hidden |
| `readiness_level` | text | ready/review_required/insufficient |
| `contains_internal_field_flag` | boolean | 必填，主屏必须 false |
| `contains_uuid_flag` | boolean | 必填，主屏必须 false |
| `evidence_ids` | text[]/jsonb | 业务 API 默认隐藏 |
| `short_evidence_refs_json` | jsonb | 展示短证据 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

section 枚举：

| section_code | 标题 | 默认状态 |
| --- | --- | --- |
| `executive` | 核心结论 | visible |
| `target_profile` | 目标 SKU 信号 | visible |
| `competitor_cards` | 核心竞品卡 | visible |
| `battlefield_context` | 目标竞争语境 | visible |
| `why_competitor` | 为什么是竞品 | visible |
| `evidence_matrix` | 证据矩阵 | collapsed |
| `strategy` | 关键差异与策略含义 | visible |
| `candidate_audit` | 候选池与未选原因 | collapsed |
| `sop_trace` | SOP 推导轨迹 | collapsed |
| `data_quality` | 数据质量说明 | collapsed |
| `export` | 报告导出 | visible |

约束：

```sql
create unique index uq_core3_report_section_current
on core3_report_section(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  selection_run_id,
  section_code,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, target_sku_code, section_order)`
- `(project_id, category_code, batch_id, display_status, readiness_level)`
- `section_payload_json` GIN。

### 6.5 `core3_report_export`

用途：保存报告导出产物，确保导出内容与页面 payload 来自同一版本，而不是导出时重新生成事实。

字段：

| 字段 | 类型建议 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `target_report_payload_id` | uuid/text | 外键到 report payload |
| `project_id` | uuid/text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | uuid/text | 必填 |
| `run_id` | uuid/text | 必填 |
| `target_sku_code` | text | 必填 |
| `selection_run_id` | uuid/text | 必填 |
| `export_type` | text | json/markdown/report_summary/evidence_cards |
| `export_title_cn` | text | 导出标题 |
| `export_payload` | text | 导出内容 |
| `export_payload_json` | jsonb | 可空，JSON 导出结构 |
| `data_scope_note_cn` | text | 必填 |
| `readiness_level` | text | 必填 |
| `checksum` | text | 导出内容 hash |
| `page_payload_hash` | text | 页面 payload hash |
| `export_status` | text | ready/failed/review_required |
| `failure_reason` | text | 可空 |
| `rule_version` | text | 必填 |
| `input_fingerprint` | text | 必填 |
| `result_hash` | text | 必填 |
| `is_current` | boolean | 必填 |
| `created_at` | timestamptz | 必填 |
| `updated_at` | timestamptz | 必填 |

导出类型：

```text
json
markdown
report_summary
evidence_cards
```

约束：

```sql
create unique index uq_core3_report_export_current
on core3_report_export(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  selection_run_id,
  export_type,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, target_sku_code, export_type, export_status)`
- `(project_id, category_code, batch_id, readiness_level)`

### 6.6 `core3_report_review_issue`

用途：保存 M15 报告复核问题。M16 读取该表进入复核队列，前端可根据 unresolved issue 显示“需复核”状态。

字段：

| 字段 | 类型建议 | 要求 |
| --- | --- | --- |
| `id` | uuid/text | 主键 |
| `target_report_payload_id` | uuid/text | 可空 |
| `evidence_card_id` | uuid/text | 可空 |
| `report_section_id` | uuid/text | 可空 |
| `report_export_id` | uuid/text | 可空 |
| `project_id` | uuid/text | 必填 |
| `category_code` | text | 必填 |
| `batch_id` | uuid/text | 必填 |
| `run_id` | uuid/text | 必填 |
| `target_sku_code` | text | 必填 |
| `selection_run_id` | uuid/text | 必填 |
| `issue_scope` | text | report/card/section/export/language/evidence |
| `section_code` | text | 可空 |
| `issue_type` | text | 见 issue 枚举 |
| `issue_level` | text | warning/review/blocker |
| `issue_message_cn` | text | 中文问题 |
| `suggested_action_cn` | text | 可空 |
| `source_payload_json` | jsonb | 问题上下文 |
| `evidence_ids` | text[]/jsonb | 必填，可为空数组 |
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

issue type 首版枚举：

```text
missing_selection_run
all_slots_empty
missing_evidence_card_field
missing_evidence
internal_field_exposed
uuid_exposed
tone_confidence_mismatch
missing_data_scope_note
claim_gap_not_disclosed
service_as_core_claim
missing_candidate_audit
export_payload_mismatch
sop_trace_too_technical
report_payload_incomplete
unknown
```

约束：

```sql
create unique index uq_core3_report_review_issue_current
on core3_report_review_issue(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  selection_run_id,
  issue_scope,
  coalesce(section_code, ''),
  issue_type,
  result_hash,
  rule_version
)
where is_current = true;
```

索引：

- `(project_id, category_code, batch_id, resolved_status, issue_level)`
- `(project_id, category_code, batch_id, target_sku_code, issue_type)`
- `(project_id, category_code, batch_id, target_sku_code, selection_run_id)`

### 6.7 downgrade

`downgrade()` 只删除 M15 五张表和相关索引，不触碰 M00-M14 表。

如果 M16 或前端已消费 M15 结果，回滚前必须先标记报告不可用或清理下游引用，避免前端展示悬空报告。

## 7. model/schema 任务

### 7.1 枚举

在 `evidence_report_schemas.py` 或共享 constants 中定义以下枚举。

报告成熟度：

```text
ready
review_required
insufficient
```

置信标签：

```text
高
中
低
需复核
```

section code：

```text
executive
target_profile
competitor_cards
battlefield_context
why_competitor
evidence_matrix
strategy
candidate_audit
sop_trace
data_quality
export
```

section display status：

```text
visible
collapsed
hidden
```

export type：

```text
json
markdown
report_summary
evidence_cards
```

export status：

```text
ready
failed
review_required
```

issue scope：

```text
report
card
section
export
language
evidence
```

issue level：

```text
warning
review
blocker
```

报告规则版本：

```text
m15_evidence_report_v1
```

### 7.2 输入 DTO

新增内部 DTO：

```text
ReportRunContext
ReportInputBundle
ReportSelectionRunInput
ReportSelectionInput
ReportSlotDecisionInput
ReportSelectionAuditInput
ReportM14IssueInput
ReportComponentScoreInput
ReportRoleScoreInput
ReportComponentExplanationInput
ReportTraceSummaryInput
EvidenceAtomInput
ShortEvidenceRef
EvidenceCardDraft
ReportSectionDraft
TargetReportPayloadDraft
ReportExportDraft
ReportGuardrailResult
```

`ReportInputBundle` 必须包含：

- M14 selection run。
- M14 selections。
- M14 slot decisions。
- M14 audit。
- M14 review issue。
- M13 component scores。
- M13 role scores。
- M13 component explanations。
- M12 candidate pool summary。
- M12 recall reasons。
- M08 SKU signal profile。
- M09 user task summary。
- M10 target group summary。
- M11 battlefield summary。
- M11.5 claim value layer summary。
- M02 evidence atoms。

### 7.3 输出 response schema

在 `apps/api-server/app/schemas/core3_real_data.py` 导出：

```text
Core3EvidenceCardResponse
Core3TargetReportPayloadResponse
Core3ReportSectionResponse
Core3ReportExportResponse
Core3ReportReviewIssueResponse
Core3ReportQualityResponse
Core3EvidenceShortRefResponse
Core3ReportRunSummaryResponse
```

业务展示 response 必须包含中文字段：

- `report_title_cn`
- `executive_conclusion_cn`
- `data_scope_note_cn`
- `target_profile_summary_cn`
- `slot_name_cn`
- `headline_cn`
- `summary_cn`
- `one_sentence_reason_cn`
- `price_evidence_cn`
- `channel_evidence_cn`
- `param_evidence_cn`
- `claim_value_evidence_cn`
- `task_audience_evidence_cn`
- `market_evidence_cn`
- `comment_evidence_cn`
- `key_difference_cn`
- `strategy_implication_cn`
- `risk_note_cn`
- `section_title_cn`
- `issue_message_cn`
- `suggested_action_cn`

业务展示 response 不得包含：

- raw UUID。
- 表名。
- SQL。
- `_score`、`_json`、`_id` 等内部字段名。
- 大段内部 JSON。

技术追溯 response 可以返回 raw evidence ID，但必须在单独 API 中返回，不混入高层主报告 API。

### 7.4 schema 测试要求

必须测试：

- section code 枚举完整。
- export type 枚举完整。
- readiness level 枚举完整。
- evidence card response 不包含 UUID-only 证据展示。
- report payload response 包含 `executive_conclusion_cn` 和 `data_scope_note_cn`。
- section response 可表达 visible/collapsed/hidden。
- export response 有 checksum 和 page payload hash。
- report issue 枚举包含 internal field、uuid、tone、data scope、service、export mismatch。

## 8. repository 任务

### 8.1 repository 类

新增 `EvidenceReportRepository`，也可以按项目现有模式拆为多个 repository，但必须保持 M15 的读写边界清晰。

建议接口：

```text
get_current_selection_run(context, target_sku_code) -> ReportSelectionRunInput | None
list_current_selections(context, selection_run_id) -> list[ReportSelectionInput]
list_current_slot_decisions(context, selection_run_id) -> list[ReportSlotDecisionInput]
list_current_selection_audits(context, selection_run_id) -> list[ReportSelectionAuditInput]
list_open_selection_issues(context, selection_run_id) -> list[ReportM14IssueInput]
load_component_scores(context, selection_ids) -> dict[selection_id, ReportComponentScoreInput]
load_role_scores(context, selection_ids) -> dict[selection_id, list[ReportRoleScoreInput]]
load_component_explanations(context, selection_ids) -> dict[selection_id, list[ReportComponentExplanationInput]]
load_candidate_pool_summary(context, target_sku_code) -> CandidatePoolSummaryInput
load_recall_reasons(context, candidate_pool_ids) -> dict[candidate_pool_id, list[RecallReasonInput]]
load_trace_summary(context, target_sku_code, competitor_sku_codes) -> ReportTraceSummaryInput
load_evidence_atoms(context, evidence_ids) -> dict[evidence_id, EvidenceAtomInput]
replace_current_report_results(cards, payload, sections, exports, issues) -> None
get_current_report_payload(context, target_sku_code, selection_run_id=None) -> TargetReportPayloadRecord | None
list_current_evidence_cards(context, target_sku_code, selection_run_id=None) -> list[EvidenceCardRecord]
list_current_report_sections(context, target_sku_code, selection_run_id=None) -> list[ReportSectionRecord]
get_current_report_export(context, target_sku_code, export_type, selection_run_id=None) -> ReportExportRecord | None
list_open_report_review_issues(context, target_sku_code, filters) -> list[ReportReviewIssueRecord]
resolve_short_evidence_ref(context, target_sku_code, short_ref) -> EvidenceAtomRecord | None
```

### 8.2 读取边界

允许读取：

```text
core3_competitor_selection_run
core3_competitor_selection
core3_competitor_slot_decision
core3_competitor_selection_audit
core3_competitor_selection_review_issue
core3_candidate_component_score
core3_candidate_role_score
core3_candidate_component_explanation
core3_candidate_pool
core3_candidate_recall_reason
core3_sku_signal_profile
core3_sku_task_score
core3_sku_target_group_score
core3_sku_battlefield_score
core3_sku_claim_value_layer
core3_evidence_atom
```

禁止读取：

```text
week_sales_data
attribute_data
selling_points_data
comment_data
old core3_mvp tables
frontend route state
```

M15 repository 必须从 M14 current selection run 开始。没有 M14 run 时只能生成 insufficient skeleton 和 blocker issue，不能绕过 M14 去 M12/M13 拼报告结论。

### 8.3 输入完整性检查

repository 或 input loader 必须识别：

- M14 selection run 缺失。
- M14 三槽位全空。
- M14 selection 有入选但缺证据卡必要字段。
- M13 explanation 缺失。
- evidence id 无法回溯到 M02。
- target profile 缺失。
- 结构化卖点缺失风险未被 M14/M13 标注。
- M14 audit 为空。
- M14 review issue 未被带入报告。

这些情况不能静默跳过，必须进入 report readiness、guardrail result 或 report review issue。

### 8.4 写入策略

`replace_current_report_results` 必须在单事务内完成：

1. 按业务键将旧 current evidence card 置 `is_current=false`。
2. 将旧 current target report payload 置 `is_current=false`。
3. 将旧 current report section 置 `is_current=false`。
4. 将旧 current report export 置 `is_current=false`。
5. 将旧 current report review issue 置 `is_current=false`，但保留 M16 resolution 字段历史。
6. 插入新 evidence cards。
7. 插入新 report payload。
8. 插入新 report sections。
9. 插入新 exports。
10. 插入新 review issues。

事务要求：

- 不允许前端看到只有 payload 没有 section 的半成品。
- 不允许导出内容与页面 payload 版本不一致。
- 不允许 current report payload 指向旧 evidence card。
- 不允许 business report API 返回未通过 guardrail 的 ready 状态。

### 8.5 fingerprint 和 hash

目标报告 `input_fingerprint`：

```text
hash(
  project_id,
  category_code,
  batch_id,
  target_sku_code,
  selection_run_id,
  m14_selection_result_hash,
  m13_explanation_fingerprint,
  m12_audit_fingerprint,
  m08_to_m115_summary_fingerprint,
  evidence_revision,
  report_rule_version
)
```

`result_hash`：

```text
hash(
  executive_conclusion_cn,
  core_competitors_json,
  empty_slots_json,
  evidence_matrix_json,
  sop_trace_json,
  candidate_pool_summary_json,
  readiness_level,
  ui_guardrail_result_json
)
```

导出 `checksum`：

```text
hash(export_payload)
```

`page_payload_hash`：

```text
hash(core3_target_report_payload.export_payload_json)
```

### 8.6 repository 测试

必须测试：

- 没有 M14 run 时不读 M12/M13 拼结论。
- 读取 M14 current run、selection、slot、audit、issue。
- 读取 M13 component explanation 生成证据矩阵。
- evidence id 可回溯到 M02 atom。
- replace current 在单事务内写五类结果。
- 重跑后旧记录 `is_current=false`，新记录 `is_current=true`。
- 导出 checksum 与页面 payload hash 可比对。
- 不读取原始四表。

## 9. service 任务

### 9.1 主服务

新增 `EvidenceReportService`：

```text
run_target_report(context, target_sku_code, rule_version="m15_evidence_report_v1") -> ReportRunResult
run_batch_reports(context, target_scope) -> ReportBatchResult
get_target_report(context, target_sku_code, selection_run_id=None) -> TargetReportPayload
get_evidence_cards(context, target_sku_code, selection_run_id=None) -> list[EvidenceCard]
get_report_sections(context, target_sku_code, selection_run_id=None) -> list[ReportSection]
get_report_export(context, target_sku_code, export_type, selection_run_id=None) -> ReportExport
resolve_short_evidence_ref(context, target_sku_code, short_ref) -> EvidenceTrace
get_report_quality(context, target_sku_code, selection_run_id=None) -> ReportQualityResult
```

### 9.2 处理流程

M15 service 必须按以下步骤执行：

1. 读取 `run_context`：`project_id`、`category_code`、`batch_id`、`run_id`、目标 SKU、`rule_version`。
2. 读取 M14 current selection run。
3. 缺 M14 run 时生成 insufficient skeleton、`missing_selection_run` blocker 和基础 data quality section。
4. 读取 M14 selections、slot decisions、audit、review issues。
5. 读取入选候选对应 M13 component score、role score、component explanation。
6. 读取 M12 candidate pool summary 和 recall reason。
7. 读取目标和竞品 M08-M11.5 摘要。
8. 汇总所有 evidence id，读取 M02 evidence atom 和状态。
9. 生成短证据编号。
10. 为每个入选竞品生成证据卡。
11. 生成页面 section。
12. 聚合生成 target report payload。
13. 生成 JSON、Markdown、汇报摘要、证据卡导出。
14. 执行主屏护栏检查。
15. 生成 report review issue。
16. 同事务写入五张 M15 输出表。
17. 发布 M16 验收影响。

### 9.3 证据短编号规则

短编号格式：

```text
市场证据 01
参数证据 03
评论证据 08
卖点证据 02
任务证据 01
战场证据 02
```

编号排序：

1. 入选核心竞品卡用到的证据。
2. 价格、渠道、参数、卖点、市场、评论。
3. 任务、客群、战场推导。
4. 候选池未选原因。

短编号映射必须保存：

- `short_ref`
- `evidence_id`
- `evidence_domain`
- `display_summary_cn`
- `source_table_cn`
- `source_time_window`
- `raw_trace_allowed`

主屏只显示 `short_ref` 和摘要。技术追溯 API 才能通过短编号回查 `core3_evidence_atom`。

### 9.4 证据卡生成

每个 M14 入选竞品必须生成一张 evidence card。

证据卡必须包含：

- 竞品角色。
- 竞品型号。
- 主要战场。
- 竞争压力。
- 一句话理由。
- 五维证据：价格、渠道、参数、卖点、市场/评论。
- 关键差异：目标优势和竞品优势。
- 策略含义。
- 置信度。
- 风险说明。
- 短证据编号。

每张卡最多展示 5-7 条关键证据。证据明细默认收起。

### 9.5 report section 生成

每个目标必须生成以下 section：

| section_code | 默认状态 | 要求 |
| --- | --- | --- |
| `executive` | visible | 先展示核心竞品结论 |
| `target_profile` | visible | 目标 SKU 信号摘要 |
| `competitor_cards` | visible | 三槽位主视觉，包含空槽卡 |
| `battlefield_context` | visible | 目标竞争语境 |
| `why_competitor` | visible | 为什么是竞品的业务推导 |
| `evidence_matrix` | collapsed | 证据强弱和来源 |
| `strategy` | visible | 关键差异和策略含义 |
| `candidate_audit` | collapsed | 候选池与未选原因 |
| `sop_trace` | collapsed | 7 步 SOP 推导 |
| `data_quality` | collapsed | 样例范围、缺口和复核 |
| `export` | visible | 导出入口 |

`sop_trace` 只能展示 7 步中文名称：

```text
① SKU 信号画像
② 用户任务识别
③ 目标客群判断
④ 价值战场判定
⑤ 候选池召回
⑥ 组件评分
⑦ 三槽位选择
```

不得在 SOP trace 中展示完整 M00-M16、SQL、公式、JSON 或模型过程。

### 9.6 高层结论生成

高层结论由 M14 入选结果驱动：

| M14 结果 | 表达 |
| --- | --- |
| 3 个高置信竞品 | 当前识别出 3 个核心竞品，分别代表... |
| 2 个高置信竞品 | 当前识别出 2 个高置信核心竞品，另有 1 个槽位暂无高置信候选... |
| 1 个高置信竞品 | 当前只有 1 个高置信核心竞品，其余方向需要补充数据或复核... |
| 0 个竞品 | 当前数据不足以形成高置信核心竞品结论... |

不能为了形成完整话术补写不存在的竞品。

### 9.7 置信语气规则

| 置信度 | 允许话术 | 禁止话术 |
| --- | --- | --- |
| high | 识别为、主要竞争压力来自 | 可能也许 |
| medium | 倾向判断为、需要业务复核 | 确定是 |
| low | 当前仅作为候选参考 | 核心竞品是 |
| insufficient | 当前数据不足以判断 | 系统已确认 |

### 9.8 中文业务语言转换

主屏必须把内部字段转换为中文业务语言：

| 内部字段 | 页面表达 |
| --- | --- |
| `direct_fight` | 正面对打竞品 |
| `price_volume_pressure` | 价格/销量挤压竞品 |
| `benchmark_potential` | 高端标杆/潜在下探竞品 |
| `battlefield_fit_score` | 价值战场重合度 |
| `task_overlap_score` | 用户任务重合度 |
| `evidence_id` | 证据编号 |
| `sample_status=insufficient` | 样本不足，需复核 |
| `review_required` | 需要业务复核 |

业务报告 API 不返回内部字段，技术追溯 API 可单独返回。

### 9.9 主屏护栏

`ReportGuardrailChecker` 必须扫描业务展示 payload、section 和导出摘要。

发现以下内容写 blocker 或 review：

| 检查 | 触发 | issue |
| --- | --- | --- |
| 内部字段 | `core3_`、`candidate_`、`_score`、`_json`、`_id`、表名 | `internal_field_exposed` |
| UUID/hash | UUID 正则或 sha256 明文 | `uuid_exposed` |
| SQL | 出现 SQL 或 select/join/from 技术片段 | `internal_field_exposed` |
| AI 过程 | AI 认为、模型判断、生成过程、正在思考 | `sop_trace_too_technical` |
| 完整技术链路 | 主屏出现 M00-M16 | `sop_trace_too_technical` |
| 低置信确定语气 | low/insufficient 但出现“确定”“已确认” | `tone_confidence_mismatch` |
| 数据范围缺失 | 缺 `26W01-26W23`、线上、样例数据范围 | `missing_data_scope_note` |
| 卖点缺口未披露 | 85E7Q 缺结构化卖点但报告未提示 | `claim_gap_not_disclosed` |
| 服务写成核心竞争力 | 服务安装售后被写成产品核心结论 | `service_as_core_claim` |
| 导出不一致 | export hash 与 page payload hash 不一致 | `export_payload_mismatch` |

UUID 正则：

```text
[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}
```

### 9.10 导出生成

M15 首版导出四类：

| export_type | 内容 |
| --- | --- |
| `json` | 完整结构化 payload |
| `markdown` | 单 SKU 竞品分析报告草稿 |
| `report_summary` | 可复制汇报摘要 |
| `evidence_cards` | 核心竞品证据卡集合 |

导出规则：

- 导出不得重新生成业务事实，只能从 `core3_target_report_payload` 和 `core3_evidence_card` 派生。
- 导出内容必须包含数据范围说明。
- Markdown 导出必须保留“当前样例数据内”的口径。
- 导出不得出现 UUID、内部字段或 AI 过程文案。
- 导出 checksum 必须可与页面 payload hash 比对。

### 9.11 report review issue 生成

M15 必须生成以下复核问题：

| issue_type | 触发 |
| --- | --- |
| `missing_selection_run` | M14 没有选择运行 |
| `all_slots_empty` | M14 三个槽位都为空 |
| `missing_evidence_card_field` | 入选竞品证据卡必要字段缺失 |
| `missing_evidence` | 入选结论没有 evidence 或缺失原因 |
| `internal_field_exposed` | 主屏出现英文内部字段、表名或 code |
| `uuid_exposed` | 主屏出现 UUID/hash |
| `tone_confidence_mismatch` | 低置信使用确定语气 |
| `missing_data_scope_note` | 数据范围说明缺失 |
| `claim_gap_not_disclosed` | 结构化卖点缺失但报告未提示 |
| `service_as_core_claim` | 服务体验被写成产品核心竞争力 |
| `missing_candidate_audit` | 候选池未选原因缺失 |
| `export_payload_mismatch` | 导出 payload 与页面 payload 不一致 |
| `sop_trace_too_technical` | SOP 推导出现 M00-M16、SQL、公式或内部过程 |

### 9.12 service 测试

必须测试：

- 缺 M14 run 时生成 insufficient skeleton 和 blocker。
- M14 有 N 个入选时生成 N 张证据卡。
- M14 有空槽时 payload 有空槽原因。
- 业务 report API 不出现 UUID。
- 业务 report API 不出现内部字段。
- 低置信使用复核语气。
- 85E7Q 缺结构化卖点时写宣传卖点数据缺口。
- 服务证据不生成产品核心防守结论。
- 导出内容与页面 payload 一致。
- SOP trace 只包含 7 步中文业务轨迹。

## 10. runner/API 任务

### 10.1 runner

新增 `evidence_report_runner.py`，并在 `runner.py` 注册 `M15`。

M16 调用形态：

```text
Core3ModuleRunner.run("M15", run_context, target_scope)
```

`target_scope` 支持：

| Scope | 含义 |
| --- | --- |
| `all_targets` | 批次内全部目标 |
| `target_sku_list` | 指定目标 |
| `changed_targets` | M14/M13/evidence 变化影响的目标 |

runner 输出：

```json
{
  "module_code": "M15",
  "status": "success",
  "input_count": 1,
  "output_count": 1,
  "evidence_card_count": 2,
  "section_count": 11,
  "export_count": 4,
  "review_issue_count": 0,
  "output_hash": "sha256...",
  "warnings": [],
  "downstream_impacts": ["M16"]
}
```

### 10.2 业务展示 API

在 `apps/api-server/app/api/core3_real_data.py` 增加业务展示 API：

| API | 方法 | 用途 |
| --- | --- | --- |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku_or_model}/report` | GET | 单 SKU 高层报告 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku_or_model}/evidence-cards` | GET | 核心竞品证据卡 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku_or_model}/report/sections` | GET | 页面 section |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku_or_model}/exports/{export_type}` | GET | 报告导出 |

业务 API 要求：

- 只返回中文业务字段和结构化展示 payload。
- 不返回原始 UUID、内部字段、SQL、技术表名。
- 不返回大段内部 JSON。
- 不返回 AI 过程文案。
- 缺 M15 current payload 时返回清晰的中文空状态。

### 10.3 技术追溯 API

新增技术追溯 API：

| API | 方法 | 用途 |
| --- | --- | --- |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/evidence-ref/{short_ref}` | GET | 短证据编号回溯 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/report-quality` | GET | 报告护栏检查结果 |
| `/api/mvp/core3/v2/projects/{project_id}/targets/{sku}/report/run` | POST | 触发目标报告生成 |

技术追溯 API 可以返回 evidence ID，但必须与业务 report API 分离。

### 10.4 增量和失效

M15 变化需要登记下游影响：

| 变化来源 | M15 动作 | 下游影响 |
| --- | --- | --- |
| M14 选择结果变化 | 重建证据卡、section、payload、导出 | M15/M16 |
| M14 空槽或审计变化 | 更新空槽说明和候选池未选原因 | M15/M16 |
| M13 组件解释变化 | 更新证据矩阵、关键差异、策略提示 | M15/M16 |
| M12 候选召回理由变化 | 更新候选池摘要和 SOP trace | M15/M16 |
| M08-M11.5 画像和推导变化 | 更新目标语境、任务、客群、战场、卖点摘要 | M15/M16 |
| M02 evidence 状态变化 | 更新短证据编号、证据明细、置信度和风险 | M15/M16 |
| 报告规则变化 | 按新 `rule_version` 重建报告 | M15/M16 |

### 10.5 runner/API 测试

必须测试：

- runner 可按 `target_sku_list` 只处理指定目标。
- runner 对缺 M14 run 的目标返回 insufficient，不抛未处理异常。
- runner output_count 与 report payload 行数一致。
- runner evidence_card_count 与 M14 入选数量一致。
- API report 返回中文主报告。
- evidence-cards API 返回证据卡，不含 UUID。
- sections API 返回 section 顺序和 display_status。
- exports API 返回指定导出内容。
- evidence-ref API 可以通过短证据编号回溯。
- report-quality API 返回护栏检查结果。
- 业务 API 不返回原始四表明细。

## 11. 测试任务

### 11.1 schema 和 input loader

`test_m15_evidence_report_schemas.py`：

- readiness level、section code、display status、export type、issue type 枚举完整。
- evidence card response 含中文字段。
- report payload response 含 `executive_conclusion_cn` 和 `data_scope_note_cn`。
- business response 不包含 UUID-only evidence。
- export response 含 checksum 和 page payload hash。

`test_m15_report_input_loader.py`：

- 缺 M14 run 时返回 missing selection 状态。
- 读取 M14 selection、slot、audit、issue。
- 读取 M13 component explanation。
- 读取 M08-M11.5 trace summary。
- 读取 M02 evidence atom。
- 不读取原始四表。

### 11.2 短证据、证据卡和 section

`test_m15_evidence_short_ref_service.py`：

- evidence UUID 转短编号。
- 短编号按证据类型和优先级稳定排序。
- 同一报告版本内短编号稳定。
- short ref 可回溯 evidence atom。
- 主屏 payload 不暴露 UUID。

`test_m15_evidence_card_builder.py`：

- 每个入选竞品生成一张证据卡。
- 0 个入选时不生成卡，但不报错。
- 证据卡包含价格、渠道、参数、卖点、市场/评论摘要。
- 每张卡最多展示 5-7 条关键证据。
- 缺 evidence 时必须写缺失原因。
- 服务证据不能写成产品核心竞争结论。

`test_m15_report_section_builder.py`：

- 生成 11 个 section。
- executive、target_profile、competitor_cards、battlefield_context、why_competitor、strategy、export 默认 visible。
- evidence_matrix、candidate_audit、sop_trace、data_quality 默认 collapsed。
- sop_trace 只包含 7 步中文名称。
- section 不包含内部字段和 UUID。

### 11.3 payload、导出和护栏

`test_m15_target_report_payload_builder.py`：

- 第一屏先展示核心竞品数量和三槽位状态。
- 0/1/2/3 个竞品分别生成不同高层结论语气。
- 空槽有原因和复核建议。
- 候选池未选原因进入 collapsed section。
- data quality note 包含样例数据范围。

`test_m15_report_export_builder.py`：

- 生成 json、markdown、report_summary、evidence_cards 四类导出。
- 导出来自页面 payload，不重新生成事实。
- Markdown 包含数据范围说明。
- 导出不含 UUID、内部字段和 AI 过程文案。
- checksum 可校验。

`test_m15_report_guardrail_checker.py`：

- payload 含 `core3_`、`_score`、`_json`、`_id` 写 `internal_field_exposed`。
- payload 含 UUID 写 `uuid_exposed`。
- payload 含 SQL 写 blocker。
- payload 含 AI 过程文案写 review。
- low/insufficient 置信使用确定语气写 `tone_confidence_mismatch`。
- 缺数据范围写 `missing_data_scope_note`。
- SOP trace 超过 7 步或出现 M00-M16 写 `sop_trace_too_technical`。

`test_m15_report_review_issue_builder.py`：

- 缺 M14 run 写 `missing_selection_run` blocker。
- 三槽位全空写 `all_slots_empty` review。
- 证据卡必要字段缺失写 `missing_evidence_card_field`。
- 入选结论无 evidence 写 `missing_evidence`。
- 85E7Q 卖点缺口未披露写 `claim_gap_not_disclosed`。
- 服务体验写成核心竞争力写 `service_as_core_claim`。
- 导出不一致写 `export_payload_mismatch`。

### 11.4 repository、service、runner、API

`test_m15_evidence_report_repositories.py`：

- current evidence card 唯一。
- current payload 唯一。
- current section 唯一。
- current export 唯一。
- replace current 保留历史。
- 导出 hash 与 page payload 可比对。

`test_m15_evidence_report_service.py`：

- 正常 M14 输入生成 report、cards、sections、exports。
- 缺 M14 run 生成 insufficient skeleton。
- 三槽位全空时报告 readiness 为 review_required 或 insufficient。
- 主屏无内部字段、UUID、AI 过程文案。
- M16 可读取 report review issue。

`test_m15_runner.py`：

- 支持 all_targets、target_sku_list、changed_targets。
- 失败目标不会阻断其他目标运行。
- summary 包含 evidence_card_count、section_count、export_count、review_issue_count。

`test_m15_api.py`：

- report API 返回单 SKU 高层报告。
- evidence-cards API 返回卡片。
- sections API 返回 11 个 section。
- exports API 返回指定导出。
- evidence-ref API 回溯短证据。
- report-quality API 返回护栏结果。

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

### 12.2 85E7Q 报告断言

以 `TV00029115` / `85E7Q` 为目标，M15 必须验证：

| 断言 | 要求 |
| --- | --- |
| 第一屏 | 先展示核心竞品数量和三槽位状态 |
| 同品牌说明 | 写当前样例数据内的同品牌内部竞争，不写外部品牌对抗 |
| 数据范围 | 写 `26W01-26W23` 线上样例数据 |
| 平台口径 | 写专业电商/平台电商或线上平台重合，不写线下 |
| 正面对打解释 | 包含双方战场、价格/尺寸/渠道、卖点价值 |
| 价格挤压解释 | 包含价格、销量、趋势或门槛体验 |
| 高端标杆解释 | 包含参数/卖点优势、销额或下探风险 |
| 卖点缺失 | 写“宣传卖点数据缺口”，不能写“卖点弱” |
| 服务评论 | 只作为服务侧证据或风险，不作为产品核心入选主因 |
| 空槽 | 有空槽原因和复核建议，不补弱候选 |
| 候选未选原因 | collapsed 候选池 section 可解释未选原因 |
| 证据短编号 | 主屏显示短证据编号，不显示 UUID |
| 主屏语言 | 无英文内部字段、无 UUID、无 SQL、无 AI 过程文案 |
| SOP trace | 只展示 7 步业务推导 |

### 12.3 85E7Q 文案示例

M15 输出可以包含类似中文表达：

- “在当前样例数据内，85E7Q 识别出若干核心竞品，分别代表不同竞争压力；未选满的槽位已列出空槽原因和复核建议。”
- “当前数据范围为 26W01-26W23 线上周数据，平台主要覆盖专业电商和平台电商，因此本报告不代表全市场结论。”
- “当前样例数据均为海信型号，本次识别的是同品牌内部的同价位、同战场或同系列竞争关系。”
- “85E7Q 缺结构化卖点记录，本次以参数、评论和市场证据补充判断，宣传证据仍需复核。”
- “服务体验只作为服务侧证据或风险，不作为产品核心竞品入选主因。”

M15 不需要在开发任务阶段预设 85E7Q 的最终三竞品名单。验收重点是：M14 给出任何入选、未选或空槽结果，M15 都能用业务语言解释清楚并可追溯证据。

## 13. 完成标准

M15 编码完成必须满足：

1. 五张 M15 表 migration 可执行，downgrade 不影响 M00-M14 表。
2. 所有 M15 表包含 project、category、batch/run、selection_run_id、rule_version、input_fingerprint、result_hash、is_current、审计时间。
3. M15 只消费 M14/M13/M12/M08-M11.5/M02 current 结果。
4. M15 不直接读取原始四表。
5. M15 不重新选择竞品。
6. M15 不重新计算 M13/M14 分数。
7. 每个 M14 入选竞品生成一张 evidence card。
8. M14 入选数为 0 时仍生成 insufficient 或 review report skeleton。
9. 每个目标生成 `core3_target_report_payload`。
10. 每个目标生成 11 个 report section。
11. 报告第一屏先展示核心竞品结论。
12. 每个入选竞品有业务角色卡。
13. 每个入选竞品解释为什么是竞品。
14. 证据卡可追溯 evidence。
15. 主屏无英文内部字段。
16. 主屏无 UUID/hash。
17. 主屏无 SQL、公式、大段 JSON。
18. 主屏无 AI 过程文案。
19. 报告说明数据覆盖范围和缺口。
20. SOP 推导链只展示 7 步。
21. 候选池未选原因可展开。
22. 空槽有原因和复核建议。
23. 低置信有提示。
24. 服务证据不替代产品核心竞争结论。
25. 85E7Q 卖点缺失正确表达为宣传卖点数据缺口。
26. 当前样例数据不冒充全市场。
27. 支持 JSON/Markdown/汇报摘要/证据卡导出。
28. 导出内容与页面 payload 一致。
29. M16 可读取 M15 report review issue。
30. pytest 覆盖 schema、input loader、short ref、card、section、payload、export、guardrail、review issue、repository、service、runner、API、85E7Q fixture。

## 14. 风险和回滚

### 14.1 主要风险

| 风险 | 表现 | 控制 |
| --- | --- | --- |
| 报告层重做选择 | M15 绕过 M14 补竞品 | 缺 M14 run 只能 skeleton |
| 报告编造事实 | 写入无 evidence 结论 | 缺 evidence 写 blocker 或缺口 |
| 高层主屏技术化 | 出现字段、UUID、SQL、公式 | guardrail blocker |
| AI 感过重 | 出现 AI、模型、生成过程文案 | guardrail review |
| 语气过度确定 | 低置信写成已确认 | tone guardrail |
| 样例冒充全市场 | 未写当前样例范围 | data scope blocker |
| 卖点缺失误判 | 写成 85E7Q 卖点弱 | 固定为宣传卖点数据缺口 |
| 服务信号误用 | 服务评论写成核心竞争 | service guardrail |
| 导出与页面不一致 | 导出重新生成事实 | 导出从 payload 派生并校验 hash |
| 前端重复拼业务逻辑 | 页面自行解释竞品 | M15 输出完整 section payload |

### 14.2 回滚策略

- migration downgrade 只删除 M15 五张表。
- 不影响 M00-M14 运行。
- 不影响旧 `core3_mvp`。
- 回滚后 M16 应标记报告不可展示。
- 回滚后前端只能展示 M14 三槽位选择技术结果，不能展示 M15 高层报告。

### 14.3 降级策略

- M14 run 缺失：生成 insufficient skeleton 和 `missing_selection_run` blocker。
- M14 三槽位全空：生成报告，但 readiness 为 review_required 或 insufficient。
- evidence 缺失：卡片或 section 写证据缺口，并生成 `missing_evidence` issue。
- guardrail 未通过：报告可保存，但 readiness 降级，不允许标记 ready。
- 导出失败：页面 payload 仍可用，`core3_report_export` 写 failed。

## 15. 下游依赖

### 15.1 M16 增量编排、复核和验收依赖

M16 必须以以下表为主输入：

- `core3_target_report_payload`
- `core3_evidence_card`
- `core3_report_section`
- `core3_report_export`
- `core3_report_review_issue`

M16 使用：

- report readiness。
- evidence card completeness。
- section completeness。
- export status。
- report review issue。
- input_fingerprint 和 result_hash。
- M15 downstream impact。

M16 不生成报告内容，只验收 M15 的报告成熟度、证据完整度、导出一致性和复核问题状态。

### 15.2 API 聚合依赖

后续 API 聚合任务应复用 M15 的业务展示 API，不能在 API 聚合层重新拼高层结论。

API 聚合可以汇总：

- 目标列表。
- 报告 readiness。
- 核心竞品摘要。
- 待复核数量。
- 导出状态。

但不能重新生成：

- 为什么是竞品。
- 证据卡。
- SOP trace。
- 候选未选原因。

### 15.3 前端页面依赖

前端页面必须消费 M15 的 section payload 和 evidence card payload：

- 前端不重新选择竞品。
- 前端不重新计算证据强度。
- 前端不把 UUID、内部字段、SQL、JSON 大段展示在主屏。
- 前端保持 M15 定义的顺序：先结论、再竞品卡、再为什么、再证据、再候选和 SOP trace。
- 前端需要保留空槽、复核、数据范围和证据缺口表达。

## 16. 建议开发子任务拆分

| 子任务 | 范围 |
| --- | --- |
| D15-01 | Alembic 新增 M15 五张表、约束和索引 |
| D15-02 | M15 enums、短证据、report、card、section、export、issue Pydantic schema |
| D15-03 | `EvidenceReportRepository` 读取上游和写 M15 current 结果 |
| D15-04 | `ReportInputLoader` 输入完整性校验 |
| D15-05 | `EvidenceShortRefService` 短证据编号和回溯 |
| D15-06 | `EvidenceCardBuilder` 核心竞品证据卡 |
| D15-07 | `ReportSectionBuilder` 11 个页面 section |
| D15-08 | `TargetReportPayloadBuilder` 单 SKU 高层报告 payload |
| D15-09 | `ReportExportBuilder` JSON/Markdown/摘要/证据卡导出 |
| D15-10 | `ReportGuardrailChecker` 主屏质量护栏 |
| D15-11 | `ReportReviewIssueBuilder` 报告复核问题 |
| D15-12 | `EvidenceReportService` 编排和事务写入 |
| D15-13 | M15 runner 和业务/追溯 API |
| D15-14 | 单元、集成、API、导出一致性和 85E7Q fixture 回归测试 |

编码阶段如果任务过大，应按 D15 子任务继续拆小；每次编码只做一个小闭环。

## 17. 下次任务

下一个开发任务文档：

```text
docs/core3_mvp/real_data_v2/development/M16_development_tasks.md
```

M16 增量任务编排、复核和验收模块必须以 M15 的 report payload、evidence card、section、export 和 review issue 为输入，判断报告是否达到可展示、可导出、可复核和可发布要求。M16 不生成报告内容，只负责调度、增量、复核队列、验收门禁和发布状态。
