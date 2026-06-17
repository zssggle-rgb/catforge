# API 聚合和接口验收开发任务

## 1. 模块目标

API 开发任务的目标是为 CatForge 彩电核心三竞品真实数据 v2 提供一套独立、稳定、可测试的后端接口层。这个接口层面向两个使用场景：

1. 业务高层展示页：读取 M15 已生成的业务报告、证据卡、推导摘要和 M16 发布门禁，用中文业务语言展示核心竞品是谁、为什么是它们、证据是否充分。
2. 运营生产线状态页：读取 M16 运行、模块状态、复核队列、验收报告和发布门禁，支撑数据运营人员判断当前结果是否可发布。

API 层必须回答的问题是：

1. 当前项目和品类有没有可用真实数据。
2. 用户输入的型号或 SKU 能否解析到唯一目标 SKU。
3. 当前目标 SKU 是否已有可展示的核心三竞品报告。
4. 目标 SKU 的核心竞品、竞争角色、关键理由、证据卡和数据范围说明是什么。
5. 报告是否可汇报、需复核、不可发布或已发布。
6. 业务页面需要的批量总览、目标列表、报告详情、证据卡、导出内容如何一次性读取。
7. 技术追溯页面如何通过短证据编号查回 evidence，而不把 UUID 暴露给高层主屏。
8. 生产线状态、复核、验收和门禁如何通过 API 查询和处理。

API 层要解决的工程问题：

1. 新建真实数据 v2 独立 API 路由，不复用旧 `core3_mvp` 粗粒度接口。
2. 新建 Pydantic response schema，把 M15/M16 内部字段映射成前端可直接消费的中文业务 payload。
3. 建立只读聚合 repository，读取 M00-M16 结果表，但不重新生成业务结论。
4. 建立 query service，把 M15 报告产物和 M16 门禁状态组合成页面 API。
5. 建立 response guardrail，阻止业务展示 API 返回内部字段、UUID、SQL、JSON 大段和 AI 过程文案。
6. 建立技术追溯 API，与业务展示 API 分离。
7. 建立复核和发布动作 API，写入 M16 决策和发布状态，不直接改 M00-M15 事实表。
8. 为 85E7Q 和 205 样例数据建立 API fixture 验收。

API 层必须固化以下边界：

