# CatForge 彩电核心三竞品真实数据 MVP 开发任务总拆分

## 1. 文档定位

本文是开发阶段的第一份任务拆分文档，用于把 `00_development_execution_plan.md`、SOP 需求和 M00-M16 详细设计转换成后续可逐一执行的开发任务队列。

本文不写代码、不写迁移、不部署。本文只确定：

1. 开发任务总顺序。
2. 每份开发任务文档要解决什么问题。
3. 每个阶段进入下一阶段的门禁。
4. 自动化定时执行时如何选择下一个任务。
5. 后续编码任务如何保持单模块边界和质量。

## 2. 输入依据

开发任务拆分依据：

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 需求总索引 | `docs/core3_mvp/real_data_v2/sop_requirements/README.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| 总体架构 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| 模块详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M00-M16*.md` |
| SOP 方法论 | `cankao/CatForge_竞品生成SOP_详细指导_v1.md` |
| UI 规范 | `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md` |

开发必须遵守现有仓库约束：

- 后端：FastAPI、Pydantic、SQLAlchemy、Alembic、pytest。
- 前端：React、TypeScript、Vite、Ant Design、vitest。
- 真实数据 v2 使用独立命名空间，不和旧 `core3_mvp` 粗粒度实现混写。
- 测试不得依赖外部 LLM 调用。
- 原始四表只读。

## 3. 总体开发阶段

| 阶段 | 任务文档 | 编码范围 | 阶段目标 |
| --- | --- | --- | --- |
| P0 任务拆分 | `00`、`INFRA`、`M00-M16`、`API`、`FRONTEND`、`ACCEPTANCE` | 不编码 | 全部模块变成可执行开发任务 |
| P1 基础设施 | `INFRA` | 通用迁移、模型基类、schema、runner、fixture | 建立真实数据 v2 工程骨架 |
| P2 数据底座 | `M00-M02` | 原始登记、清洗、evidence | 保证后续结论有稳定输入和证据 |
| P3 抽取画像 | `M03-M11.5` | 参数、卖点、评论、市场、SKU、任务、客群、战场 | 形成可解释 SKU 画像 |
| P4 竞品结果 | `M12-M15` | 候选、评分、选择、报告 | 生成核心三竞品和高层报告 payload |
| P5 编排展示 | `M16`、`API`、`FRONTEND`、`ACCEPTANCE` | 编排、复核、门禁、页面、部署前验收 | 可运行、可复核、可展示、可部署 |

## 4. 文档生成任务清单

后续需要生成 23 份开发任务文档，加上本文和开发总纲共 25 份开发阶段文档。

| 顺序 | 文档 | 状态 | 主要输出 |
| ---: | --- | --- | --- |
| 00 | `00_development_task_breakdown.md` | 本文 | 全局任务拆分 |
| 01 | `INFRA_development_tasks.md` | 待生成 | 通用工程骨架任务 |
| 02 | `M00_development_tasks.md` | 待生成 | 原始数据批次与行登记任务 |
| 03 | `M01_development_tasks.md` | 待生成 | 清洗规范化与质量诊断任务 |
| 04 | `M02_development_tasks.md` | 待生成 | Evidence 原子层任务 |
| 05 | `M03_development_tasks.md` | 待生成 | 参数抽取任务 |
| 06 | `M04a_development_tasks.md` | 待生成 | 基础卖点激活任务 |
| 07 | `M05_development_tasks.md` | 待生成 | 评论基础证据任务 |
| 08 | `M06_development_tasks.md` | 待生成 | 评论下游信号任务 |
| 09 | `M04b_development_tasks.md` | 待生成 | 评论验证增强任务 |
| 10 | `M07_development_tasks.md` | 待生成 | 市场画像任务 |
| 11 | `M08_development_tasks.md` | 待生成 | SKU 综合画像任务 |
| 12 | `M09_development_tasks.md` | 待生成 | 用户任务任务 |
| 13 | `M10_development_tasks.md` | 待生成 | 目标客群任务 |
| 14 | `M11_development_tasks.md` | 待生成 | 价值战场任务 |
| 15 | `M11_5_development_tasks.md` | 待生成 | 战场内卖点价值分层任务 |
| 16 | `M12_development_tasks.md` | 待生成 | 候选池召回任务 |
| 17 | `M13_development_tasks.md` | 待生成 | 组件评分任务 |
| 18 | `M14_development_tasks.md` | 待生成 | 三槽位选择任务 |
| 19 | `M15_development_tasks.md` | 待生成 | 证据卡与高层报告任务 |
| 20 | `M16_development_tasks.md` | 待生成 | 增量编排、复核和验收任务 |
| 21 | `API_development_tasks.md` | 待生成 | API 聚合和接口验收任务 |
| 22 | `FRONTEND_development_tasks.md` | 待生成 | 独立页面和业务展示任务 |
| 23 | `ACCEPTANCE_development_tasks.md` | 待生成 | 全链路验收和部署前检查任务 |

