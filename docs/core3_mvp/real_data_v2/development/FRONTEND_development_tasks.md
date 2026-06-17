# FRONTEND 独立页面和业务展示开发任务

## 1. 模块目标

FRONTEND 开发任务的目标是为 CatForge 彩电核心三竞品真实数据 v2 建一套独立前端页面，让业务高层和数据运营人员能够基于真实数据查看核心竞品、推导依据、证据卡、复核状态和生产线状态。

前端不是算法调试台，也不是 AI 对话产品。页面必须用业务语言回答：

1. 当前目标 SKU 的核心竞品是谁。
2. 每个竞品分别代表正面对打、价格/销量挤压、高端标杆/潜在下探中的哪类竞争压力。
3. 为什么这些 SKU 是竞品，而不是普通相似 SKU。
4. 主要价值战场是什么，目标 SKU 和竞品是否都在这些战场有证据。
5. 价格、渠道、参数、卖点、任务、客群、战场、市场、评论证据如何支撑结论。
6. 哪些结论可以汇报，哪些需要复核，哪些被发布门禁阻断。
7. 当前 205 样例数据的范围和限制是什么，特别是全量海信样例、线上平台样例和 85E7Q 宣传卖点数据缺口。

前端要解决的工程问题：

1. 建立 `core3RealData` 独立页面族，不混入旧 `pages/core3` 和 Goal3 工作台。
2. 基于 API 任务定义的 `/api/mvp/core3/v2` 契约读取数据，不直接读取旧 `/api/mvp/core3`。
3. 把业务高层报告页和运营生产线状态页分开。
4. 把 M15 业务报告 payload 以“先竞品、再理由、后证据和推导”的顺序展示。
5. 把 M16 发布门禁、复核、验收状态转成中文业务提示。
6. 为证据短编号提供可展开追溯抽屉，但不在主屏展示 UUID、SQL、表名和内部字段。
7. 为 blocked、review_required、releasable、released 做清晰状态区分。
8. 提供 85E7Q 的完整演示路径和错误/空状态。

前端必须固化以下边界：