- API 不做清洗、证据生成、抽取、画像、评分、选择或报告生成。
- API 不直接读取原始四表拼业务页面。
- API 不在前端请求时临时拼竞品算法结果。
- API 不把 M00-M16 完整技术链路返回给高层主屏。
- API 不把 `evidence_id`、UUID、hash、SQL、内部表名、字段名、英文枚举暴露在业务展示 response。
- API 不把 blocked 或 review_required 的报告伪装成 ready。
- API 不修改旧 `core3_mvp` 接口语义。
- API 不实现前端页面，也不部署 205。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M15 开发任务 | `docs/core3_mvp/real_data_v2/development/M15_development_tasks.md` |
| M15 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M15_evidence_report_design.md` |
| M16 开发任务 | `docs/core3_mvp/real_data_v2/development/M16_development_tasks.md` |
| M16 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M16_incremental_review_acceptance_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| UI 规范 | `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md` |
| SOP 方法论 | `cankao/CatForge_竞品生成SOP_详细指导_v1.md` |
| 现有旧接口参考 | `apps/api-server/app/api/core3_mvp.py`、`apps/api-server/app/schemas/core3_mvp.py` |

编码前必须确认：

- `apps/api-server/app/services/core3_real_data/` 已由 INFRA 和 M00-M16 任务建立。
- M15 已提供 `core3_target_report_payload`、`core3_evidence_card`、`core3_report_section`、`core3_report_export`、`core3_report_review_issue`。
- M16 已提供 `core3_pipeline_run`、`core3_module_run`、`core3_review_queue`、`core3_acceptance_report`、`core3_release_gate`、`core3_pipeline_watermark`。
- M00/M01 已提供目标 SKU 可解析的清洗主数据或 SKU registry。
- M02 已提供 evidence atom，且短证据编号由 M15 生成。
- 高层展示 API 只读取 M15/M16 的 display payload，不直接读 M12-M14 拼结论。

## 3. 本次范围

本次开发任务拆分覆盖真实数据 v2 API 层实现准备：

| 范围 | 说明 |
| --- | --- |
| 路由 | 新增 `core3_real_data.py` router，使用 `/api/mvp/core3/v2` 前缀 |
| schema | 新增业务展示、证据追溯、生产线状态、复核、验收、门禁 response schema |
| repository | 新增只读聚合 repository，读取 M00-M16 产物，写操作只委托 M16 |
| query service | 新增数据状态、SKU 解析、总览、目标列表、单品报告、证据卡、导出、生产线状态查询 |
| response mapper | 把内部状态、枚举和表字段转换成中文业务字段 |
| response guardrail | 扫描业务展示 response，阻断内部字段、UUID、SQL、AI 过程文案泄露 |
| 复核动作 | 通过 M16 review service 提交复核决策 |
| 发布动作 | 通过 M16 release gate service 标记发布 |
| 错误处理 | 统一 400/404/409/422/423/500 中文错误 |
| 测试 | schema、route、service、repository、guardrail、85E7Q fixture 和前端契约测试 |

本次不做：

- 不新增业务分析表。
- 不写 Alembic migration。
- 不改 M00-M16 算法服务。
- 不实现前端页面。
- 不部署到 205。
- 不修改旧 `apps/api-server/app/api/core3_mvp.py` 的接口行为。
- 不为了 API 方便把内部字段直接透传给前端。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/api_repositories.py
apps/api-server/app/services/core3_real_data/api_response_schemas.py
apps/api-server/app/services/core3_real_data/api_response_mapper.py
apps/api-server/app/services/core3_real_data/api_response_guardrail.py
apps/api-server/app/services/core3_real_data/sku_resolution_service.py
apps/api-server/app/services/core3_real_data/overview_query_service.py
apps/api-server/app/services/core3_real_data/business_report_query_service.py
apps/api-server/app/services/core3_real_data/evidence_trace_query_service.py
apps/api-server/app/services/core3_real_data/pipeline_status_query_service.py
apps/api-server/app/services/core3_real_data/review_action_api_service.py
apps/api-server/app/services/core3_real_data/export_delivery_service.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `api_repositories.py` | 读取 M00-M16 表的聚合 repository；写操作只代理 M16 复核/发布 |
| `api_response_schemas.py` | API 内部 DTO 和 mapper 输入输出契约 |
| `api_response_mapper.py` | 把 M15/M16 内部记录映射为中文业务 response |
| `api_response_guardrail.py` | 扫描业务 response，防止内部信息泄露 |
| `sku_resolution_service.py` | 通过 M00/M01 清洗主数据解析型号或 SKU |
| `overview_query_service.py` | 批量总览、目标列表、数据范围和 KPI 查询 |
| `business_report_query_service.py` | 单品报告、核心竞品、证据卡、报告 section 查询 |
| `evidence_trace_query_service.py` | 短证据编号到 evidence atom 的技术追溯 |
| `pipeline_status_query_service.py` | 生产线 run、module、plan、acceptance、gate 查询 |
| `review_action_api_service.py` | 复核决策、返工触发和发布标记的 API 封装 |
| `export_delivery_service.py` | 读取 M15 导出产物，返回 markdown/json/summary/evidence cards |

### 4.2 允许修改的共享文件

```text
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/main.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `core3_real_data.py` API | 新增 `/api/mvp/core3/v2` 路由 |
| `core3_real_data.py` schema | 导出 API request/response schema |
| `main.py` | 注册 `core3_real_data.router` |
| `constants.py` | 补 API section、业务状态、中文状态文案、禁用字段规则 |
| `conftest.py` | 增加 API fixture、85E7Q report fixture、M16 gate fixture |

