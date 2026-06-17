# ACCEPTANCE 全链路验收和部署前检查开发任务

## 1. 模块目标

ACCEPTANCE 的目标是为 CatForge 彩电核心三竞品真实数据 MVP 建立一套可执行、可复核、可阻断发布的全链路验收任务。它不是新的业务算法模块，也不是部署任务；它负责在 M00-M16、API 和独立前端完成后，证明真实数据 v2 已经达到可以进入演示、试运行或部署到 205 的标准。

ACCEPTANCE 必须回答的问题是：

1. 原始表到清洗表、证据表、抽取表、画像表、结果表、报告表、门禁表的链路是否完整。
2. M00-M16 是否按独立模块运行，没有被一个脚本绕过，也没有跳过 SOP 推导步骤。
3. 原始四表是否只读，新增原始数据后是否能通过增量链路进入清洗、证据、抽取、画像和报告。
4. 85E7Q 是否能从真实样例数据中完成目标识别、画像生成、候选召回、三竞品选择、证据卡生成和业务报告展示。
5. 同品牌海信 SKU 是否没有被错误过滤，且当前样例数据的“全海信、线上平台、宣传卖点缺口”是否被明确说明。
6. API 是否只返回业务展示字段，不暴露 UUID、hash、SQL、表名、字段名、内部英文枚举、JSON 大段和 AI 过程文案。
7. 前端是否是独立真实数据 v2 页面，不混入旧 `core3_mvp` 粗粒度页面，也不展示非业务语言。
8. 高层报告是否先说明竞品是谁，再解释为什么，并用价格、渠道、参数、卖点、任务、客群、价值战场、市场和评论证据证明。
9. blocked、review_required、releasable、released 等门禁状态是否能正确阻断或放行业务展示。
10. 205 部署前需要检查哪些数据库、服务、域名、HTTPS、反向代理、浏览器页面和日志项。

ACCEPTANCE 要解决的工程问题：

1. 建立统一验收清单，把 M00-M16、API、FRONTEND 的完成标准串成一条发布门禁。
2. 建立后端测试、API 契约测试、前端构建测试、页面验收和 205 预检查的执行顺序。
3. 建立 85E7Q 真实样例 fixture 验收，覆盖当前数据库基线的数据范围限制。
4. 建立业务展示 guardrail 验收，阻断内部技术字段和 AI 过程语言泄露。
5. 建立增量验收，验证 `bootstrap_full`、`daily_incremental`、`single_target_refresh`、`review_rework`、`acceptance_only` 等模式。
6. 建立部署前 go/no-go 判定，让后续编码完成后能明确是否允许部署或演示。

ACCEPTANCE 必须固化以下边界：

- ACCEPTANCE 不实现 M00-M16 的算法。
- ACCEPTANCE 不新增业务分析表。
- ACCEPTANCE 不修改原始四表。
- ACCEPTANCE 不替代 M16 的复核、验收报告和发布门禁，只校验它们是否按设计工作。
- ACCEPTANCE 不直接生成高层报告内容；报告内容来自 M15，门禁来自 M16。
- ACCEPTANCE 不改 API 或前端业务逻辑，只在后续编码阶段补充测试、检查脚本和验收文档。
- ACCEPTANCE 不自动部署 205；205 部署必须在用户明确确认后单独执行。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| 基础设施任务 | `docs/core3_mvp/real_data_v2/development/INFRA_development_tasks.md` |
| M00-M16 任务 | `docs/core3_mvp/real_data_v2/development/M00_development_tasks.md` 到 `M16_development_tasks.md` |
| API 任务 | `docs/core3_mvp/real_data_v2/development/API_development_tasks.md` |
| FRONTEND 任务 | `docs/core3_mvp/real_data_v2/development/FRONTEND_development_tasks.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M16 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M16_incremental_review_acceptance_design.md` |
| M15 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M15_evidence_report_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 方法论 | `cankao/CatForge_竞品生成SOP_详细指导_v1.md` |
| UI 规范 | `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md` |
| 参考模块 | `cankao/catforge_sop_md/modules/` |
| 部署参考 | `scripts/deploy.sh`、`docs/deployment-runbook.md`、`docs/environments.md`、`scripts/check-env.sh` |

编码前必须确认：

- P0 开发任务文档已经全部生成并通过人工评审。
- 用户明确确认进入编码阶段。
- INFRA、M00-M16、API、FRONTEND 的编码任务将按小闭环逐一执行。
- ACCEPTANCE 的实现只能作为最终验收和部署前检查，不能提前绕过业务模块生成结论。