- 不修改后端 API、service、schema、migration。
- 不重新计算竞品、分数、候选池或证据。
- 不在前端拼接业务结论；主报告结论来自 API 的 M15/M16 聚合 payload。
- 不直接渲染 raw JSON、UUID、SQL、内部英文枚举、表名、字段名。
- 不展示“AI 认为”“模型判断”“生成过程”“正在思考”等过程文案。
- 不把生产线状态页的 M00-M16 技术细节放到高层主报告页。
- 不复用旧 `Core3Mvp` 作为真实数据 v2 页面主体。
- 不部署 205。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| API 开发任务 | `docs/core3_mvp/real_data_v2/development/API_development_tasks.md` |
| M15 开发任务 | `docs/core3_mvp/real_data_v2/development/M15_development_tasks.md` |
| M16 开发任务 | `docs/core3_mvp/real_data_v2/development/M16_development_tasks.md` |
| 总体架构 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M15 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M15_evidence_report_design.md` |
| M16 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M16_incremental_review_acceptance_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| UI 规范 | `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md` |
| 旧页面参考 | `apps/factory-web/src/pages/core3/Core3Mvp.tsx`、`apps/factory-web/src/pages/core3/core3Format.ts` |
| 前端入口参考 | `apps/factory-web/src/App.tsx`、`apps/factory-web/src/api/client.ts`、`apps/factory-web/src/types/index.ts` |

编码前必须确认：

- API 任务已经定义 `/api/mvp/core3/v2` 的业务展示、证据追溯、生产线状态、复核和发布接口。
- M15 产物已经提供报告标题、核心竞品、证据卡、section、导出和复核问题。
- M16 产物已经提供发布门禁、运行状态、验收报告、复核队列和水位。
- 前端当前使用 React、TypeScript、Vite、Ant Design、Vitest。
- 旧 `pages/core3` 属于早期粗粒度 MVP，只能作为布局和格式化经验参考，不能作为 v2 页面混写位置。

## 3. 本次范围

本次开发任务拆分覆盖真实数据 v2 前端实现准备：

| 范围 | 说明 |
| --- | --- |
| 页面族 | 新建 `apps/factory-web/src/pages/core3RealData/` |
| 独立入口 | 在 `App.tsx` 中增加真实数据 v2 路由或入口，不影响旧页面 |
| API client | 增加 `core3RealData` API 方法，调用 `/api/mvp/core3/v2` |
| TypeScript 类型 | 新增 v2 API response 类型、页面 view model 类型和状态枚举 |
| 页面结构 | 批量总览、单品报告、证据卡/追溯、生产线状态四类页面 |
| 业务组件 | 目标结论条、目标画像卡、三竞品角色卡、价值战场摘要、证据矩阵、推导轨迹、候选池未选原因 |
| 运营组件 | 运行列表、模块状态、重算计划、复核队列、验收报告、发布门禁 |
| 状态处理 | loading、empty、error、blocked、review_required、releasable、released |
| 导出入口 | 读取 API 已生成导出内容，不在前端重新生成事实 |
| 视觉样式 | 按 UI 规范建立克制、可信、报告感强的样式 |
| 测试 | 类型、格式化、页面配置、API client、guardrail、85E7Q fixture、构建和浏览器验收 |

本次不做：

- 不写后端代码。
- 不写数据库迁移。
- 不修改 M00-M16 开发文档。
- 不改旧 `pages/core3` 的页面逻辑。
- 不把 v2 页面挂到 Goal3 工作台下。
- 不部署 205。
- 不引入新的大型状态管理库。
- 不使用三维、动效大屏、黑底指挥舱或 AI 聊天式 UI。

## 4. 要改文件

### 4.1 新增前端页面目录

```text
apps/factory-web/src/pages/core3RealData/Core3RealDataApp.tsx
apps/factory-web/src/pages/core3RealData/core3RealDataPages.ts
apps/factory-web/src/pages/core3RealData/core3RealDataFormat.ts
apps/factory-web/src/pages/core3RealData/core3RealDataGuards.ts
apps/factory-web/src/pages/core3RealData/Core3RealDataOverview.tsx
apps/factory-web/src/pages/core3RealData/Core3RealDataReport.tsx
apps/factory-web/src/pages/core3RealData/Core3RealDataEvidence.tsx
apps/factory-web/src/pages/core3RealData/Core3RealDataPipeline.tsx
apps/factory-web/src/pages/core3RealData/components/DataScopeBar.tsx
apps/factory-web/src/pages/core3RealData/components/ReleaseStatusBadge.tsx
apps/factory-web/src/pages/core3RealData/components/TargetConclusionStrip.tsx
apps/factory-web/src/pages/core3RealData/components/TargetSignalCards.tsx
apps/factory-web/src/pages/core3RealData/components/CoreCompetitorCards.tsx
apps/factory-web/src/pages/core3RealData/components/CompetitorRoleCard.tsx
apps/factory-web/src/pages/core3RealData/components/BattlefieldSummaryPanel.tsx
apps/factory-web/src/pages/core3RealData/components/EvidenceMatrix.tsx
apps/factory-web/src/pages/core3RealData/components/DerivationTracePanel.tsx
apps/factory-web/src/pages/core3RealData/components/CandidateAuditPanel.tsx
apps/factory-web/src/pages/core3RealData/components/ReviewHintPanel.tsx
apps/factory-web/src/pages/core3RealData/components/EvidenceTraceDrawer.tsx
apps/factory-web/src/pages/core3RealData/components/ReportExportActions.tsx
apps/factory-web/src/pages/core3RealData/components/PipelineRunTimeline.tsx
apps/factory-web/src/pages/core3RealData/components/ReviewQueueTable.tsx
apps/factory-web/src/pages/core3RealData/components/AcceptanceSummary.tsx
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `Core3RealDataApp.tsx` | v2 页面壳、项目选择、页签、全局状态 |
| `core3RealDataPages.ts` | 页面 key、导航配置、页面中文名 |
| `core3RealDataFormat.ts` | 中文标签、数字、金额、百分比、状态文案格式化 |
| `core3RealDataGuards.ts` | 前端渲染 guardrail，阻止内部字段泄露 |
| `Core3RealDataOverview.tsx` | 批量总览页 |
| `Core3RealDataReport.tsx` | 单品高层报告页 |
| `Core3RealDataEvidence.tsx` | 证据卡和短证据追溯页 |
| `Core3RealDataPipeline.tsx` | 运营生产线状态页 |
| `DataScopeBar.tsx` | 数据范围、更新时间、样例限制 |
| `ReleaseStatusBadge.tsx` | 发布门禁中文状态 |
| `TargetConclusionStrip.tsx` | 顶部目标 SKU 结论条 |
| `TargetSignalCards.tsx` | 目标 SKU 市场和产品信号 |
| `CoreCompetitorCards.tsx` | 三竞品角色卡容器 |
| `CompetitorRoleCard.tsx` | 单个竞品角色卡 |
| `BattlefieldSummaryPanel.tsx` | 价值战场摘要 |
| `EvidenceMatrix.tsx` | 证据矩阵 |
| `DerivationTracePanel.tsx` | 可展开 SOP 推导轨迹 |
| `CandidateAuditPanel.tsx` | 候选池和未选原因 |
| `ReviewHintPanel.tsx` | 复核和数据缺口提示 |
| `EvidenceTraceDrawer.tsx` | 短证据编号追溯抽屉 |
| `ReportExportActions.tsx` | 报告导出按钮 |
| `PipelineRunTimeline.tsx` | 生产线运行状态 |
| `ReviewQueueTable.tsx` | 复核队列表 |
| `AcceptanceSummary.tsx` | 验收摘要 |

