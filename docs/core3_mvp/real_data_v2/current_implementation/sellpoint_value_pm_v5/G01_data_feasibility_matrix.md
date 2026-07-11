# V5-G01 真实数据可行性与覆盖基准

状态：通过，允许进入 G02

采集日期：2026-07-11

环境：`deploy@123.56.42.205` / `catforge_dev`

方式：容器 stdin 执行只读探针，事务首句 `SET TRANSACTION READ ONLY`，结束 rollback

## 1. 结论

V5 的多层反事实、市场合成候选池、同宣称不同用户兑现、自身价格曲线和高/低绩效组合在当前数据上具有足够的候选覆盖，可以进入 G02 方法与 schema 冻结。

但 G01 只证明“候选可召回”和“字段存在”，没有证明每个 SKU 的合成对照已经平衡、增量已经可识别或新战场已经可进入。所有观察性增量、严格价格区间和战场拓展资格仍必须经过后续门禁。

当前最重要的五个事实是：

1. M14 有 84 个历史 target、147 个选择槽，但全部为 `review_required/warning`，当前合格 M14 覆盖为 0；
2. 375/377 个 SKU 有市场池基线，367 个有同尺寸 ±15% 同预算替代，346 个有同品牌同尺寸梯度；
3. 327 个 SKU 可以召回至少 5 个“同尺寸、共享已进入战场、价格 ±30%”的合成 donor 候选，但尚未做平衡诊断；
4. 312 个 SKU 有至少 8 周、2 平台和实际价格变化，可构造自身价格曲线；
5. M11C v0.4 覆盖 348 个，机会战场非空 335 个；机会战场仍属于已进入战场，excluded 的“可召回候选”不等于可拓展。

## 2. requirement -> source -> field -> quality

| 需求 | 来源与字段 | 当前版本/覆盖 | 可用结论 | 限制与门禁 |
| --- | --- | --- | --- | --- |
| 目标市场池、量价位置 | M07 `market_pool_key`、size、price、sales、percentiles | v2 full，377 | 市场池、同预算和量价位置 | 是整机市场表现，不是卖点归因 |
| 自身价格曲线 | M07 周数/平台/price min/max/volatility + clean weekly | 312 强样本 | 观测范围内价格—销量响应 | 促销只可疑似过滤；无库存字段 |
| 同品牌同尺寸梯度 | M07 brand/size/price + M03B tiers | 346 有候选 | 品牌内部版本梯度 | 系列字段质量和其他配置需审计 |
| 参数档位反事实 | M03B dimension/tier/rank | v0.2，377×9；367 有同预算可比 | lower/same/higher 档位召回 | unknown 不得作为基础档；共线需合并 |
| 产品宣称 | M04C claim codes/fact codes | v0.2，328 | 产品在讲什么 | 缺失不等于没有卖点 |
| 用户兑现 | M05C supported/contradicted/unmentioned claim codes | v0.2，348；287 个宣传 SKU 有兑现 | 同宣称不同兑现 | 评论口径必须一致；频次不生成金额 |
| 已进入战场 | M11C primary/secondary/opportunity/user-observed | v0.4，348 | existing battlefield portfolio | 多 rule current，必须精确锁版本 |
| excluded 候选 | M11C summary、param strong、top user voice、战场 taxonomy | 288 有初步召回 | 只可作 expansion candidate recall | 还须尺寸/价格门槛、任务相邻和 donor；不是已可进入 |
| 当前战场空间 | M11D dimension summary | v0.1 | 战场销量、销额和量价空间 | 是语义分配市场空间，不是增量 |
| 本品战场分配 | M11D contribution allocation | v0.1，335 SKU | 本品既有销量的战场分账 | 不同于最新 M11C lineage；不能当新增销量 |
| 采购理由 | M12D published profile/source refs | v0.1，377 | 已发布理由假设和证据边界 | 当前存在旧上游 lineage，须局部 revalidate/block |
| 直接竞品 | M14 run/selection | 84 raw，0 eligible | raw 仅可作为召回线索 | 全部 review required，不可作为权威角色 |
| 市场合成 donor | M07 + M11C + M03B | 327 个目标有 ≥5 broad donors | 进入合成平衡筛选 | broad pool 不等于合格合成对照 |
| 高/低绩效组合 | M07 + M11C + M11D + claim/comment | 335 有市场/战场/分配，312 有强时序 | 观察性 residual archetype | 无库存；促销仅 suspect；不得因果化 |
| 严格组合价格区间 | 上述反事实 + own curve | 字段部分具备 | 仅允许通过独立变化/稳定门禁的 cohort | G01 未发现可直接宣告金额的 target |
| cannibalization/net | 同系列/战场重叠/市场量价 | 只能构造重叠风险 | 风险分级、gross 与 net 分离 | 没有消费者级流向，数量可能不可识别 |

