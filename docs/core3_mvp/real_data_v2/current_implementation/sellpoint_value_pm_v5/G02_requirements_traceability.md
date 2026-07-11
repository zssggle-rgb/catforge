# V5-G02 需求追溯矩阵

| 需求 | Schema | 方法 | 测试 | Goal |
| --- | --- | --- | --- | --- |
| F01 权威上下文 | V5Context/SourceAuthority | V4 authority + hashes | lineage/multi-current | G03 |
| F02 上游只读复用 | V5Context | V4 adapters | query/write boundary | G03/G08 |
| F03 用户价值—组合 | ValueAccountRow/SellpointBundle | V4 linkage reuse | generic comment/AI mismatch | G07 |
| F04 价值与量化分开 | ValueStatus + independent realization models | parallel states | value exists/amount null | G06/G07 |
| F05 多层反事实 | CounterfactualSet/Candidate | resolver | M14=0/fallback/order | G03 |
| F06 pool/ladder/tier/claim/curve | Candidate methods | recall v1 | coverage/unknown/weak curve | G03 |
| F07 synthetic gates | SyntheticControlResult/Diagnostics | synthetic v1 | balance/placebo/leave-one | G04 |
| F08 high/low archetype | PerformanceArchetype | residual v1 | OOF/stability/prevalence | G04 |
| F09 量价分账 | Price/Volume/Allocation/Increment/BundlePrice | parallel accounting | price-vs-volume/net null | G06 |
| F10 战场组合 | BattlefieldOption/ExpansionEligibility | portfolio state machine | existing/excluded/size gate | G05 |
| F11 真实亮点 | ValueHighlight/DecisionSummary | highlight gate/rank | empty highlight/generic ban | G07 |
| F12 PM outputs | Report DTO | single DTO renderers | cross-carrier/hash/language | G07/G08 |
| F13 审计 | refs/config/input/result hash | canonical hashing | reorder/determinism | G03-G08 |
| F14 默认关闭 | explicit entry contract | pre-query flag | no flag SQL=0 | G07/G08 |
| 市场基线 | SyntheticControlResult | weighted balance | C03 | G04 |
| 高低组合 | PerformanceArchetype | OOF residual | C03/C04 | G04 |
| opportunity 已进入 | BattlefieldMembership | existing state | C06 | G05 |
| true new expansion | ExpansionEligibility | immutable/mutable gap gate | C06/C07 | G05 |
| M11D 非增量 | BattlefieldAllocation | source-lineage allocation | C01 | G06 |
| gross/cannibalization/net | IncrementDecomposition | interval accounting | unknown/available/inconsistent | G06 |
| 严格金额 | BundlePriceInterval | V4 Q5 gates only | full gate/fail/null | G06 |
| 无购买前数据 | no pre-purchase model | not implemented | banned phrase | G07 |
| 无成本利润 | no cost/profit schema | not implemented | field absence | G02/G07 |

所有需求均有 schema、方法、测试和执行 Goal；未发现未归属项。
