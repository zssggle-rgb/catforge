# V5-G02 方法与状态机合同

状态：冻结候选

## 1. 设计取舍

V5 不是在 V4 直接 SKU 反事实上放宽门槛，而是新增“按业务问题选择证据”的 resolver。高覆盖 broad pool 负责召回，comparability 和识别门禁负责决定允许输出什么。

```text
recalled -> screened -> eligible
                    \-> rejected/degraded
```

召回成功不得直接生成亮点、观察性增量或金额。

## 2. 方法路由

| 问题 | 首选 | 次选 | 失败时 |
| --- | --- | --- | --- |
| 用户兑现 | 同宣称不同兑现 | 同池用户结果分布 | 只展示本品用户事实 |
| 相对亮点 | direct same-value/base | 同预算、品牌梯度、参数梯度 | 不生成相对亮点 |
| 没有该价值的基线 | direct base | market synthetic | 只展示市场池位置 |
| 价格承接 | direct + own curve | 同预算/品牌梯度 | 只展示价格百分位 |
| 销量承接 | synthetic + same-price choice | residual archetype | 只展示原始销量百分位 |
| 严格组合价格区间 | V4 A-grade base pairs | 无降级金额 | `null` |
| 战场组合 | current portfolio + eligible expansion | market space only | 定性/空结果 |

## 3. 召回配置 v1

`sellpoint_value_pm_v5_counterfactual_recall_v1`：

- same budget：同尺寸，目标均价 ±15%；
- market synthetic broad donor：同尺寸、至少一个 entered battlefield 重合、目标均价 ±30%；
- same brand ladder：同品牌同尺寸，不要求同价；
- parameter tier：同预算池有共同 dimension tier rank；
- same claim realization：双方 advertise 同 claim，目标 supported，peer unmentioned/contradicted；
- own curve strong：active weeks ≥8、platforms ≥2、price volatility >0；
- direct candidate：保留 M14/fallback/M12C provenance，但角色由 comparability 计算。

这些阈值只决定召回，不决定金额。

## 4. Comparability

### A

- exact product form/size；
- shared primary battlefield 或明确相同用户任务；
- 共同周 ≥12、平台 ≥2、价格支持重叠；
- 焦点 bundle 外主要差异 0；
- 关键事实和 lineage 无 conflict/unknown；
- promotion suspect 主分析排除。

### B

另有 1 个主要 bundle 差异或一个关键 unknown；可支持组合/整机市场关联，不支持严格金额。

### C

多个主要差异、品牌/系列强差异或共同市场不足；只支持市场位置和参照描述。

### unusable

尺寸/形态不符、无共同在售、价格无支持或 lineage blocking；不进入量化。

## 5. 市场合成配置 v1

`sellpoint_value_pm_v5_synthetic_control_v1`：

### 5.1 输入

- target 与 donor 的 week×platform clean cells；
- log price、brand tier、size、active week、other bundle tiers、promotion suspect；
- focus bundle tier/presence 用于排除同值 donor；
- M11D 只提供战场解释，不改销量。

### 5.2 broad -> eligible

必须同时满足：

1. broad donors ≥5；
2. common weeks ≥8，common platforms ≥2；
3. focus bundle 为 lower/missing，unknown 不算 lower；
4. target price 位于 donor 共同支持范围；
5. 非 promotion suspect 主样本；
6. 关键 lineage 无 blocking；
7. 约束权重非负、和为 1；
8. effective donor count `1/sum(w²) ≥3`；
9. 单 donor 最大权重 ≤0.50；
10. 核心连续/有序变量 after-SMD ≤0.10；0.10—0.20 只可 degraded，>0.20 failed；
11. 分类变量最大比例差 ≤0.10；
12. 不外推到未观察价格/价值档位。

### 5.3 稳定性

- leave-one-donor 和 leave-one-week 方向一致率 ≥0.75；
- cluster-by-week deterministic bootstrap 500 次，seed 取 input hash；
- placebo percentile ≥0.80 才可写“目标差异相对突出”；否则仍可展示区间但不得作为亮点；
- 任一核心结论符号在主样本/去促销/leave-one 中翻转，status=`unidentifiable`；
- causal claim 固定 false，因为缺库存、完整促销和外生价格来源。

## 6. 高低绩效原型配置 v1

`sellpoint_value_pm_v5_performance_archetype_v1`：

