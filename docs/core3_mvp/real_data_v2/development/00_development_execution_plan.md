# CatForge 彩电核心三竞品真实数据 MVP 开发实施总纲

## 1. 文档目标

本文定义 `real_data_v2` 从需求和详细设计进入开发阶段的实施方式。开发阶段的目标不是一次性把 M00-M16 全部写完，而是把已完成的 SOP 需求和详细设计转换为可验收、可测试、可回滚的工程任务。

后续开发必须保持“每次只处理一个独立模块或一个独立基础设施任务”的节奏。不得在一个任务中同时改多个模块的业务逻辑，也不得把 M00-M16 压缩成一个大脚本。

## 2. 当前准入结论

当前状态满足进入开发准备阶段，理由如下：

| 检查项 | 当前状态 | 结论 |
| --- | --- | --- |
| SOP 需求文档 | `M00-M16` 已完成 | 通过 |
| 真实数据基线 | 已记录 205 PostgreSQL 样例数据约束 | 通过 |
| 详细设计总纲 | 已完成 | 通过 |
| 模块详细设计 | `00` 和 `M00-M16` 已完成 | 通过 |
| 分层边界 | 原始表、清洗表、证据表、抽取表、画像表、结果表、治理表已拆分 | 通过 |
| 业务展示边界 | 高层页面与生产线状态分离 | 通过 |
| 待评审问题 | 存在少量首版口径选择 | 不阻断开发，但必须固化为首版默认 |

结论：

```text
可以进入开发任务拆分阶段。
不建议立即进入自动编码阶段。
```

在正式编码前，必须先完成 `development/` 下的模块开发任务拆分文档，至少先完成 `00`、`M00`、`M01`、`M02` 的开发任务拆分。

## 3. 开发依据

开发必须以以下文件为准：

1. `docs/core3_mvp/real_data_v2/sop_requirements/`
2. `docs/core3_mvp/real_data_v2/sop_detailed_design/`
3. `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md`
4. `cankao/CatForge_竞品生成SOP_详细指导_v1.md`
5. `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md`
6. `cankao/catforge_sop_md/modules/`
7. 仓库现有工程结构和约束：
   - 后端：FastAPI、SQLAlchemy、Alembic、Pydantic、pytest
   - 前端：React、TypeScript、Vite、Ant Design、vitest
   - 当前旧 MVP：`apps/api-server/app/services/core3_mvp/`
   - 新真实数据 v2：必须走独立命名空间，不与旧 `core3_mvp` 粗粒度链路混写

如果开发实现与详细设计冲突，以详细设计为准；如果详细设计内部存在冲突，应先生成修订任务，不得在代码里自行改变业务口径。

## 4. 命名空间和目录原则

### 4.1 后端

真实数据 v2 后端建议新增独立包：

```text
apps/api-server/app/services/core3_real_data/
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
```

模型可以根据现有项目风格选择：

```text
apps/api-server/app/models/entities.py
```

或在后续重构中拆为：

```text
apps/api-server/app/models/core3_real_data.py
```

首版原则：优先少量、清晰、可迁移，不为了拆文件而破坏现有 Alembic/env 加载方式。

### 4.2 数据库迁移

所有新表必须通过 Alembic migration 落地：

```text
apps/api-server/alembic/versions/
```

迁移要求：

- 每个开发任务只新增本模块需要的表。
- 不修改原始四表结构。
- 不删除或覆盖旧 MVP 表。
- 新表必须包含 `project_id`、`category_code`、`batch_id/run_id`、版本、hash、审计字段等追溯字段。
- 所有唯一键、索引和 JSONB 字段必须与详细设计一致。

### 4.3 前端

真实数据 v2 页面必须与现有页面分离：

```text
apps/factory-web/src/pages/core3RealData/
```

首版页面分层：

| 页面 | 面向对象 | 说明 |
| --- | --- | --- |
| 批量总览 | 业务/运营 | 看可发布报告数量、待复核数量、目标 SKU 列表 |
| 单品报告 | 业务高层 | 先看核心竞品是谁，再看为什么 |
| 证据卡 | 业务/分析人员 | 看短证据编号和证据摘要 |
| 生产线状态 | 运营/数据人员 | 看 M16 运行、复核、验收和门禁 |