### 4.2 允许修改的共享文件

```text
apps/factory-web/src/App.tsx
apps/factory-web/src/api/client.ts
apps/factory-web/src/types/index.ts
apps/factory-web/src/styles.css
```

| 文件 | 允许改动 |
| --- | --- |
| `App.tsx` | 增加 v2 独立入口和导航，不改变旧页面行为 |
| `client.ts` | 增加 `/api/mvp/core3/v2` API 方法 |
| `types/index.ts` | 增加 v2 API 类型 |
| `styles.css` | 增加 `core3-real-data-*` 样式块 |

### 4.3 新增测试文件

```text
apps/factory-web/src/pages/core3RealData/core3RealDataPages.test.ts
apps/factory-web/src/pages/core3RealData/core3RealDataFormat.test.ts
apps/factory-web/src/pages/core3RealData/core3RealDataGuards.test.ts
apps/factory-web/src/pages/core3RealData/core3RealDataViewModels.test.ts
apps/factory-web/src/pages/core3RealData/core3RealDataFixture.test.ts
```

如编码阶段决定引入 React 组件渲染测试，应先确认项目是否已有 `@testing-library/react`；没有时首版不强行新增依赖，优先做纯函数、配置、view model 和构建验收。

## 5. 不允许改文件

本任务开发时不得修改以下范围：

```text
apps/api-server/
apps/factory-web/src/pages/core3/Core3Mvp.tsx
apps/factory-web/src/pages/core3/core3Pages.ts
apps/factory-web/src/pages/core3/Core3StandaloneApp.tsx
apps/factory-web/src/pages/workbenchPages.ts
apps/factory-web/src/pages/Workbench.tsx
apps/factory-web/package.json
docs/core3_mvp/real_data_v2/sop_requirements/
docs/core3_mvp/real_data_v2/sop_detailed_design/
cankao/
```

允许例外：

- 如果必须在 `App.tsx` 增加入口，可只改入口选择和菜单项。
- 如果必须在 `styles.css` 增加样式，只追加 `core3-real-data-*` 命名空间样式。
- 如果测试需要新增依赖，必须先单独提出，不在本任务默认范围内。

不得引入的行为：

