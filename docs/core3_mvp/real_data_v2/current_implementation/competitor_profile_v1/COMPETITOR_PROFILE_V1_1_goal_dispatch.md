# CatForge 竞品画像 V1.1 串行 Goal 调度

状态：G27—G39 completed；G40—G41 pending；G42 approval-only

日期：2026-07-16

授权范围：V1.1 需求、设计、开发、测试、精确提交、205 代码与 migration 部署、65E7Q 单 SKU draft 验收、AC 单 SKU draft 验收、双品类通过后的 TV/AC 全量 draft 生成。

不含授权：review、publish、current、deprecated 状态切换；修改或覆盖 V1 草稿；修改旧 M12/M13/M14；重跑 M03B—M12D；重新设计卡片、报告或问答。

## 1. 调度原则

1. 任意时刻只允许一个 active Goal；
2. 当前 Goal complete 后才能创建第一个满足前置条件的 pending Goal；
3. 每个 Goal 使用 Goal 模式，不设置 token budget；
4. 使用一个 10 分钟 heartbeat 续跑当前线程；heartbeat 只推进当前 active Goal；
5. 禁止并发数据库写入、部署或批量生成；
6. 只暂存当前 Goal 精确产生的文件，禁止 `git add .`；
7. 保护当前工作树中的用户文件、卖点价值修改和未跟踪产物；
8. 任何 schema、migration、算法、reader 或 adapter Goal 必须同时完成对应测试；
9. 65E7Q 未通过前禁止 AC 和全量；AC 未通过前禁止全量；
10. 全量只生成 draft；publish/current 必须进入 G42 并再次获得用户明确批准；
11. 旧智能体兼容基线必须在改算法前冻结；
12. 不允许以性能为由截断候选、删除维度过程或恢复统一全局门槛；
13. 同一阻塞连续三次且无法继续时才标记 blocked。
14. 10 分钟 heartbeat 只用于 active Goal 的断点续跑，不是十分钟工作切片；一次唤醒后必须持续推进当前 Goal，直到完成或遇到真实阻塞，禁止人为拆成“读文档、改一点、跑一点、下次再继续”的重复检查点。
15. G32—G38 每个 Goal 在实现期间只运行本模块专项测试和受影响的必要回归；不得在每个 Goal 重复执行完整 competitor-profile 回归、覆盖率和总评审。完整回归、性能、覆盖率及方法/工程/业务总评审统一在 G39 执行。
16. 当前 Goal 的实现、专项测试、一次性独立复核、问题修复和关闭回执应在同一连续执行链内完成；复核意见先合并处理，再做一次终审，避免“修一点—复核一次”的往返。
17. Goal 完成后立即标记 complete，并按前置条件创建下一个 pending Goal；不得等待下一次 heartbeat 才完成可立即执行的状态切换。

## 2. Goal 总表

| Goal | 唯一目标 | 核心门禁 | 205 写入 |
| --- | --- | --- | --- |
| G27 | 冻结 V1.1 不降级需求、详细设计和任务链 | 画像/智能体边界、门槛重构和完整数据合同一致 | 否 |
| G28 | 冻结旧竞品分析兼容基线 | 完整字段映射、八类 fixture、性能/存储基线可重复 | 否，只读 |
| G29 | 实现 V1.1 Typed Schema | SKU snapshot、dimension、pair analysis、summary 和 adapter contract 测试通过 | 否 |
| G30 | 实现 migration 与 entities | 新表/列、约束、索引、upgrade/downgrade guard 通过 | 否 |
| G31 | 实现 Repository 与 V1.1 Reader | snapshot/profile/pair/selection 原子写入和完整回读通过 | 否 |
| G32 | 实现 SKU 分析快照生成 | M03B—M12D 事实按版本只保存一次，missing unknown 正确 | 否 |
| G33 | 实现完整 PairAnalysisCalculator + Assembler | 成熟锚点/替代/购买压力计算完成后无损持久化 | 否 |
| G34 | 重构候选和关系门槛 | scope、dimension、strength、review 四轴分离 | 否 |
| G35 | 实现 V1.1 排序、角色和重点选择 | 旧 Top 3 全部参与；局部未知不全局淘汰 | 否 |
| G36 | 扩展 materializer 与生成服务 | 单 SKU/批量 draft、幂等、失败隔离和 hash 通过 | 否 |
| G37 | 实现竞品分析画像 Adapter + 纯展示入口 | 映射已算结果，全部分析/排序/选择调用为 0 | 否 |
| G38 | 改造竞品分析智能体读取路径 | preview/formal 读取画像，只做问题路由和业务表达 | 否 |
| G39 | 完成综合测试、性能、方法/工程评审和精确提交 | 无 P0/P1；兼容、门槛、迁移、性能和回退通过 | 否 |
| G40 | 部署 205 代码和 migration，不生成画像 | commit/container/migration/health/ready/rollback 通过 | migration only |
| G41A | 只生成并验收 65E7Q V1.1 draft | 多维数据完整、新旧差异可解释、智能体零重算 | 单 SKU draft |
| G41B | 只生成并验收 AC 单 SKU V1.1 draft | AC taxonomy/能力段/语义/量价无 TV 串线 | 单 SKU draft |
| G41C | 生成 TV/AC 全量 V1.1 draft 并只读复核 | 532 SKU 完整、无截断/串线/重复/失败 | 全量 draft |
| G42 | 单独评审是否 review/publish/current | 必须重新获得明确批准 | 未授权 |