## 3. 覆盖统计与定义

分母均为 377 个 M07 v2 full-window TV 目标，除非另行说明。

| 反事实/数据层 | 覆盖 | G01 定义 | 当前上限 |
| --- | ---: | --- | --- |
| 市场池基线 | 375 | 同 `market_pool_key` 至少 1 个其他 SKU | 整机市场位置 |
| 同预算替代 | 367 | 同尺寸、价格相差不超过 ±15% | 真实选择池位置 |
| 同预算且共享已进入战场 | 332 | 上述条件 + entered battlefield 有交集 | 战场内选择关联候选 |
| 同预算且同主战场 | 311 | 上述条件 + primary battlefield 相同 | 更严格的战场内候选 |
| 战场同预算 peer ≥3 | 315 | 同上，至少 3 个 | pool 比较候选 |
| 战场同预算 peer ≥5 | 284 | 同上，至少 5 个 | 较强 pool 比较候选 |
| 同主战场同预算 peer ≥3/≥5 | 246/193 | primary battlefield 相同 | 严格 pool 候选；不能替代配置平衡 |
| 同品牌同尺寸 | 346 | 至少一个同品牌同尺寸 SKU | 品牌梯度候选 |
| 参数档位可比较 | 367 | 同预算 peer 至少一个共同维度 tier rank | 档位关联候选 |
| 自身价格曲线强样本 | 312 | active week ≥8、platform ≥2、volatility >0 | 整机价格响应候选 |
| 宣传卖点存在 | 328 | M04C v0.2 有 profile/claim | 产品侧主张 |
| 宣传卖点有用户兑现 | 287 | advertised claim 与 supported claim 有交集 | 用户兑现成立候选 |
| 同宣称 peer 未兑现 | 249 | 同预算 peer 宣称相同但未 supported | 宣称兑现反事实 |
| 同宣称 peer 有矛盾 | 263 | 同预算 peer 同宣称且 contradicted | 负向兑现反事实 |
| 合成 donor ≥5 | 327 | 同尺寸、共享 entered、价格 ±30% | 只完成 broad recall；不得输出增量 |

参数梯度 broad pool 中：357 个目标可见 lower、367 可见 same、361 可见 higher，351 同时具备三类。数字高说明可用于候选召回，不代表单个卖点已被隔离。

## 4. 价值战场覆盖与重要修正

- TV 战场 taxonomy：13 个；
- M11C v0.4：348 SKU；
- 辅战场非空：218；
- 机会战场非空：335；
- 平均机会战场：3.3103；
- 平均已进入战场（主/辅/机会/用户观察并集）：5.2557；
- excluded 初步可召回候选：288 SKU。

最后一个数字必须严格命名为“可召回候选”，不能叫“可进入新战场”。G01 的初步规则是：excluded、进入 top user voice、参数 strong、battlefield score ≥0.55。65E7Q 会召回“大屏家庭影院、高配下探、主流家庭性价比”，但 M11C 原因明确提示尺寸/价格门槛不成立。

因此 G02/G05 必须新增 `ExpansionEligibilityGate`：

```text
excluded
  + size/price market gate passes
  + task/group adjacency
  + capability gap reachable
  + real market donor/cohort exists
  + overlap/cannibalization assessed
  -> eligible expansion candidate
```

任一条件失败只能展示 rejected/deferred reason，不能形成新战场机会方案。

## 5. 市场合成与高低绩效可行性

可用字段：尺寸、市场池、价格、销量、销额、周数、平台、价格波动、品牌、参数档位、已进入战场、宣传/兑现、M11D 分配和 promotion suspect。

覆盖：

- 327 个目标有至少 5 个 broad donor；
- 348 个目标有市场 + M11C；
- 335 个目标有市场 + M11C + M11D；
- 312 个目标有较强时序量价；
- inventory 明确 unavailable；
- promotion 只有 suspect flag，不能视为完整促销控制。

结论：可以做透明的加权匹配/平衡与残差绩效原型，但首版只能输出观察性区间和组合参照。G02 必须冻结 overlap、standardized difference、effective sample size、leave-one、placebo 和时间稳定性门槛；失败时降级为市场池描述。

## 6. M11C 与 M11D lineage 不能静默合并

