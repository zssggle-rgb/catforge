# 用户卖点价值分析 V5 详细设计

状态：G00 架构冻结候选；G01/G02 可用真实数据和评审修订，修订必须留痕

需求：`V5_requirements.md`

## 1. 设计原则

V5 复用 V4 已通过的只读上下文、lineage、用户价值连接、量价曲线和跨载体发布基础，不复制一套上游画像。新增部分集中在：

1. 多层反事实召回和问题—方法路由；
2. 市场合成基线；
3. 高/低绩效价值组合原型；
4. 战场组合优化；
5. 价格、销量、分配、增量和挤占分账；
6. PM 决策 DTO 和亮点召回。

核心计算必须为确定性纯函数或确定性配置驱动服务，不调用外部 LLM。

## 2. 数据流

```text
显式 V5 入口 / feature flag off by default
                |
                v
V4 只读上下文 + 最新权威来源解析
                |
      +---------+----------+
      |                    |
      v                    v
用户价值与卖点组合       市场单元构造
      |                    |
      +---------+----------+
                v
多层反事实 resolver
 direct / budget / brand ladder / param tier
 same-claim-realization / own curve / synthetic pool
                |
      +---------+----------+
      |                    |
      v                    v
合成市场基线           高/低绩效组合原型
      |                    |
      +---------+----------+
                v
量价分账 + 战场组合优化 + cannibalization
                |
                v
PM business DTO
 JSON / short / Markdown / Feishu / card
```

## 3. 顶层合同

建议新增 `SellpointValueV5Context`，包含：

- V4 context 引用和 hash；
- 全市场候选轻快照；
- 周×平台市场单元；
- battlefield portfolio；
- counterfactual pool manifest；
- method config versions；
- evidence refs 和 input hash。

建议业务结果 `SkuPerceivedValueMarketRealizationReport`：

- `decision_summary`；
- `value_account_rows`；
- `market_reference`；
- `battlefield_portfolio_options`；
- `overall_boundary`；
- `audit`。

所有 Pydantic 模型 `extra=forbid`；missing 使用 `null + availability`，不得转为 false 或 0。

## 4. 关键模型

### 4.1 ValueAccountRow

主键：`battlefield_code + value_bundle_code`。

字段：

- battlefield identity/role/market space/current allocated sales；
- perceived user value、scenario、outcome、status；
- bundle members 和事实状态；
- highlight types 和理由；
- counterfactual summaries；
- price realization；
- volume realization；
- quantification boundary；
- confidence、limitations、evidence refs。

### 4.2 CounterfactualCandidate/Set

统一字段：

- method type；
- source provenance；
- target question；
- candidate SKU/pool IDs；
- control dimensions；
- overlap/balance；
- isolation grade；
- eligible conclusions；
- reject/degrade reasons；
- sample manifest hash。

### 4.3 MarketSyntheticControl

字段：

- treated SKU/bundle；
- donor pool；
- pre/control window；
- donor weights；
- standardized balance diagnostics；
- price/sales/share/amount outcomes；
- estimate interval；
- leave-one-donor、leave-one-week 和 placebo results；
- `causal_claim=false`；
- method config/hash。

首版采用透明的受约束加权匹配/熵平衡或最近邻加权，不引入难审计的黑箱模型。方法选择必须由 G02 合成数据和真实数据门禁决定。

### 4.4 PerformanceArchetype

字段：

- market cell definition；
- residual metric and model config；
- high/low/neutral cohort；
- prevalent bundle/tier/user outcomes；
- target gap；
- sample/stability/confounding；
- representative SKUs；
- source hash。

### 4.5 BattlefieldPortfolioOption

字段：

- option type：`strengthen_existing|expand_excluded`；
- battlefield and current role；
- pathway：communication activation、capability completion、market activation、portfolio priority 或 expansion；
- addressable market space；
- current allocated sales；
- capability gap/reachability；
- price/volume reference；
- overlap/cannibalization；
- evidence boundary；
- comparison score components，不在 PM 主表展示总分。

## 5. 反事实路由

系统先识别业务问题，再选择最高可用证据：

| 业务问题 | 首选 | 降级 |
| --- | --- | --- |
| 该价值是否形成用户兑现 | 同宣称不同兑现 + 用户事实 | 同池用户结果分布 |
| 是否是相对亮点 | 直接同价值/同预算对照 | 市场池、参数档位、品牌梯度 |
| 没有该组合会怎样 | 直接 base | 市场合成基线 |
| 价格是否承接 | 直接对照 + 自身价格曲线 | 同预算池价格位置 |
| 销量是否承接 | 合成基线 + 同价选择 | 残差绩效和市场池位置 |
| 单项是否可给金额 | 独立变化的直接 base | 不降级为伪金额，保持 null |
| 战场增强/拓展空间 | 当前 portfolio + 合成参照 | 市场空间和可达性，仅定性 |

单个分析行可以同时使用多个反事实，但每个指标必须标记自己的方法来源，不得混成一个总体置信度。

## 6. 市场单元与控制变量

基础市场单元：

```text
category × product_form × size_tier × week × platform/channel
```

战场是解释和分层维度，不用 M11D 权重改写真实 SKU 销量。控制变量至少包括：

- target/baseline value bundle tiers；
- price level/band；
- brand tier and series relation；
- other core bundles；
- active weeks；
- week/platform fixed effects；
- promotion suspect/abnormal price；
- available inventory only if source exists；missing 保持 unknown。

## 7. 市场合成方法门禁

候选 donor pool 至少满足同尺寸形态、价格重叠、共同周平台和基础战场可比。输出差异前必须通过：