## 5. 后续任务选择规则

每次定时或人工触发时，按以下规则选择下一个任务：

1. 先查看 `development/` 目录已有文件。
2. 按固定顺序选择第一个不存在的任务文档。
3. 只生成或强化这一个文档。
4. 不写代码、不写迁移、不部署。
5. 完成后说明本次文档、补充内容、下次文档。

固定顺序：

```text
00_development_task_breakdown
-> INFRA
-> M00
-> M01
-> M02
-> M03
-> M04a
-> M05
-> M06
-> M04b
-> M07
-> M08
-> M09
-> M10
-> M11
-> M11.5
-> M12
-> M13
-> M14
-> M15
-> M16
-> API
-> FRONTEND
-> ACCEPTANCE
```

本文完成后，下一个任务是：

```text
docs/core3_mvp/real_data_v2/development/INFRA_development_tasks.md
```

## 6. 每份任务文档统一结构

后续每份 `*_development_tasks.md` 必须包含：

| 章节 | 内容要求 |
| --- | --- |
| 1. 模块目标 | 本任务解决什么工程问题 |
| 2. 设计引用 | 对应需求、详细设计、参考文档 |
| 3. 本次范围 | 必须做什么、明确不做什么 |
| 4. 要改文件 | 预计新增或修改的文件清单 |
| 5. 不允许改文件 | 避免越界影响其他模块 |
| 6. 数据库任务 | migration、表、索引、约束、回滚策略 |
| 7. model/schema 任务 | SQLAlchemy、Pydantic、枚举、类型契约 |
| 8. repository 任务 | 数据访问边界、只读/写入范围 |
| 9. service 任务 | 核心业务逻辑、幂等、hash、状态 |
| 10. runner/API 任务 | runner 协议、内部 API 或展示 API |
| 11. 测试任务 | 单元、repository、service、API、fixture |
| 12. 205/85E7Q 验收 | 与真实样例数据相关的验收点 |
| 13. 完成标准 | 可判定的 done 条件 |
| 14. 风险和回滚 | 主要风险、回滚或降级方式 |
| 15. 下游依赖 | 后续模块依赖本任务的什么产物 |

## 7. 任务粒度规则

### 7.1 文档阶段粒度

文档阶段每次只生成一个任务文档。不得一次生成多份，也不得在生成任务文档时顺手修改代码。

### 7.2 编码阶段粒度

编码阶段每次只做一个小闭环：

| 任务类型 | 允许范围 |
| --- | --- |
| migration | 只建当前模块表和索引 |
| model/schema | 只建当前模块模型和 Pydantic schema |
| repository | 只实现当前模块数据访问 |
| service | 只实现当前模块核心逻辑 |
| runner | 只接入当前模块 runner |
| API | 只实现当前模块或聚合 API |
| test | 只补当前模块测试 |
| frontend | 只做一个页面或组件 |

如果一个模块任务过大，应在该模块任务文档中继续拆成 `A/B/C` 子任务，编码时一次只执行一个子任务。

## 8. 编码前强制门禁

完成以下文档前，不进入编码：

| 门禁 | 文件 | 标准 |
| --- | --- | --- |
| 开发总纲 | `00_development_execution_plan.md` | 已完成 |
| 全局任务拆分 | `00_development_task_breakdown.md` | 已完成 |
| 基础设施任务 | `INFRA_development_tasks.md` | 已完成 |
| M00 任务 | `M00_development_tasks.md` | 已完成 |

推荐在编码前再完成：

| 推荐门禁 | 文件 | 原因 |
| --- | --- | --- |
| M01 任务 | `M01_development_tasks.md` | 清洗会影响所有 evidence |
| M02 任务 | `M02_development_tasks.md` | evidence 是所有结论的底座 |

编码前必须得到用户明确确认。

## 9. 里程碑和阶段验收

### 9.1 P0 文档拆分完成

