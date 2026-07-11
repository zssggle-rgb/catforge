# 用户卖点价值分析 V4 详细设计

状态：G02 冻结候选

日期：2026-07-11

前置需求：`../sop_requirements/CATFORGE_ANALYST_sellpoint_value_pm_v4_requirements.md`

真实数据边界：`../current_implementation/sellpoint_value_pm_v4/G01_data_feasibility_matrix.md`

## 1. 设计结论

V4 是 analyst 层的只读分析能力。它不生产新的价值战场、市场空间或采购理由，而是把已发布资产组织成产品经理可读的一笔“用户价值账”：

```text
价值战场和市场空间
  -> 已发布采购理由假设
  -> 用户购后实际获得的价值
  -> 共同支撑该价值的卖点组合
  -> 基础价值 / 同价值 / 上探反事实
  -> 当前选择和价格兑现层级
```

首版不采用多 SKU 结构需求模型。当前缺少完整促销、库存、外生工具变量和消费者级选择数据，不能可靠处理价格内生性和未观测产品质量。市场隐含 WTP 只允许采用高可比匹配反事实：当其他主要差异受控、价值组合独立变化、共同周×平台价格和选择有足够变化时，用等选择概率对应的价格差估计组合的历史市场承接区间。

这不是用户心理最高价，也不是建议售价。

## 2. What already exists

| 子问题 | 现有实现 | V4 决策 |
| --- | --- | --- |
| SKU/型号解析 | analyst repository + CLI | 直接复用 |
| M03B-M11D 事实简报 | `sku_fact_brief()` | 复用，但增加显式版本 lineages |
| 评论严格归因 | V2 `claim_value_pm_service.py` | 复用纯函数和 value unit 注册，不复制正则 |
| 周×平台价格曲线 | V2 pair curve/PAVA/不外推 | 复用为整机选择关联基础 |
| M12D 已发布读取 | `RepositoryPurchaseReasonProfileReader` | 直接复用，不调用 runner |
| M12D 三轴输入质量 | availability/usability/severity/scope | 复用语义，不重新发明全局 partial |
| M12/M14 竞品候选和角色 | candidate pool / selection run | 复用候选 ID、角色、evidence，不消费结论文案 |
| M12C 可比池和参数档位 | context pool + param tier | 只读复用中间事实，不消费旧金额 |
| Markdown/飞书发布 | `claim_value_pm_answer.py` 发布基础设施 | 复用发布器，新增 V4 DTO renderer |

V4 新增的只有两层：

1. 关系层：采购理由 -> 用户价值 -> 卖点组合；
2. 识别层：反事实角色、可比性、选择贡献、市场隐含 WTP 门禁。

## 3. 总体数据流

```text
Explicit V4 CLI / feature-flagged NL route
                  |
                  v
        Target resolution (reuse)
                  |
                  v
   Authority + lineage resolver [G03]
   ├─ M03B/M04C/M05C/M07
   ├─ M09C/M10C/M11C/M11D
   ├─ published M12D + source refs
   ├─ M14 or explicit fallback provenance
   └─ M12C pool/tier facts only
                  |
                  v
        Versioned V4 Context
                  |
       +----------+----------+
       |                     |
       v                     v
 Reason/value/bundle      Market cells
 linkage [G04]            week × platform
       |                     |
       +----------+----------+
                  v
 Counterfactual candidates [G05]
 base / same-value / stretch
                  |
                  v
 Identification gate [G06]
 ├─ relative experience
 ├─ same-price choice association
 ├─ whole-product price acceptance
 └─ matched market-implied WTP
                  |
                  v
 Business DTO [G07]
 JSON / short answer / Markdown / Feishu
```

## 4. 运行模块和文件预算

新增运行文件不超过 3 个：

1. `analyst/claim_value_pm_v4_schemas.py`：全部 V4 typed contracts；
2. `analyst/claim_value_pm_v4_service.py`：关系、反事实、识别和 DTO 纯函数；
3. `analyst/claim_value_pm_v4_answer.py`：短答、Markdown、卡片/飞书渲染。

修改既有集成点：

- `analyst_repository.py`：批量只读 V4 context；
- `atomic_handlers.py`：V4 evidence atom；
- `sop_orchestrators.py`：薄编排；
- `catforge_analyst.py` 和必要的 CLI 注册；
- 测试文件。