## 3. 本次范围

本任务文档覆盖后续 ACCEPTANCE 编码阶段需要完成的验收设计：

| 范围 | 说明 |
| --- | --- |
| 验收清单 | 形成数据、模块、API、前端、业务展示、205 预检查的统一 checklist |
| 后端验收测试 | 对 M00-M16 的表、schema、repository、service、runner 和集成链路做 pytest 验收 |
| API 契约测试 | 对 `/api/mvp/core3/v2` 的业务展示、证据追溯、生产线状态和复核发布 API 做契约验收 |
| 前端验收测试 | 对独立页面、中文业务语言、guardrail、85E7Q 展示、构建和浏览器流程做验收 |
| 数据基线验收 | 对 205 PostgreSQL 当前样例数据和本地 fixture 做数量、范围、水位和数据缺口验收 |
| 增量模式验收 | 覆盖全量启动、日增量、单目标刷新、复核返工和只验收模式 |
| 业务报告验收 | 验证先列竞品、再说明推导逻辑、后展示证据卡和未选原因 |
| 发布门禁验收 | 验证 blocked、review_required、releasable、released 对 API 和页面的影响 |
| 部署前检查 | 定义 205 上线前的服务、数据库、域名、HTTPS、日志和回滚检查项 |
| 验收报告 | 产出机器可读 JSON 和人工可读 Markdown 验收结论 |

本次不做：

- 不写任何业务模块代码。
- 不写数据库迁移。
- 不部署到 205。
- 不修改已有开发任务文档。
- 不修改 SOP 需求、详细设计和参考文档。
- 不把验收脚本设计成新的数据处理生产线。
- 不把 205 样例数据结论写成完整市场结论。

## 4. 要改文件

### 4.1 当前文档阶段只新增

```text
docs/core3_mvp/real_data_v2/development/ACCEPTANCE_development_tasks.md
```

### 4.2 后续编码阶段允许新增的验收文档

```text
docs/core3_mvp/real_data_v2/acceptance/acceptance_checklist.md
docs/core3_mvp/real_data_v2/acceptance/205_predeploy_checklist.md
docs/core3_mvp/real_data_v2/acceptance/85e7q_fixture_acceptance.md
docs/core3_mvp/real_data_v2/acceptance/business_display_guardrail.md
docs/core3_mvp/real_data_v2/acceptance/acceptance_report_template.md
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `acceptance_checklist.md` | 全链路验收清单和 go/no-go 标准 |
| `205_predeploy_checklist.md` | 205 上线前数据库、服务、代理、域名和回滚检查 |
| `85e7q_fixture_acceptance.md` | 85E7Q 样例数据、业务结论和页面展示验收 |
| `business_display_guardrail.md` | 业务语言、内部字段、AI 过程文案、中文展示门禁 |
| `acceptance_report_template.md` | 人工可读验收报告模板 |

### 4.3 后续编码阶段允许新增的后端验收测试

```text
apps/api-server/tests/core3_real_data/test_acceptance_database_baseline.py
apps/api-server/tests/core3_real_data/test_acceptance_module_contracts.py
apps/api-server/tests/core3_real_data/test_acceptance_full_pipeline.py
apps/api-server/tests/core3_real_data/test_acceptance_incremental_modes.py
apps/api-server/tests/core3_real_data/test_acceptance_release_gate.py
apps/api-server/tests/core3_real_data/test_acceptance_business_report_guardrail.py
apps/api-server/tests/core3_real_data/test_acceptance_85e7q_end_to_end.py
apps/api-server/tests/core3_real_data/test_acceptance_no_raw_table_mutation.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `test_acceptance_database_baseline.py` | 校验 fixture 或 205 只读基线、数量、水位、样例限制 |
| `test_acceptance_module_contracts.py` | 校验 M00-M16 关键输入输出契约 |
| `test_acceptance_full_pipeline.py` | 校验全量链路能按 DAG 运行到 M15/M16 |
| `test_acceptance_incremental_modes.py` | 校验全量、增量、单目标、返工和只验收模式 |
| `test_acceptance_release_gate.py` | 校验复核、验收、发布门禁状态 |
| `test_acceptance_business_report_guardrail.py` | 校验业务展示不泄露内部字段和过程语言 |
| `test_acceptance_85e7q_end_to_end.py` | 校验 85E7Q 完整场景 |
| `test_acceptance_no_raw_table_mutation.py` | 校验验收和生产线不会改写原始四表 |