1. 主指标：week×platform 的 `log1p(sales_volume)`；辅助为 choice share/amount；
2. 基线控制：log price、size、brand tier、week、platform、active week、promotion suspect；
3. 使用按 week 分组的 out-of-fold regularized linear baseline，禁止同样本拟合后直接贴标签；
4. SKU residual 取有效 cells 的加权中位；
5. high/low 分别为残差上/下 25%，每组至少 10 SKU；
6. 至少 70% 时间折方向一致，否则 unstable；
7. bundle prevalence 差至少 15pp 且 bootstrap 方向一致率 ≥0.80 才进入原型差异；
8. 原型只输出“组合常见/稀缺”，不得输出单项因果或金额；
9. 同一 family 完全共线时合并 bundle；
10. 输出 causal claim=false。

## 7. 价格与销量分账

### PriceRealization

整机当前价格位置、direct/pool gap、自身曲线和严格组合区间分别保存。严格区间继续使用 V4 `matched_equal_choice_price_gap` 全门禁，不由 synthetic 或 archetype 生成。

### VolumeRealization

原始销量百分位、控制后 residual、synthetic difference、same-price choice 分开。任何一项失败不覆盖其他项。

### BattlefieldAllocation

固定 `incremental=false`，保存 M11D source lineage hash。若与当前 M11C 不一致，显示 lineage status，禁止重命名分配项。

### IncrementDecomposition

```text
observational gross
  - observational cannibalization
  = observational net
```

- gross 只有 synthetic gate pass 才可用；
- cannibalization 默认只给 overlap risk；
- 只有同品牌/系列替代集有足够共同周、价格事件和稳定负向转移时才给观察性区间；
- 任一数量缺失则 net=null；
- 战场市场空间不代替 gross；
- causal claim=false。

## 8. BattlefieldPortfolio 状态机

### 8.1 Existing

primary/secondary/opportunity/user_observed 一律进入 existing：

- user value 已观察、claim weak -> communication activation；
- capability gap present -> capability completion；
- capability/value 成立但 residual/price 弱 -> market activation；
- 证据成立但受 top-N 角色限制 -> portfolio priority；
- 已强承接或 overlap 高 -> maintain or cap。

### 8.2 Excluded expansion

必须是 excluded，并通过：

1. immutable product-form/size market gate；
2. task/group adjacency；
3. 每个 gap 标明 communication/capability/price/size/product-form；
4. 本 SKU/下一版本范围内所有 blocking gap 可改变；
5. 同尺寸/预期价格有 ≥5 real donors；
6. 市场空间存在且 lineage 可用；
7. overlap/cannibalization 已评估。

size/product-form 不可改变时直接 rejected。价格或能力可改变时只生成“达到条件”的 option，不假定已经进入。

65E7Q 的大屏家庭影院因当前尺寸/价格门槛不成立，在本 SKU 增卖点范围内 rejected；不能因为 param strong 就当机会。

## 9. 亮点规则

亮点候选至少满足一项：

- user realization：具体场景结果 observed，非泛化技术映射；
- relative value：eligible counterfactual 下差异稳定；
- price realization：同档/曲线显示价格承接，且不是只有高价；
- volume realization：controlled residual 或 synthetic 方向正且稳定。

blocking lineage、纯参数具备、原始高价低销、通用行业门槛不得成为亮点。内部排序仅决定阅读顺序，PM 不看总分。所有候选不达门槛时 highlights=[]。

## 10. 错误与降级

| 条件 | 状态 |
| --- | --- |
| M14 eligible=0 | 继续多层 fallback，保留警告 |
| broad donors <5 | 不跑 synthetic |
| balance/overlap fail | 只展示 donor pool，不输出差异 |
| placebo 不突出 | 差异可展示，不能成为市场亮点 |
| time stability flip | unidentifiable/null |
| inventory missing | causal=false，限制说明 |
| opportunity battlefield | existing strengthening |
| excluded 但 immutable gate fail | expansion rejected |
| M11D/M11C lineage mismatch | allocation 原名展示，禁止当增量 |
| cannibalization only risk | net=null |
| strict amount gate fail | amount=null |

## 11. 工程文件预算

新增运行文件最多 4 个：

1. `claim_value_pm_v5_schemas.py`；
2. `claim_value_pm_v5_counterfactuals.py`；
3. `claim_value_pm_v5_service.py`；
4. `claim_value_pm_v5_answer.py`。

复用 V4 context/repository/linkage/pair curve 能力，集成点只做薄入口。若实现证明必须拆第 5 个文件，G03 前先补设计回执；不得复制 V4 2,000 行服务。

## 12. 性能与查询预算

- authority/target/V4 context：沿用 V4 批量查询；
- V5 全市场 universe 追加查询 ≤6；
- 端到端 SQL ≤30，不随候选数增长；
- 10k market cells peak ≤80MB；
- 单 SKU 不含飞书 P95 ≤3s；
- synthetic 运行在裁剪后的 donor×cell 集，硬上限 20k rows；
- 超限返回 degraded，不静默截断金额；
- 同 input/config/source hash 结果确定。
