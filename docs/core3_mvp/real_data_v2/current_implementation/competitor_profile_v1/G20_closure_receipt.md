# 竞品画像 V1 G20 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_materializer_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_materializer.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_materializer.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_schemas.py` 的最小 pair membership 与 target market summary 兼容修复。

## 2. 研究过的现有模式

实现前对照了三类以上现有模式：

1. G04 detailed design §5.10、§8.2、§10.1、§14：主画像字段、完整阶段链、状态组合和失败隔离；
2. G05 `CompetitorProfileDraftBundle`、`SkuCompetitorDecisionProfileDraft`、`CompetitorPairDraft`：沿用 pair/selection 一致、连续 rank、七关系和 profile hash 合同；
3. G12—G19 各阶段 bundle：沿用 scope/hash/candidate 守恒，不重新推导或旁路读取；
4. 既有卖点价值 materializer/batch status：沿用稳定 SKU 顺序、安全错误码、单 SKU 异常隔离和结果 hash，不复制其旧竞品评分方法。

## 3. 单 SKU 完整 materializer

`CompetitorProfileMaterializer.materialize(category_bundle, target_bundle, config)` 固定执行：

1. scope、authoritative SKU 和 config 品类门禁；
2. G12 canonical candidate pipeline；
3. G14 pair feature；
4. G15 purchase pool；
5. G16 value substitution evidence；
6. G17 price-volume pressure；
7. G18 relation evaluation；
8. G19 key selection；
9. G20 pair/profile/QA 装配。

每个阶段只调用一次，并在装配前验证所有 candidate SKU 列表与顺序一对一守恒。输出保存八个 stage result hash、materializer input fingerprint 和 result hash。

目标在 G09 已被 hard blocked 时不会错误进入 G10 召回，而是直接形成 `blocked + insufficient_evidence` 空画像；G12—G19 阶段保存稳定的 `not_run_target_blocked` hash，不伪造 pair 或关系。

## 4. 完整 pair 装配

每个召回 candidate 均保存：

- recall sources/facts 和稳定 manifest key；
- competitor/reference membership 与 candidate status；
- purchase pool；
- 五证据族；
- M07 market comparison；
- 七类 relation assessments；
- 八类 question eligibility；
- reference purposes；
- selected/rank 或明确未入选原因；
- confidence/review、exact evidence refs、limitations 和 hash。

没有正式关系、没有入选、需要复核或仅作 reference 的 candidate 均不会被删除。

## 5. G05 pair schema 最小修复

集成测试证明旧基础 validator 存在两处矛盾，已做最小向后兼容修复：

- `competitor_member=true` 只允许 `eligible/limited`；
- `recalled_only/review_required/blocked` 允许 competitor/reference membership 均为 false，以保存完整候选；
- `reference_only` 仍必须是独立 reference membership；
- 低/unknown confidence 自动 review 只约束正式 competitor，不误伤纯 reference；
- review/blocked status 必须 `review_required=true`。

同时补充了 detailed design 已要求但基础 DTO 缺失的 `target_market_summary` 字段，默认值保持兼容。

## 6. SKU 主画像

主画像保存：

- target identity 和 M07 target market summary；
- ready/partial/blocked analysis state；
- available/no_priority_competitor/insufficient_evidence conclusion state；
- candidate/relation status counts；
- 0—3 key competitor summary；
- 有正式关系支撑的 competitive advantages；
- F1/F4 支撑的 substitutable values；
- 描述性 price/scale pressures；
- passed/limited same-brand findings；
- 正式关系下的 configuration follow/do-not-follow findings；
- no-conclusion reason；
- source lineage、exact evidence、limitations、八问题 QA index 和 hashes。

业务结论只从 passed/limited relation 和问题可用性生成。量价结论固定为描述性市场关联；`causal_wtp_claim=false`、`causal_claim=false`、`price_change_sales_increment_claim=false`。

状态严格区分：

- `ready + available`；
- `ready + no_priority_competitor`；
- `partial + available`；
- `partial/blocked + insufficient_evidence`。

目标本身 partial 时，即使没有重点竞品，也不会误写为“数据充分但无重点竞品”。

## 7. 纯内存批量失败隔离

`materialize_batch`：

- 按 target SKU 稳定排序；
- 重复 target 在生成前明确拒绝；
- 每个 SKU 独立 try/catch；
- 一个目标 scope/程序异常只生成安全 failure status，其余目标继续；
- status 仅返回白名单错误码和安全中文消息，不泄露原始异常；
- 保存 requested/succeeded/failed counts、每 SKU stage/profile hashes、稳定 batch fingerprint/hash；
- 重跑修正后的目标可独立成功，纯内存服务不写持久化状态。

## 8. 验证

- G20 schema/service tests：11 passed；
- G05—G20 全链：232 passed；
- G20 service + schema coverage：92%；
- 单 SKU full chain 和八阶段 hash：通过；
- 0/1/2/3 selections 与连续 rank 装配：通过；
- candidate/pair/selection 全量守恒：通过；
- 七关系、五证据族、八问题完整性：通过；
- reference/review/recalled/blocked pair schema：通过；
- ready/partial/blocked 与三类 conclusion：通过；
- blocked pre-recall 空画像：通过；
- 业务结论只消费正式关系：通过；
- WTP/因果销量/降价增量边界：通过；
- batch 单 SKU 失败隔离、安全错误、顺序无关和修正后重跑：通过；
- duplicate target fail fast：通过；
- TV/AC、config/fact/hash 和语义顺序确定性：通过；
- 无数据库、repository、SQLAlchemy、外部 LLM 和 N+1：通过；
- Ruff、format、compileall：通过。

## 9. 状态变化

- 本地数据库写入：无；
- 205 连接、数据库写入和 migration：无；
- G21 quality/diff/stale：未实现；
- 画像 review/publish/current/deprecated：均未执行；
- 部署：无；
- Git 暂存/提交：无。

## 10. 下一 Goal

允许创建 G21，只消费 G20 materialized drafts 和既有 lifecycle/repository read DTO，实现质量评估、stale 判断和版本 diff；不得写 205、部署、发布、切 current 或提交 Git。