### 4.4 后续编码阶段允许新增的 API 验收测试

```text
apps/api-server/tests/core3_real_data/test_acceptance_api_contract.py
apps/api-server/tests/core3_real_data/test_acceptance_api_guardrail.py
apps/api-server/tests/core3_real_data/test_acceptance_api_release_status.py
apps/api-server/tests/core3_real_data/test_acceptance_api_evidence_trace.py
```

### 4.5 后续编码阶段允许新增的前端验收测试和 fixture

```text
apps/factory-web/src/pages/core3RealData/core3RealDataAcceptance.fixture.ts
apps/factory-web/src/pages/core3RealData/core3RealDataAcceptance.test.ts
apps/factory-web/src/pages/core3RealData/core3RealDataBusinessLanguage.test.ts
apps/factory-web/src/pages/core3RealData/core3RealDataInternalFieldGuard.test.ts
apps/factory-web/src/pages/core3RealData/core3RealData85E7Q.test.ts
```

如果项目已经有 Playwright 测试基础，可在后续编码阶段新增：

```text
apps/factory-web/e2e/core3-real-data-acceptance.spec.ts
```

如果项目没有 Playwright 基础，首版不强行新增依赖；用 vitest、构建检查和人工浏览器检查覆盖。

### 4.6 后续编码阶段允许新增的验收 runner