完成条件：

- 24 个开发任务文档全部存在。
- 每份文档都说明要改文件、不允许改文件、测试和验收。
- 首版待评审问题已映射到对应任务。
- 明确哪些任务可以并行，哪些必须串行。

### 9.2 P1 基础设施完成

完成条件：

- 真实数据 v2 后端包存在。
- 通用枚举、hash、run context、runner 协议、fixture 目录可用。
- Alembic 迁移策略已落地首批基础表或表基线。
- 不影响旧 `core3_mvp` 页面。

### 9.3 P2 数据底座完成

完成条件：

- M00-M02 可独立运行。
- 原始四表只读。
- 205 样例数据可生成批次、清洗事实和 evidence。
- 85E7Q 可识别为有量价、参数、评论但无结构化卖点。

### 9.4 P3 抽取画像完成

完成条件：

- M03-M11.5 可基于 M02 evidence 和上游画像运行。
- 参数、卖点、评论、市场、SKU、任务、客群、战场和卖点价值层均有独立输出。
- 评论不会直接硬生成任务、客群、战场或竞品结论。

### 9.5 P4 竞品报告完成

完成条件：

- M12-M15 可为 85E7Q 生成 0-3 个核心竞品。
- 候选、评分、选择、报告逐层可追溯。
- 报告先展示竞品是谁，再解释为什么。
- 卖点缺失、线上样例和同品牌样例范围表达准确。

### 9.6 P5 全链路可展示

完成条件：

- M16 可输出运行状态、复核队列、验收报告和发布门禁。
- API 可支持单品报告、证据卡、批量总览和生产线状态。
- 前端页面独立于旧页面。
- 高层页面无内部字段、UUID、SQL、英文枚举和 AI 过程文案。
- 可部署到 205 供查看。

## 10. 模块依赖关系

| 模块 | 必须依赖 | 下游使用 |
| --- | --- | --- |
| INFRA | 开发总纲、总体架构 | 全部模块 |
| M00 | INFRA、原始表 | M01、M16 |
| M01 | M00 | M02、M03-M07 |
| M02 | M01 | M03-M15 |
| M03 | M02、M01 参数清洗 | M04a、M08、M11.5、M13 |
| M04a | M02、M03、卖点 seed | M04b、M08、M11.5 |
| M05 | M01、M02 评论 evidence | M06 |
| M06 | M05 | M04b、M08、M09-M11.5 |
| M04b | M04a、M06 | M08、M11.5、M13 |
| M07 | M01、M02 市场 evidence | M08、M12、M13 |
| M08 | M03、M04b、M06、M07 | M09-M12 |
| M09 | M08 | M10、M11、M12、M15 |
| M10 | M08、M09 | M11、M12、M15 |
| M11 | M08、M09、M10 | M11.5、M12、M15 |
| M11.5 | M11、M04b、M07、M08 | M12、M13、M15 |
| M12 | M08-M11.5 | M13、M14 |
| M13 | M12 | M14、M15 |
| M14 | M13 | M15、M16 |
| M15 | M14、M13、M12、M08-M11.5、M02 | M16、API、FRONTEND |
| M16 | M00-M15 状态和结果 | API、FRONTEND、ACCEPTANCE |
| API | M15、M16 | FRONTEND |
| FRONTEND | API、UI 规范 | ACCEPTANCE |
| ACCEPTANCE | 全链路 | 205 部署 |

## 11. 推荐并行策略

默认按顺序串行。只有在以下边界明确时才允许并行：

| 可并行任务 | 条件 |
| --- | --- |
| API schema 草案和后端 service | 对应 payload 已在详细设计中稳定 |
| 前端静态页面壳和后端 M12-M15 | 使用 mock payload，且不提前固化最终字段 |
| 测试 fixture 和 INFRA | fixture 不依赖最终数据库模型 |

禁止并行：

- M01 未稳定时开发 M02 正式 evidence 写入。
- M02 未稳定时开发 M03-M15 正式结论。
- M15 payload 未稳定时开发高层页面正式数据绑定。
- M16 门禁未稳定时部署给业务领导看。

## 12. 代码改动边界

### 12.1 真实数据 v2 新增路径

后续编码优先新增：

```text
apps/api-server/app/services/core3_real_data/
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/tests/core3_real_data/
apps/factory-web/src/pages/core3RealData/
```

### 12.2 允许谨慎修改的共享文件