## 3. G27：需求与设计冻结

### 输入

- V1 requirements、method、detailed design 和 G01—G26 回执；
- 当前 `competitor-set`、`competitor_answer` 数据流；
- 65E7Q V1 draft 实际候选、关系、选择和质量结果；
- 用户确认的边界：画像算数据，智能体读数据并负责展示。

### 产物

- `COMPETITOR_PROFILE_V1_1_requirements_addendum.md`；
- `COMPETITOR_PROFILE_V1_1_detailed_design.md`；
- `COMPETITOR_PROFILE_V1_1_goal_dispatch.md`；
- `G27_closure_receipt.md`。

### 关闭条件

1. CA01—CA30 完整且无冲突；
2. 明确画像不负责卡片、报告和问答样式；
3. 现有智能体能力被转换成画像最低数据合同；
4. 统一门槛被替换为四状态轴和问题级结论强度；
5. 明确复用 V1，不重跑 M03B—M12D；
6. schema、迁移、adapter、测试、205 和单 SKU/全量步骤有独立 Goal；
7. 设计评审无未关闭 P0/P1；
8. 未修改运行代码、数据库或 205。

## 4. G28：旧智能体兼容基线

### 目标

在任何算法和 schema 修改前，冻结当前竞品分析智能体在同一权威输入快照上的完整机器可读结果。

### 样本矩阵

- TV：海信 65E7Q；
- TV：一款 M12D 复核/局部缺失但旧智能体仍有结果的 SKU；
- AC：一款十模块完整 SKU；
- AC：一款局部缺失但仍可形成部分比较的 SKU。
- Pair 状态：complete、M12D missing、M05C review、battlefield conflict、market-only、config-only、AC complete、AC partial；
- 基础功能：HDMI 2.1 等高普及功能。

### 必须冻结

- 候选列表、Top 3 和角色；
- 购买池；
- 战场、任务、客群双方条目和加权得分；
- 参数/卖点双方值和差异；
- 价值锚点 15 分制完整 payload；
- 替代压力 10 分制完整 payload；
- 量价和市场验证；
- 六维得分和综合排序；
- recall rank、旧 `competitor_score`、semantic/param-claim/sales-closeness 分项；
- 完整 M12C claim values/contribution 和 supported/contradicted/unsupported；
- 完整 sales overlap method/window/overlap weeks/双方总体与共同窗口周均量/gap/ratio/boundary；
- 使用的上游版本和 result hash。

### 关闭门禁

- fixture 两次运行 hash 一致；
- 不写数据库、不发布飞书；
- fixture 包含完整数据，不只保存展示文案；
- 明确哪些字段来自旧 atom、哪些来自 M12D pair contract。
- 形成“旧 atom 字段 → V1.1 typed 字段”映射矩阵；
- 记录旧链单 SKU、单 pair、最大候选 SKU 的时延、内存、字段量和存储估算，作为 G29 数值预算输入；
- 65E7Q 全候选逐个对账；旧候选无五类 hard exclusion code 时不得从 V1.1 消失；
- 任一旧链已知字段在 V1.1 设计映射中变 unknown 为失败。

## 5. G29—G31：Schema、数据库和读取