```text
scripts/core3_real_data_acceptance.py
scripts/core3_real_data_205_precheck.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `core3_real_data_acceptance.py` | 只编排测试和读取 M16 验收报告，不生成业务结论 |
| `core3_real_data_205_precheck.py` | 只读检查 205 数据库、服务 URL、域名和 HTTPS，不改远端数据 |

验收 runner 必须是薄封装，核心判断仍落在 pytest、API contract、frontend tests 和 M16 表中。

## 5. 不允许改文件

ACCEPTANCE 编码阶段不得修改以下范围：

```text
docs/core3_mvp/real_data_v2/sop_requirements/
docs/core3_mvp/real_data_v2/sop_detailed_design/
cankao/
apps/api-server/app/services/core3_mvp/
apps/api-server/app/api/core3_mvp.py
apps/api-server/app/schemas/core3_mvp.py
apps/factory-web/src/pages/core3/
```

除非用户单独批准，ACCEPTANCE 编码阶段不得修改：

```text
scripts/deploy.sh
docker-compose*.yml
nginx*.conf
apps/api-server/alembic/versions/
apps/api-server/app/services/core3_real_data/
apps/factory-web/src/pages/core3RealData/
```

原因：

- ACCEPTANCE 的主要职责是验收和阻断，不是补写业务逻辑。
- 如果验收发现 M00-M16、API 或 FRONTEND 缺陷，应回到对应模块任务修复。
- 205 部署脚本和 Nginx 配置属于部署任务，不在验收文档阶段顺手修改。

不得引入的行为：

- 为了让验收通过而降低门禁。
- 在验收脚本中硬编码最终竞品结论。
- 在验收脚本中修改原始表、清洗表、证据表、抽取表、画像表或结果表。
- 在 API 或前端测试中接受 UUID、SQL、内部英文枚举、表字段名出现在业务展示主屏。
- 把“服务体验、物流安装、价格感知、未知初判”等原始评论粗标签当成最终客群、任务或价值战场结论。
- 把 85E7Q 无结构化宣传卖点数据写成“没有卖点”。
- 把当前样例全是海信写成外部品牌竞争格局。

## 6. 数据库任务

### 6.1 migration

ACCEPTANCE 首版不新增业务表，不写 Alembic migration。

理由：

1. M16 已设计 `core3_acceptance_report` 和 `core3_release_gate`，验收结果应优先读取这些治理表。
2. ACCEPTANCE 的自动化测试结果可以输出到 CI 日志、JSON artifact 和 Markdown 报告，不需要新增生产表。
3. 如未来需要长期保存测试执行记录，应作为 M16 治理增强单独设计，不在本任务默认范围。

### 6.2 只读检查表

ACCEPTANCE 允许只读检查以下表族：

| 表族 | 检查目标 |
| --- | --- |
| 原始表 | 行数、水位、hash、只读权限、增量时间范围 |
| M00 表 | 批次、source file、raw row、受影响 SKU、水位 |
| M01 表 | 清洗 SKU、清洗属性、清洗评论、清洗卖点、质量问题 |
| M02 表 | evidence atom、source binding、confidence、review status |
| M03-M11.5 表 | 参数、卖点、评论信号、市场画像、SKU 画像、任务、客群、价值战场、价值层 |
| M12-M14 表 | 候选池、评分组件、三槽位选择、空槽原因、未选审计 |
| M15 表 | 证据卡、报告 payload、section、export、报告复核问题 |
| M16 表 | pipeline run、module run、review queue、acceptance report、release gate、watermark |

### 6.3 205 数据库只读要求

205 预检查必须使用只读查询：

1. 不执行 `INSERT`、`UPDATE`、`DELETE`、`TRUNCATE`、`DROP`、`ALTER`。
2. 不改写原始四表、清洗表或结果表。
3. 需要写入验收结果时，只能写本地 artifact；是否写入 205 的 M16 验收表必须由正式 pipeline run 完成。
4. 查询必须带 schema 和项目条件，避免误读其他库或其他项目。

## 7. model/schema 任务

ACCEPTANCE 后续编码阶段需要定义轻量验收 schema。首版建议放在测试或验收脚本内，不进入生产 API schema，除非 M16/API 已经需要复用。

### 7.1 验收状态枚举

```text
AcceptanceCheckStatus = passed | warning | failed | blocked | skipped
AcceptanceSeverity = p0 | p1 | p2 | info
AcceptanceScope = database | module | integration | api | frontend | business_report | deployment_precheck
```

含义：

| 字段 | 含义 |
| --- | --- |
| `passed` | 验收项通过 |
| `warning` | 不阻断演示，但必须在报告中说明 |
| `failed` | 验收项失败，不能进入下一阶段 |
| `blocked` | 上游缺失或环境不可用，不能判断 |
| `skipped` | 本轮不适用，必须说明原因 |

### 7.2 验收检查结果

```text
AcceptanceCheckResult
- check_code: string
- check_name: string
- scope: AcceptanceScope
- status: AcceptanceCheckStatus
- severity: AcceptanceSeverity
- target_sku_code: string | null
- project_id: string
- category_code: string
- evidence_ref: string | null
- expected: string
- actual: string
- failure_reason: string | null
- remediation_owner: string | null
- remediation_module: string | null
- artifact_path: string | null
```

### 7.3 验收套件结果

```text
AcceptanceSuiteResult
- suite_code: string
- suite_name: string
- run_mode: string
- started_at: datetime
- finished_at: datetime
- status: AcceptanceCheckStatus
- total_checks: int
- passed_checks: int
- warning_checks: int
- failed_checks: int
- blocked_checks: int
- skipped_checks: int
- p0_failures: list[AcceptanceCheckResult]
- go_no_go: go | no_go | go_with_notes
- report_markdown_path: string | null
- report_json_path: string | null
```

### 7.4 业务展示禁止项

前后端验收必须共享一组禁止项：

```text
InternalDisplayForbiddenPattern
- uuid_pattern
- sql_keyword_pattern
- internal_table_pattern
- raw_field_pattern
- hash_pattern
- english_enum_pattern
- ai_process_phrase_pattern
- raw_json_pattern
```

禁止项覆盖：

- UUID 和 evidence 内部 ID。
- `SELECT`、`JOIN`、`WHERE` 等 SQL 片段。
- `market_aggregate`、`core3_` 内部表名和字段名。
- `price_wavg_12m`、`task_battlefield` 等字段编码。
- `blocked`、`review_required` 等未映射的英文状态。
- “AI 认为”“模型判断”“生成过程”“提示词”“置信度算法”等非业务过程文案。
- 大段 JSON 或数组对象。

## 8. repository 任务

### 8.1 后续可实现 `AcceptanceReadRepository`

职责：

1. 读取 205 或测试库的数据范围、水位、行数和 hash 摘要。
2. 读取 M00-M16 关键表的 run、module、report、gate 和 acceptance 状态。
3. 读取目标 SKU 85E7Q 的清洗主数据、证据数量、画像状态、报告状态和发布门禁。
4. 读取 API 返回结果的短证据编号和技术追溯结果。
5. 只读访问，不写生产表。

建议方法：

```text
get_source_baseline(project_id, category_code) -> SourceBaselineSummary
get_module_run_summary(pipeline_run_id) -> list[ModuleRunSummary]
get_target_pipeline_state(target_sku_code) -> TargetPipelineState
get_report_gate(target_sku_code) -> ReleaseGateSummary
get_85e7q_acceptance_snapshot() -> TargetAcceptanceSnapshot
assert_raw_table_unchanged(before_hash, after_hash) -> RawMutationCheck
```

### 8.2 不允许 repository 行为

- 不从原始表直接生成竞品、战场、任务、客群或报告结论。
- 不改写 M16 门禁状态。
- 不为验收通过而补写缺失数据。
- 不读取旧 `core3_mvp` 表作为真实数据 v2 验收依据。

## 9. service 任务

### 9.1 后续可实现 `Core3RealDataAcceptanceService`

职责：

1. 组织验收套件执行顺序。
2. 汇总 pytest、API contract、frontend test、M16 acceptance report 和人工浏览器检查结果。
3. 根据 P0/P1/P2 严重程度计算 go/no-go。
4. 生成 JSON artifact 和 Markdown 验收报告。
5. 输出失败项的归属模块和下一步修复建议。

### 9.2 验收套件

| 套件 | 目标 | 阻断级别 |
| --- | --- | --- |
| `database_baseline` | 数据库连接、样例范围、原始表只读、水位、85E7Q 可识别 | P0 |
| `module_contracts` | M00-M16 输入输出表、字段、主键、唯一键、状态、confidence、review status | P0 |
| `full_pipeline` | bootstrap full 能从 M00 到 M16 产生报告和门禁 | P0 |
| `incremental_modes` | daily incremental、single target refresh、review rework、acceptance only | P1 |
| `business_report` | 先竞品、再理由、后证据；推导链完整；样例限制明确 | P0 |
| `api_contract` | `/api/mvp/core3/v2` schema、错误码、中文业务字段、追溯 API 分离 | P0 |
| `api_guardrail` | API 不泄露内部字段、UUID、SQL、AI 过程文案 | P0 |
| `frontend_build` | 类型、测试、构建通过 | P0 |
| `frontend_business_display` | 独立页面、中文业务语言、无内部字段、85E7Q 可展示 | P0 |
| `release_gate` | blocked/review_required/releasable/released 正确影响 API 和页面 | P0 |
| `205_predeploy` | 205 服务、域名、HTTPS、反向代理、日志和回滚检查 | P1 |

### 9.3 go/no-go 规则

| 条件 | 结论 |
| --- | --- |
| 任一 P0 failed 或 blocked | `no_go` |
| 无 P0 failed，但有 P1 failed | `go_with_notes`，不能对外发布，只能内部演示 |
| 无 P0/P1 failed，有 warning | `go_with_notes`，报告必须说明限制 |
| 全部 passed 或允许 skipped | `go` |

### 9.4 失败归属

每个失败项必须映射到修复模块：

| 失败类型 | 归属 |
| --- | --- |
| 原始行、批次、水位错误 | M00 |
| 清洗字段、标准化错误 | M01 |
| evidence 缺失或无 source binding | M02 |
| 参数、卖点、评论、市场、画像错误 | M03-M08 |
| 任务、客群、战场、价值层错误 | M09-M11.5 |
| 候选、评分、三槽位错误 | M12-M14 |
| 报告、证据卡、业务语言错误 | M15 |
| run、复核、验收、发布门禁错误 | M16 |
| response schema 或字段泄露 | API |
| 页面独立性、中文展示或布局错误 | FRONTEND |
| 域名、HTTPS、进程、日志错误 | DEPLOYMENT |

## 10. runner/API 任务

### 10.1 runner

后续可新增薄 runner：

```text
python scripts/core3_real_data_acceptance.py --suite all --project-id demo --category-code TV
python scripts/core3_real_data_acceptance.py --suite 85e7q --target-sku-code TV00029115
python scripts/core3_real_data_acceptance.py --suite api --base-url http://127.0.0.1:8000
python scripts/core3_real_data_acceptance.py --suite frontend --frontend-url http://127.0.0.1:5173
python scripts/core3_real_data_205_precheck.py --host 123.56.42.205 --domain cftest.ctfcoach.com --read-only
```

runner 只能做：

1. 调用测试命令。
2. 调用只读 API。
3. 读取 M16 验收和门禁。
4. 输出报告。

runner 不能做：

1. 生成竞品结论。
2. 修改生产数据。
3. 自动部署。
4. 自动降低发布门禁。

### 10.2 API

ACCEPTANCE 首版不新增对外 API。

如后续需要在运营页面查看验收结果，应优先复用 API 任务已经定义的 M16 验收查询接口：

```text
GET /api/mvp/core3/v2/pipeline/runs/{run_id}/acceptance
GET /api/mvp/core3/v2/reports/{target_sku_code}/release-gate
```

不新增“运行验收并写库”的公开接口。验收执行应由内部 runner、CI 或受控后台任务触发。

## 11. 测试任务

### 11.1 后端测试命令

后续编码完成后至少执行：

```text
cd apps/api-server
pytest tests/core3_real_data -q
```

按阶段可拆分：

```text
pytest tests/core3_real_data/test_m00_*.py -q
pytest tests/core3_real_data/test_m01_*.py -q
pytest tests/core3_real_data/test_m02_*.py -q
pytest tests/core3_real_data/test_m03_*.py tests/core3_real_data/test_m04*.py -q
pytest tests/core3_real_data/test_m05_*.py tests/core3_real_data/test_m06_*.py -q
pytest tests/core3_real_data/test_m07_*.py tests/core3_real_data/test_m08_*.py -q
pytest tests/core3_real_data/test_m09_*.py tests/core3_real_data/test_m10_*.py tests/core3_real_data/test_m11*.py -q
pytest tests/core3_real_data/test_m12_*.py tests/core3_real_data/test_m13_*.py tests/core3_real_data/test_m14_*.py -q
pytest tests/core3_real_data/test_m15_*.py tests/core3_real_data/test_m16_*.py -q
pytest tests/core3_real_data/test_api_*.py tests/core3_real_data/test_acceptance_*.py -q
```

### 11.2 前端测试命令

后续编码完成后至少执行：

```text
cd apps/factory-web
npm run test
npm run build
```

如项目已有浏览器验收基础，再执行：

```text
npm run test:e2e -- core3-real-data
```

如果没有 e2e 基础，使用手工浏览器验收清单，不在 ACCEPTANCE 阶段强行新增依赖。

### 11.3 API 契约测试

必须覆盖：

1. `GET /api/mvp/core3/v2/overview`
2. `GET /api/mvp/core3/v2/targets`
3. `GET /api/mvp/core3/v2/reports/{target_sku_code}`
4. `GET /api/mvp/core3/v2/reports/{target_sku_code}/evidence-cards`
5. `GET /api/mvp/core3/v2/evidence/{short_evidence_code}`
6. `GET /api/mvp/core3/v2/pipeline/runs`
7. `GET /api/mvp/core3/v2/pipeline/runs/{run_id}`
8. `GET /api/mvp/core3/v2/pipeline/runs/{run_id}/acceptance`
9. `POST /api/mvp/core3/v2/review/decisions`
10. `POST /api/mvp/core3/v2/reports/{target_sku_code}/release`

契约要求：

- 成功 response 必须是中文业务字段或前端明确映射字段。
- 业务展示 response 不得出现内部字段和英文枚举。
- 技术追溯 API 可以返回 evidence 技术信息，但必须与高层主屏分离。
- 错误 response 必须是中文业务可理解信息。

### 11.4 业务展示 guardrail 测试

必须验证以下内容不会出现在高层主屏和业务展示 API：

```text
UUID
SQL
hash
market_aggregate
price_wavg_12m
task_battlefield
comment_signal
review_required
blocked
display_payload_json
AI 认为
模型判断
生成过程
提示词
```

允许出现在技术追溯页或运营状态页的内容必须受控展示，并附带中文解释。

### 11.5 增量测试

必须覆盖：

| 模式 | 验收点 |
| --- | --- |
| `bootstrap_full` | 空目标结果库可从 M00 跑到 M16 |
| `daily_incremental` | 新增原始行只处理受影响 SKU |
| `single_target_refresh` | 只刷新指定目标 SKU 的画像、竞品和报告 |
| `review_rework` | 复核拒绝或要求补数据后能回到正确模块 |
| `acceptance_only` | 不重跑业务模块，只读取现有结果做验收和门禁 |

## 12. 205/85E7Q 验收

### 12.1 当前真实样例数据基线

验收必须以当前 205 PostgreSQL 样例数据为约束，首版不得假设外部品牌数据已经存在。

已知样例基线：

| 项 | 当前基线 |
| --- | --- |
| SKU 数 | 约 35 个彩电型号 |
| 周销售行 | 约 1326 行 |
| 参数属性行 | 约 2843 行 |
| 宣传卖点行 | 约 65 行 |
| 评论行 | 约 62426 行 |
| 品牌范围 | 当前样例为海信系 |
| 周期范围 | `26W01` 到 `26W23` |
| 渠道范围 | 专业电商、平台电商 |
| 目标 SKU | `85E7Q`，内部 SKU `TV00029115` |
| 目标数据限制 | `85E7Q` 有量价、参数、评论，但无结构化宣传卖点 |

如果后续 205 新增数据导致数量变化，验收不得写死精确总数。应采用：

1. 基线下限检查。
2. 当前水位检查。
3. 数据范围说明检查。
4. 变化摘要检查。

### 12.2 85E7Q 数据链路验收

必须通过：

1. 可以通过 `85E7Q` 解析到 `TV00029115`。
2. 可以确认目标品类为 `TV`。
3. 可以读取目标的价格、销量、渠道、参数和评论证据。
4. 可以识别目标无结构化宣传卖点，并在报告中写成“宣传卖点数据缺口”，不能写成“没有卖点”。
5. 可以召回同品牌候选 SKU，不因同品牌而过滤。
6. 可以生成三槽位结果；如果某槽为空，必须给出空槽原因。
7. 可以生成证据卡，且主屏显示短证据编号。
8. 可以生成数据范围说明，包括全海信样例、线上渠道样例和周期范围。
9. 可以生成发布门禁状态。
10. 可以在独立前端页面展示完整报告。

### 12.3 业务报告验收

85E7Q 页面必须按以下顺序展示：

1. 目标 SKU 和当前报告状态。
2. 核心三竞品是谁，每个竞品的竞争角色是什么。
3. 为什么这些是竞品，按价格、渠道、参数、卖点、评论、任务、客群、价值战场和市场信号解释。
4. 每个价值战场为什么成立，目标 SKU 和竞品是否都有证据。
5. 哪些候选 SKU 被排除，原因是什么。
6. 证据卡和短证据编号。
7. 当前数据范围和限制。
8. 复核问题和发布门禁。

不得出现：

- 先展示技术表格再展示业务结论。
- 用英文字段解释竞品理由。
- 用“AI 过程”“模型生成”“算法推断过程”作为主屏语言。
- 只列价值战场，不解释价值战场如何由任务、客群、卖点、参数、评论和市场信号推导。
- 把评论粗标签当成最终用户任务或客群。

### 12.4 205 部署前验收

部署前必须检查：

1. 205 上 PostgreSQL 连接正常，目标库和 schema 正确。
2. 205 上 API 服务健康检查通过。
3. 205 上前端静态资源或容器版本与本次构建一致。
4. 80 和 443 已开放，443 HTTPS 可访问。
5. `cftest.ctfcoach.com` 解析到 205。
6. Nginx 或反向代理把 API 和前端路由转发到正确服务。
7. `https://cftest.ctfcoach.com/` 能打开真实数据 v2 独立页面。
8. 页面不跳到旧生产器或旧 `core3_mvp` 页面。
9. 浏览器控制台无 P0 错误。
10. 后端日志无启动异常、数据库连接异常或 migration 缺失错误。
11. 回滚路径明确，至少能恢复到上一版容器或上一版静态资源。