不新增 ORM entity、Alembic migration、队列、缓存服务或外部模型调用。

## 5. 顶层输入合同

`SellpointValueV4Context` 必须 `extra=forbid`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | literal | `sellpoint_value_v4_context_v1` |
| `project_id/category_code` | string | 分类隔离 |
| `requested_batch_id` | string | 用户输入的 latest/历史批次 |
| `serving_batch_ids` | list[string] | 实际 serving scope |
| `market_window` | enum | full/recent/latest |
| `target` | `SkuIdentity` | 目标 SKU |
| `authority_manifest` | list[`SourceAuthority`] | 每个模块选中版本、batch、hash、质量 |
| `lineage_gate` | `LineageGate` | 跨模块线谱状态 |
| `target_snapshot` | `SkuEvidenceSnapshot` | 目标事实/评论/市场/语义 |
| `purchase_reason_profile` | `PurchaseReasonSnapshot` | 已发布 M12D，不重算 |
| `candidate_snapshots` | list[`SkuEvidenceSnapshot`] | 候选事实和市场 |
| `market_cells` | list[`MarketCellRow`] | 目标与候选批量周×平台行 |
| `m12c_pool_tiers` | list[`ComparablePoolTierFact`] | 只含池/档位/样本状态 |
| `evidence_refs` | list[`EvidenceRef`] | 审计引用 |
| `input_hash` | sha256 | canonical context hash |

所有 unknown 保持 `null + availability=missing`，禁止转为 `false/0/空数组代表无`。

## 6. 权威版本与线谱闸门

### 6.1 SourceAuthority

每个来源保存：

- module code；
- table name；
- selected rule/schema/taxonomy version；
- selected batch IDs；
- release ID（如有）；
- row count；
- source/result hash；
- authority mode：`published_release/configured_rule/fallback`；
- availability/usability；
- selected reason；
- warnings。

### 6.2 解析顺序

```text
published artifact exists?
  ├─ yes -> lock published release + its source refs
  └─ no  -> configured allowed rule version
              |
              v
       exact rule-version filter
              |
              v
       serving-scope batch filter
              |
              v
       duplicate/current resolution
```

禁止只使用 `is_current=true`，因为 G01 已证明多个 rule version 可同时 current。

### 6.3 双时间面

M12D 是已发布采购理由假设，最新 M03B/M04C/M05C/M07/M11C/M12C 是当前验证事实。两者不静默合并：

- `published_lineage`：M12D 当时实际引用的 source refs；
- `current_validation_lineage`：本次 V4 选中的最新允许版本；
- `lineage_status`：`aligned/stale_revalidated/stale_conflict/unresolved`。

处理：

| 状态 | 处理 |
| --- | --- |
| aligned | 正常消费 M12D role/strength |
| stale_revalidated | M12D 仅提供理由名称和族；强度由当前证据重新验证，不沿用旧分数 |
| stale_conflict | 受影响理由/组合局部阻断；显示版本冲突 |
| unresolved | 完整产品价值结构 blocked |

65E7Q 当前属于 `stale_conflict`：发布 M12D 写 param conflict，最新 M03B v0.2 conflict_count=0。V4 不选择对自己有利的版本，而是显示冲突并阻断价格归因。

## 7. 采购理由 -> 用户价值 -> 卖点组合

### 7.1 三个对象

`PurchaseReasonNode`：用户为什么可能选择该 SKU 的已发布假设。

`RealizedUserValue`：购后评论中实际出现的场景结果、正向结果和风险，不代表购买前心智。

`SellpointBundle`：共同产生同一用户结果的参数事实和卖点事实集合，不是一条孤立宣传语。

### 7.2 关系对象

`ReasonValueBundleLink` 一行对应一个战场下的一个采购理由：

- battlefield code/name/market space；
- purchase reason code/name/family/role/source status；
- realized value code/name/scenario/outcome；
- bundle code/name/member capabilities；
- link status：`supported/partial/conflicted/insufficient`；
- evidence domains；
- limitation codes；
- source refs；
- relation hash。

### 7.3 去重和归属