### G29 Typed Schema

完成状态：completed；关闭回执：`G29_closure_receipt.md`。

允许修改：

- 新增 V1.1 schema 文件；
- 现有 persistence/reader schema 的兼容扩展；
- 对应 schema tests。

必须把 G28 字段映射矩阵 100% 落入 typed schema，并冻结维度量纲、归一规则、权重、weighted contribution、基础功能 prevalence 合同、machine-readable conclusion 合同和性能/存储预算。

禁止：migration、数据库写入、算法修改。

### G30 Migration/Entities

完成状态：completed；关闭回执：`G30_closure_receipt.md`。

允许修改：

- 新 Alembic revision；
- entities；
- migration tests。

必须验证：

- V1 历史行兼容，旧 `candidate_status` / relation status 约束不参与 V1.1 选择；
- version 复合唯一键、snapshot 四列复合 FK `ON DELETE CASCADE`、AuditMixin、scope/category 数据库一致性和读取索引；
- V1.1 scope/relation/available weight/必填分析字段 conditional checks；
- `selected=true` 对 V1.1 只受 analyzable scope 和问题级非 unknown 结论控制；
- downgrade 在存在 V1.1 version 行、snapshot 行或 V1.1 分析列值时拒绝；仅有旧 V1 草稿不阻止回退。

### G31 Repository/Reader

完成状态：completed；关闭回执：`G31_closure_receipt.md`。

实现：

- SKU snapshot 幂等写入和版本内唯一；
- V1.1 snapshot/profile/pair/relation/selection 原子写入；
- full/compact/question-specific 回读；
- V1/V1.1 reader 明确分流；
- formal current published 与 explicit draft preview 边界。
- `target_snapshot_ref` / `candidate_snapshot_ref` 必须在同一 version/scope 的共享 snapshot 中精确解析；G30 按冻结设计保存逻辑引用而未增加 pair→snapshot 数据库 FK，因此 Repository 写入和 Reader 回读必须 fail-closed，不能返回悬空引用。

## 6. G32—G36：分析与画像生成

### G32 SKU Snapshot

完成状态：completed；关闭回执：`G32_closure_receipt.md`。

从现有 category input bundle 生成共享 SKU 分析快照。不得访问外部 LLM，不得在 pair 内复制完整 SKU JSON。

### G33 Pair Analysis

完成状态：completed；关闭回执：`G33_closure_receipt.md`。

新增 `PairAnalysisCalculator`，显式调用并冻结 `ValueAnchorMatcher`、`ReplacementPressureClassifier`、`PurchasePressureComparator` 的 method/config version，产出完整 15 分制、10 分制和购买压力 payload；再由 `PairAnalysisAssembler` 只做 typed 组装、证据引用和 hash。禁止 assembler 从 V1 简化摘要反推这些结果。重点验证 materializer 不再丢失 aligned features、value assessments、量价共同窗口、旧链 score basis、角色和排序组成。

### G34 门槛

完成状态：completed；关闭回执：`G34_closure_receipt.md`。

只允许 `self_pair`、`project_mismatch`、`category_mismatch`、`candidate_outside_manifest`、`identity_decode_failed` 五类 hard scope error 全局排除。其他 authority/review/missing/taxonomy/lineage/conflict 均按维度保存。relation status 只允许 passed/limited/unassessable/failed，review 独立叠加。必须使用 65E7Q 全部旧候选和 G28 fixture matrix 做回归。

### G35 排序选择

完成状态：completed；关闭回执：`G35_closure_receipt.md`。

实现六维权重、可用权重归一、市场验证同分排序、角色多样性和未入选原因。G29 必须先冻结防止低覆盖 pair 被 normalized score 放大的确定性公式；coverage 只影响问题结论强度和同分排序，不得成为隐藏门槛。任何非 unknown 的问题结果均参与相应选择，不得使用旧 `candidate_status` 作为入口。

### G36 Materializer/Generation

完成状态：completed；关闭回执：`G36_closure_receipt.md`。

形成 V1.1 draft persistence bundle，支持单 SKU、batch、幂等、失败隔离、checkpoint、hash receipt 和 compact readback。

## 7. G37—G38：智能体消费切换

### G37 Adapter

完成状态：completed；关闭回执：`G37_closure_receipt.md`。

