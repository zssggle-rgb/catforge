# G02 V4 需求追溯矩阵

## 1. 功能需求

| 需求 | 设计章节 | Typed contract | 实施 Goal | 必测场景 |
| --- | --- | --- | --- | --- |
| F01 目标和版本上下文 | 5、6 | `SellpointValueV4Context`、`SourceAuthority` | G03 | SKU/型号、latest/历史、多 current、版本冲突 |
| F02 价值战场和市场空间 | 3、7、14 | `ReasonValueBundleLink.battlefield_*` | G03/G04 | M11C/M11D 缺失、M11D 解释性分配边界 |
| F03 采购理由 | 6、7 | `PurchaseReasonSnapshot` | G03/G04 | published、weak-only、stale lineage、missing |
| F04 用户实际价值 | 7 | `ReasonValueBundleLink.realized_value_*` | G04 | 购后体验、正负向、泛化不可归因、无评论 |
| F05 卖点组合 | 8 | `SellpointBundle`、`BundleMember` | G04 | 组合去重、档位、unknown、共线合并 |
| F06 三类反事实 | 9 | `ComparabilityAssessment` | G05 | base/same/stretch、M14/fallback/M12C/family provenance |
| F07 市场分析单元 | 10 | `MarketCellRow` | G03/G05 | 周×平台、促销疑似、库存 unavailable、异常价、零销量 |
| F08 相对体验增量 | 11 | `QuantificationResult.relative_experience` | G06 | 口径可比/不可比、base vs same-value |
| F09 选择贡献 | 12.1 | `ChoiceAssociation` | G06 | 同价、近同价、价差空洞、不外推、方向不稳 |
| F10 市场隐含 WTP | 12.2-12.4 | `MarketImpliedWtp` | G06 | 两个独立 A 级 base 且跨两个 model family、crossing、敏感性、同价值-only、共线、版本冲突 |
| F11 价值与量化分离 | 7.4、11 | `ValueStatus` + `QuantificationLevel` + role + monetization | G04/G06 | 价值成立但 WTP null、价格承接但单项不可归因 |
| F12 产品经理结果 | 14 | `ProductValueStructureRow`、report | G07 | 一行一个战场+采购理由、下钻、跨载体一致 |
| F13 不生成工作清单 | 14、15、18 | output invariant | G07 | 无增减配/涨降价/研究清单 |

## 2. 量化与降级需求

| 需求边界 | 状态/字段 | 预期 |
| --- | --- | --- |
| 权威画像冲突 | `LineageStatus.stale_conflict` | 受影响 relation 局部阻断 |
| M11C/M11D/M12D 缺失 | source availability | 不重建；完整结构降级 |
| weak expression | purchase reason source status | 不升级采购理由或支付价值 |
| 无 base value | exclusion `base_counterfactual_missing` | Q5 null |
| 只有一个 A 级 pair 或单一 model family | pair/family gate | 封顶 Q4，WTP null |
| 只有 same value | `same_value_only` | 封顶 Q3/Q4 |
| 完全共线 | bundle collinearity | 合并组合；单项 WTP null |
| 无价格变化/重叠 | choice/WTP exclusion | 截面量价或 null |
| 促销污染 | `promotion_suspect` | 主分析排除、敏感性单列 |
| 库存 | `inventory_status=unavailable` | 明示限制，不声称控制 |
| 价格方向异常 | WTP unstable | amount null |
| 体验不可比 | relative experience null | 不输出强弱 |
| M12C 金额存在 | invariant | 不进入 V4 WTP |

## 3. 非功能需求

| 非功能要求 | 设计/合同 | 验证 |
| --- | --- | --- |
| 首版只读 | 4、18 | repository source scan + 205 shadow write-count=0 |
| 无外部 LLM | 4、18 | deterministic unit tests，无网络 mock |
| category/project/version/batch/audit | context/report/source authority | schema tests |
| 同输入同 hash | 17 | repeat-run fixture |
| 无 N+1 | 16 | query counter integration test |
| manifest/config versioned | 5、17 | JSON snapshot/hash test |
| 跨载体一致 | 14 | one DTO snapshot test |
| V2 不受影响 | 4、18 | existing V2 regression |
| feature flag off | 18 | CLI/router tests |

## 4. 固定验收样本

| 样本 | 合同预期 | 测试层 |
| --- | --- | --- |
| 65E7Q | Q3、WTP null、stale conflict、same-value only price pair | fixture replay + integration |
| C01 可识别候选 | 进入 Q5 gate，但 G01 不预填金额 | unit/integration |
| C02 只有同价值 | 不到 Q5 | unit |
| C03 完全共线 | bundle-only | unit |
| C04 单周 | no price sensitivity | unit |
| C05 版本冲突 | affected relation blocked | integration |
| synthetic identified | recover known crossing interval | deterministic unit |
| synthetic unstable | direction flips -> WTP null | deterministic unit |

## 5. 实施文件映射

| 文件 | 单一职责 | 首次 Goal |
| --- | --- | --- |
| `claim_value_pm_v4_schemas.py` | typed contracts only | G03 |
| `analyst_repository.py` | batch read and authority context | G03 |
| `atomic_handlers.py` | V4 evidence atom | G03 |
| `claim_value_pm_v4_service.py` | linkage/counterfactual/quantification pure functions | G04-G06 |
| `claim_value_pm_v4_answer.py` | business DTO render/delivery | G07 |
| `sop_orchestrators.py` | thin orchestration | G07 |
| `catforge_analyst.py` | explicit command/flag | G07 |

若实现需要第 4 个新增运行文件，必须先证明无法保持单一职责；若新增服务超过 2 个，停止并重审。