- 通过旧 `api.core3Report`、`api.core3Overview`、`api.core3Evidence` 读取 v2 页面数据。
- 前端从 M13/M14 明细自行组合最终竞品。
- 前端把 `display_payload_json` 原样渲染。
- 前端展示原始表名、字段名、UUID、SQL、JSON 大段、内部英文枚举。
- 前端把服务体验或物流安装评论包装成产品核心竞争力。
- 前端把“宣传卖点数据缺口”写成“产品没有卖点”。
- 前端把全海信样例误写成外部品牌竞争格局。

## 6. 数据库任务

前端任务不涉及数据库迁移、表结构、索引和回滚。

前端只能消费 API 返回的业务展示 payload、证据追溯 payload 和生产线状态 payload。若发现 API 缺字段，应在开发任务中记录 API 缺口，不得直接绕到后端表或原始四表取数。

## 7. model/schema 任务

### 7.1 TypeScript 类型

在 `apps/factory-web/src/types/index.ts` 增加 v2 类型：

```text
Core3V2DataStatusResponse
Core3V2SkuResolveResponse
Core3V2OverviewResponse
Core3V2TargetListResponse
Core3V2TargetSummary
Core3V2BusinessReportResponse
Core3V2TargetProfile
Core3V2CoreCompetitor
Core3V2EvidenceCard
Core3V2ReportSection
Core3V2CandidateAudit
Core3V2DataScope
Core3V2ReleaseStatus
Core3V2ReviewHint
Core3V2ExportItem
Core3V2EvidenceTraceResponse
Core3V2PipelineRunResponse
Core3V2ModuleRunResponse
Core3V2ReviewQueueResponse
Core3V2AcceptanceReportResponse
Core3V2ReleaseGateResponse
```

### 7.2 前端状态枚举

必须定义并集中映射：

```text
ReleaseStatus = not_ready / review_required / releasable / released / blocked
PageLoadStatus = idle / loading / ready / empty / error
ReportVisibility = blocked_summary / review_with_report / full_report / not_ready
CompetitorRole = direct_fight / price_volume_pressure / benchmark_potential
EvidenceTraceUsage = business_short_ref / technical_trace
PipelineStatus = pending / running / success / warning / review_required / blocked / failed
```

页面展示必须使用中文：

| 内部值 | 页面中文 |
| --- | --- |
| `not_ready` | 尚未生成 |
| `review_required` | 需要复核 |
| `releasable` | 可汇报 |
| `released` | 已发布 |
| `blocked` | 已阻断 |
| `direct_fight` | 正面对打竞品 |
| `price_volume_pressure` | 价格/销量挤压竞品 |
| `benchmark_potential` | 高端标杆/潜在下探竞品 |

### 7.3 view model

新增前端 view model，不把 API response 原样塞给组件：

```text
Core3RealDataOverviewView
Core3RealDataTargetListView
Core3RealDataReportView
Core3RealDataCompetitorCardView
Core3RealDataEvidenceCardView
Core3RealDataDerivationStepView
Core3RealDataPipelineView
Core3RealDataReviewView
```

view model 要求：

- 所有主屏文案已经是中文业务语言。
- 证据只显示短证据编号。
- blocked 报告只生成阻断摘要 view，不生成完整报告 view。
- review_required 报告必须有复核提示。
- 空槽必须显示原因，不能显示空白卡。
- 85E7Q 宣传卖点缺口必须进入 `ReviewHint` 或 `DataScope`。

### 7.4 schema 测试

必须测试：

- v2 类型不复用旧 `Core3SkuReport`。
- release status 映射完整。
- 竞品角色顺序固定为正面对打、价格/销量挤压、高端标杆/潜在下探。
- view model 不包含 raw UUID。
- blocked response 不生成完整报告主体。

## 8. repository 任务

前端 repository 对应 API client。

### 8.1 API client 方法

在 `client.ts` 或新增 `core3RealDataClient.ts` 中提供：

