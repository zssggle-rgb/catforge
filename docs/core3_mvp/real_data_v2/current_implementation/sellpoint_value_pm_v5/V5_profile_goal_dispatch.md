# 用户卖点价值画像串行 Goal 与 10 分钟调度

状态：G01 执行中

日期：2026-07-13

授权范围：需求、设计、开发、测试、精确提交、205 部署、65E7Q 单 SKU 草稿验收、验收通过后的 205 全 SKU 草稿生成

不含授权：正式发布画像版本、切换 published/current、修改或重跑 M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D/M12D/M12/M13/M14

## 1. 调度原则

1. 任意时刻只允许一个 active Goal；后续 Goal 只能在前置 Goal `complete` 后创建。
2. 每个 Goal 使用 Goal 模式，不设置 token budget。
3. 当前线程使用一个 10 分钟 heartbeat，始终只推进当前 active Goal。
4. heartbeat 不得并发启动另一个数据库写入、部署或批量生成任务。
5. 每个 Goal 只暂存自己产生的精确文件，禁止 `git add .`。
6. 用户未跟踪文件、其他任务产物和既有工作树修改全部保留。
7. 数据库迁移、部署和 205 写入只在对应 Goal 的前置门禁通过后执行。
8. 65E7Q 单 SKU 验收未通过时，禁止创建全 SKU 生成 Goal。
9. 全 SKU 生成只写 draft 画像；正式 publish/current 切换需要另行明确授权。
10. 同一阻塞连续三次且无法继续时才标记 blocked。

当前 heartbeat：