| 文件 | 允许原因 |
| --- | --- |
| `apps/api-server/app/main.py` | 注册新 API router |
| `apps/api-server/app/models/entities.py` | 若沿用现有 model 聚合方式 |
| `apps/api-server/alembic/env.py` | 仅当新 model 导入需要 |
| `apps/factory-web/src/routes/*` | 注册新页面路由 |
| `apps/factory-web/src/types/index.ts` | 增加 v2 展示类型 |

### 12.3 不允许改动

除非用户明确要求，不改：

- 旧 `core3_mvp` 页面业务逻辑。
- Goal1/Goal2/Goal3 workbench。
- 原始四表结构。
- 部署脚本。
- 205 配置。
- 与本模块无关的样式和导航。

## 13. 测试矩阵

| 阶段 | 必跑测试 | 可延后测试 |
| --- | --- | --- |
| INFRA | hash、枚举、runner 协议、fixture 加载 | 全链路 |
| M00 | source registry service/repository | 205 实库扫描 |
| M01 | clean normalize、unknown/null/`-` | 大数据量性能 |
| M02 | evidence atom/link、追溯 | 全证据矩阵 |
| M03-M07 | 各自规则和 fixture | 全 SKU 大批量 |
| M08-M11.5 | 画像合并、分数、复核 | 复杂业务复核界面 |
| M12-M15 | 85E7Q 核心竞品链路 | 多目标批量 |
| M16 | 门禁、复核队列、增量计划 | 完整定时队列 |
| API | schema、错误、边界 | 权限体系 |
| FRONTEND | 中文展示、无内部字段、构建 | Playwright 全流程 |
| ACCEPTANCE | 85E7Q、205 样例、部署前检查 | 压测 |

通用命令：

```bash
cd apps/api-server && .venv/bin/pytest
cd apps/factory-web && npm run test
cd apps/factory-web && npm run build
```

如果当前任务只改文档，不需要运行测试，但必须做文档校验。

## 14. 205 样例验收路径

205 样例验收不是每个任务都执行。阶段性验收使用：

| 阶段 | 205 验收点 |
| --- | --- |
| P2 完成 | 能读取四张原始表并生成 M00-M02 产物 |
| P3 完成 | 能为 85E7Q 生成参数、评论、市场、任务、客群、战场画像 |
| P4 完成 | 能为 85E7Q 生成核心三竞品、证据卡和报告 payload |
| P5 完成 | 能通过页面查看业务化报告 |

205 验收必须明确样例限制：

- 当前均为海信品牌。
- 当前只有线上渠道。
- 85E7Q 无结构化卖点。
- 评论有重复和服务类内容。

## 15. 风险清单

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 表一次性建太多 | 迁移难审、回滚困难 | 按模块分迁移 |
| 继续复用旧粗粒度 JSON | 后续无法追溯证据 | v2 独立表和服务 |
| 评论信号越权 | 业务结论不可信 | 评论只作信号，M09-M15 多源推导 |
| 85E7Q 卖点缺失被误判为产品弱 | 业务误导 | M04a/M15/M16 固化数据缺口说明 |
| 前端过早开发 | payload 变动导致返工 | M15/API 稳定后再正式绑定 |
| 定时器批量生成质量下降 | 文档不可执行 | 每次只一个文档，完成后校验 |
| 单元测试依赖 205 | 不稳定 | fixture/mock 优先 |
| 直接部署未验收页面 | 给业务高层错误观感 | P5 门禁后再部署 |

## 16. 完成标准

本文完成后应满足：

1. 能明确还需要生成哪些开发任务文档。
2. 能明确下一个任务是 `INFRA_development_tasks.md`。
3. 能明确编码前至少需要完成哪些文档。
4. 能明确每个阶段的验收门禁。
5. 能明确后续开发不能跨模块、不能混旧页面、不能绕过 evidence。
6. 能支撑 10 分钟定时器逐一推进。

## 17. 下次任务

下次应生成：

```text
docs/core3_mvp/real_data_v2/development/INFRA_development_tasks.md
```

INFRA 文档需要重点拆清：

- 新后端包和命名空间。
- 通用枚举和类型。
- hash 工具。
- runner 协议。
- run context。
- repository 基类或会话边界。
- fixture 目录和 85E7Q 测试数据。
- 第一批 Alembic migration 的边界。
- 不影响旧 `core3_mvp` 页面和 Goal workbench 的保护措施。