```text
core3V2DataStatus(projectId, categoryCode)
core3V2ResolveSku(projectId, query, categoryCode)
core3V2Overview(projectId, filters)
core3V2Targets(projectId, filters)
core3V2Report(projectId, skuOrModel, options)
core3V2Competitors(projectId, skuOrModel, options)
core3V2EvidenceCards(projectId, skuOrModel, options)
core3V2ReportSections(projectId, skuOrModel, options)
core3V2EvidenceTrace(projectId, skuOrModel, shortRef)
core3V2Export(projectId, skuOrModel, exportType)
core3V2StartPipelineRun(projectId, payload)
core3V2PipelineRuns(projectId, filters)
core3V2PipelineRun(projectId, runId)
core3V2PipelineModules(projectId, runId, filters)
core3V2RecomputePlan(projectId, runId, filters)
core3V2Reviews(projectId, runId, filters)
core3V2SubmitReviewDecision(projectId, reviewId, payload)
core3V2Acceptance(projectId, runId)
core3V2ReleaseGates(projectId, runId, filters)
core3V2Release(projectId, gateId, payload)
```

### 8.2 API client 约束

- 所有 v2 方法统一走 `/api/mvp/core3/v2`。
- 旧 `core3Run`、`core3Overview`、`core3Report`、`core3Evidence` 保留给旧页面。
- 错误处理要解析 `message_cn`、`action_hint_cn`。
- 导出接口按文本或 blob 读取，不再由前端从 JSON 重新生成 markdown。
- API client 不包含业务判定逻辑，只做请求和错误包装。

### 8.3 repository 测试

必须测试：

- v2 API 路径前缀正确。
- old core3 API 方法未被删除。
- 404/409/423 错误能显示中文 message。
- 导出接口不会调用旧 export 路径。

## 9. service 任务

前端 service 是页面状态和 view model 构建层，不做业务算法。

### 9.1 页面状态 hook

建议新增：

```text
useCore3RealDataProjects
useCore3RealDataOverview
useCore3RealDataReport
useCore3RealDataEvidenceTrace
useCore3RealDataPipeline
useCore3RealDataReviews
```

如果不单独建 hook 文件，也必须在页面组件内保持状态边界清晰，不把多个页面的 loading/error 混在一起。

### 9.2 view model builder

建议新增或放在 `core3RealDataFormat.ts`：

```text
buildOverviewView(response)
buildReportView(response)
buildCompetitorCardView(response)
buildEvidenceCardView(response)
buildPipelineView(response)
buildReviewQueueView(response)
```

职责：

- 映射中文状态和标签。
- 处理空槽和数据缺口。
- 将长文案压缩为适合卡片的短句。
- 将生产线状态页文案和高层报告页文案隔离。
- 在 view model 层执行前端 guardrail。

### 9.3 前端 guardrail

`core3RealDataGuards.ts` 必须检查主屏 view model：

| 检查 | 处理 |
| --- | --- |
| UUID | 不渲染，显示“证据编号异常，需复核” |
| `core3_`、`_json`、`_id`、`candidate_` | 不渲染，记录前端错误状态 |
| SQL 片段 | 不渲染 |
| AI 过程文案 | 不渲染 |
| 低置信确定语气 | 显示复核提示 |
| 数据范围缺失 | 显示“数据范围待确认” |

前端 guardrail 是最后防线；后端 API guardrail 仍是主防线。

### 9.4 错误和空状态

页面必须有明确状态：

| 状态 | 展示 |
| --- | --- |
| 无项目 | 提示选择或创建项目 |
| 无 v2 数据 | 提示先完成真实数据生产线 |
| SKU 未找到 | 提示检查型号或 SKU |
| 多 SKU 匹配 | 展示候选列表供用户选择 |
| 报告未生成 | 提示启动单目标刷新 |
| 报告被阻断 | 显示阻断原因和复核入口 |
| 需要复核 | 显示报告但置顶复核提示 |
| API 错误 | 显示中文错误和重试按钮 |

## 10. runner/API 任务

前端没有 runner，不启动后端算法，只调用 API。

### 10.1 页面路由和入口

建议首版支持两种入口：