1. 主键：`battlefield_code + purchase_reason_code`；
2. 同一理由命中多个相近用户结果时，按 value family 合并；
3. 同一卖点可支撑多个理由，但证据只在对应 relation 记录一次；
4. 同一评论句在一个 value bundle 中只计一次；
5. 泛化评论只能支撑上层体验组合，不能拆给具体技术；
6. M12D 角色不等于 V4 产品角色，V4 产品角色还要看反事实和市场兑现。

### 7.4 价值成立与可量化分离

每个 relation 独立保存：

- `value_status`：established/partial/not_observed/conflicted；
- `quantification_level`：见第 11 节；
- `product_role`：核心差异、基础门槛、辅助成交、客户获得、配置支撑、价格压力、不可判断；
- `monetization_status`：not_measured/choice_supported/whole_product_only/partially_captured/fully_captured/over_captured/unidentifiable。

不得压成单一总分。

## 8. 卖点组合和值强度

### 8.1 BundleDefinition

首版复用 V2 TV value unit registry，并增加：

- bundle family；
- linked M12D anchor families；
- required/optional param codes；
- linked claim codes；
- comment subdimensions；
- business tier rules；
- independently identifiable flag；
- forbidden single-claim attribution rules。

### 8.2 业务档位

档位来自 M12C 中间 pool/tier 或确定性参数阈值：

- `unknown`；
- `base`；
- `enhanced`；
- `premium`；
- `flagship`。

原始数值不直接当档位。同一业务档内 288Hz 与 300Hz 不形成价值强度差。

### 8.3 共线合并

在候选 cohort 内，如果两个能力：

- presence 完全一致；或
- tier 完全一致；或
- 任一能力只有一个非空档位；

则标记 `perfect_collinearity`，合并为 bundle，不输出单项选择贡献/WTP。

## 9. 三类反事实

### 9.1 CounterfactualRole

| 角色 | 回答的问题 | 最低要求 |
| --- | --- | --- |
| base_value | 没有/较低该价值时表现如何 | 同尺寸形态、同战场、较低价值档位、共同周平台 |
| same_value | 都具备该价值时本品是否兑现更好 | 同尺寸、同战场、同价值档位 |
| stretch_benchmark | 更高价值档位的市场上限和差距 | 同战场、更高档位、真实在售 |

### 9.2 候选来源优先级

1. M14 合格 selection；
2. 已有 competitor-set fallback，只复用 candidate ID/role/provenance；
3. M12C pool member；
4. 同品牌同系列/同尺寸高可比搜索。

来源只是召回，不决定反事实角色。角色由 V4 可比性纯函数判定。

### 9.3 ComparabilityAssessment

逐候选输出：

- exact size/product form；
- battlefield/reason overlap；
- base/same/stretch value tier relation；
- common week/platform cells；
- observed price overlap；
- brand/series relation；
- other bundle difference count；
- promotion suspect overlap；
- inventory status=`unavailable`；
- abnormal price exclusions；
- comment comparability；
- isolation grade：A/B/C/unusable；
- eligible levels；
- reject reasons。

### 9.4 隔离等级

| 等级 | 定义 | 可输出 |
| --- | --- | --- |
| A | 焦点 bundle 外无已知主要差异；事实完整 | 可进入 matched WTP 门禁 |
| B | 另有 1 个主要 bundle 差异或一个关键 unknown | 只能组合/整机选择关联 |
| C | 多个主要差异、品牌/系列强差异或事实不足 | 事实观察/整机位置 |
| unusable | 尺寸/战场/时间/价格无可比性 | 不进入量化 |

## 10. 市场分析单元和选择集

基本单元：

```text
battlefield × size_tier × period_week_index × platform_type
```

`MarketCellRow` 至少包含：

- sku identity；
- battlefield allocation weight（解释权重）；
- value bundle tier；
- avg price/sales volume/sales amount；
- channel/platform；
- price check；
- promotion suspect；
- inventory status=`unavailable`；
- brand/series；
- other bundle tiers；
- source refs/hash。

共同选择集只包含同一 cell 中真实有有效价格和销量的 SKU。M11D weight 不改变实际销量，只用于战场样本权重和解释。

过滤：

- record active；
- price check ok；
- price > 0；
- sales >= 0；
- 促销疑似 cell 在主结果排除，在敏感性中单列；
- 单边零销量不自动解释为拒绝或缺货；主模型排除，敏感性保留；
- 相同 clean record key 去重。

