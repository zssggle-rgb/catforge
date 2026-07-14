# 竞品画像 V1 G19 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_key_competitor_selection_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_key_competitor_selection.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_key_competitor_selection.py`。

## 2. 研究过的现有模式

实现前对照了三类以上现有模式：

1. G03 方法合同 §13、A13—A15 与需求 §10：0—3 款、按独立决策信息选择、不补位、不机械 TopN；
2. G04 `DecisionTopic`、`KeyCompetitorSelectionDraft` 和 detailed design §5.9：沿用连续 rank、主/辅关系、覆盖主题、独立信息理由和 exact evidence；
3. `competitor_profile_schemas`/`lifecycle`：沿用 selected pair 与 selection row 一致、rank 连续、最多三款和候选全量守恒；
4. 既有 candidate manifest 的确定性排序与“不改变候选宇宙”测试：选择只增加标签和解释，不截断完整候选。

## 3. 最小决策集合

选择顺序固定为：

1. `purchase_choice`：谁最可能与本品进入同一购买选择；
2. `price_scale_pressure`：谁在同预算、下探或上探形成价格与规模压力；
3. `portfolio_or_scenario`：谁揭示同品牌产品线重叠或另一种场景方案；
4. `value_route`：谁证明本品价值可被替代或另一条路线更值得关注。

每个候选可以覆盖多个主题，但只占一个重点位置。后续候选必须带来尚未覆盖的主题，或在同一主题上形成明确更强、证据更完整的压力。最多选择三款；只有一款或两款时保留真实数量，不补足。

## 4. 非总分的逐级比较

主题内只做确定性的逐级比较：

1. relation passed 优先于 limited；
2. high 优先于 medium；
3. 独立证据族更多者优先；
4. F1/F4 更完整者优先；
5. 对应量价压力更明确者优先；
6. limitations 更少者优先；
7. 仍相同时按规范化 SKU code 稳定排序。

实现中没有跨主题加权分、总分、TopN 或第三名补位逻辑。价格主题允许已入选购买对手之外，再保留一款形成明显更强规模压力的候选；相同主题且证据更弱的候选只保存未入选解释。

## 5. 入选和未入选结果

每条入选记录保存：

- 连续 selection rank；
- primary/covered decision topics；
- primary/auxiliary relations；
- 为什么改变产品决策；
- 为什么同主题其他候选不优先；
- relation business effects、市场压力清晰度和可用证据族；
- confidence、exact evidence refs 和稳定 hash。

G18 全部候选一对一保存 selection decision。未入选原因明确区分：

- `ineligible_status`；
- `review_required`；
- `question_unavailable`；
- `confidence_insufficient`；
- `no_verified_decision_topic`；
- `topic_already_covered`；
- `weaker_duplicate_pressure`；
- `specialized_question_only`；
- `selection_capacity_reached`。

不使用 `rank > 3` 代替业务原因。

## 6. 0 款结果状态

- `no_priority_competitor`：数据已可判断，但没有候选形成需要占据重点位置的独立决策信息；
- `insufficient_evidence`：必要关系事实仍有 unassessable；
- `review_required`：关键候选证据或状态需要复核；
- `selected`：实际入选 1—3 款。

高销量 reference 若没有正式关系仍不会入选。limited 候选只有在 `key_competitor_selection` 和对应决策主题均明确 eligible 时才可入选。

## 7. Schema、守恒与确定性

- schema 强制四个主题完整评估；
- selections 为 0—3 且 rank 从 1 连续；
- selected pair decisions 与 selection rows 严格一致；
- covered/uncovered topics 完整分区且遵守配置顺序；
- 保留 G18 全部候选，不改 relation bundle；
- 输入顺序不改变结果；G18 事实 hash 或 config 变化会改变 G19 input/result hash；
- TV/AC 隔离，配置跨品类时 fail closed；
- 纯内存处理，无数据库、repository、外部 LLM 或 per-candidate query。

## 8. 验证

- G19 schema/service tests：13 passed；
- G05—G19 全链：221 passed；
- G19 service + schema coverage：92%；
- 0/1/2/3 款及连续 rank：通过；
- A13 高销量 reference 不入选：通过；
- A14 只一款不补足：通过；
- A15 同主题只保留证据更强候选：通过；
- 同候选覆盖多主题只占一席：通过；
- 同主题更强价格压力可增加独立席位：通过；
- passed/limited、high/medium、证据族、F1/F4、压力清晰度、SKU tie-break：通过；
- 八类要求内未入选原因均由实际输出覆盖：通过；
- no-priority/insufficient/review 三种 0 款状态：通过；
- limited 候选双重 question eligibility：通过；
- TV/AC、候选守恒、顺序/config/事实/hash：通过；
- 无总分、TopN、数据库、repository、SQLAlchemy 和外部 LLM：通过；
- Ruff、format、compileall：通过。

## 9. 状态变化

- 本地数据库写入：无；
- 205 连接、数据库写入和 migration：无；
- G20 SKU 竞争决策画像 materializer 和持久化：未实现；
- 画像 review/publish/current/deprecated：均未执行；
- 部署：无；
- Git 暂存/提交：无。

## 10. 下一 Goal

允许创建 G20，只消费 G09—G19 的已完成 typed 产物，实现单 SKU/批量 SKU 竞争决策画像 materializer、失败隔离、候选/关系/选择完整装配和结果 hash。不得写入 205、部署、切换发布状态或提交 Git。