1. 独立展示入口：访问非 `/factory` 路径时进入 v2 页面，例如 `/core3-real-data`。
2. 工厂后台入口：在侧边栏增加“彩电三竞品 v2”，进入独立页面族。

实现要求：

- 不替换旧 `Core3StandaloneApp`，除非入口判断明确区分 v1/v2。
- 新菜单 key 不与 Goal3 工作台和旧 core3 页面重复。
- 页面默认定位到单品报告，默认查询 `85E7Q`。
- 项目选择复用现有 `api.listProjects()`。

### 10.2 页面一：批量总览

目标：给业务和运营看到当前报告总体可用性。

内容：

- 数据范围条：时间、渠道、品牌样例、更新时间。
- KPI：目标数、可汇报、需复核、已阻断、未生成。
- 目标 SKU 表：型号、主战场、核心竞品数、门禁状态、复核数量、最近更新时间。
- 操作：查看报告、查看生产线状态、导出汇总。

禁止：

- 显示完整模块 run 明细。
- 显示 raw UUID 或内部字段。

### 10.3 页面二：单品高层报告

目标：领导 30 秒内看懂核心竞品和原因。

页面顺序：

```text
顶部输入与数据范围
-> 目标 SKU 结论条
-> 目标 SKU 画像信号卡
-> 核心竞品三角色卡
-> 为什么是这些竞品
-> 价值战场摘要
-> 证据矩阵
-> 候选池和未选原因
-> 可展开推导轨迹
-> 复核和数据缺口
-> 导出入口
```

核心竞品卡字段：

- 竞品型号。
- 竞品角色。
- 一句话理由。
- 价值战场重合。
- 市场压力。
- 关键差异。
- 策略含义。
- 置信度。
- 证据短编号。

空槽处理：

- 如果不足 3 个高置信竞品，显示“暂无高置信候选”。
- 必须展示空槽原因。
- 不得硬凑第三个竞品。

### 10.4 页面三：证据卡和证据追溯

目标：业务人员可读证据卡，分析人员可查短证据追溯。

内容：

- 按竞品角色分组的证据卡。
- 证据类型：价格、渠道、参数、卖点、任务/客群、战场、市场、评论。
- 短证据编号按钮。
- 点击短证据编号打开追溯抽屉。
- 追溯抽屉明确标注“技术追溯，不用于主屏汇报”。

禁止：

- 主证据卡显示 raw UUID。
- 主证据卡显示 SQL 或内部字段。
- 评论证据直接作为产品核心卖点。

### 10.5 页面四：生产线状态

目标：运营人员查看 M16 运行、复核、验收和门禁。

内容：

- 最新 run 状态。
- 模块运行摘要。
- 重算计划摘要。
- 复核队列。
- 验收报告四层摘要。
- 发布门禁列表。
- 复核决策动作。
- 标记发布动作。

边界：

- 可以显示 M00-M16 模块码，因为对象是运营人员。
- 不能把这页内容混到高层报告主屏。
- 复核和发布动作必须确认后执行。

## 11. 测试任务

### 11.1 页面配置测试

`core3RealDataPages.test.ts`：

- 页面 key 不与旧 core3 和 Goal3 工作台重复。
- 页面顺序固定：总览、单品报告、证据卡、生产线状态。
- 默认页是单品报告。
- 页面中文名不包含英文内部术语。

### 11.2 格式化测试

`core3RealDataFormat.test.ts`：

- release status 中文映射完整。
- 竞品角色中文映射完整。
- 价格、销量、百分比格式正确。
- `unknown`、空字符串、`-` 显示为“未确认”或“暂无证据”，不显示 false。
- 85E7Q 数据范围格式为 `26W01-26W23 线上样例`。

### 11.3 guardrail 测试

`core3RealDataGuards.test.ts`：

- UUID 被拦截。
- `core3_`、`candidate_`、`_json`、`_id` 被拦截。
- SQL 片段被拦截。
- AI 过程文案被拦截。
- 低置信确定语气被识别。
- 数据范围缺失会产生前端警告。

