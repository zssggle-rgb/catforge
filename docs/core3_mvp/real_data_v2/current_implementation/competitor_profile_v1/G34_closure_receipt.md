# G34 竞品画像 V1.1 候选与关系门槛关闭回执

状态：completed

日期：2026-07-16

## 1. Goal

在不连接或写入业务数据库、不访问 205、不修改 G35 排序选择、G36 materializer、G37 Adapter、G38 智能体、旧 M12/M13/M14 或 V1 草稿、不执行 review/publish/current 的前提下，重构 V1.1 候选资格与 pair 关系门槛，把 scope、dimension availability、conclusion strength、review overlay 四轴明确分离，保证局部缺失、冲突或待复核不会让合法候选从其他可比较维度和问题中消失。

## 2. Scope 门槛

- 全局排除严格限定为 `self_pair`、`project_mismatch`、`category_mismatch`、`candidate_outside_manifest`、`identity_decode_failed` 五类 hard scope error；
- authority、lineage、taxonomy 和版本范围差异只形成独立复核项，不全局排除；
- missing、partial、conflict 和 review 保留在具体维度，不转换成候选级失败；
- 显式空白、无法解码或与快照不一致的 identity token 均 fail closed，不被快照值静默替换；
- scope 与 G33 assembly 的 project/category/version/release/snapshot/hash 权威链不一致时立即失败。

## 3. 被旧门槛拦截候选的真实关系计算

- 仅忽略旧 `candidate_relation_evaluation_eligibility` 占位 gate 不足以恢复分析，因为 V1 对未准入候选没有运行七类领域关系计算；
- 新增 `V11RelationEvidenceCalculator`，复用成熟 `CompetitorRelationEvaluator` 的 pair 关系算法，只中和旧 `candidate_status` 和 `relation_evaluation_member` 两个全局控制字段，不改产品、语义、价值或市场事实；
- 所有 G34 analyzable pair 都真实计算 direct substitute、same budget、uptrade、downtrade、same brand、scenario 和 same value 七类关系，不再把“未准入”占位行当作分析结果；
- pair/purchase pool/value substitution/price-volume 的完整 identity 与 hash 链在计算前校验，错链 fail closed；
- V1.1 relation calculator method version 已绑定 G34 input hash；旧 V1 默认路径及其 public 行为保持不变。

## 4. 四轴结果合同

- 每个 analyzable pair 固定保存全部维度状态、七类关系、八类产品决策问题和证据引用；
- relation status 只允许 `passed`、`limited`、`unassessable`、`failed`；review 作为独立 overlay 保存；
- required dimension 局部 unknown/conflict 只影响使用该维度的关系或问题，其他维度继续计算；
- legacy 全局 review 不再让全部关系和问题失效；独立证据不足只标记对应关系复核；
- 只要至少一个产品决策问题可回答，候选继续进入 G35 重点竞品选择输入；
- available weight、旧 candidate status、共同周度/共同平台、正式直接竞品身份、固定候选数和完整度均未作为 G34 全局门槛。

## 5. 样本与回归

- G28 65E7Q 旧默认候选 20 款全部通过 analyzable scope，候选差集为 0；
- G28 gate fixture matrix 的 TV complete、M12D missing、M05C review、battlefield conflict、market-only、configuration-only、AC complete、AC partial 八类场景全部继续；
- TV/AC complete、partial、missing、conflict 均保留完整维度、七类关系和八类问题结构；
- market-only 与 configuration-only 均能保留对应可回答问题，并继续作为 G35 输入；
- HDMI 2.1 等基础功能没有被设置为候选准入门槛。

## 6. 测试与独立复核

- G34 专项测试：41 passed；
- 候选资格、确定性、旧关系计算、G33、G34 和 V1.1 schema 受影响回归：131 passed；
- G34 核心模块 branch coverage：408 statements、39 missing、86%；
- Ruff、Python compile、whitespace check：passed；
- 独立复核中发现并修复：G33 assembly hash 未重验、scope authority/snapshot 链未闭合、空 identity token 被静默替换、局部独立证据复核被全局化、问题方向使用固定占位值、替代证据复核未降低问题强度、旧候选控制 gate 被重放为关系失败、旧门槛候选没有真实运行七类关系算法；
- 终审无未关闭问题：P0=0、P1=0、P2=0。

## 7. 写入与运行边界

- 业务数据库读取或写入：0；
- 205 访问、部署或 migration：0；
- G35 排序/角色/重点选择和 G36—G38 修改：0；
- 旧 M12/M13/M14、V1 草稿或旧 V1 关系算法默认路径修改：0；
- review/publish/current/deprecated 状态切换：0；
- 外部 LLM、网络分析调用、飞书消息/卡片/报告/文档：0；
- git stage/commit：0；
- 用户其他未跟踪文件未暂存、未删除、未覆盖。

## 8. 本 Goal 文件

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_v1_1_gate_evaluation.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_v1_1_gate_evaluation.py`；
- 本关闭回执与串行 Goal 调度状态。

## 9. 下一 Goal

G35：实现 V1.1 六维排序、关系角色和重点竞品选择。所有存在非 unknown 产品决策结论的候选均参与相应选择；coverage 只影响结论强度和同分排序，不能恢复为候选级门槛。