## 11. 量化状态机

### 11.1 QuantificationLevel

按单向顺序，不能跳级：

```text
Q0 NOT_OBSERVED
  |
  v
Q1 USER_VALUE_ESTABLISHED
  |
  v
Q2 RELATIVE_EXPERIENCE
  |
  v
Q3 MARKET_CHOICE_ASSOCIATION
  |
  v
Q4 WHOLE_PRODUCT_PRICE_ACCEPTANCE
  |
  v
Q5 MARKET_IMPLIED_WTP
```

### 11.2 逐级门禁

Q1：当前事实可用，用户购后有可归因结果或风险。

Q2：base/same-value 评论口径、时间、渠道和去重规则一致，样本门槛满足。

Q3：至少一个可用共同市场对照，价格范围覆盖同价/近同价，选择方向可计算。

Q4：整机至少两个强直接对照或同一家族稳定价格曲线，结果仍是整机方案。

Q5：第 12 节全部 matched WTP 门禁通过。

较低层失败不会否定价值是否成立。

## 12. 选择贡献与 matched market-implied WTP

### 12.1 选择贡献

复用 V2 pair curve：

```text
x = (target_price - counterfactual_price) / counterfactual_price
y = target_sales / (target_sales + counterfactual_sales)
```

同周同平台、P90 合计销量截尾加权、2pp 价差箱、PAVA 单调不增、不外推。

输出：

- observed gap range；
- valid cells/weeks/bins；
- same-price or near-same-price share；
- choice difference pp；
- direction consistency；
- applicable battlefield/size/platform/window；
- uncertainty/limitations。

这仍是市场选择关联，不是因果贡献。

### 12.2 Q5 硬门槛

同时满足：

1. 至少一个 `base_value` A 级反事实；
2. 目标价值至少两个业务档位；
3. 焦点 bundle 外主要差异为 0；
4. 至少 12 个共同 cell、8 个不同周、4 个价差箱、价差跨度 >= 8%；
5. 0 或 50% crossing 位于观测范围内，且附近局部样本支持；
6. 目标与 base pair 的选择曲线随相对价格单调不增；
7. 排除 promotion suspect 后仍通过；
8. leave-one-week-out 的 crossing 方向一致，区间不过度漂移；
9. 至少 2 个独立 A 级高可比 pair，且来自至少 2 个 model family，方向一致；单一同品牌同系列 pair 仍只到 Q4；
10. 无版本线谱冲突、关键事实 unknown 或完全共线；
11. 不超出观测价格和 value tier；
12. 结果通过 bootstrap/leave-one-week-out 区间稳定性门槛。

### 12.3 等选择价格差

对每个 A 级 base pair，在拟合曲线中找选择约回到 50% 的相对价差 `g*`：

```text
pair_wtp = g* × base_reference_price
```

只有 crossing 在观测区间且局部支持时才计算。多 pair 使用质量加权中位数；区间取 pair dispersion 与 leave-one-week-out/cluster bootstrap 的联合保守包络。

输出字段：

- method=`matched_equal_choice_price_gap`；
- estimate_low/high；
- reference_price；
- currency；
- pair count/cell count/week count；
- model family count；
- observed price/value range；
- sensitivity summary；
- assumptions；
- exclusion reasons；
- `causal_claim=false`；
- `psychological_max_price=false`。

全部门槛和阈值归属 `sellpoint_value_pm_v4_matched_wtp_config_v1`，随结果保存。后续修改最小 cell/week/bin、价差跨度或稳定性阈值必须升级配置版本并重跑 cohort，不能静默改常量。

### 12.4 当前不做多 SKU 系数比

虽然离散选择理论允许在效用模型中用 `-beta_value/beta_price` 转换边际 WTP，但当前 CatForge 数据不足以稳定识别：

- 价格内生；
- 未观测产品质量与价格相关；
- 无完整促销和库存；
- 无外生工具变量；
- 聚合销量不含消费者选择集和 outside option。

因此首版不实现 BLP、conditional logit 或简单回归系数比。未来必须新增独立方法 Goal，经数据可行性审计后才能启用。

## 13. 65E7Q 的预期状态

固定验收：