205 预检查只定义验收项，不代表本任务会自动部署。

## 13. 完成标准

### 13.1 本文档完成标准

本开发任务文档完成后，P0 开发任务拆分阶段完成：

1. `00_development_task_breakdown.md` 存在。
2. `INFRA_development_tasks.md` 存在。
3. M00-M16 开发任务文档全部存在。
4. `API_development_tasks.md` 存在。
5. `FRONTEND_development_tasks.md` 存在。
6. `ACCEPTANCE_development_tasks.md` 存在。
7. 每份任务文档都明确要改文件、不允许改文件、数据库/model/repository/service/runner/API/测试/验收/风险/依赖。

本文档完成不代表已经可以部署。进入编码阶段仍需用户明确确认。

### 13.2 后续编码完成标准

后续完成 ACCEPTANCE 编码任务时，必须满足：

1. 后端 `pytest tests/core3_real_data -q` 通过。
2. API contract 和 guardrail 测试通过。
3. 前端 `npm run test` 和 `npm run build` 通过。
4. 85E7Q fixture 验收通过。
5. 原始表只读和增量水位验收通过。
6. M16 `core3_acceptance_report` 生成通过，P0 项无 failed 或 blocked。
7. M16 `core3_release_gate` 能正确区分 blocked、review_required、releasable、released。
8. 高层业务展示 API 和页面不泄露内部字段、UUID、SQL、英文枚举和 AI 过程文案。
9. 独立页面路径可访问，不混入旧页面。
10. 205 预检查通过后，才能申请部署。