1. donor 数量和有效市场单元门槛；
2. 核心控制变量 standardized difference；
3. 正权重且有效样本量不塌缩；
4. 价格和结果的共同支持；
5. 留一 donor/week 方向稳定；
6. 假处理 placebo 不显示同等普遍“增量”；
7. 不外推到未观察价格/档位；
8. 无 blocking lineage/事实冲突。

失败时保留市场池描述，不输出合成增量。

## 8. 高低绩效组合

首版以周销量/选择份额为主要结果，销额作辅助。使用可解释基线模型移除尺寸、价格、品牌层级、活跃周、week×platform 和 promotion suspect 的影响，按 out-of-fold residual 分组。

- high：稳定处于正残差上分位；
- low：稳定处于负残差下分位；
- unstable：跨窗口方向翻转，不进入原型；
- bundle prevalence：只描述共同出现和相对富集；
- 单项金额：始终不由原型生成。

模型、阈值、窗口和随机种子（如方法需要）全部版本化。

## 9. 量价分账

### 9.1 PriceRealization

- current price percentile；
- same-budget/brand-ladder/direct comparison gap；
- own price curve observed range and elasticity proxy；
- strict bundle price acceptance interval or null；
- limitations。

### 9.2 VolumeRealization

- raw volume/share percentile；
- controlled residual performance；
- synthetic baseline difference interval；
- confidence and noncausal flag。

### 9.3 BattlefieldAllocation

- M11D allocated current volume/amount；
- battlefield share of existing sales；
- `incremental=false` 固定标记。

### 9.4 NetIncrementBoundary

```text
observational gross difference
  - estimated internal cannibalization range
  = observational net range
```

任一部分不可识别时不计算净值。战场空间不得直接填入 gross difference。

## 10. 战场组合优化

### 10.1 已有战场增强

对 main/secondary/opportunity/user-observed 战场判定：

- `communication_activation`：用户已感知，产品宣称/claim evidence 弱；
- `capability_completion`：用户需求/市场存在，参数或能力不完整；
- `market_activation`：能力和用户价值存在，但量价承接弱；
- `portfolio_priority`：证据成立但因角色上限/组合取舍未进入更高优先级；
- `maintain/cap`：已充分承接或重叠高，不强推增强。

### 10.2 新战场拓展

候选必须当前为 excluded，并同时检查：

- 与现有用户任务/客群的相邻性；
- 所需能力与现有能力的距离；
- 同类 SKU 的真实市场空间和量价；
- 新组合是否已有市场 donor；
- 与现有战场和同系列的重叠；
- 数据是否只能支持“可达”，不能支持销量区间。

### 10.3 比较合同

每个 option 输出 market space、current position、gap、observational upside、effort proxy、cannibalization 和 evidence boundary。没有成本数据，不做利润排序。

## 11. 亮点召回

亮点不是固定 Top 3。候选必须命中用户兑现、相对价值或市场承接至少一类，且无 blocking 冲突。

排序用于减少阅读负担，由以下独立维度组成：

- 用户结果具体度和稳定性；
- 相对对照差异；
- 量价承接；
- 战场相关度和空间；
- 数据质量与反事实等级。

主报告展示“为什么是亮点”，不展示加权总分。所有候选不达门槛时输出空列表和原因。

## 12. PM DTO 文案规则

- 先说结论，再说证据边界；
- “用户未观察到”不能写成“用户无感”；
- “观察性销量差”不能写成“增加销量”；
- “当前战场分配”不能写成“该战场贡献的新增销量”；
- “市场价格承接区间”不能写成“用户心理最高价”；
- “机会战场”不能写成“尚未进入”；
- 没有相对差异时不输出通用问题；
- 不出现内部模块码、英文枚举和方法名。

## 13. 工程边界

- 优先扩展 V4 typed context adapter 和纯函数，不修改上游合同；
- 新增运行文件预计不超过 5 个，新服务不超过 3 个；超出须在 G02 单独评审；
- 只读 session；无 Alembic migration；
- 候选和市场行批量读取，端到端查询数不随候选 SKU 线性增长；
- 10k 市场行目标峰值内存不高于 80 MB；
- 单 SKU 本地 P95 目标不高于 3 秒（不含飞书网络）；
- result hash 排除 generated_at 和 delivery URL；
- feature flag 默认 off，显式命令才运行；
- 无 flag 应在数据库查询前拒绝。

## 14. 失败与降级

| 失败 | 降级 |
| --- | --- |
| M14 无合格候选 | 使用多层市场召回，保留 provenance |
| direct base 缺失 | 尝试合成基线；失败则只输出市场位置 |
| 合成池失衡 | 不输出增量，只展示 donor 市场描述 |
| bundle 完全共线 | 保留组合，不拆单项金额 |
| 自身价格无变化 | 不输出自身价格敏感性 |
| 高低绩效不稳定 | 不生成原型亮点 |
| 战场已是 opportunity | 归为已有增强，不归新拓展 |
| excluded 战场不可达 | 不进入拓展候选 |
| cannibalization 不可识别 | 不输出净新增 |
| lineage conflict | 局部阻断受影响结论，不伪造填补 |

## 15. 实施映射

- G01：覆盖审计、Gold Set、真实数据 manifest；
- G02：schema、算法配置、测试与性能合同冻结；
- G03：多层反事实 resolver；
- G04：合成基线和高低绩效原型；
- G05：战场组合优化；
- G06：量价/WTP/挤占分账；
- G07：PM DTO、CLI、Markdown、飞书；
- G08：完整验收、RC、205 默认关闭重跑和回滚。