- 战场和采购理由可展示；
- 用户实际价值按 M05C 购后体验展示；
- 高亮、控光、MiniLED 共同作为画质 bundle；
- base value 候选 65E5Q 因 M04C/M12C v0.2 缺失而降级；
- same-value L65MC-SP 可用于整机同价选择关联；
- stretch K-65XR50 只作上探事实观察；
- lineage status 为 stale conflict；
- quantification level 最高 Q3；
- WTP 必须 `null`，原因至少包含 `base_counterfactual_not_eligible`、`single_strong_pair`、`bundle_collinearity`、`version_lineage_conflict`。

## 14. 产品经理输出合同

顶层：`SkuProductValueRealizationReport`。

第一屏：

- target；
- analysis status；
- headline；
- `value_structure_rows`；
- overall quantification boundary；
- data scope note。

主表一行一个 `battlefield + purchase reason`：

| DTO 字段 | 产品经理看到的含义 |
| --- | --- |
| battlefield | 本品在哪个价值战场竞争及空间 |
| purchase_reason | 用户可能为什么选它 |
| realized_user_value | 用户买后实际获得什么 |
| sellpoint_bundle | 哪些卖点共同支撑 |
| counterfactual_result | 相对基础/同价值/上探表现 |
| selection_price_realization | 当前量化到用户价值、选择、整机承接或 WTP 哪层 |
| product_role | 在 SKU 中承担什么作用 |
| confidence_label | 高/中/有限/不可判断 |

禁止在主表展示：内部 module codes、SQL、模型变量、evidence IDs、英文状态码、评论条数自证、通用下一步清单。

下钻：

- bundle member capabilities；
- product fact；
- user experience support/risk；
- base/same/stretch comparability；
- independent quantification status；
- limitations；
- QA appendix。

### 14.1 产品角色确定规则

按顺序命中第一条，避免 renderer 自由发挥：

| 条件 | 产品角色 |
| --- | --- |
| value established + base 差异成立 + Q3 以上选择优势 | 核心差异价值 |
| 同价值竞品普遍具备、缺失会影响理由成立 | 基础门槛 |
| value established + 支撑理由但非主要选择差异 | 辅助成交价值 |
| Q3 选择成立但 Q4/Q5 显示价格未完全上收 | 客户获得价值 |
| capability confirmed 但 value not observed/quantification < Q2 | 配置支撑 |
| 高价位置 + 选择/体验承接偏弱 | 价格压力 |
| 事实、线谱或反事实不足 | 当前不可判断 |

产品角色不直接生成配置或定价动作。

## 15. 错误与降级状态机

| code | scope | 用户结果 |
| --- | --- | --- |
| target_not_found/ambiguous | report | blocked |
| authority_version_missing | source/report | blocked or affected row unavailable |
| multiple_current_same_rule | source | blocked，不能自动择一 |
| version_lineage_conflict | relation | 局部阻断价格归因 |
| battlefield_missing | report | 无完整价值结构 |
| purchase_reason_missing | report | 不重建；只显示现有价值/事实边界 |
| weak_expression_only | relation | 不升级为采购理由/支付价值 |
| base_counterfactual_missing | quantification | 封顶 Q3/Q4 |
| same_value_only | quantification | 封顶 Q3/Q4 |
| full_collinearity | bundle | 合并组合，单项 WTP null |
| no_price_variation | quantification | 封顶截面量价 |
| no_price_overlap | quantification | 不插值/不外推 |
| promotion_contaminated | market cell | 排除/敏感性降级 |
| inventory_unavailable | audit | 明示限制，不伪装已控制 |
| price_direction_unstable | quantification | WTP null |
| experience_not_comparable | relation | 不输出相对体验强弱 |
| feishu_publish_failed | delivery | JSON/Markdown 保留，发布错误清晰 |

任何错误都不能生成增减配、涨降价或研究清单。

## 16. Query plan 与性能预算

### 16.1 批量读取

请求级查询预算：

1. target + source authorities：<= 4 queries；
2. published M12D profile/anchors：<= 2；
3. candidate recall/roles：<= 3；
4. all target/candidate snapshots：按模块批量 `sku_code IN (...)`，<= 8；
5. all weekly rows：1 query；
6. M12C pool/tier facts：<= 2；
7. optional evidence drilldown：懒加载，不进入首页。

总预算：首页 <= 20 SQL queries，禁止逐 SKU/逐评论 N+1。