- automation id：`catforge-m12d-v5-10`
- 名称：`CatForge 用户卖点价值画像 10分钟续跑`
- 周期：10 分钟
- target thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`

## 2. 任务链总览

| Goal | 唯一目标 | 主要产物 | 关闭门禁 |
| --- | --- | --- | --- |
| G01 | 冻结任务链、详细设计和追溯 | 本文、详细设计、追溯矩阵 | 文档一致；不改运行代码、DB、205 |
| G02 | 实现完整竞品宇宙与分析参考池 | M12/M13/M14 loader、typed manifest、问题资格 | 无固定数量；M14 不截断；确定性和查询测试通过 |
| G03 | 实现门槛功能与投入分类 | prevalence、known/missing、六类投入判断 | missing 不作 false；TV/AC 配置化；65E7Q 规则样例通过 |
| G04 | 实现画像 schema、实体、迁移和 repository | 4 张表、Pydantic schema、migration、CRUD | upgrade/downgrade、唯一键、current/draft 隔离和 repository 测试通过 |
| G05 | 实现画像生成、版本和批处理服务 | materializer、fingerprint/hash、draft 生命周期、单/批生成 | 幂等、历史不覆盖、失败隔离、无 N+1 |
| G06 | 改造报告只消费画像 | profile -> PM DTO -> 所有渲染器 | 渲染阶段零业务重算；跨载体一致；V5 默认关闭不回归 |
| G07 | 实现基于画像的深入问答 | topic index、profile ask、事实路径与边界 | 同版本锁定；未知诚实返回；无外部 LLM 测试 |
| G08 | 综合本地质量门禁与不可变 RC | 全回归、性能、query count、方法/工程/PM 审查 | 无 P0/P1；迁移与回滚包；精确提交和推送 |
| G09 | 205 部署并只验收 65E7Q | migration、单 SKU draft、回读、报告、问答、回执 | 画像/报告 hash 一致；业务结论可读；健康和回滚通过 |
| G10 | 205 全 SKU draft 生成 | TV/AC 全量 draft version、逐 SKU 状态、质量统计 | 仅在 G09 通过后；无漏 SKU/重复/跨类目；不 publish |
| G11 | 发布准备审计（不执行发布） | version quality report、diff、发布/回滚建议 | 只读审计；等待用户另行授权 publish/current |

## 3. G01：设计冻结

允许：仅修改 `sellpoint_value_pm_v5/` 内需求、设计、追溯和调度文档。

必须完成：

- 竞品宇宙与分析参考池的数据流和资格状态；
- 门槛功能和投入分类算法合同；
- 画像版本、SKU、候选、价值项 4 张表；
- draft/review/published/current 生命周期；
- 单 SKU、批量、get、report、ask 命令边界；
- 报告只消费画像的接口；
- 65E7Q 先验收、全 SKU 后生成的硬门禁；
- PF01—PF20 需求追溯。

禁止：代码、迁移、数据库、205、提交发布。

关闭：文档 diff check 通过；三份合同一致；标记 Goal complete 后创建 G02。

## 4. G02：竞品宇宙与分析参考池

目标：以全部当前 M12/M13 有效候选作为竞品宇宙，M14 仅增加重点标签。

必须实现：

- 全量读取 M12 `Core3CandidatePool`；
- 关联 M13 component/role score；
- 关联 M14 selection 标签但不截断；
- `eligible/limited/review_required/blocked/recalled_only` 状态；
- 每个问题的 `eligible_questions`；
- 与 M07/M11C 等分析参考池分离；
- 全量轻 manifest、结构化批量加载、证据延迟加载；
- 移除 V5/V4 候选 12 上限的业务影响。

测试：

- 0、1、12、超过 30 个候选；
- M14 为 0、1、3；
- 候选输入顺序反转 hash 不变；
- review/blocked 不参与正式结论；
- 无 M12/M13 时同尺寸池只进入 reference。

关闭：候选数量等于权威源有效记录数；无 N+1；不生成画像或报告。

## 5. G03：门槛功能与投入分类

目标：将产品事实、用户体验和竞争表现分开，生成六类产品投入判断。

必须实现：

- known/present/missing/contradicted 计数；
- category/price band/product form 分层 prevalence；
- TV、AC 可配置最小 known 样本和普及率阈值；
- table_stake 只过滤能力，不过滤可差异化体验结果；
- retain、unconverted、do_not_follow、table_stake、missing_competitive_gap、unknown；
- 分类理由、候选 scope、事实和反馈证据；
- 分类冲突转 review_required。

65E7Q 样例：HDMI 2.1 门槛判定、1920 分区 unconverted 候选、量子点 do_not_follow 候选；结果必须由数据和门禁决定，不写 SKU 白名单。

关闭：纯函数确定性、边界和 TV/AC 双类目测试通过；不写数据库。

## 6. G04：画像持久化合同

目标：新增 4 张表并完成 typed repository。

表：

- `core3_sellpoint_value_profile_version`；
- `core3_sku_sellpoint_value_profile`；
- `core3_sku_sellpoint_value_candidate`；
- `core3_sku_sellpoint_value_item`。

门禁：

- migration upgrade/downgrade；
- category/project/batch/version/SKU 唯一性；
- draft 和 published current 不互相覆盖；
- JSON 字段有 Pydantic 回读校验；
- candidate/value item 可分页、可按问题和分类查询；
- SQLite 测试兼容、PostgreSQL GIN/索引正确；
- export boundary 不暴露 prompt/Gold Set。

关闭：schema、entity、migration、repository tests 全通过；不接入 orchestrator。

## 7. G05：画像生成与版本生命周期

目标：把 G02/G03 与现有 V5 分析组装成可保存画像。

必须实现：

- 单 SKU generate draft；
- version 级 batch generate，支持 resume 和失败隔离；
- input fingerprint 包含全部上游 hash、候选 manifest 和方法配置；
- 相同输入幂等；新 draft 不覆盖 published；
- 自动质量状态和 review reason；
- stale 判断；
- profile/version summary counts；
- 回读 result hash 校验；
- `generate/get/list/diff` 服务接口。

关闭：本地 fixture 的单/批生成、resume、并发幂等和历史回读通过。

## 8. G06：报告消费画像

目标：现有 `sellpoint-value-pm-v5` 不再临时构造候选或业务结论。

必须实现：

- 默认读取 current published；
- `preview_profile_version` 显式读取 draft；
- profile -> report adapter；
- 短答、JSON、Markdown、飞书、卡片只使用同一 profile DTO；
- 报告展示 profile version/release/hash；
- 第一屏固定五个产品经理答案；
- 下钻全量候选、投入分类和问题 scope；
- 无画像、stale、blocked 诚实降级。

关闭：报告生成路径不查询 M03B—M14、不重新选择候选、不重新计算量价；跨载体一致。

## 9. G07：画像深入问答

目标：围绕报告使用的同一 profile version 回答追问。

必须实现：

- topic index 和事实路径；
- 按投入、价格、销量、竞品、候选选择、版本变化检索；
- 指定竞品问答；
- 直接答案、事实、工作含义、边界四段合同；
- answer payload 包含 profile/version、fact paths、candidate/value item ids；
- 画像不支持时返回 unknown，不静默重跑；
- 确定性规则/mock 测试，不调用外部 LLM。

关闭：需求列出的 10 类问题测试通过；报告和问答引用同一 hash。

## 10. G08：本地综合质量与 RC

必须完成：

- 所有新增 public function 的正常、异常和边界测试；
- V4/V5/AC 全回归；
- migration upgrade/downgrade；
- query count 和最大候选性能；
- full manifest 不被展示上限截断；
- category isolation；
- published/current 并发安全；
- PM 语言检查；
- pre-landing diff review；
- 精确 commit、push 和不可变 commit SHA；
- 205 migration/rollback 命令和校验 SQL。

关闭：无 P0/P1，形成 RC 后才能创建 G09。

## 11. G09：205 仅 65E7Q 验收

唯一允许目标 SKU：`TV00029112 / 65E7Q`。

步骤：

1. 记录 205 revision、migration head、DB 基线和 rollback；
2. 部署不可变 RC、执行 migration；
3. 创建单 SKU draft profile version；
4. 生成 65E7Q 画像并回读；
5. 从回读画像生成短答、JSON、Markdown/飞书预览；
6. 验证门槛、投入分类、当前价格、走量角色；
7. 运行至少 5 个画像问答；
8. 双跑验证幂等/hash；
9. 验证 API health、V2/V4 和 AC 不回归；
10. 输出验收和回滚回执。

硬门禁：任何结果不可读、候选宇宙不正确、hash 不一致、画像与报告不一致或迁移异常，均不得创建 G10。

## 12. G10：205 全 SKU 草稿生成

前置：G09 complete。

范围：205 当前有效 TV、AC SKU；按类目、批次和画像版本隔离。

必须实现和执行：

- batch version draft；
- 分批、resume、逐 SKU commit；
- 已成功 SKU 不重算；
- 单 SKU 失败不回滚整批；
- 生成数 = 权威目标 SKU 数；
- ready/review_required/blocked/missing_input 统计；
- 候选数量分布和最大候选性能；
- 每类抽样回读、报告和问答；
- 生成前后 DB、CPU、内存、API 健康；
- 不 publish、不切 current published。

关闭：无漏 SKU、重复 current draft、跨类目污染；输出全量生成收据。

## 13. G11：发布准备审计

只读审计 G10 draft version：

- 版本质量门禁；
- 与旧即时 V5 和代表 SKU 的差异；
- review_required 清单；
- published/current 切换计划和 rollback；
- 产品经理抽样报告。

本 Goal 不执行正式发布。完成后停止 heartbeat，等待用户明确发布授权。