### 11.4 view model 测试

`core3RealDataViewModels.test.ts`：

- blocked gate 只生成阻断摘要。
- review_required gate 生成报告和复核提示。
- releasable gate 生成完整报告。
- 空槽生成“暂无高置信候选”和空槽原因。
- 技术追溯字段不会进入主报告 view。

### 11.5 85E7Q fixture 测试

`core3RealDataFixture.test.ts`：

- 默认输入为 `85E7Q`。
- target SKU 显示 `TV00029115`。
- 数据范围显示 `26W01-26W23`、线上样例、专业电商/平台电商。
- 同品牌样例不显示成“缺少外部品牌所以无竞品”。
- 宣传卖点数据缺口显示为数据缺口，而不是产品无卖点。
- 服务体验不显示为产品核心竞争力。
- 主报告 view 不含 UUID、SQL、内部字段和 AI 过程文案。

### 11.6 构建和浏览器验收

编码完成后必须运行：

```text
npm run test
npm run build
```

如果本任务实际实现页面，还必须用浏览器验证：

- 桌面 1440px：主报告首屏能看到目标结论、核心竞品卡和下一屏提示。
- 笔记本 1280px：三竞品卡不溢出。
- 移动 390px：卡片纵向排列，文本不重叠。
- 页面无英文内部字段、UUID、SQL 和 AI 过程文案。
- 证据追溯抽屉可打开和关闭。

## 12. 205/85E7Q 验收

前端首版必须能围绕 85E7Q 完成演示：

| 验收点 | 前端表现 |
| --- | --- |
| 默认目标 | 单品报告默认查询 `85E7Q` |
| SKU 解析 | 页面显示 `TV00029115` 和业务型号 |
| 数据范围 | 顶部显示 `26W01-26W23`、线上样例、专业电商/平台电商 |
| 同品牌样例 | 页面说明“当前样例内竞品关系”，不写外部品牌结论 |
| 宣传卖点缺口 | 复核提示显示“宣传卖点数据缺口” |
| 核心竞品 | 三角色卡展示 0-3 个竞品；不足时说明空槽原因 |
| 推导过程 | 展示目标画像、价值战场、候选池、评分选择、证据卡的业务链路 |
| 证据卡 | 主屏只展示短证据编号，追溯抽屉可查看详情 |
| 业务语言 | 页面无 UUID、SQL、内部字段、英文枚举和 AI 过程文案 |
| 发布门禁 | blocked/review_required/releasable/released 状态清晰 |

当前页面是给海信业务高层看效果。文案必须像产品经理向领导汇报：

- 先说结论。
- 再解释为什么。
- 再展示证据。
- 最后说明限制和复核项。

不能像系统日志、算法过程、数据库查询结果或 AI 生成过程。

## 13. 完成标准

FRONTEND 开发完成必须满足：

| 标准 | 要求 |
| --- | --- |
| 独立页面 | `core3RealData` 页面族存在，不混旧 `pages/core3` |
| 独立入口 | 能从独立路径或工厂后台入口进入 |
| API 契约 | 只调用 `/api/mvp/core3/v2` |
| 页面完整 | 总览、单品报告、证据卡/追溯、生产线状态四类页面可用 |
| 结论先行 | 单品报告先展示核心竞品，再解释为什么 |
| 业务语言 | 主屏全中文业务文案 |
| 证据可追溯 | 短证据编号可打开技术追溯抽屉 |
| 门禁清晰 | blocked/review_required/releasable/released 有不同状态 |
| 样例边界 | 85E7Q、线上样例、同品牌样例、卖点缺口表达正确 |
| 无泄露 | 主屏无 UUID、SQL、内部字段、英文枚举、AI 过程文案 |
| 响应式 | 桌面、笔记本、移动不重叠、不溢出 |
| 测试 | Vitest、TypeScript build 通过 |
| 旧页面 | 旧 `Core3Mvp` 和 Goal3 工作台不被破坏 |

## 14. 风险和回滚