### 16.2 数据量预算

- candidate cap：召回 <= 30，进入完整 snapshot <= 12，最终每角色 <= 3；
- weekly rows：默认 <= 52 周 × 2 平台 × 13 SKU；
- comment evidence：每 SKU 每 bundle 聚合后 <= 5 条代表证据，首页不搬运全文；
- model cells：<= 2,000；超限按市场窗口和候选质量裁剪并记录。

### 16.3 延迟预算

- 本地 SQLite fixture P95 <= 1s；
- 205 read-only JSON P95 <= 8s；
- Markdown render <= 0.5s；
- 飞书发布不计入分析 P95，单独记录 delivery latency。

无跨请求缓存。输入版本和数据可能变化，首版优先正确性；同请求内按 immutable snapshot 复用。

## 17. Hash 与确定性

Canonical hash：

```text
input_hash = sha256(
  schema_version
  + sorted authority manifest
  + sorted source/result hashes
  + sorted market cell record keys
  + versioned config
)

result_hash = sha256(canonical business DTO excluding generated_at/delivery URL)
```

同输入、同配置、同版本必须产生同 result hash。代表证据按稳定 key 排序，禁止数据库自然顺序。

## 18. 安全和运行边界

- 只读 DB session；
- 不调用上游 runner/service write path；
- 不导出 prompt、Gold Set 或工厂资产；
- 错误不包含数据库 URL、token、飞书 secret；
- evidence refs 只在 QA 附录；
- JSON/Markdown/Feishu 使用同一业务 DTO；
- feature flag 默认 off；
- 自然语言路由到 G10 才允许启用。

## 19. 失败模式

| 路径 | 生产失败 | 处理 | 测试 |
| --- | --- | --- | --- |
| authority resolver | 多个同版本 current | 明确 blocked，不择一 | schema/integration |
| M12D reader | 发布版本 source refs 过旧 | stale conflict/revalidation | 65E7Q fixture |
| linkage | 一个评论句重复支持多个参数 | bundle 内去重 | unit |
| candidate builder | fallback 被误标 M14 | provenance enum | integration |
| market cells | 促销/零销量被当选择 | 主分析排除，敏感性单列 | unit |
| pair curve | 0 在价差空洞中 | 不插值 | unit |
| WTP | crossing 在样本外 | null/no extrapolation | unit |
| WTP | leave-one-week-out 方向翻转 | unstable/null | unit |
| renderer | JSON 和 Markdown 结论漂移 | 单 DTO snapshot | integration |
| Feishu | 发布失败 | 保留 JSON/Markdown | mock integration |

没有“无测试、无错误处理且静默”的已知路径。

## 20. NOT in scope

- 多 SKU 结构需求/BLP/简单回归系数比：当前无法处理价格内生性和未观测质量；
- 实验 WTP、联合分析、购买前传播心智：没有数据；
- 库存补全：没有字段；
- 自动增配/减配/涨价/降价：没有成本和产品约束；
- 新数据库表或迁移：首版可确定性重算；
- 重跑或修复 M11C/M11D/M12D：属于上游独立任务；
- 非 TV taxonomy：首版返回 unsupported；
- G10 自然语言路由/canary：必须单独授权。

## 21. 方法依据

随机效用/条件 logit 为“价值效用和价格效用共同决定选择”的理论基础；差异化产品需求研究也说明，产品级聚合数据可以估计需求，但必须认真处理未观测产品质量、价格内生性和识别。G01 已证明 CatForge 当前缺少这些关键控制，因此首版采用更保守的高可比匹配，不实现结构需求系数比。

参考：

- Daniel McFadden, *Conditional Logit Analysis of Qualitative Choice Behavior*；
- Berry, Levinsohn and Pakes, *Automobile Prices in Market Equilibrium*。

## 22. G03-G07 实施切分

- G03：context、authority、lineage gate；不生成价值结论；
- G04：reason/value/bundle linkage；不生成反事实/WTP；
- G05：counterfactual candidates/comparability；不生成 WTP；
- G06：quantification state machine、choice association、matched WTP；
- G07：business DTO、CLI、Markdown、Feishu。

每个 Goal 只改自己的层，前序 typed contract 错误必须走修复 Goal，不能在后续静默改 schema。
