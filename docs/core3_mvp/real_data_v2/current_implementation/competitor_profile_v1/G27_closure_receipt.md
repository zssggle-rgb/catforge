# G27 竞品画像 V1.1 需求与设计冻结回执

状态：completed

日期：2026-07-15

## 1. Goal

冻结竞品画像 V1.1 的不降级数据需求、详细设计和串行任务链。画像只负责计算并保存竞品多维事实、分析过程、分维度结论、综合结论、角色、顺序和证据边界；竞品分析智能体只读取画像并完成问题路由与业务表达。

## 2. 冻结产物

- `COMPETITOR_PROFILE_V1_1_requirements_addendum.md`；
- `COMPETITOR_PROFILE_V1_1_detailed_design.md`；
- `COMPETITOR_PROFILE_V1_1_goal_dispatch.md`；
- 本回执。

## 3. 冻结决策

1. V1.1 复用 V1 已完成的权威输入、候选宇宙、关系资产、版本状态机和批量框架，不重跑 M03B—M12D；
2. 画像新增共享 SKU snapshot、完整 pair analysis、机器可读结论和综合 summary；
3. `PairAnalysisCalculator` 复用并冻结成熟的价值锚点 15 分制、替代压力 10 分制和购买压力计算器；Assembler 只做 typed 组装；
4. 候选仅允许五类 hard exclusion；authority、review、taxonomy、lineage 和局部冲突均按维度保存，不全局淘汰；
5. relation status 与 review overlay 分离；available weight 不设保存、问题参与或重点选择门槛；
6. 基础功能保存原始差异和市场普及率，但不贡献差异得分、重点理由或产品建议；
7. 画像保存 recall rank、旧 score basis、完整 M12C/M12D、锚点、压力、量价共同窗口、角色、排序、重点与未入选原因；
8. Adapter 映射已完成分析的结果，纯展示入口禁止 enrichment、分析、打分、角色分配、排序和 Top 3 选择；
9. V1 历史约束与 V1.1 条件约束分流；version 与 snapshot scope 使用复合外键保证一致；
10. downgrade guard 识别 V1.1 version、snapshot 和分析列值，旧 V1 草稿不阻断回退；
11. 65E7Q 先做全候选逐字段验收，AC 单 SKU 通过后才允许 TV/AC 全量 draft；
12. review、publish 和 current 不在当前授权范围内。

## 4. 评审关闭

独立方法评审发现的消费时二次计算、成熟计算器缺位、review 状态混用、字段不完整、隐藏门槛、hard exclusion 兜底、基础功能合同和 fixture 覆盖问题已全部关闭。

独立工程评审发现的旧数据库约束冲突、migration 约束不完整、downgrade 误判、性能验收时序、跨表 scope 一致性和空 V1.1 version 回退风险已全部关闭。

最终复核：无剩余 P0/P1，允许冻结 G27。

## 5. 验证

- CA01—CA30 各出现一次；
- 三份文档 `git diff --check` 通过；
- 设计与用户最新边界一致；
- 未修改运行代码；
- 未写入本地或 205 数据库；
- 未部署 205；
- 未执行 review、publish 或 current 切换。

## 6. 下一 Goal

G28：在修改算法和 schema 前，冻结旧竞品分析智能体的完整机器可读兼容基线、字段映射矩阵、门槛 fixture matrix 和性能/存储基线。
