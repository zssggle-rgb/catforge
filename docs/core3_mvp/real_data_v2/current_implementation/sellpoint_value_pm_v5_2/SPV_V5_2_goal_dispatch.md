# 用户卖点价值画像 V5.2 串行 Goal 调度

状态：SPV52-G01—G08 completed；用户批准后的正式发布 completed

日期：2026-07-18

授权范围：需求、设计、开发、专项测试、综合测试、精确提交与推送、205 代码部署、65E7Q draft、AC 单 SKU draft、双品类通过后的 TV/AC 全量 draft 生成与只读审计。

不含授权：review、publish、current；修改已发布 V5.1/竞品画像；重跑 M03B—M12D；修改旧 M12/M13/M14。

## 1. 调度与效率原则

1. 任意时刻只允许一个 active Goal；
2. 每个 Goal 使用 Goal 模式，不设置 token budget；
3. 10 分钟 heartbeat 只负责异常中断后的断点续跑，不是工作切片；
4. 一次唤醒持续推进 active Goal 直到完成或真实阻塞；
5. 当前 Goal 完成且下一 Goal 前置满足时立即进入，不等待 heartbeat；
6. 不重复读取未变化文档，不重复运行没有新增价值的阶段检查；
7. 开发 Goal 只跑本模块专项测试和必要受影响回归；
8. 完整回归、覆盖率、性能和三类总评审只在 G06 执行一次；
9. 禁止并发数据库写入、部署或批量生成；
10. 只暂存当前 Goal 精确文件，禁止 `git add .`；
11. 65E7Q 未通过不得创建 AC/全量验收；AC 未通过不得执行全量；
12. 全量只生成 draft；review/publish/current 必须另行明确批准；
13. 同一真实阻塞连续三次且无法继续时才标记 blocked。

## 2. Goal 总表

| Goal | 唯一目标 | 关闭门禁 | 测试范围 | 205 写入 |
| --- | --- | --- | --- | --- |
| SPV52-G01 | 冻结需求、详细设计和调度合同 | 三份文档一致，四层对象和来源规则无冲突 | 文档自检 | 否 |
| SPV52-G02 | Typed Schema 与 M04C 原始卖点 Reader | 原文、标准标签、quote、证据、无来源状态均可回读 | 新 schema/adapter 专项 | 否 |
| SPV52-G03 | 分层映射、卖点分类、参数分类和完整性校验 | 参数/主题不能生成卖点；table-stake 正确分流 | mapping/classifier 专项 | 否 |
| SPV52-G04 | materializer、repository、readback 和 V5.1 兼容 | V5.2 immutable draft 完整回读；V5.1 不变 | persistence/materializer 专项 | 否 |
| SPV52-G05 | 报告、卡片、QA 只消费分层画像 | 无现场上游读取、无卖点生成、跨载体同 hash | consumption 专项 | 否 |
| SPV52-G06 | 集成回归、性能、三类评审和精确提交 | 无 P0/P1；完整测试与边界通过 | 完整测试集中执行 | 否 |
| SPV52-G07 | 部署 205 并只验收 65E7Q V5.2 draft | 原始卖点、参数、用户价值、内部主题严格分层 | 单 SKU 线上验收 | 单 SKU draft |
| SPV52-G08 | AC 单 SKU与 TV/AC 全量 V5.2 draft 审计 | 双品类无串线/伪造/悬空引用；正式版本不变 | AC+全量只读审计 | draft only |

## 3. 分 Goal 范围

### SPV52-G01 需求、设计与任务链冻结

产物：

- `SPV_V5_2_requirements.md`；
- `SPV_V5_2_detailed_design.md`；
- `SPV_V5_2_goal_dispatch.md`；
- `SPV52_G01_closure_receipt.md`。

关闭条件：

- 产品参数、产品原始卖点、用户价值、内部价值主题四层清楚；
- 产品卖点只能来自 M04C；
- 卖点分类和参数分类分开；
- 8 个 Goal 完整但不过碎；
- 完整回归集中在 G06；
- 未修改代码、数据库或 205。

状态：completed。

### SPV52-G02 Typed Schema 与原始卖点 Reader

实现：

- `SourceSellpointFact`；
- sellpoint/parameter/value typed links；
- sellpoint/parameter assessment schema；
- layer integrity summary；
- M04C profile/fact 只读 adapter；
- `source_claim_key + claim_code` 去重与证据合并。

专项测试：

- exact quote 必须是原文子串；
- M04C 缺失合法降级；
- TV/AC 隔离；
- supported/partial/unknown/conflict；
- 禁止外部 LLM。

不改报告，不部署。

状态：completed；关闭回执：`SPV52_G02_closure_receipt.md`。

### SPV52-G03 分层映射与分类

实现：