### 13.3 编码准入标准

用户确认进入开发前，应至少完成：

1. 评审 P0 开发任务文档。
2. 确认真实数据 v2 先做 MVP 的模块范围。
3. 确认第一轮编码从 INFRA 开始，不直接跳 API 或前端。
4. 确认每次编码只做一个小闭环，并运行对应测试。

## 14. 风险和回滚

| 风险 | 表现 | 处理 |
| --- | --- | --- |
| 验收范围过大 | 一个验收任务变成大而全开发 | 拆为后端、API、前端、205 预检查子任务 |
| 为过验收硬编码 | fixture 写死竞品结果 | 验收只检查契约、证据、状态和推导完整性，不写死最终结论 |
| 样例数据变化 | 205 新增数据导致固定数量失败 | 使用基线下限、水位和范围说明，不写死总数 |
| 误写原始表 | 验收脚本造成数据污染 | 使用只读连接和 raw hash 前后比对 |
| 内部字段泄露 | 高层页面出现 UUID、SQL、英文枚举 | API 和前端双 guardrail，P0 阻断 |
| 页面混入旧实现 | v2 入口复用旧页面 | 前端验收检查独立路由、目录和 API 前缀 |
| 业务语言不专业 | 页面展示“AI 生成过程” | business language 测试和人工验收阻断 |
| 205 环境漂移 | 本地通过但远端失败 | 预检查读取远端服务、域名、HTTPS、日志和数据库水位 |
| 发布门禁失效 | blocked 报告仍展示为可汇报 | API/前端 release gate 测试作为 P0 |