高层页面禁止展示：

- 英文内部字段名。
- UUID。
- SQL。
- JSON 大段结构。
- M00-M16 完整技术链路。
- AI 过程、模型思考、机器人话术。
- 原始大表。

## 5. 开发阶段划分

开发分为六个阶段，每个阶段再按模块拆任务。

| 阶段 | 范围 | 目标 |
| --- | --- | --- |
| P0 开发任务拆分 | `development/` 文档 | 把详细设计拆成可执行任务 |
| P1 基础设施和治理骨架 | 迁移、模型、通用 schema、runner 协议、测试 fixture | 让模块能独立运行和记录状态 |
| P2 数据底座 | M00-M02 | 原始登记、清洗、evidence |
| P3 抽取和画像 | M03-M11.5 | 参数、卖点、评论、市场、任务、客群、战场 |
| P4 竞品推导和报告 | M12-M15 | 候选、评分、三槽位、证据卡、报告 |
| P5 编排验收和页面 | M16、API、前端页面、导出、部署 | 全链路可运行、可复核、可展示 |

## 6. 任务执行方式

### 6.1 定时模式建议

后续如果继续使用定时器，建议：

```text
间隔：10 分钟
方式：每次只处理一个开发任务
```

定时器前两轮建议先用于开发任务拆分：

1. 生成 `00_development_task_breakdown.md`
2. 生成 `M00_development_tasks.md`

之后再按任务拆分进入编码。

### 6.2 每次任务只允许一种类型

每次任务只能属于以下一种：

| 类型 | 示例 |
| --- | --- |
| 开发任务拆分 | 只写 `M00_development_tasks.md` |
| 数据库迁移 | 只实现 M00 表迁移 |
| 后端模型/schema | 只实现 M00 models 和 schemas |
| repository/service | 只实现 M00 repository/service |
| runner/API | 只实现 M00 runner 或 API |
| 测试 | 只补 M00 测试 |
| 前端页面 | 只做某个页面或组件 |
| 修复 | 只修一个已发现问题 |

禁止一个任务同时完成：

- 多个模块业务逻辑。
- 后端和前端大范围联动。
- 数据库迁移和复杂 UI。
- M00-M16 全链路脚本。
- 部署和业务逻辑改造。

### 6.3 每次任务开始前必须做的检查

1. 查看当前任务对应开发任务文档。
2. 查看对应 SOP 需求和详细设计。
3. 查看 git 状态，避免覆盖无关变更。
4. 查看现有代码模式，至少对齐 3 个相似实现或邻近文件。
5. 明确本次只改哪些文件。

### 6.4 每次任务结束必须做的检查

1. 运行与本次变更相关的最小测试。
2. 如果是后端迁移或模型，运行 Alembic/schema 相关检查。
3. 如果是 API，运行 pytest API/schema 测试。
4. 如果是前端，运行 vitest 或 `npm run build`。
5. 汇报本次改动、验证结果、未做事项、下一任务。

## 7. 模块开发顺序

开发顺序必须遵循依赖，不按 UI 优先。

```text
00 开发任务拆分和基础约定
-> INFRA 数据库/通用类型/runner 骨架
-> M00 原始数据批次与行登记
-> M01 清洗规范化与质量诊断
-> M02 Evidence 原子层
-> M03 参数字段画像与标准参数抽取
-> M04a 基础卖点激活
-> M05 评论基础证据层
-> M06 评论下游信号抽取层
-> M04b 评论验证增强
-> M07 市场画像与可比池基线
-> M08 SKU 综合信号画像
-> M09 用户任务
-> M10 目标客群
-> M11 价值战场
-> M11.5 战场内卖点价值分层
-> M12 候选池召回
-> M13 竞品组件评分
-> M14 三槽位核心竞品选择
-> M15 证据卡与高层报告
-> M16 增量任务编排、复核和验收
-> API 聚合
-> 前端页面
-> 全链路验收
-> 205 部署
```