如果 `core3_real_data.py` schema 已在前序任务中存在，本任务只能追加 API schema，不重写上游模块 schema。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_api_schema_contract.py
apps/api-server/tests/core3_real_data/test_api_sku_resolution.py
apps/api-server/tests/core3_real_data/test_api_overview.py
apps/api-server/tests/core3_real_data/test_api_business_report.py
apps/api-server/tests/core3_real_data/test_api_evidence_cards.py
apps/api-server/tests/core3_real_data/test_api_evidence_trace.py
apps/api-server/tests/core3_real_data/test_api_pipeline_status.py
apps/api-server/tests/core3_real_data/test_api_review_actions.py
apps/api-server/tests/core3_real_data/test_api_export_delivery.py
apps/api-server/tests/core3_real_data/test_api_response_guardrail.py
apps/api-server/tests/core3_real_data/test_api_route_registration.py
apps/api-server/tests/core3_real_data/test_api_85e7q_fixture.py
```

## 5. 不允许改文件

本任务开发时不得修改以下范围：

```text
apps/factory-web/
apps/web/
apps/api-server/app/api/core3_mvp.py
apps/api-server/app/schemas/core3_mvp.py
apps/api-server/app/services/core3_mvp/
apps/api-server/alembic/versions/
docs/core3_mvp/real_data_v2/sop_requirements/
docs/core3_mvp/real_data_v2/sop_detailed_design/
cankao/
```

不得修改的业务逻辑：

- M00-M16 的数据处理、抽取、画像、候选、评分、选择、报告和门禁算法。
- M15 report payload、evidence card、section、export 的生成规则。
- M16 review、acceptance、release gate 的门禁规则。
- 旧 `core3_mvp` API、schema 和 service 的兼容行为。
- 原始四表结构和导入逻辑。

不得引入的行为：

- API 请求实时计算竞品选择。
- API 请求实时拼 evidence 或绕过 M15 证据卡。
- API 从原始四表读取后直接给前端展示。
- API 透传 `display_payload_json` 中未经 guardrail 检查的内容。
- 业务展示 API 返回 UUID、hash、表名、字段名、SQL、内部英文枚举或大段 JSON。
- 业务展示 API 返回“AI 认为”“模型判断”“生成过程”等过程文案。
- blocked 报告在业务主屏以正常报告形式返回。

## 6. 数据库任务

### 6.1 migration

API 层首版不新增表，不写 migration。

理由：

1. M15 已负责报告、证据卡、section 和 export 的落表。
2. M16 已负责 run、review、acceptance、release gate 和 watermark 的落表。
3. API 层只做查询聚合、响应映射、动作代理和边界校验。

### 6.2 允许读取的表

| 来源 | 允许读取 |
| --- | --- |
| M00/M01 | SKU registry、清洗 SKU、批次、水位、数据范围摘要 |
| M02 | evidence atom，仅技术追溯 API 可返回 raw evidence 信息 |
| M12-M14 | 原则上不直接读；需要候选审计时优先读取 M15 section 或 report payload |
| M15 | report payload、evidence card、report section、report export、report review issue |
| M16 | pipeline run、module run、review queue、acceptance report、release gate、watermark |

业务展示 API 读取优先级：

```text
M16 release gate
-> M15 target report payload
-> M15 evidence card
-> M15 report section
-> M15 export
-> M00/M01/M16 data scope
```

### 6.3 允许写入的对象

API 层不直接写业务表。以下写操作必须委托 M16 service：

| 动作 | 委托服务 | 写入表 |
| --- | --- | --- |
| 提交复核决策 | `ReviewActionApiService` -> M16 review service | `core3_review_decision`、`core3_review_queue` |
| 标记报告发布 | `ReviewActionApiService` -> M16 release gate service | `core3_release_gate` |
| 启动运行 | `PipelineStatusQueryService` -> M16 pipeline runner | `core3_pipeline_run` 等 M16 表 |

### 6.4 查询性能要求

API 开发时不新增索引，但必须使用 M15/M16 已设计索引：

- 按 `project_id`、`category_code`、`target_sku_code` 查询 report payload。
- 按 `run_id` 查询 module run、acceptance report、release gate。
- 按 `project_id`、`category_code`、`gate_status` 查询目标列表。
- 按 `target_sku_code` 查询 evidence card 和 report section。
- 按 `review_status`、`severity`、`target_sku_code` 查询 review queue。

如果发现现有设计缺索引，本任务只能记录风险；不能在 API 任务里顺手写 migration。

## 7. model/schema 任务

### 7.1 schema 基础规则

`apps/api-server/app/schemas/core3_real_data.py` 中所有 API schema 应使用：

```text
ConfigDict(extra="forbid")
```

业务展示 response 的值必须是中文业务语言。字段名可以保持 API 工程命名，但以下内部字段不得出现在业务展示 response 的任意字符串值里：

```text
core3_
candidate_
component_score
selection_run_id
evidence_id
dependency_hash
output_hash
_json
_id
SQL
select
join
from
AI 认为
模型判断
生成过程
正在思考
```

### 7.2 业务展示 schema

必须定义：

```text
Core3V2DataStatusResponse
Core3V2SkuResolveResponse
Core3V2OverviewResponse
Core3V2TargetListResponse
Core3V2TargetSummaryResponse
Core3V2BusinessReportResponse
Core3V2TargetProfileResponse
Core3V2CoreCompetitorResponse
Core3V2EvidenceCardResponse
Core3V2ReportSectionResponse
Core3V2CandidateAuditResponse
Core3V2DataScopeResponse
Core3V2ReleaseStatusResponse
Core3V2ReviewHintResponse
Core3V2ExportResponse
```

`Core3V2BusinessReportResponse` 必须包含：

| 字段 | 说明 |
| --- | --- |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `target` | 目标 SKU 中文展示信息 |
| `report_title_cn` | 报告标题 |
| `executive_conclusion_cn` | 高层结论 |
| `data_scope` | 数据范围、样例限制、更新时间 |
| `release_status` | 可汇报、需复核、不可发布、已发布 |
| `core_competitors` | 核心竞品卡列表 |
| `why_these_competitors_cn` | 为什么是这些竞品 |
| `battlefield_summary_cn` | 主要价值战场摘要 |
| `evidence_cards` | 业务证据卡，只含短证据编号 |
| `sections` | 可展开 section |
| `candidate_audit` | 候选池和未选原因摘要 |
| `review_hint` | 复核提示 |
| `exports` | 可用导出入口 |

核心竞品卡必须包含中文字段：

| 字段 | 说明 |
| --- | --- |
| `competitor_sku_code` | 竞品 SKU，可作为技术标识显示在小号位置 |
| `competitor_model_name` | 竞品型号 |
| `role_name_cn` | 正面对打竞品/价格销量挤压竞品/高端标杆潜在下探竞品 |
| `one_sentence_reason_cn` | 一句话原因 |
| `battlefield_fit_cn` | 价值战场重合解释 |
| `market_pressure_cn` | 市场压力解释 |
| `key_difference_cn` | 关键差异 |
| `strategy_implication_cn` | 策略含义 |
| `confidence_label_cn` | 高/中/低/需复核 |
| `risk_note_cn` | 风险说明 |
| `evidence_short_refs` | 短证据编号 |

### 7.3 证据追溯 schema

技术追溯 API 必须与业务展示 API 分离。

必须定义：

```text
Core3V2EvidenceTraceResponse
Core3V2EvidenceAtomTraceItem
Core3V2EvidenceSourceLineage
```

技术追溯 response 可以返回：

- `evidence_id`
- `source_type`
- `source_table`
- `raw_row_id`
- `source_file_id`
- `field_name`
- `raw_value`
- `normalized_value`
- `confidence`

但该 response 只能由 `/evidence/{short_ref}/trace` 或等价技术追溯接口返回，不能混入 `/report` 主接口。

### 7.4 生产线治理 schema

必须定义：

```text
Core3V2PipelineRunRequest
Core3V2PipelineRunResponse
Core3V2PipelineRunListResponse
Core3V2ModuleRunResponse
Core3V2RecomputePlanResponse
Core3V2ReviewQueueResponse
Core3V2ReviewDecisionRequest
Core3V2ReviewDecisionResponse
Core3V2AcceptanceReportResponse
Core3V2ReleaseGateResponse
Core3V2ReleaseActionRequest
Core3V2ReleaseActionResponse
```

生产线治理 schema 可以包含内部模块码和 run id，因为页面对象是运营人员；但返回给高层报告页的业务接口不能包含这些字段。

### 7.5 错误 schema

统一错误结构：

```json
{
  "message_cn": "未找到目标 SKU",
  "error_code": "target_sku_not_found",
  "action_hint_cn": "请检查型号输入，或先确认原始数据是否已完成清洗。",
  "trace_id": "可选，仅日志追踪"
}
```

错误码首版：

```text
project_not_found
target_sku_not_found
multiple_sku_matches
report_not_ready
report_blocked
review_required
release_gate_not_found
pipeline_run_not_found
invalid_review_decision
export_not_ready
internal_response_guardrail_failed
```

## 8. repository 任务

### 8.1 repository 类

新增 `Core3RealDataApiRepository`。

建议接口：

```text
get_data_status(project_id, category_code) -> DataStatusRecord
resolve_sku(project_id, category_code, query) -> SkuResolveRecord
list_targets(project_id, category_code, filters, pagination) -> list[TargetSummaryRecord]
get_target_summary(project_id, category_code, sku_code) -> TargetSummaryRecord | None

