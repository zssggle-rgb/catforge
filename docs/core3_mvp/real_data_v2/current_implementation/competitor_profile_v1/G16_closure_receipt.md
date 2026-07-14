# 竞品画像 V1 G16 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_value_substitution_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_value_substitution.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_value_substitution.py`。

## 2. 研究过的现有模式

实现前对照了四类已有模式：

1. G03 方法合同 §5、§7.7、§9：F1/F4/F5 证据族、同价值至少两层可比较事实、P3 业务边界；
2. G04 detailed design 的 `EvidenceFamilyAssessment`：保留 family、status、matched code、lineage、evidence 和 confidence 的 typed 边界；
3. `anchor_substitutability.ValueAnchorMatcher`：沿用 M12D core/supporting/weak/risk 分离，弱表达和风险拖累不推高替代证据；
4. M12C claim-value role 常量与 `purchase_pressure_comparison`：沿用 positive/basic/brand/drag/opportunity/sample 角色语义，以及只比较双方独立成立理由的原则。

## 3. 已实现的采购理由事实评估

对每个 M12D 稳定 reason code 保存：

- 双方原始 role；
- strong/supporting/weak/risk/conflict/absent/unknown；
- shared strong、shared limited、different role、单边、conflict；
- generic/table-stake/discriminative/supporting 分类与覆盖率；
- exact evidence refs、独立 lineage keys 和结果 hash。

边界：

- 只允许 exact code 对齐，不做中文相似、字符串相似、LLM 推断或跨 code 猜映射；
- `weak_expression_anchor`/`proposition_anchor` 始终为 weak，不能解释为成交理由成立，也不能解释为“没有理由”；
- `risk_drag_anchor` 始终为风险，不能作为正向替代；
- 同一 code 一方正向、一方风险时标记 conflict/review_required。

## 4. 已实现的用户价值分层证据

每个 M12D/M12C/M05C 语义 code 固定输出五层：

1. F1 M12D 采购理由；
2. F4 M12C 卖点价值角色；
3. F4 M05C 用户兑现；
4. F5 M04C 卖点表达；
5. F5 M03B 参数能力。

每层保存双方 values、positive/supporting/weak/risk/absent/unknown/conflict、matched/different/单边/unknown、证据族、lineage 和 exact evidence。M04C/M03B 只能提供 F5 支撑，不能单独形成强价值替代证据。

M12C 角色处理：

- premium/sales/value-bundle/unique-payment：positive；
- basic/brand/user-need/weak-user-perception：supporting；
- opportunity/high-price-intercept/price-up：weak/opportunity；
- drag：risk；
- sample-insufficient：unknown。

## 5. Evidence status 与业务边界

输出只允许：

- `strong_overlap`：同一项区分性价值至少两层可比较，且至少两个独立证据族成立，其中含 F1 或 F4；
- `limited_overlap`：存在同 code 正向重合，但层数、独立证据族或区分性不足；
- `different_route`：双方各有正向价值，但没有相同稳定 code；
- `conflict`：区分性价值的正向与风险/矛盾证据冲突；
- `unassessable`：候选侧没有实际可消费的语义事实。

同一 lineage 跨模块只计算一次；多层来自同一 lineage 时不能升级为 strong。

无论 evidence status 如何，G16 的 `purchase_choice_conclusion_allowed` 固定为 false，正式关系留给 G18。P3 即使 strong_overlap，也只允许价值研究，明确返回 `value_research_only_purchase_choice_forbidden`。

## 6. 通用性与品类隔离

- taxonomy generic/table-stake 或 serving scope 高覆盖率 value 只 supporting；
- taxonomy 标记 discriminative 但 coverage 缺失时仍只 supporting；
- taxonomy、覆盖率、M12C/M12D role sets 均在 category-specific config version 中冻结；
- TV/AC config category 不一致时 fail closed。

## 7. 验证

- G16 schema/service tests：20 passed；
- G05—G16 schema/migration/repository/lifecycle/input/recall/eligibility/determinism/performance/pair feature/purchase pool/value substitution：171 passed；
- G16 service + schema coverage：93%；
- shared established、同 code 异 role、单边/weak/risk：通过；
- M12C positive/basic/brand/drag/opportunity/sample：通过；
- M05C 支持/矛盾、M04C/M03B supporting：通过；
- generic/table-stake/high coverage/coverage unknown：通过；
- P0/P1/P3/unknown 与 P3 研究边界：通过；
- sparse/unassessable、review/conflict：通过；
- 同 lineage 去重：通过；
- TV/AC、候选守恒、输入顺序、config hash 变化：通过；
- 无数据库、repository、SQLAlchemy、外部 LLM 和正式关系生成：通过；
- Ruff、format check、compileall：通过。

默认 4 个 TV candidate 的事实烟测结果为 limited/P0、limited/P3、limited/P1、unassessable/unknown；默认数据不会因不同 code 的理由与价值被强行合并成 strong。

## 8. 状态变化

- 本地数据库写入：无；
- 205 连接、数据库写入和 migration：无；
- 画像 materialize、review/publish/current/deprecated：均未执行；
- G17 量价压力、G18 七类正式关系、G19 重点选择：均未实现；
- 部署：无；
- Git 暂存/提交：无。

## 9. 下一 Goal

允许创建 G17，只基于 G14 描述性 M07 facts 与 G15/G16 已保存判断实现量价压力方向；不得把市场关联写成因果销量、WTP 或降价必然增量，不得实现七类正式关系、重点选择、画像持久化、205 写入、部署或 Git 提交。