65E7Q 最新 M11C v0.4 的已进入战场为：画质、智能、游戏、主流客厅、护眼。当前 M11D contribution 却把 6,023 台既有销量只分配到画质、游戏、护眼三项：

| M11D 战场 | allocation | 分配销量 |
| --- | ---: | ---: |
| 高端画质升级 | 0.438110 | 2,638.7365 |
| 游戏体育流畅 | 0.292731 | 1,763.1188 |
| 家庭护眼舒适 | 0.269159 | 1,621.1447 |

三项相加正好回到本品 6,023 台，证明它是现有销量分账，不是三项各自新增。它与最新 M11C 角色结构也不完全一致，V5 必须保存 M11D 生成时的 lineage，不能用最新 M11C 名称覆盖旧 allocation 含义。

## 7. 65E7Q 多层反事实可用性

目标：TV00029112 / 海信 65E7Q，65 英寸，均价 5,949.39，销量 6,023，24 周、2 平台；同池价格百分位 96.30%，销量百分位 13.58%。

同预算 ±15% 有 3 个真实替代：

| SKU | 均价 | 销量 | 与本品关系 |
| --- | ---: | ---: | --- |
| 小米 L65MC-SP | 5,852.58 | 3,756 | 同主战场、同画质档的整机对照 |
| 创维 65A7H PRO | 5,637.05 | 5,199 | 同主战场、护眼更高角色的价值组合对照 |
| TCL 65Q9L PRO | 5,521.97 | 4,268 | 同主/辅/机会结构高度重合的量价对照 |

本品另有：51 个同 market-pool SKU、8 个同品牌同尺寸 SKU、9 个 broad synthetic donors；参数梯度同时有 lower/same/higher；同宣称不同兑现可观察高亮、MiniLED、影院、高刷和游戏低延迟等 claim。

这意味着 V5 可以为 65E7Q 提供真实参照亮点，但当前仍不能输出严格金额，原因包括 published lineage conflict、画质 bundle 共线和合成对照尚未通过平衡。

## 8. Gold Set

| Cohort | 样本 | 用途 |
| --- | --- | --- |
| C01 | 65E7Q + 65E5Q + L65MC-SP + K-65XR50 | 多层反事实、lineage、组合共线和金额阻断 |
| C02 | 75E5Q + 75E5Q-PRO | 同品牌同尺寸直接档位候选 |
| C03 | 75R69A-A、75A28F、75E3S-PRO+ | donor-rich 合成池和平衡门禁 |
| C04 | 85S595C ULTRA、75S595C PRO、85VX5Q | 同宣称不同用户兑现 |
| C05 | L55RA-RA、L100MB-SP、75J7K-JN | 单平台导致自身曲线降级 |
| C06 | 65E7Q | 已有机会战场与 excluded 召回同时存在 |
| C07 | TV00025500、TV00025501、L55RA-RA | 无可观察拓展候选的合法空结果 |
| C08 | 32F195C | 负向与正反并存价值保持分离 |

每个 cohort 的源 hash 组合由只读探针确定性生成，见 `G01_cohort_manifest.json`。

## 9. 只读、健康与确定性

- `healthz={"status":"ok"}`；
- `readyz={"status":"ready","database":"ok"}`；
- 每次 Session 的首个业务动作是 `SET TRANSACTION READ ONLY`；
- 未执行 INSERT/UPDATE/DELETE、迁移、上游重跑、发布或部署；
- 完整探针 stdout 连续两次 SHA-256 均为 `d6c0bd60d9c35cef56cfb275c1a0d0d5375cf400b85b22dcd2f39e2bf1f468d6`；
- 业务内容 hash 为 `e74fcfb73d72e149daae048079fb6f34b51fc772134f09fc2355f474a45d785a`；
- cohort lineage manifest hash 为 `ae3ea428f5293a9016e2d88ca6e908ae8c4f842af671953aa7d6a1fa3defb450`。

## 10. G02 准入约束

1. broad pool coverage 与 eligible counterfactual 必须是两个状态；
2. M14 raw 与 eligible 分离，当前不以 M14 为硬依赖；
3. `ExpansionEligibilityGate` 必须包含尺寸/价格市场门槛；
4. M11D 分配绑定自身 lineage，固定 `incremental=false`；
5. market synthetic 必须有平衡、overlap、placebo 和稳定性门禁；
6. high/low archetype 只做 residual 组合参照，不生成单卖点因果；
7. inventory unknown 和 promotion suspect 必须进入限制；
8. strict amount 未通过时为 null；
9. C01-C08 全部进入测试计划和 schema 追溯。
