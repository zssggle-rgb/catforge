# 用户卖点价值画像 V5.1 串行 Goal 调度

状态：SPV51-G01—G06 completed；SPV51-G07 pending

日期：2026-07-17

授权范围：需求、设计、开发、专项测试、综合测试、精确提交、205 代码/migration 部署、65E7Q draft 验收、AC 单 SKU draft 验收、双品类通过后的 TV/AC 全量 draft 生成与只读发布准备审计。

不含授权：review、publish、current；修改 V5/竞品画像已发布行；重跑 M03B—M12D；修改旧 M12/M13/M14。

## 1. 调度与效率原则

1. 任意时刻只允许一个 active Goal；完成后立即创建第一个满足前置条件的 Goal；
2. 每个 Goal 使用 Goal 模式，不设置 token budget；
3. 10 分钟 heartbeat 只负责异常中断后的断点续跑，不是十分钟工作切片；
4. 一次唤醒持续推进 active Goal，直到完成或真实阻塞；不重复读取未变化的全部上下文；
5. 开发 Goal 只跑本模块专项测试和必要受影响回归；
6. 完整回归、覆盖率、性能和方法/工程/业务总评审只在 SPV51-G13 执行一次；
7. 一个 Goal 不同时承担大块实现、全量回归、部署和生产验收；
8. 禁止并发数据库写入、部署或批量生成；
9. 只暂存当前 Goal 精确文件，禁止 `git add .`，保护现有修改和未跟踪产物；
10. 65E7Q 未通过不得创建 AC Goal；AC 未通过不得创建全量 Goal；
11. 全量只生成 draft；review/publish/current 必须另行明确批准；
12. 低门槛不等于删除证据边界：unknown 不伪造、market association 不冒充随机实验因果；
13. 同一真实阻塞连续三次且无法继续时才标记 blocked。

## 2. Goal 总表

| Goal | 唯一目标 | 关闭门禁 | 205 写入 |
| --- | --- | --- | --- |
| SPV51-G01 | 冻结需求、详细设计、低门槛和调度合同 | 三份文档一致，无 P0/P1 冲突 | 否 |
| SPV51-G02 | 冻结兼容基线和 205 只读审计 fixture | V5 现状、65E7Q、TV/AC 分布、竞品画像 source/version/hash 可重复 | 否，只读 |
| SPV51-G03 | 实现 V5.1 Typed Schema 与配置合同 | 四状态、问题级候选、四层量化、低门槛配置测试通过 | 否 |
| SPV51-G04 | 实现 migration 与 entities | 最小列/约束/索引、upgrade/downgrade、V5 历史保护通过 | 否 |
| SPV51-G05 | 实现竞品画像正式/预览 Reader Adapter | formal 只读 current；preview 锁版本；旧 M12/M13/M14 调用为 0 | 否 |
| SPV51-G06 | 实现竞品与分析参考池、问题级候选资格 | 两池分离；Top3 不截断；局部缺失只影响本题 | 否 |
| SPV51-G07 | 重构基础能力、投入分类和局部 review 传播 | not_assessed 不 review；取消 linked investment 全局传播 | 否 |
| SPV51-G08 | 实现低门槛直接量价与参数组比较 | 1 个对照可答；周均量价；无需共同周/平台/高中低 | 否 |
| SPV51-G09 | 分层市场原型、合成对照和严格 WTP | 增强层失败不影响普通结论、SKU 或版本 | 否 |
| SPV51-G10 | 重构 value/SKU 状态、confidence 和生命周期质量 | conclusion/partial/no_conclusion/invalid 正确；仅 invalid 阻断 | 否 |
| SPV51-G11 | 集成 materializer、repository、generation 与 fingerprint | 新 draft 幂等、竞品画像 lineage/hash、失败隔离、完整回读 | 否 |
| SPV51-G12 | 报告和问答只消费 V5.1 保存结果 | 零现场重算；无结论/invalid 诚实返回；跨载体同 hash | 否 |
| SPV51-G13 | 完整回归、覆盖率、性能、三类评审和精确提交 | 无 P0/P1；测试/迁移/性能/边界全通过 | 否 |
| SPV51-G14 | 部署 205 代码和 migration，不生成 | commit/container/migration/health/ready/rollback 通过 | migration only |
| SPV51-G15 | 只生成并验收 65E7Q V5.1 draft | 20 候选/Top3、两池、量价、局部状态、报告问答通过 | 单 SKU draft |
| SPV51-G16 | 只生成并验收一个 AC V5.1 draft | AC taxonomy/能力段/量价/状态无 TV 串线 | 单 SKU draft |
| SPV51-G17 | 生成 TV/AC 全量 V5.1 draft | 532 SKU 完整、invalid/failure/串线/悬空引用为 0 | 全量 draft |
| SPV51-G18 | 发布准备只读审计并停止 | 分布、diff、rollback 方案齐全；等待发布批准 | 否，只读 |

## 3. 分 Goal 范围

### SPV51-G01 需求与设计冻结

产物：本 requirements、detailed design、goal dispatch 和 `SPV51_G01_closure_receipt.md`。

关闭条件：

- 新竞品画像为正式竞品唯一来源；
- 低门槛、四状态、四层量化、局部 review、limited 可发布语义无冲突；
- 18 个 Goal 边界清楚，完整测试集中在 G13；
- 未修改代码、数据库或 205。