| 风险 | 处理 |
| --- | --- |
| 页面又混回旧 core3 | 新建 `core3RealData` 目录，测试页面 key 隔离 |
| 前端重算业务结论 | view model 只映射 API payload，缺字段时显示缺口 |
| 主屏泄露内部字段 | 前端 guardrail + 后端 guardrail + fixture 测试 |
| 业务页面像算法日志 | 信息结构固定为结论、理由、证据、限制 |
| 生产线状态污染主报告 | 运营状态页独立，主报告只显示门禁摘要 |
| 文字太长或重叠 | 卡片短句化、可展开详情、响应式测试 |
| 设计过度 AI 化 | 遵守 UI 规范，克制商用数据产品风格 |
| 旧页面回归 | 旧 core3 tests 保留，新入口可单独关闭 |

回滚策略：

1. 从 `App.tsx` 移除 v2 入口，旧页面仍可用。
2. 删除或隐藏 `core3RealData` 菜单项，不影响后端 API。
3. 样式使用 `core3-real-data-*` 命名空间，可单独移除。
4. API client v2 方法可保留，不影响旧 API 方法。

## 15. 下游依赖

ACCEPTANCE 任务依赖本任务输出：

- 可以通过 UI 完成 85E7Q 演示路径。
- 可以验证单品报告是否“先说竞品，再解释为什么”。
- 可以验证业务主屏无英文内部字段、UUID、SQL、AI 过程文案。
- 可以验证数据范围和样例限制是否清晰。
- 可以验证发布门禁和复核状态是否能被业务理解。
- 可以验证旧页面和新真实数据 v2 页面分离。

205 部署验收依赖本任务输出：

- 前端 build 可通过。
- v2 页面路径明确。
- 部署后能在 `cftest.ctfcoach.com` 或 205 访问对应页面。
- 业务高层看到的是报告页，不是生产线日志页。

## 16. 子任务拆分

| 子任务 | 内容 | 主要产物 |
| --- | --- | --- |
| DFE-01 | 新增 v2 TypeScript 类型 | `types/index.ts` |
| DFE-02 | 新增 v2 API client 方法 | `api/client.ts` 或 `api/core3RealDataClient.ts` |
| DFE-03 | 新增页面配置和格式化工具 | `core3RealDataPages.ts`、`core3RealDataFormat.ts` |
| DFE-04 | 新增前端 guardrail | `core3RealDataGuards.ts` |
| DFE-05 | 新增 v2 页面壳和入口 | `Core3RealDataApp.tsx`、`App.tsx` |
| DFE-06 | 实现批量总览页 | `Core3RealDataOverview.tsx` |
| DFE-07 | 实现单品报告页核心布局 | `Core3RealDataReport.tsx` |
| DFE-08 | 实现三竞品角色卡和目标画像组件 | role cards、signal cards |
| DFE-09 | 实现价值战场、证据矩阵、推导轨迹 | battlefield/evidence/trace components |
| DFE-10 | 实现证据卡和追溯抽屉 | `Core3RealDataEvidence.tsx`、`EvidenceTraceDrawer.tsx` |
| DFE-11 | 实现生产线状态页 | `Core3RealDataPipeline.tsx` |
| DFE-12 | 实现复核和发布动作 UI | `ReviewQueueTable.tsx`、release actions |
| DFE-13 | 追加样式 | `styles.css` |
| DFE-14 | 补前端测试和 fixture | `core3RealData*.test.ts` |
| DFE-15 | 运行构建和浏览器验收 | `npm run test`、`npm run build`、截图验收 |

编码时每次只做一个子任务或一个可测试闭环，不要在同一轮同时做后端、前端和部署。

## 17. 下次任务

完成 FRONTEND 开发任务文档后，下一个文档是：

```text
docs/core3_mvp/real_data_v2/development/ACCEPTANCE_development_tasks.md
```

ACCEPTANCE 任务应基于 M00-M16、API 和 FRONTEND 的开发任务文档，设计全链路验收、部署前检查、205 样例验证和最终开发准入门禁。