说明：

- `M16` 的表和基础状态可以在 INFRA 阶段先落一部分。
- `M16` 的完整编排必须等 M00-M15 runner 至少有可调用实现后再做。
- 前端页面不能在后端 payload 未稳定前大量开发，避免反复返工。

## 8. 首版待评审问题处理口径

以下待评审问题不阻断开发，首版按建议执行，并在对应开发任务中写入测试或注释。

| 模块 | 问题 | 首版口径 |
| --- | --- | --- |
| M00 | `write_time` 是否参与 hash | 首版参与，后续如导入噪声大再升 `hash_version` |
| M00 | 增量 overlap 窗口 | 首版 1 天 |
| M00 | schema snapshot 是否单独表 | 首版放 `core3_source_batch.schema_snapshot_json` |
| M00 | 是否保存完整原始行 JSON | 首版不复制完整原始行 |
| M01 | `core3_clean_sku` 是否保存所有来源行 | 首版保存代表来源和覆盖统计 |
| M01 | 评论 source segment 是否入句表 | 首版入表，用 `sentence_source` 区分 |
| M01 | 卖点缺失严重度 | 首版 warning，不阻断 |
| M02 | `core3_evidence_link` 是否首版落地 | 首版落表 |
| M02 | 长文本 evidence 是否完整保存 | 完整保存到 payload，列表摘要截断 |
| M03 | `亮度=5200` 无单位 | 可推断单位，但标记 `unit_inferred` |
| M03 | 刷新率 300Hz 口径 | 归系统/倍频高刷并复核 |
| M04a | 参数-only 技术卖点等级 | 不超过 medium |
| M04a | 性价比卖点 | M04a 只接宣传命中，强结论等 M07/M11.5 |
| M05 | 评论 evidence link | 首版落 `core3_comment_unit_evidence_link` |
| M05 | `TOPIC_UNKNOWN` | 不作为下游主题，只做 profile 统计 |
| M06 | 服务型卖点 | 可作为服务验证，必须有 `service_guardrail_flag` |
| M06 | 风险/价格/服务字典 | MVP 内置，后续资产化 |
| M07 | 可比池是否包含目标自身 | M07 包含，M12 召回时排除目标 |
| M07 | 平台重合阈值 | MVP 用 0.70 |

这些口径如果后续被业务评审推翻，必须走规则版本或 `hash_version` 升级，不直接改历史结果。

## 9. 数据库开发策略

### 9.1 迁移拆分原则

建议按层分批迁移：

| 迁移批次 | 内容 |
| --- | --- |
| `0005_core3_real_data_foundation` | 通用枚举、M16 基础 run 表可选 |
| `0006_core3_real_data_source_clean` | M00-M01 表 |
| `0007_core3_real_data_evidence` | M02 表 |
| `0008_core3_real_data_extract_profile` | M03-M11.5 表 |
| `0009_core3_real_data_competitor_report` | M12-M15 表 |
| `0010_core3_real_data_pipeline_governance` | M16 表和索引 |

如果单个 migration 太大，应继续拆小，但不能把多个不相关模块混在同一个任务里实现。

### 9.2 表实现门禁

每张表必须具备：

- 主键。
- 业务唯一键。
- 常用查询索引。
- `project_id`。
- `category_code`。
- `batch_id` 或 `run_id`。
- 版本字段。
- hash 字段。
- evidence 或 source 追溯字段。
- 审计字段。

### 9.3 原始表保护

开发期间禁止：