完成状态：completed；关闭回执：`SPV51_G01_closure_receipt.md`。

### SPV51-G02 兼容基线与只读审计

冻结：

- V5 旧 65E7Q 画像、5 个价值项、4 个已有量价 gap、review 原因；
- TV/AC profile/value/investment 状态分布；
- 当前正式竞品画像 TV/AC version id、profile/pair/selection 计数；
- 65E7Q 20 候选、Top 3、逐候选可用维度；
- golden fixture 和旧路径调用计数桩。

不写数据库，不修改 205。

完成状态：completed；关闭回执：`SPV51_G02_closure_receipt.md`。

### SPV51-G03 Typed Schema 与配置

新增 schema/config，兼容读取 V5 旧 payload。专项测试覆盖状态组合、空/单/多候选、unknown、invalid、TV/AC 隔离。

完成状态：completed；关闭回执：`SPV51_G03_closure_receipt.md`。

### SPV51-G04 Migration/Entities

只实现 G03 冻结的最小持久化变更。测试 upgrade/downgrade、唯一键、历史 V5 行、current isolation 和 PostgreSQL/SQLite 差异。

完成状态：completed；关闭回执：`SPV51_G04_closure_receipt.md`。

### SPV51-G05 竞品画像 Adapter

formal 只读 agent snapshot v2 current published；preview 显式锁版本；映射完整候选、Top3、pair 事实和 hash。通过禁止桩证明不调用旧 M12/M13/M14 或现场 competitor-set。

完成状态：completed；关闭回执：`SPV51_G05_closure_receipt.md`。

### SPV51-G06 两池与问题级资格

保留既有市场参考生成，和正式竞品 manifest 分开。候选每个问题单独 selected/rejected；缺某维度不影响其他问题。Top3 只标优先级。

完成状态：completed；关闭回执：`SPV51_G06_closure_receipt.md`。

### SPV51-G07 基础能力与投入

基础能力样本不足返回 not_assessed；known/missing 正确。投入分类 unknown 不向 value/SKU 传播；只保留真实冲突 review。

### SPV51-G08 直接量价与参数组

允许 single/small/group 三种证据强度；周均量价直接比较；参数任意不同取值分组。测试 1、2、5 个对照、缺价格/销量行和 HDMI 2.1 基础功能样例。

### SPV51-G09 增强量化

把同预算原型、卖得好/差组合、相邻战场、synthetic 和 strict WTP 统一映射到分层结果。严格方法失败只保存技术限制。

### SPV51-G10 状态与生命周期

实现 question→value→SKU→version 的局部聚合；移除全体 investment confidence 平均门槛；release quality 只由完整性和 invalid 决定。

### SPV51-G11 生成与持久化集成

fingerprint 加竞品画像 version/hash；生成新 V5.1 draft；repository 回读 typed validation/hash；单 SKU 失败隔离；V5 历史和 published current 不变。

### SPV51-G12 消费路径

报告和 QA 映射保存的状态与四层量化，不现场重算。测试 formal、preview、no_conclusion、invalid、strict WTP absent 和同 hash。

### SPV51-G13 集成质量

集中执行：

- SPV 与竞品画像消费全回归；
- coverage、migration upgrade/downgrade；
- 最大候选 query count/内存/时延；
- 方法评审：市场关联、严格 WTP、证据边界；
- 工程评审：状态机、事务、hash、回退、工厂边界；
- 业务评审：65E7Q 输出是否能指导产品定义、投入、价格和 SKU 角色；
- 只暂存本任务精确文件并提交。

### SPV51-G14 205 部署

部署 G13 commit 和 migration；不创建版本、不生成画像。验证容器、revision、migration、healthz、readyz、CLI import 和 rollback。

### SPV51-G15 65E7Q draft

只生成一个 V5.1 draft。按 requirements 第 9 节逐项回读；报告和 QA 使用 preview；任何旧候选回退、20/Top3 不一致、4 个量价结果整体丢失、局部状态再全局传播均失败。

### SPV51-G16 AC 单 SKU draft

从正式 AC 竞品画像选择一个上游较完整 SKU，验证 AC 术语、能力段、候选、价格销量和用户价值，无 TV 假设。失败即停止。

### SPV51-G17 TV/AC 全量 draft

仅在 G15/G16 均通过后创建。生成 377 TV + 155 AC 新 draft，复核 coverage、invalid/failure、状态分布、直接量价覆盖、局部 review 和 hash。

### SPV51-G18 发布准备审计

只读输出 ready/limited/blocked 判定、V5→V5.1 diff、no_conclusion 清单、发布/回退步骤。停止 heartbeat，等待用户明确批准；不执行 review/publish/current。

## 4. Heartbeat 提示词

每次唤醒：

1. 读取本 requirements、detailed design、goal dispatch、上一个关闭回执和当前 Goal；
2. 有 active Goal 时只完成该 Goal；无 active Goal 时只创建首个满足前置条件的 Goal；
3. heartbeat 是断点续跑信号，不是工作切片；持续做到完成或真实阻塞；
4. 开发 Goal 只跑专项测试，完整测试只在 G13；
5. 不并发写数据库，保护现有工作树，只精确暂存；
6. 205 写入严格遵守 G14—G17 顺序；
7. 任何 review/publish/current 未获新授权一律禁止。