回滚原则：

1. 文档阶段只新增本文件，回滚只删除本文件。
2. 编码阶段如果 ACCEPTANCE 测试失败，不改验收标准，回到对应模块修复。
3. 205 部署失败时按部署 runbook 回滚容器或静态资源，不回滚数据库原始数据。

## 15. 下游依赖

ACCEPTANCE 是开发任务拆分阶段最后一个文档，没有下一份开发任务文档。

后续阶段依赖关系：

1. 用户评审并确认 P0 开发任务文档。
2. 进入编码阶段，从 `INFRA_development_tasks.md` 对应的小闭环开始。
3. 完成 INFRA 后依次开发 M00、M01、M02。
4. 数据底座稳定后再开发抽取画像、候选评分、报告、编排、API 和前端。
5. 所有模块完成后执行本 ACCEPTANCE 验收。
6. 验收通过并经用户确认后，单独执行 205 部署任务。

如果继续使用定时器，本文件完成后应停止当前“生成开发任务文档”的自动化，避免重复生成或开始未经确认的编码。

## 16. 子任务拆分

后续编码阶段可拆成以下独立子任务：

| 子任务 | 内容 | 前置 |
| --- | --- | --- |
| DACC-01 | 生成 acceptance checklist 和报告模板 | P0 文档评审 |
| DACC-02 | 编写数据库基线和原始表只读验收测试 | M00-M02 完成 |
| DACC-03 | 编写 M00-M16 module contract 验收测试 | M16 完成 |
| DACC-04 | 编写 full pipeline 和增量模式验收测试 | M16 完成 |
| DACC-05 | 编写 API contract 和 response guardrail 验收测试 | API 完成 |
| DACC-06 | 编写 frontend business language 和 internal field guard 测试 | FRONTEND 完成 |
| DACC-07 | 编写 85E7Q end-to-end fixture 验收 | M15/M16/API/FRONTEND 完成 |
| DACC-08 | 编写 205 predeploy 只读检查脚本和清单 | 本地验收通过 |
| DACC-09 | 生成 acceptance JSON 和 Markdown 报告 | DACC-01 到 DACC-08 |
| DACC-10 | 执行 go/no-go 评审并申请部署 | 全部 P0 通过 |

每个子任务仍需按“小闭环开发、测试、验收”的方式执行，不得一次性把所有验收代码写完。

## 17. 下次任务

没有下一份开发任务文档。

建议下一步：

1. 停止 `catforge` 开发任务文档定时器。
2. 人工评审 P0 开发任务文档目录。
3. 如确认进入编码阶段，从 INFRA 的第一个小闭环开始，不直接跳到页面或部署。