- claim→parameter；
- claim→user value；
- internal value theme 只作内部链接；
- 卖点四分类；
- 参数五分类；
- table-stake 有来源/无来源分流；
- 卖点机会和纯参数差异分离；
- layer integrity validator。

专项测试：

- 65E7Q 游戏卖点 fixture；
- value theme 不得成为 sellpoint；
- 参数不得成为 sellpoint；
- 无来源参数进入参数账；
- 复合原始卖点按 claim code 分项判断；
- AC taxonomy 不串 TV。

不改持久化，不部署。

状态：completed；关闭回执：`SPV52_G03_closure_receipt.md`。

### SPV52-G04 持久化、回读与兼容

将 G02/G03 结果接入 V5.2 materializer/repository：

- 优先复用现有 JSON payload；
- 新 method/schema/rule version；
- fingerprint 绑定 M04C/M03B/用户价值/竞品画像 hash；
- V5.2 immutable draft 幂等；
- V5.1 current/readback/result hash 保持不变；
- 单 SKU 失败隔离。

如现有 JSON 不能满足完整性，再增加最小 migration；不得为形式完整新增空表。

专项测试只覆盖 materializer、repository、hash 和 V5.1 compatibility。

状态：completed；关闭回执：`SPV52_G04_closure_receipt.md`。

### SPV52-G05 报告、卡片与 QA

删除或禁用：

- `_v5_1_product_sellpoint_cn()` 参数拼接；
- capability/value theme fallback；
- 无来源 `product_sellpoint_cn`。

消费输出：

- 本品原始卖点；
- 标准卖点标签；
- 支撑参数；
- 用户价值；
- 用户认知；
- 市场表现；
- 产品卖点修改建议；
- 独立参数账。

报告、卡片、QA 只读取 V5.2 保存结果。正式 current 仍读取 V5.1，preview 才读取 V5.2 draft。

状态：completed；关闭回执：`SPV52_G05_closure_receipt.md`。

### SPV52-G06 集成质量与提交

集中执行一次：

- 全部 V5.2 专项测试；
- V5.1 正式消费回归；
- competitor-profile consumption 回归；
- migration（如有）upgrade/downgrade；
- 最大卖点/候选 SKU query count、内存和时延；
- 方法评审：来源、分类、用户价值和市场关联边界；
- 工程评审：schema、hash、事务、兼容和回退；
- 业务评审：产品经理是否看到熟悉原文，是否还存在主题/参数冒充卖点；
- 精确暂存、提交并推送。

不得在 G02—G05 重复执行本 Goal 的完整门禁。

状态：completed。

### SPV52-G07 205 部署与 65E7Q draft

部署 G06 精确提交，不生成全量。

只生成 65E7Q V5.2 draft，逐项验证 requirements 第 10 节。重点检查：

- “游戏影音双丝滑”来自原文；
- “游戏与运动流畅”只在内部主题；
- 170Hz/300Hz/HDMI/48Gbps 只在参数；
- table-stake 基础卖点/基础参数分流；
- 原有竞品、价值和量价结论不回退；
- 正式 V5.1 current 未变化。

失败即停止，不创建 AC 或全量写入。

状态：completed；关闭回执：`SPV52_G07_closure_receipt.md`。

### SPV52-G08 AC 与全量 draft

前置：G07 通过。

1. 先选择一个 M04C 较完整的 AC SKU 生成 draft；
2. 验证 AC 卖点原文、参数和用户价值，无 TV 术语串线；
3. AC 通过后才生成 TV/AC 全量 V5.2 draft；
4. 只读审计来源覆盖、无来源分布、四类卖点、五类参数和完整性计数；
5. `unsourced/parameter_as_sellpoint/value_theme_as_sellpoint/hash mismatch/dangling` 均为 0；
6. 输出 V5.1→V5.2 diff 和回退方案；
7. 停止并等待用户决定是否 review/publish/current。

状态：completed；TV/AC 版本级最终 typed readback 已通过；关闭回执：`SPV52_G08_closure_receipt.md`。

## 4. Heartbeat 提示词

每次唤醒：

1. 读取 requirements、detailed design、goal dispatch、上一个关闭回执和当前 Goal；
2. 有 active Goal 时只完成该 Goal；无 active Goal 时创建首个满足前置条件的 pending Goal；
3. heartbeat 是断点续跑信号，不是 10 分钟工作切片；
4. 开发 Goal 只跑专项测试，完整测试只在 G06；
5. 当前 Goal 完成后立即进入下一项；
6. 禁止并发写数据库，保护工作树，只精确暂存；
7. G07 前禁止 205 写入，G08 前必须先通过 65E7Q；
8. 任何 review/publish/current 未获新授权一律禁止。

## 5. 用户批准后的正式发布

2026-07-18 用户明确批准 TV、AC V5.2 执行 review、publish 和 current
切换。两品类已完成正式发布，飞书智能体正式消费已验证。发布详情见
`SPV52_publish_receipt.md`。