get_current_report_payload(project_id, category_code, sku_code) -> ReportPayloadRecord | None
list_current_evidence_cards(project_id, category_code, sku_code) -> list[EvidenceCardRecord]
list_current_report_sections(project_id, category_code, sku_code) -> list[ReportSectionRecord]
get_current_report_export(project_id, category_code, sku_code, export_type) -> ReportExportRecord | None
resolve_evidence_short_ref(project_id, category_code, sku_code, short_ref) -> EvidenceTraceRecord | None

get_latest_pipeline_run(project_id, category_code) -> PipelineRunRecord | None
list_pipeline_runs(project_id, category_code, filters, pagination) -> list[PipelineRunRecord]
get_pipeline_run(run_id) -> PipelineRunRecord | None
list_module_runs(run_id, filters) -> list[ModuleRunRecord]
list_recompute_plan(run_id, filters) -> list[RecomputePlanRecord]
list_reviews(run_id, filters, pagination) -> list[ReviewQueueRecord]
get_review(review_id) -> ReviewQueueRecord | None
get_acceptance_report(run_id) -> AcceptanceReportRecord | None
list_release_gates(run_id, filters) -> list[ReleaseGateRecord]
get_target_release_gate(project_id, category_code, sku_code, run_id=None) -> ReleaseGateRecord | None
```

### 8.2 读取规则

业务接口读取规则：

1. 先读取 M16 release gate。
2. gate 为 `blocked` 时，业务主接口只返回阻断状态、原因和建议动作，不返回完整报告主体。
3. gate 为 `review_required` 时，返回报告主体但必须带显著复核提示。
4. gate 为 `releasable` 或 `released` 时，返回完整业务报告。
5. 找不到 gate 时，返回 `report_not_ready`。
6. 找不到 M15 payload 时，返回 `report_not_ready`，不得从 M14/M13 临时拼报告。

技术追溯接口读取规则：

1. 必须通过 `short_ref` 定位 evidence。
2. 必须校验 `short_ref` 属于当前 target report。
3. 不允许按任意 evidence UUID 查询，避免绕过报告上下文。
4. 返回 raw evidence 时必须标注“技术追溯”，前端不得用于高层主屏。

### 8.3 写入规则

API repository 不直接写 M00-M15。

复核和发布动作只调用 M16 service：

```text
submit_review_decision(review_id, request, operator) -> ReviewDecisionResponse
mark_release_gate_released(gate_id, request, operator) -> ReleaseActionResponse
start_pipeline_run(project_id, request, operator) -> PipelineRunResponse
```

这些方法可以放在 `review_action_api_service.py`，repository 只负责读取复核对象和门禁对象。

### 8.4 repository 测试

必须测试：

- 找不到项目返回 `project_not_found`。
- 找不到 SKU 返回 `target_sku_not_found`。
- 多个型号匹配返回 `multiple_sku_matches` 和候选列表。
- blocked gate 不返回完整报告主体。
- review_required gate 返回报告主体和复核提示。
- evidence short ref 不能跨目标 SKU 查询。
- release gate 缺失时不从 M15 直接标 ready。

## 9. service 任务

### 9.1 `SkuResolutionService`

职责：

- 支持用户输入 SKU code、型号名、型号片段。
- 返回唯一 SKU 时给出品牌、型号、尺寸、数据覆盖摘要。
- 多匹配时返回候选列表，不自动选择第一个。
- 找不到时返回中文建议。

首版 85E7Q 要能解析到 `TV00029115`。

### 9.2 `OverviewQueryService`

职责：

- 返回项目数据状态。
- 返回目标 SKU 列表和门禁状态分布。
- 返回可发布、需复核、阻断、未生成数量。
- 返回最新数据范围：`26W01-26W23`、线上渠道、专业电商/平台电商、样例数据说明。
- 返回最新 pipeline run 和 acceptance 摘要。

总览不能展示：

- 模块内部字段。
- SQL。
- UUID。
- 大段 JSON。

### 9.3 `BusinessReportQueryService`

职责：

1. 解析 target SKU。
2. 读取 release gate。
3. 根据 gate 判断报告可见范围。
4. 读取 M15 report payload、evidence cards、sections、exports。
5. 调用 `ApiResponseMapper` 转换成中文业务 response。
6. 调用 `ApiResponseGuardrail` 扫描 response。
7. 返回 `Core3V2BusinessReportResponse`。

报告接口必须保持“先说竞品，再解释为什么”的信息结构：

```text
报告标题
-> 当前核心竞品列表
-> 每个竞品的竞争角色和一句话理由
-> 为什么选择这些竞品
-> 价值战场和证据矩阵
-> 候选池未选原因
-> 数据范围和复核提示
```

### 9.4 `EvidenceTraceQueryService`

职责：

- 通过短证据编号回查 M02 evidence atom。
- 返回 raw evidence、source row、confidence、source lineage。
- 只服务证据详情抽屉或技术追溯页。
- 不被业务主报告接口调用为内嵌字段。

### 9.5 `PipelineStatusQueryService`

职责：

- 启动 M16 pipeline run。
- 查询 run 列表、run 详情、模块运行、重算计划、复核队列、验收报告、发布门禁。
- 把 M16 内部状态映射为运营页面中文状态：

| 内部状态 | 中文显示 |
| --- | --- |
| `pending` | 等待运行 |
| `running` | 运行中 |
| `success` | 已完成 |
| `warning` | 已完成，有提示 |
| `review_required` | 需要复核 |
| `blocked` | 已阻断 |
| `failed` | 运行失败 |
| `skipped_reused` | 复用上次结果 |
| `skipped_by_dependency` | 因上游未通过而跳过 |

### 9.6 `ReviewActionApiService`

职责：

- 提交复核决策。
- 校验复核问题是否属于当前 project/category。
- 校验决策类型。
- `reject`、`request_data`、`rework_rule` 返回是否需要重算和建议 run mode。
- 标记 release gate released 时校验 gate 当前状态是 `releasable`。
- 不允许直接把 blocked gate 标记为 released。

### 9.7 `ExportDeliveryService`

职责：

- 读取 M15 已生成导出内容。
- 支持 `json`、`markdown`、`report_summary`、`evidence_cards`。
- 校验 export checksum 和 page payload hash。
- 对 markdown 和 summary 设置正确 media type。
- export 未 ready 时返回 `export_not_ready`。

### 9.8 `ApiResponseGuardrail`

扫描对象：

- `/report` response。
- `/competitors` response。
- `/evidence-cards` response。
- `/sections` response。
- `/exports/{export_type}` 的业务导出内容。

阻断规则：

| 检查 | 触发 |
| --- | --- |
| UUID | UUID 正则 |
| hash | 64 位 hex hash 明文 |
| 内部表名 | `core3_`、`week_sales_data`、`attribute_data` 等 |
| 内部字段 | `_id`、`_json`、`_score`、`candidate_`、`component_` |
| SQL | select/from/join/where 等技术片段 |
| AI 过程 | AI 认为、模型判断、生成过程、正在思考 |
| 低置信越权 | 需复核/样本不足同时出现“确定”“已确认” |
| 数据范围缺失 | 缺少线上、样例、时间窗口说明 |

guardrail 失败时：

1. 记录服务日志。
2. 返回 500 或 423，错误码 `internal_response_guardrail_failed`。
3. 不返回原始违规 payload。
4. 测试必须覆盖每类违规。

## 10. runner/API 任务

### 10.1 router 注册

新增：

```text
apps/api-server/app/api/core3_real_data.py
```

router：

```python
router = APIRouter(prefix="/api/mvp/core3/v2", tags=["tv-core3-real-data"])
```

在 `apps/api-server/app/main.py` 注册：

```python
from app.api import core3_real_data
app.include_router(core3_real_data.router)
```

### 10.2 业务展示 API

| API | 方法 | 用途 |
| --- | --- | --- |
| `/projects/{project_id}/data-status` | GET | 数据状态 |
| `/projects/{project_id}/sku/resolve` | GET | 型号/SKU 解析 |
| `/projects/{project_id}/overview` | GET | 批量总览 |
| `/projects/{project_id}/targets` | GET | 目标 SKU 列表 |
| `/projects/{project_id}/targets/{sku_or_model}/report` | GET | 单品高层报告 |
| `/projects/{project_id}/targets/{sku_or_model}/competitors` | GET | 核心竞品卡 |
| `/projects/{project_id}/targets/{sku_or_model}/evidence-cards` | GET | 业务证据卡 |
| `/projects/{project_id}/targets/{sku_or_model}/sections` | GET | 可展开报告 section |
| `/projects/{project_id}/targets/{sku_or_model}/exports/{export_type}` | GET | 读取 M15 导出 |

查询参数：

| 参数 | API | 说明 |
| --- | --- | --- |
| `category_code` | 全部 | 默认 `TV` |
| `run_id` | report/overview/targets | 指定运行版本，默认 latest |
| `gate_status` | targets | 过滤门禁状态 |
| `include_sections` | report | 是否返回 section，默认 true |
| `include_candidate_audit` | report | 是否返回候选池摘要，默认 true |
| `export_type` | exports | json/markdown/report_summary/evidence_cards |

### 10.3 证据追溯 API

| API | 方法 | 用途 |
| --- | --- | --- |
| `/projects/{project_id}/targets/{sku_or_model}/evidence/{short_ref}/trace` | GET | 短证据编号技术追溯 |

该接口允许返回 raw evidence 信息，但必须满足：

- `short_ref` 属于当前 target report。
- 默认不被高层主屏调用。
- response 明确标注 `trace_usage_cn="技术追溯使用，不用于高层主屏展示"`。

### 10.4 生产线状态 API

| API | 方法 | 用途 |
| --- | --- | --- |
| `/projects/{project_id}/pipeline/runs` | POST | 启动运行 |
| `/projects/{project_id}/pipeline/runs` | GET | 运行列表 |
| `/projects/{project_id}/pipeline/runs/latest` | GET | 最新运行 |
| `/projects/{project_id}/pipeline/runs/{run_id}` | GET | 运行详情 |
| `/projects/{project_id}/pipeline/runs/{run_id}/modules` | GET | 模块运行 |
| `/projects/{project_id}/pipeline/runs/{run_id}/recompute-plan` | GET | 重算计划 |
| `/projects/{project_id}/pipeline/runs/{run_id}/reviews` | GET | 复核队列 |
| `/projects/{project_id}/pipeline/runs/{run_id}/acceptance` | GET | 验收报告 |
| `/projects/{project_id}/pipeline/runs/{run_id}/release-gates` | GET | 发布门禁 |

这些 API 面向生产线状态页，可以返回 run id、module code 和技术状态，但仍要用中文状态文案辅助展示。

### 10.5 复核和发布动作 API

| API | 方法 | 用途 |
| --- | --- | --- |
| `/projects/{project_id}/reviews/{review_id}/decision` | POST | 提交复核决策 |
| `/projects/{project_id}/release-gates/{gate_id}/release` | POST | 标记发布 |

复核决策请求：

```json
{
  "decision_type": "waive",
  "decision_reason_cn": "当前为样例数据，卖点缺失作为报告限制说明，不阻断演示",
  "need_recompute": false,
  "operator": "business_reviewer"
}
```

发布请求：

```json
{
  "release_note_cn": "已确认当前报告仅用于线上样例数据演示",
  "operator": "business_reviewer"
}
```

### 10.6 HTTP 状态码

| 场景 | 状态码 | 错误码 |
| --- | ---: | --- |
| 请求参数错误 | 400 | `invalid_request` |
| 项目不存在 | 404 | `project_not_found` |
| SKU 不存在 | 404 | `target_sku_not_found` |
| 多个 SKU 匹配 | 409 | `multiple_sku_matches` |
| 报告未生成 | 404 | `report_not_ready` |
| 报告被阻断 | 423 | `report_blocked` |
| 需复核 | 200 | response 中 `release_status.status_code=review_required` |
| 复核动作非法 | 422 | `invalid_review_decision` |
| guardrail 失败 | 500 | `internal_response_guardrail_failed` |

## 11. 测试任务

### 11.1 schema 测试

`test_api_schema_contract.py`：

- 所有 response schema `extra="forbid"`。
- 业务报告 response 必含 `executive_conclusion_cn`、`core_competitors`、`data_scope`、`release_status`。
- 证据卡 response 只返回短证据编号，不返回 raw UUID。
- pipeline response 可以包含 run id，但必须包含中文状态。
- 错误 response 包含 `message_cn` 和 `action_hint_cn`。

### 11.2 SKU 解析测试

`test_api_sku_resolution.py`：

- `85E7Q` 解析到 `TV00029115`。
- `TV00029115` 直接解析成功。
- 多个模糊匹配返回 409 和候选列表。
- 找不到返回 404 和中文建议。

### 11.3 总览测试

`test_api_overview.py`：

- 返回可发布、需复核、阻断、未生成数量。
- 返回数据范围 `26W01-26W23`、线上样例、专业电商/平台电商。
- 不出现 UUID、内部表名和英文内部枚举。
- latest run 和 acceptance 摘要可为空但字段稳定。

### 11.4 单品报告测试

`test_api_business_report.py`：

- `releasable` gate 返回完整报告。
- `review_required` gate 返回报告和复核提示。
- `blocked` gate 只返回阻断状态、原因和建议动作，不返回完整报告主体。
- 缺 M15 payload 时返回 `report_not_ready`。
- 报告顺序是先核心竞品，再解释为什么。
- 业务 response 不包含 `core3_`、`candidate_`、UUID、SQL、AI 过程文案。

### 11.5 证据卡和追溯测试

`test_api_evidence_cards.py`：

- 证据卡包含短证据编号、中文摘要、证据类型、置信提示。
- 证据卡不包含 raw evidence UUID。
- 证据不足时返回风险说明。

`test_api_evidence_trace.py`：

- 短证据编号可追溯到 M02 evidence atom。
- 跨 target 的短证据编号查询被拒绝。
- 技术追溯 response 可以包含 raw evidence id。
- 技术追溯 response 标注不用于高层主屏。

### 11.6 生产线状态测试

`test_api_pipeline_status.py`：

- 可以启动 `single_target_refresh`。
- run 列表支持状态过滤。
- modules 返回中文状态和 module code。
- recompute-plan 返回中文重算原因。
- acceptance 返回四层验收摘要。
- release-gates 返回目标级门禁。

### 11.7 复核和发布动作测试

`test_api_review_actions.py`：

- `waive` 写入 M16 decision，不触发重算。
- `reject` 返回需要 `review_rework`。
- blocked gate 不能 release。
- releasable gate 可 release。
- 操作人为空时拒绝。

### 11.8 导出测试

`test_api_export_delivery.py`：

- markdown 导出 media type 正确。
- json 导出不重新生成业务事实。
- report_summary 包含数据范围说明。
- evidence_cards 导出不含 UUID。
- checksum 和 page payload hash 不一致时返回错误。

### 11.9 guardrail 测试

`test_api_response_guardrail.py`：

- UUID 泄露被阻断。
- `core3_`、`_json`、`_id` 泄露被阻断。
- SQL 片段被阻断。
- AI 过程文案被阻断。
- 缺数据范围说明被阻断。
- 低置信同时出现确定语气被阻断。

### 11.10 route 注册测试

`test_api_route_registration.py`：

- `main.py` 注册 `core3_real_data.router`。
- 新 v2 路由和旧 `/api/mvp/core3` 路由共存。
- OpenAPI 中能看到 `tv-core3-real-data` tag。
- 旧 `core3_mvp` 测试仍通过。

## 12. 205/85E7Q fixture 验收

API fixture 必须覆盖当前 205 样例数据业务约束：

| 数据事实 | API 验收 |
| --- | --- |
| 35 个型号 | `/targets` 可返回目标列表和门禁分布 |
| 周销 `26W01-26W23` | `/overview` 和 `/report` 返回线上样例周期 |
| 渠道为专业电商/平台电商 | data scope 不扩展到线下门店 |
| 品牌全部为海信 | `/report` 不提示“缺少外部品牌所以无竞品” |
| 85E7Q 为 `TV00029115` | `/sku/resolve?query=85E7Q` 可解析 |
| 85E7Q 无结构化卖点 | `/report` 显示宣传卖点数据缺口 |
| 评论有服务体验内容 | `/report` 不把服务体验写成产品核心竞争力 |
| 报告需业务语言 | `/report` 不出现 UUID、SQL、内部字段、AI 过程文案 |

85E7Q 单品报告 API 的最低可验收响应：

1. `target.sku_code=TV00029115`。
2. `data_scope.period_cn` 包含 `26W01-26W23`。
3. `data_scope.channel_scope_cn` 包含线上样例。
4. `release_status.status_name_cn` 是可汇报、需复核、不可发布或已发布之一。
5. `core_competitors` 中每个竞品都有中文角色和一句话理由，或给出空槽原因。
6. `review_hint` 说明宣传卖点数据缺口。
7. response guardrail 通过。

## 13. 完成标准

API 开发完成必须满足：

| 标准 | 要求 |
| --- | --- |
| 独立路由 | `/api/mvp/core3/v2` 可用，不影响旧 `/api/mvp/core3` |
| schema 完整 | 业务、证据、生产线、复核、验收、门禁 schema 完整 |
| 不新增表 | API 任务不写 migration |
| 只读聚合 | 业务查询只读 M00-M16 产物，不重新生成结论 |
| 写入边界 | 复核和发布动作只委托 M16 service |
| 报告顺序 | 单品报告先说竞品，再解释为什么 |
| 业务语言 | 业务 response 使用中文业务文案 |
| 技术隔离 | raw evidence 只在技术追溯 API 返回 |
| guardrail | 业务 response 无 UUID、内部字段、SQL、AI 过程文案 |
| 205 样例 | 85E7Q、线上样例、同品牌、卖点缺口表达正确 |
| 测试 | API schema、service、route、guardrail、fixture 测试通过 |

## 14. 风险和回滚

| 风险 | 处理 |
| --- | --- |
| API 层重算业务结果 | repository 只读 M15/M16 display 产物，测试缺 payload 不允许临时拼结论 |
| 业务页面泄露内部字段 | `ApiResponseGuardrail` 阻断，schema 测试覆盖 |
| 旧接口被破坏 | 新增 `core3_real_data.py`，旧 `core3_mvp.py` 不改；保留旧测试 |
| blocked 报告被展示 | gate 先行，blocked 只返回阻断摘要 |
| 技术追溯混入主屏 | trace API 独立，主 report schema 不含 raw evidence 字段 |
| 接口粒度过粗导致前端重拼 | report API 返回主屏完整 payload，front 不重新组合业务结论 |
| 接口粒度过细导致首屏慢 | overview/report 提供聚合接口，证据详情按需加载 |

回滚策略：

1. 从 `main.py` 移除 `core3_real_data.router` 注册即可关闭 v2 API。
2. 不需要数据库回滚，因为本任务不新增表。
3. 旧 `core3_mvp` API 不受影响。
4. 若 guardrail 误杀，可临时只关闭业务 report API，保留生产线状态 API 供排查。

## 15. 下游依赖

FRONTEND 任务依赖本任务输出：

- `/overview`：批量总览页。
- `/targets`：目标 SKU 列表。
- `/targets/{sku_or_model}/report`：单品高层报告页。
- `/targets/{sku_or_model}/evidence-cards`：证据卡区。
- `/targets/{sku_or_model}/evidence/{short_ref}/trace`：证据详情抽屉。
- `/pipeline/runs`、`/reviews`、`/acceptance`、`/release-gates`：生产线状态页。

ACCEPTANCE 任务依赖本任务输出：

- API 可以完整支撑 85E7Q 的演示路径。
- API 可以证明旧页面和新真实数据 v2 页面分离。
- API 可以证明高层主屏无内部字段、UUID、英文枚举和 AI 过程文案。
- API 可以证明 blocked/review_required/releasable/released 的门禁状态可被前端正确消费。

## 16. 子任务拆分

| 子任务 | 内容 | 主要产物 |
| --- | --- | --- |
| DAPI-01 | 新增 schema 契约 | `schemas/core3_real_data.py` |
| DAPI-02 | 新增 API repository | `api_repositories.py` |
| DAPI-03 | 新增 response mapper | `api_response_mapper.py` |
| DAPI-04 | 新增 response guardrail | `api_response_guardrail.py` |
| DAPI-05 | 实现 SKU 解析服务 | `sku_resolution_service.py` |
| DAPI-06 | 实现 overview 和 targets 查询 | `overview_query_service.py` |
| DAPI-07 | 实现单品报告查询 | `business_report_query_service.py` |
| DAPI-08 | 实现证据卡和追溯查询 | `evidence_trace_query_service.py` |
| DAPI-09 | 实现生产线状态查询 | `pipeline_status_query_service.py` |
| DAPI-10 | 实现复核和发布动作封装 | `review_action_api_service.py` |
| DAPI-11 | 实现导出读取 | `export_delivery_service.py` |
| DAPI-12 | 新增 router 并注册 | `api/core3_real_data.py`、`main.py` |
| DAPI-13 | 补 API fixture | `conftest.py` |
| DAPI-14 | 补 schema、service、route、guardrail 测试 | `test_api_*.py` |
| DAPI-15 | 补 85E7Q API 验收测试 | `test_api_85e7q_fixture.py` |

编码时每次只做一个子任务或一个可测试闭环，不要在同一轮同时做 API、前端和部署。

## 17. 下次任务

完成 API 开发任务文档后，下一个文档是：

```text
docs/core3_mvp/real_data_v2/development/FRONTEND_development_tasks.md
```

FRONTEND 任务应基于本文定义的 v2 API 契约设计独立页面，不重新定义后端数据结构，不直接读取旧 `core3_mvp` 接口。