只实现已完成分析的领域 DTO 到纯展示输入结构的映射，并新增 `render_competitor_answer_from_profile()` 纯展示入口。Adapter 不接受 DB session、AtomicHandlers、原始上游 provider 或任何 calculator；不把画像重新映射成供旧 `build_competitor_answer()` 二次分析的 raw inputs。

### G38 智能体路径

完成状态：completed；关闭回执：`G38_closure_receipt.md`。

`competitor-set` 默认通过 V1.1 Reader、G37 Adapter 和纯展示入口读取 formal current published；普通业务调用不需要知道内部 source-fingerprint release scope，Reader 只在已发布且 current 的 V1.1 中按最近 `current_at` 定位正式 serving 版本。preview 必须同时显式提供 scope、version 和 opt-in。旧现场路径仅保留为显式运维参数；画像不可用时明确返回，不自动回退。问题级读取锁定一个画像版本，局部 unknown 保留为局部边界；全部现场分析、打分、角色、排序和选择函数为零调用。

## 8. G39：测试、评审和提交

完成状态：completed；关闭回执：`G39_closure_receipt.md`。

必须执行：

- V1.1 全部专项单测；
- 当前全部 V1 回归，基线不少于 299 项；
- competitor answer/PM report/Feishu publish mock/offline 回归，不发送消息或创建文档；
- migration upgrade/downgrade；
- 65E7Q golden diff；
- 旧 Top 3 门槛回归；
- AtomicHandlers、enrichment、分析、打分、角色、排序和选择函数零调用测试；
- 最大候选 SKU 本地等价性能、SQL 次数和存储预算；
- deterministic rerun/hash；
- 冻结 0046 已部署 DDL 的 SQLite/PostgreSQL golden hash，防止历史 revision 被后续 ORM 或 migration 修改漂移；
- ruff、compile、`git diff --check`；
- 方法、工程和业务边界评审。

提交时只暂存 G27—G39 产生的精确文件。

## 9. G40：205 代码部署

只允许：

- 部署 G39 已提交 commit；
- 执行新 migration；
- health/ready/import/CLI smoke；
- 空 V1.1 表阶段 rollback 演练。

禁止生成画像、修改 V1 草稿、publish/current。

## 10. G41：数据验收

### G41A 65E7Q

只写一个明确版本的 V1.1 draft。验收：

- 共享 SKU snapshot；
- 完整 pair 多维结果；
- 原 Top 3 全部参与；
- 新旧差异报告；
- 画像 Reader/Adapter/智能体读取一致；
- AtomicHandlers=0；
- 205 compact readback 不高于 2 秒且无 N+1；
- 旧 V1 和其他画像不变。

失败时停止，不创建 G41B。

### G41B AC

只选择一个 AC SKU，验证 AC product form、能力段、任务、客群、价值锚点、量价和参数不存在 TV 假设，并在 205 验证 compact readback 不高于 2 秒且无 N+1。失败时停止，不创建 G41C。

### G41C 全量

生成 377 TV + 155 AC V1.1 draft。只读复核：

- authoritative SKU 差集 0；
- generation failure 0；
- pair 截断 0；
- 跨品类/self/duplicate 0；
- SKU snapshot 重复 0；
- 各维度 availability/strength/review 分布；
- 旧 Top 3 可分析覆盖率；
- adapter 可读率；
- 全量 hash 和性能预算。

## 11. G42：发布审批边界

G42 不自动创建。只有用户在看过 G41C 结果后明确批准，才允许设计和执行：

1. release quality review；
2. draft→review；
3. review→published；
4. set current；
5. 正式智能体默认切换；
6. 回退演练。

上述步骤仍需拆分，不能一次性越过。

## 12. Heartbeat 提示词

Heartbeat 每次执行必须：

1. 读取本调度、requirements、detailed design 和当前 Goal；
2. 有 active Goal 时只推进该 Goal；
3. 无 active Goal 时只创建第一个满足前置条件的 pending Goal；
4. 不跨 Goal，不并发写数据库；
5. 保护未跟踪文件和卖点价值现有修改；
6. 任何 205 写入前确认无其他 active database writer；
7. 任何 publish/current 操作在 G42 明确批准前一律禁止。
8. heartbeat 唤醒后持续执行当前 Goal 至完成或真实阻塞；专项验证随 Goal 执行，完整回归与总评审只在 G39 集中执行。
