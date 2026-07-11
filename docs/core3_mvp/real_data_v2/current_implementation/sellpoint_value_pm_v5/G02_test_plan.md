# V5-G02 测试计划

## 1. 测试层次

| 层 | 目标 | 外部依赖 |
| --- | --- | --- |
| schema | extra forbid、枚举、null/unknown、hash | 无 |
| pure unit | resolver、balance、archetype、portfolio、分账、亮点 | 无 |
| synthetic data | 已知方向、失衡、placebo、稳定性、共线 | 固定种子，无 LLM |
| fixture | G01 C01-C08 source-hash replay | 无网络 |
| repository integration | 批量 context、query count、lineage | SQLite/mock/Postgres fixture |
| answer integration | JSON/短答/Markdown/卡片同 DTO | 飞书 mock |
| regression | V2/V4/M11C/M11D/M12D/M12C | 无外部 LLM |
| 205 | 默认关闭真实双跑、飞书回读、回滚 | 仅 G08 |

## 2. Schema tests

- missing 不能被 false/0 替代；
- M11D allocation 必须 `incremental=false`；
- Synthetic/Archetype `causal_claim=false`；
- BundlePriceInterval `psychological_max_price=false`；
- net 非空时 gross 与 cannibalization 必须非空；
- expand option 只能 current membership=excluded；
- strengthen option 不能 membership=excluded；
- highlights 长度 0..3，空结果合法；
- PM DTO 不接受内部枚举直接作为中文文本。

## 3. Resolver tests

- M14 eligible=0 时 same-budget/brand/tier/claim/own-curve/synthetic 仍召回；
- provenance 不伪装为 M14；
- unknown tier 不作 lower；
- direct role 由 tier/comparability 判定，不接受 slot 声明覆盖；
- 候选稳定排序/hash；
- broad recall 与 eligible 状态分离；
- 65E7Q 返回 3 个同预算 peer、品牌梯度、三档 param role 和 9 个 broad donors；
- 无候选时正确 empty/degradation。

## 4. Synthetic tests

### Positive

固定合成数据：5+ donors、已知 +20 sales/week effect、良好 overlap；检查方向恢复、区间覆盖和确定性。

### Gates

- donor <5；
- effective donors <3；
- max weight >0.5；
- after-SMD >0.2；
- category proportion gap >0.1；
- target outside price support；
- only one platform/less than 8 weeks；
- promotion-only overlap；
- unknown base tier；
- leave-one sign consistency <0.75；
- placebo percentile <0.8；
- interval sign flips；
- row cap >20k。

所有失败都必须不输出观察性 gross；placebo 单独失败允许展示差异但禁止 highlight。

## 5. Archetype tests

- out-of-fold baseline 不读验证 fold 结果；
- price/size/brand/week/platform 控制字段齐全；
- high/low 每组 <10 时不生成原型；
- 时间稳定性 <0.7 -> unstable；
- prevalence diff <15pp 不进入差异；
- 完全共线成员合并 bundle；
- 同一输入顺序打乱结果 hash 不变；
- 不生成单项金额/因果词。

## 6. Battlefield tests

- primary/secondary/opportunity/user-observed 全为 existing；
- role cap 导致 opportunity -> portfolio priority；
- 65E7Q eye-care 不作为新战场；
- 65E7Q large-screen cinema immutable size gate fail -> rejected；
- excluded + mutable capability gap + donors + adjacency -> eligible；
- excluded 但 donor=0 -> deferred/rejected；
- no expansion candidate -> 合法空结果；
- market space 不进入 net increment；
- M11D/M11C mismatch 保留旧 allocation lineage。

## 7. 分账与金额 tests

- price strong/volume weak 分开；
- price weak/volume strong 分开；
- allocation sums to current total but remains non-incremental；
- synthetic gross available, cannibalization unknown -> net null；
- cannibalization range available -> interval arithmetic direction correct；
- gross/cannibalization inconsistent -> blocked；
- V4 strict amount gates 全通过才有 interval；
- synthetic/archetype 不能回填 strict amount；
- M12C legacy amount never imported。

## 8. PM language tests

禁止主输出出现：

- WTP、价值棒、因果提升、必然增加销量；
- M03B/M11C/M11D/M12D、SQL、evidence ID、英文 enum；
- “机会战场尚未进入”；
- “M11D 战场贡献新增销量”；
- “高价=高端价值成立”；
- 空证据时的通用 Top 3 或工作清单。

必须检查：亮点说明比较对象，价格/销量分列，市场合成标观察性，existing/expansion 双栏，金额为空有边界说明。

## 9. C01-C08 fixture map

| Cohort | 核心断言 |
| --- | --- |
| C01 65E7Q | fallback 多层可用；lineage/共线阻断金额；真实参照不为空 |
| C02 direct tier | brand-size ladder 和 direct tier 正确；不自动金额 |
| C03 donor-rich | broad -> balance；positive/failed 两组配置 |
| C04 same claim | supported/unmentioned/contradicted 三态正确 |
| C05 weak own curve | 单平台不输出自身曲线 |
| C06 battlefield | existing 与 excluded 同时存在且不混淆 |
| C07 no expansion | 空 expansion 不强填 |
| C08 negative/mixed | negative、mixed、fact conflict 分离 |

## 10. 覆盖和性能门禁

- V5 新代码 line coverage ≥90%；
- schema/state/amount/expansion 核心分支 100%；
- related test 全通过；
- query count ≤30；
- 10k rows peak ≤80MB；
- 20k cap 正确 degraded；
- single SKU P95 ≤3s；
- full JSON 双跑一致；
- 默认 flag off 时 SQL=0。

## 11. G03-G08 分配

- G03：schema/resolver/unit/fixture；
- G04：synthetic/archetype/synthetic-data/performance；
- G05：battlefield state/fixture；
- G06：分账、strict amount、cannibalization；
- G07：DTO/renderer/CLI/cross-carrier；
- G08：全回归、覆盖、205 real replay、rollback。
