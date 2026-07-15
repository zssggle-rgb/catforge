# G35 竞品画像 V1.1 排序、角色与重点选择关闭回执

状态：completed

日期：2026-07-16

## 1. Goal

在不连接或写入业务数据库、不访问 205、不修改 G36 materializer、G37 Adapter、G38 智能体、旧 M12/M13/M14、V1 草稿或旧 V1 默认行为、不执行 review/publish/current 的前提下，实现 V1.1 六维排序、竞争角色、重点竞品选择、全部候选未入选原因和新旧 Top 3 machine-readable diff。排序只消费 G33 PairAnalysisAssembly 与 G34 PairGateEvaluation 已算事实，不重算上游分析。

## 2. 六维得分过程

- 冻结六维与权重：购买池 20%、价值战场 25%、用户任务 15%、目标客群 15%、价值锚点 15%、替代压力 10%；
- 每个候选完整保存六维 availability、raw score、weighted contribution、raw total、available weight、normalized total、coverage、ranking score 和固定同分顺序；
- unknown/conflict 维度 raw score 为 null、贡献为 0，不填假 0 分；available/partial 维度使用完整冻结权重；
- `normalized_total = raw_total / available_weight`，coverage 等于 available weight；coverage 最低门槛仍为 null；
- market validation 不进入六维主体得分，只在 ranking score 相同后用于验证和同分排序；
- 旧 competitor score 与旧 basis 只作为兼容审计字段保存，不参与 V1.1 入口门槛。

## 3. 排序顺序与低覆盖保护

候选的确定性顺序为：

1. 对应产品决策问题的最高结论强度；
2. 六维 normalized ranking score；
3. market validation strength；
4. available weight；
5. recall rank；
6. candidate SKU code。

因此，低覆盖候选不被删除，也没有显性或隐性 coverage gate；但它不能只靠少数已知维度的高归一分越过结论强度更高、证据更完整的候选。仅有市场事实但能独立回答量价问题的候选可以参与并被选择：pair ranking score 仍保持 null，selection plan 使用 0 作为持久化排序值，不把 unknown 维度伪造为 0 分。

## 4. 角色与重点选择

- 关系结论只有 `passed/limited + positive_pressure` 才形成对应关系角色，避免把“已知无影响”误写成直接竞争；
- 产品问题补充 configuration benchmark、market reference 等可回答角色；价格梯度根据双方价格比确定 price-adjacent、downtrade 或 uptrade；
- 每个候选保存全部角色和一个主角色；主角色由最高结论强度的问题和冻结问题优先级确定；
- 第一名按完整排序选择；第二、三名优先补充尚未覆盖的主产品决策问题和主竞争角色，再使用完整排序；
- 最多选择 3 款，但候选分析池不设上限、不截断；
- 所有未入选候选仍保存六维得分、coverage、角色、问题结论和明确原因：无可回答问题、相同角色已有更强候选、或重点容量已满。

## 5. 旧 Top 3 与 65E7Q

- 旧 Top 3 必须作为完整候选宇宙成员参与；任一旧 Top 3 缺失时 fail closed；
- 每个旧 Top 3 保存 legacy rank 与 legacy role，不使用旧 candidate status 作为资格；
- 输出 `retained|added|dropped` diff、旧/新名次和对应选择或未选原因；
- G28 65E7Q 默认 20 款旧候选全部进入同一个选择宇宙，pair decision 数 20、分析候选数 20、候选差集 0、重点选择 3；
- 没有固定 12 款、20 款或其他候选池上限；20 只是本次 G28 兼容 fixture 的真实规模。

## 6. 局部缺失和复核

- TV/AC complete、partial、missing、conflict 均进入选择过程；
- M05C 用户兑现复核只保留为 review overlay，不阻断其他维度；
- battlefield conflict 仅令战场得分不可用，不删除候选；
- market-only 与 configuration-only 都能以对应非 unknown 产品问题参与选择；
- HDMI 2.1 等基础功能、共同周度、共同平台、正式直接竞品身份、旧 candidate status 和 relation evaluation member 均未作为选择入口。

## 7. Hash、确定性与失败保护

- G35 重验 G33 assembly hash、G34 scope/gate hash、project/category/version/release/target/candidate/snapshot 权威链；
- 一个候选的 selection input fingerprint 同时绑定 assembly、gate、legacy reference 与 score policy；
- 顶层 result hash 绑定全候选决策、priority plans、role buckets 和 legacy diff；
- 输入顺序变化不改变结果；同分时 recall rank 和 SKU code 形成稳定顺序；
- 旧 Top 3 缺失、重复候选、跨 scope 输入、身份/hash 错链均 fail closed。

## 8. 测试与独立复核

- G35 专项测试：21 passed；
- V1.1 schema、G33、G34、G35 与旧 key competitor selector 受影响回归：124 passed；
- G35 核心模块 branch coverage：419 statements、48 missing、83%；
- Ruff、Python compile、whitespace check：passed；
- 独立复核中发现并修复：角色多样性误按全部辅角色去重导致主角色无法补位、limited 但 no-material-effect 的关系被误标竞争角色、运行时关键状态使用可被 `python -O` 移除的 assert；
- 终审无未关闭问题：P0=0、P1=0、P2=0。

## 9. 写入与运行边界

- 业务数据库读取或写入：0；
- 205 访问、部署或 migration：0；
- G36 materializer、G37 Adapter、G38 智能体修改：0；
- 旧 M12/M13/M14、V1 草稿或旧 key selector 修改：0；
- review/publish/current/deprecated 状态切换：0；
- 外部 LLM、网络分析调用、飞书消息/卡片/报告/文档：0；
- git stage/commit：0；
- 用户其他未跟踪文件未暂存、未删除、未覆盖。

## 10. 本 Goal 文件

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_v1_1_selection.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_v1_1_selection.py`；
- 本关闭回执与串行 Goal 调度状态。

## 11. 下一 Goal

G36：扩展 V1.1 materializer 与生成服务，把 G33、G34、G35 已完成结果无损组装为 PairAnalysisSnapshot、priority selections、SKU summary 与 draft persistence bundle；支持单 SKU、batch、幂等、失败隔离、checkpoint 和 hash receipt，不在 materializer 内重新分析、打分、定角色或排序。
