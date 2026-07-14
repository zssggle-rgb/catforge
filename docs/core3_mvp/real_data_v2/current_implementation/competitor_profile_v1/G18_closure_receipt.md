# 竞品画像 V1 G18 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_relation_evaluation_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_relation_evaluation.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_relation_evaluation.py`。

## 2. 研究过的现有模式

实现和收尾复核对照了三类以上既有模式：

1. G03 方法合同 §5、§7—§9、§12：五个证据族、七类关系必要门槛、问题级可用性、置信度和 review 边界；
2. G04 `RelationAssessment`、`QuestionEligibility` 与 detailed design §5.7—§5.8：沿用 typed 状态、逐 gate 结果、业务边界和稳定 hash；
3. G14—G17 pair feature、purchase pool、value substitution、price-volume pressure：严格消费已完成 DTO，不重复读取数据库或重新生成 M12C/M12D；
4. G10—G13 候选守恒和确定性模式：全量保留候选、稳定 SKU 顺序、输入/config/hash 链一致，无 TopN 截断和 per-candidate query。

## 3. 七类关系

每个 target×candidate 固定完整输出七条独立关系：

- `direct_substitute`；
- `same_budget_alternative`；
- `downtrade_diversion`；
- `uptrade_alternative`；
- `same_brand_ladder`；
- `scenario_substitute`；
- `same_value_substitute`。

每条关系分别保存 `passed`、`limited`、`failed`、`unassessable` 或 `review_required`，逐 gate 的 known/pass/reason、支持证据族、exact evidence refs、business effect、limitations、eligible questions 和 result hash。必要事实明确失败与事实缺失严格分开；上游冲突传播为 review，不把 unknown 写成“不成立”。

## 4. 五个证据族和置信度

- F1—F4 只有 `discriminative` 且 lineage 独立时才计入正式证据族；
- 同一 lineage 跨模块映射只计一次；
- F5 只作为能力/表达支撑，不能独立成立正式关系；
- weak expression 不当作 absent，直接替代最高为 limited；
- 三个及以上独立族且含 F1/F4 为 high；两个独立族为 medium；只有一个独立族但其他门槛通过时进入 relation review，不自动驱动正式结论；
- generic、table-stake、高覆盖或覆盖未知价值不能冒充区分性证据。

## 5. 八类业务问题可用性

每个 pair 固定输出：

- `purchase_choice`；
- `price_volume_pressure`；
- `value_substitution`；
- `configuration_follow`；
- `same_brand_portfolio_role`；
- `scenario_solution`；
- `price_ladder_defense`；
- `key_competitor_selection`。

每个问题独立保存 `eligible`、`limited` 或 `unavailable`、可用关系、required/available evidence families、missing inputs、中文原因和业务边界。P3 同价值只开放价值研究，不开放购买二选一。配置跟进必须同时存在正式关系、F5 差异和 F1/F2/F4 用户价值证据；不能因竞品多一个功能就自动要求跟进。

## 6. 量价和业务边界

- 升档/降档 8% 门槛按包含边界执行；
- 15% 强价格差和 1.25 倍周均量只增强降档压力标记，不替代关系门槛；
- 升档只要求有效市场承接，不额外要求销量高于目标；
- same budget 和 up/down 关系可并存，由版本化 primary priority 选择主关系，不做总分兜底；
- 全部 pair 固定 `causal_claim=false`、`wtp_claim=false`、`price_change_sales_increment_claim=false`；
- G18 不执行 0—3 重点竞品选择，`selected=false`、`selection_status=not_evaluated`。

## 7. 候选状态和确定性

- 候选可保留多条 passed/limited 关系；
- primary relation 按配置化优先级和已成立状态确定；
- `eligible`、`limited`、`review_required`、`blocked`、`recalled_only`、`reference_only` 分开；
- 全部 G17 candidate 一对一守恒，TV/AC 隔离；
- 语义输入顺序变化不改变 input fingerprint/result hash；事实或 config 变化会改变 hash；
- schema 强制七关系、五证据族、八问题完整覆盖。

## 8. 验证

- G18 schema/service tests：20 passed；
- G05—G18 全链：208 passed；
- G18 service + schema coverage：93%；
- 七类关系 passed/limited/failed/unassessable/review：通过；
- P0/P1/P2/P3 与 purchase-choice 边界：通过；
- weak expression、risk/conflict、generic、F5-only：通过；
- 同 lineage 去重与 F5 不计独立族：通过；
- 同品牌非自动通过和单证据低置信复核：通过；
- 升降档 ±8%、强压力 15%/1.25 边界：通过；
- 八类问题、primary relation、candidate status：通过；
- TV/AC、候选守恒、输入顺序、事实/config/hash 变化：通过；
- 无数据库、repository、SQLAlchemy、外部 LLM、重点选择和 TopN：通过；
- Ruff、format、compileall：通过。

## 9. 状态变化

- 本地数据库写入：无；
- 205 连接、数据库写入和 migration：无；
- 画像 materialize、review/publish/current/deprecated：均未执行；
- G19 重点竞品选择、画像持久化和报告消费：均未实现；
- 部署：无；
- Git 暂存/提交：无。

## 10. 下一 Goal

允许创建 G19，只消费 G18 完整候选、七类关系和八类 question eligibility，实现按独立决策主题选择 0—3 款重点竞品及未入选解释。不得机械 TopN、不得强补三款、不得丢弃完整候选、不得实现画像持久化、205 写入、部署或 Git 提交。