- 修改 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data` 的表结构。
- 覆盖、删除、清洗原始表记录。
- 在下游模块绕过 M00/M01/M02 直接从原始表生成业务结论。

## 10. 后端开发策略

### 10.1 服务拆分

后端服务按详细设计拆分：

| 模块 | 服务建议 |
| --- | --- |
| M00 | `source_registry_service.py` |
| M01 | `cleaning_service.py` |
| M02 | `evidence_service.py` |
| M03 | `param_extraction_service.py` |
| M04a/M04b | `claim_activation_service.py` |
| M05 | `comment_evidence_service.py` |
| M06 | `comment_signal_service.py` |
| M07 | `market_profile_service.py` |
| M08 | `sku_signal_profile_service.py` |
| M09-M11 | `task_group_battlefield_service.py` |
| M11.5 | `claim_value_layer_service.py` |
| M12 | `candidate_recall_service.py` |
| M13 | `component_scoring_service.py` |
| M14 | `core3_selection_service.py` |
| M15 | `evidence_report_service.py` |
| M16 | `pipeline_orchestration_service.py` |

### 10.2 Repository 分层

建议仓库层：

| Repository | 范围 |
| --- | --- |
| `RawSourceRepository` | 只读原始表 |
| `SourceRegistryRepository` | M00 |
| `CleanRepository` | M01 |
| `EvidenceRepository` | M02 |
| `FeatureRepository` | M03-M08 |
| `SemanticProfileRepository` | M09-M11.5 |
| `CompetitorRepository` | M12-M14 |
| `ReportRepository` | M15 |
| `JobRepository` | M16 |

除 `RawSourceRepository` 外，其他 repository 不允许直接读原始表。

### 10.3 Runner 协议

每个模块都要实现统一 runner，哪怕首版内部是同步执行：

```text
Core3ModuleRunner.run(module_code, run_context, target_scope)
```

runner 必须返回：

- `status`
- `input_count`
- `changed_input_count`
- `output_count`
- `output_hash`
- `warnings`
- `review_issues`
- `downstream_impacts`

## 11. API 开发策略

### 11.1 API 分层

API 必须分三类：

| 类型 | 面向对象 | 示例 |
| --- | --- | --- |
| 内部调度 API | 运营/任务系统 | 启动 pipeline、查看 run、重试 |
| 业务展示 API | 高层页面 | 单品报告、证据卡、批量总览 |
| 技术追溯 API | 内部分析人员 | 证据回溯、候选审计、SOP 轨迹 |

### 11.2 路径建议

真实数据 v2 使用：

```text
/api/mvp/core3/v2/projects/{project_id}/...
```

不要复用旧 `core3_mvp` 的粗粒度接口输出结构。

### 11.3 响应边界

业务展示 API 不返回：

- 原始 UUID。
- SQL。
- 内部英文枚举。
- 表名和字段名。
- 模型过程。
- 大段 JSON 调试结构。

技术追溯 API 可以返回内部信息，但必须与高层页面分开。

## 12. 前端开发策略

### 12.1 页面顺序

前端应在后端 payload 稳定后开发，顺序如下：

1. 批量总览。
2. 单品报告。
3. 证据卡。
4. 候选池审计展开。
5. 生产线状态。
6. 导出入口。

### 12.2 业务语言要求

页面必须使用业务语言：

| 技术词 | 页面表达 |
| --- | --- |
| `direct` | 正面对打竞品 |
| `pressure` | 价格/销量挤压竞品 |
| `benchmark_potential` | 高端标杆/潜在下探竞品 |
| `review_required` | 需业务复核 |
| `insufficient` | 样本不足 |
| `missing_structured_claim` | 宣传卖点数据缺口 |
| `evidence_id` | 短证据编号 |

### 12.3 高层页面验收

高层页面 30 秒内必须回答：

1. 目标 SKU 的核心竞品是谁。
2. 每个竞品代表什么压力。
3. 为什么选择它。
4. 证据强度和限制是什么。
5. 对业务策略有什么含义。

## 13. 测试策略

### 13.1 后端测试

每个模块至少包含：

| 测试类型 | 要求 |
| --- | --- |
| schema 测试 | Pydantic 输入输出字段、枚举、错误 |
| repository 测试 | 主键、唯一键、索引查询、历史版本 |
| service 测试 | 核心处理逻辑、质量状态、复核问题 |
| runner 测试 | 输入统计、输出 hash、失败状态 |
| API 测试 | 成功、错误、权限或边界 |
| fixture 测试 | 85E7Q、unknown、缺卖点、同品牌竞品 |

### 13.2 前端测试

前端至少包含：

- API payload 渲染。
- 中文业务文案映射。
- 无英文内部字段。
- 低置信/需复核/样本不足状态。
- 85E7Q 卖点缺失展示。
- 移动端和桌面布局基础检查。

### 13.3 固定 fixture

必须建立 85E7Q fixture，覆盖：

- 有市场、参数、评论。
- 无结构化卖点。
- 评论有重复和服务类内容。
- 同品牌候选可进入候选池。
- 当前只有线上渠道。

测试不得依赖外部 LLM 调用。语义结果用规则、mock 或离线 fixture。

## 14. 验证命令

后端常用命令：

```bash
cd apps/api-server
uv run pytest
```

如当前环境未使用 `uv`，可用现有虚拟环境：

```bash
cd apps/api-server
.venv/bin/pytest
```

前端常用命令：

```bash
cd apps/factory-web
npm run test
npm run build
```

全链路开发阶段不要求每个小任务都跑完整前后端，但每个任务必须运行与本次改动最相关的最小测试，并在最终说明中写明未运行的测试。

## 15. 205 数据和部署策略

### 15.1 开发期数据策略

开发时分三层验证：

| 层 | 数据来源 |
| --- | --- |
| 单元测试 | 小型 fixture，不连 205 |
| 集成测试 | 本地测试库或 mock repository |
| 验收测试 | 205 PostgreSQL 样例数据 |

不得让单元测试依赖 205 网络或真实数据库状态。

### 15.2 部署时机

只有满足以下条件后才部署 205：

1. M00-M16 至少有一条 85E7Q 全链路可运行路径。
2. 后端测试通过。
3. 前端 build 通过。
4. 高层页面无内部字段、UUID、英文枚举和 AI 过程文案。
5. 发布门禁能识别 85E7Q 卖点缺失和线上样例限制。

部署不是每个模块任务的默认动作。只有用户明确要求看效果或阶段验收时才部署。

## 16. 开发任务文档清单

后续建议逐一生成以下开发任务文档：

| 顺序 | 文件 | 内容 |
| ---: | --- | --- |
| 00 | `00_development_task_breakdown.md` | 全局开发任务拆分、依赖、里程碑、验收门禁 |
| 01 | `INFRA_development_tasks.md` | 通用迁移、model/schema 基础、runner 协议、fixture |
| 02 | `M00_development_tasks.md` | 原始数据批次与行登记 |
| 03 | `M01_development_tasks.md` | 清洗规范化与质量诊断 |
| 04 | `M02_development_tasks.md` | Evidence 原子层 |
| 05 | `M03_development_tasks.md` | 参数抽取 |
| 06 | `M04a_development_tasks.md` | 基础卖点激活 |
| 07 | `M05_development_tasks.md` | 评论基础证据 |
| 08 | `M06_development_tasks.md` | 评论下游信号 |
| 09 | `M04b_development_tasks.md` | 评论验证增强 |
| 10 | `M07_development_tasks.md` | 市场画像 |
| 11 | `M08_development_tasks.md` | SKU 综合画像 |
| 11.6 | `M08_6_product_anchor_evidence_layer_development_tasks.md` | 参数、卖点、评论分层产品锚点校准 |
| 12 | `M09_development_tasks.md` | 用户任务 |
| 13 | `M10_development_tasks.md` | 目标客群 |
| 14 | `M11_development_tasks.md` | 价值战场 |
| 15 | `M11_5_development_tasks.md` | 战场内卖点价值分层 |
| 16 | `M12_development_tasks.md` | 候选池召回 |
| 17 | `M13_development_tasks.md` | 组件评分 |
| 18 | `M14_development_tasks.md` | 三槽位选择 |
| 19 | `M15_development_tasks.md` | 证据卡与高层报告 |
| 20 | `M16_development_tasks.md` | 增量编排、复核和验收 |
| 21 | `API_development_tasks.md` | API 聚合和接口验收 |
| 22 | `FRONTEND_development_tasks.md` | 独立页面和业务展示 |
| 23 | `ACCEPTANCE_development_tasks.md` | 全链路验收、205 部署前检查 |

每次定时任务只生成或执行其中一个文件对应的工作。

## 17. 每个模块开发任务文档模板

后续每个 `*_development_tasks.md` 必须包含：

1. 模块目标。
2. 输入设计引用。
3. 本模块要改的文件。
4. 不允许改的文件。
5. 数据库迁移任务。
6. model/schema 任务。
7. repository 任务。
8. service 任务。
9. runner/API 任务。
10. 测试任务。
11. 85E7Q 或相关 fixture 验收。
12. 完成标准。
13. 回滚和风险。
14. 下一模块依赖。

## 18. 首轮开发建议

首轮不要直接做 M00 编码，建议顺序：

1. 生成 `00_development_task_breakdown.md`。
2. 生成 `INFRA_development_tasks.md`。
3. 生成 `M00_development_tasks.md`。
4. 评审前三个任务文档。
5. 开始 `INFRA` 编码。
6. 开始 `M00` 编码。

理由：

- INFRA 会影响所有模块，不先设计会导致每个模块重复造 runner、hash、repository、fixture。
- M00 是原始数据水位和增量边界，不先稳定，后续 M01-M16 会反复返工。
- M01/M02 是证据底座，必须在参数、卖点、评论抽取之前完成。

## 19. 自动化定时器建议

如果继续用定时器，建议提示词为：

```text
按 CatForge 彩电核心三竞品真实数据 MVP 开发阶段顺序，每次只处理一个开发任务文档或一个模块实现任务，不要批量生成多个文档，不要跨模块开发。工作目录是 /Users/sjs/catforge，开发文档目录是 /Users/sjs/catforge/docs/core3_mvp/real_data_v2/development/。每次醒来先查看开发总纲、已有开发任务文档、对应 SOP 需求和详细设计、git 状态，按 00_development_task_breakdown -> INFRA -> M00 -> M01 -> M02 -> M03 -> M04a -> M05 -> M06 -> M04b -> M07 -> M08 -> M09 -> M10 -> M11 -> M11.5 -> M12 -> M13 -> M14 -> M15 -> M16 -> API -> FRONTEND -> ACCEPTANCE 的顺序选择下一个任务。开发任务拆分阶段只改一个 development md 文件；编码阶段只改当前模块需要的代码和测试；不部署，除非用户明确要求。每次完成后说明本次处理的任务、改了什么、验证了什么、下次应处理什么。
```

建议间隔：

```text
10 分钟
```

## 20. 进入编码的门禁

满足以下条件后，才进入自动编码：

| 门禁 | 要求 |
| --- | --- |
| 开发总纲 | 已完成 |
| 全局任务拆分 | `00_development_task_breakdown.md` 已完成 |
| INFRA 任务 | `INFRA_development_tasks.md` 已完成 |
| M00 任务 | `M00_development_tasks.md` 已完成 |
| 首版待评审口径 | 已在开发总纲中固化 |
| 测试策略 | fixture、mock、无外部 LLM 已明确 |
| 用户确认 | 同意进入编码 |

当前本文完成后，下一步不是编码，而是生成：

```text
docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md
```

## 21. 最终交付标准

真实数据 MVP 开发完成的最低标准：

1. 205 样例数据可跑通 85E7Q。
2. 原始表只读。
3. 清洗、证据、抽取、画像、结果、治理分层落表。
4. 每个业务结论可追溯 evidence。
5. 85E7Q 无结构化卖点被正确表达为数据覆盖限制。
6. 同品牌海信 SKU 可作为竞品。
7. 竞品报告先展示竞品是谁，再解释为什么。
8. 高层页面全中文业务语言，无内部字段、UUID、SQL、AI 过程文案。
9. M16 能输出运行状态、复核队列、验收报告和发布门禁。
10. 后端 pytest 通过。
11. 前端 build/test 通过。
12. 205 部署后可通过指定域名访问。
