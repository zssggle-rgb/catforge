# 竞品画像 V1 G12 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_candidate_determinism_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_candidate_determinism.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_candidate_determinism.py`。

## 2. 研究过的现有模式

实现前对照了三类确定性与幂等模式：

1. `hash_utils.py`：复用 `normalize_for_hash`、`canonicalize_json` 和带版本的 `stable_hash`，保持 `None`、空字符串、unknown 和 `-` 的语义差异，不在 hash 规范化阶段改写业务含义；
2. `comment_unit_link_builder.py` 及其重复 unit/source ID 测试：复用“完全相同的重复输入只形成一个业务节点”的规则；G12 将其扩展到 source record、evidence ref、recall fact、candidate 和 question；
3. `sellpoint_value_profile_materializer.py` 与 persistence 的 input fingerprint、重复写入复用、不可变冲突和 readback hash 测试：复用全 lineage/config 入 hash、重放幂等和已保存结果不可被不同 hash 覆盖的门禁。

## 3. 已实现的确定性 Guard

- `CandidatePipelineDeterminismGuard.run`：规范化 G09 category/target bundle，连续执行两遍 G10 recall 和 G11 eligibility，只有两次完整 typed payload 完全一致才返回；
- `CandidatePipelineDeterminismGuard.verify`：使用已保存 manifest 自带配置重算全链，逐层比较 source、fact、candidate、question 和 manifest；任一嵌套 hash 或内容被篡改即失败；
- `CandidatePipelineRun` 同时返回 canonical category/target bundle、recall manifest、eligibility manifest 和 typed determinism receipt；
- 计算全程纯内存，不访问数据库、不调用 repository、不调用外部 LLM。

## 4. Canonicalization 与冲突策略

- source record 稳定业务键为 `module_code + source_batch_id + record_type + record_id`；
- 同一业务键、全部 typed 内容完全相同的记录只保留一条并记录 duplicate count，不重复进入证据或候选计算；
- 同一业务键但 facts、result hash、scope 或其他内容不同，抛出 `CandidatePipelineDuplicateConflictError`，禁止 last-write-wins；
- 模块、SKU、record、evidence ref、candidate、check 和 hash payload 均使用稳定业务键排序；
- 可接收同一 exact-authority 记录的任意分页分组与页内顺序；分页缺行、增行或内容变化立即 fail closed；
- target module 的 canonical records 必须与 category bundle 中该 target 的记录完全一致，不能使用另一份漂移输入。

## 5. Hash chain 与候选守恒

- 连续两次重放必须产生完全相同的 recall/eligibility typed payload 和 result hash；
- eligibility 的候选 SKU 列表必须与 recall 一一对应、顺序一致、数量一致；
- eligibility `recall_result_hash` 必须精确指向本次 recall result；
- recall/eligibility 配置版本、category/target exact-authority fingerprint、canonicalization stats 和所有下游 hash 均进入 receipt hash；
- 修改 recall config version 会改变 recall 与 eligibility hash；只修改 eligibility config version 只改变 eligibility 及 receipt hash；
- 修改 exact-authority fingerprint 会改变下游 hash；修改 G11 使用的受保护 claim role 会改变 eligibility hash；
- 多入口命中仍只保留一个 target×candidate，全部 recall source/fact 保留，不因去重丢失入口原因。

## 6. Typed Receipt

receipt 保存：

- generated/verified 模式；
- project/category/release scope/target；
- category/target input fingerprint 与两级 config version；
- recall/eligibility result hash；
- candidate、recall fact、八问题 assessment 和唯一 evidence ref 数量；
- 每个上游模块 category/target 的 input、unique、exact duplicate 数；
- candidate conservation、source dedupe、两级 replay idempotency、八问题覆盖和稳定 hash chain 检查；
- receipt 自身 input fingerprint 与 result hash。

样例包含 4 个候选、26 条 recall fact、32 个问题 assessment、25 个唯一 evidence ref，两遍重放完全一致。

## 7. 验证

- G12 determinism/schema tests：10 passed；
- G05—G12 schema/migration/repository/lifecycle/input/recall/eligibility/determinism：113 passed；
- G12 service + schema coverage：94%；
- TV、AC、空候选 manifest：通过；
- 原始记录乱序和分页重新分组：result hash 不变；
- category 与 target 完全相同重复记录：去重后 recall/eligibility hash 不变；
- 同 key 冲突记录、分页缺行：fail closed；
- recall fact hash、question hash 篡改：verify 拒绝；
- duplicate evidence ref、recall fact、question：typed DTO 拒绝；
- 配置、authority fingerprint 和受保护事实变化向下游 hash 传播：通过；
- 候选一对一守恒、多入口 pair 去重：通过；
- Ruff、format check、编译检查：通过。

## 8. 状态变化

- 本地业务数据库写入：无；
- 205 连接/数据库写入/migration：无；
- 画像生成、review/publish/current/deprecated：均未执行；
- pair 特征、购买池、语义替代、量价压力、七类正式关系和重点竞品选择：均未实现；
- 部署：无；
- Git 暂存/提交：无。

## 9. 下一 Goal

允许创建 G13，只验证最大候选宇宙、分页/批量输入读取、内存与耗时基线、无 N+1 和失败不静默截断；不得实现 G14 pair 特征、G15—G18 关系判断、G19 重点选择、画像持久化、205 写入、部署或 Git 提交。
