# 用户卖点价值分析智能体 V2（产品经理版）详细设计

## 1. 设计结论

V2 是 analyst 层新增的只读 SOP，不新增工厂资产表、不修改 M12C、不重跑上游模块。运行时从已发布 SKU 画像聚合一个 `sellpoint_value_pm_v2` 合同，并由独立渲染器生成短答、看板卡片、Markdown 和飞书文档。

```text
已发布画像与市场明细
  -> 上游合同加载
  -> 一致性闸门
  -> 用户价值单元编组
  -> 评论严格归因
  -> 既有竞品事实对照
  -> 市场选择与价格情景
  -> 产品经理决策与报告
```

## 2. 模块边界

建议新增：

- `claim_value_pm_schemas.py`：Pydantic 类型合同；
- `claim_value_pm_service.py`：纯函数分析、证据闸门与量化；
- `claim_value_pm_answer.py`：产品经理语言、Markdown/飞书输出；
- `AnalystRepository.sellpoint_value_pm_context()`：只读加载聚合上下文；
- `SopOrchestrators.sellpoint_value_pm()`：薄编排；
- 命令 `sellpoint-value-pm`：与旧命令并行；
- 对应测试文件。

不新增：

- M12C 或 M12D 资产写表；
- 新竞品筛选算法；
- 外部 LLM 调用；
- 成本/利润估计；
- 单卖点金额分摊。

## 3. 运行时输入合同

`SellpointValuePmContext`：

```json
{
  "schema_version": "sellpoint_value_pm_context_v1",
  "project_id": "...",
  "category_code": "TV",
  "batch_id": "...",
  "target": {},
  "fact_brief": {},
  "comment_atoms": [],
  "market_weekly_rows": [],
  "market_pool": [],
  "competitor_source": "M14|competitor_set_fallback|none",
  "competitors": [
    {"selection": {}, "fact_brief": {}, "comment_atoms": [], "market_weekly_rows": []}
  ],
  "purchase_reason_hypothesis": {},
  "source_versions": {},
  "evidence_ids": []
}
```

仓储层加载顺序：

1. 解析目标 SKU；
2. 复用 `sku_fact_brief` 读取 M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D；
3. 对每个 SKU 先锁定当前 M05C 画像批次，再只读取该批次的商品体验事实原子；
4. `latest` serving scope 会主动纳入独立 M14 可用 run 的批次；在本次显式批次或 serving scope 内，优先锁定 M14 最新的单一可用 selection run；兼容真实产出的 `success/success` 与 `limited/warning`，且要求已有选择、无待复核阻断，再读取该 run 的 1–3 个 selection，禁止跨 run 或未来批次补槽；
5. 对目标和已选竞品加载事实画像；每个 SKU 先锁定当前 M07 画像批次，再只读取该批次的 M01 周度市场行；
6. M14 缺失时由 SOP 复用现有 `competitor-set` 的候选 ID 和角色，禁止消费其最终卖点结论；
7. M12D 只作为 `hypothesis` 附加，不进入独立证据计数。

## 4. 输出合同

`SellpointValuePmResult` 顶层字段：

| 字段 | 含义 |
| --- | --- |
| `schema_version` | `sellpoint_value_pm_v1` |
| `analysis_status` | `ready/partial/blocked` |
| `data_gate` | 上游完整性、冲突、受影响单元、修复动作 |
| `decision_summary` | 产品经理本周可执行动作 |
| `value_units` | 卖点称重明细 |
| `market_pricing` | 同价销量承接、当前价格承接状态、选择保持价差、价格情景 |
| `competitor_boundary` | 竞品来源、角色、原报告引用边界 |
| `test_backlog` | 下一步价格/表达/体验验证 |
| `limitations` | 不能下的结论 |
| `audit` | 批次、规则、样本、证据 ID、时间 |

每个 `value_unit`：

```json
{
  "unit_code": "tv_bright_room_dark_detail",
  "unit_name_cn": "明亮环境与明暗层次",
  "product_claim_cn": "产品侧有哪些配置和表达",
  "linked_param_codes": [],
  "linked_claim_codes": [],
  "product_fact_status": "confirmed|partial|conflict|unknown",
  "user_understanding": {
    "status": "direct|outcome_only|unrecognized|negative|mixed|insufficient",
    "eligible_sentence_count": 0,
    "direct_sentence_count": 0,
    "indirect_sentence_count": 0,
    "unattributable_sentence_count": 0,
    "negative_sentence_count": 0,
    "direct_choice_sentence_count": 0,
    "examples": []
  },
  "purchase_role": {
    "status": "direct_reason|entry_requirement_hypothesis|post_purchase_satisfaction|mixed_experience|drag|not_proven",
    "status_cn": "",
    "basis_cn": ""
  },
  "weights": {
    "product_fact_weight": null,
    "user_perception_weight": null,
    "pricing_readiness": "single_test|bundle_test|not_ready|insufficient"
  },
  "evidence_stage": "E0|E1|E2|E3|E4",
  "competitor_comparison": [],
  "decision_cn": "",
  "limitations": [],
  "evidence_ids": []
}
```

## 5. 价值单元注册表

MVP 使用代码内确定性 TV 注册表。每个注册项包含：

- 参数 code 集合；
- 卖点 code 集合；
- M05C 子维度集合；
- 直接表达正则；
- 体验结果正则；
- 禁止直接归因的泛化词；
- 适用任务/客群/战场；
- 单项可识别最低条件；
- 产品动作模板。

空调等其他品类不复用 TV 词表；MVP 若请求非 TV，返回类型化 `blocked/unsupported_product_category`，不生成错误结论。

## 6. 一致性闸门算法

### 6.1 全局检查

- 必需：M03B、M05C、M07；
- 建议：M04C、M09C、M10C、M11C、M11D；
- 竞品：M14 优先，允许回退；
- 每个来源记录是否存在、规则版本、批次、置信度和质量标记。

### 6.2 M03B/M04C 冲突

检查：

1. M04C `m03b_param_profile_missing` 但 M03B 存在；
2. M04C `fact_claim_count=0` 且 `matched_claim_count>0`；
3. M04C claim 映射所需参数在 M03B 为已知，但声明未知；
4. 产品原始表达与参数画像存在数字冲突（可获得时）。

冲突输出到 `data_gate.issues`，映射到受影响价值单元。全局仍可 `partial`，但该单元产品事实最高为 `conflict`，价格准备度强制 `not_ready`。

### 6.3 评论过度映射检查

如果某具体卖点所有支持句均不含该技术/参数词，且仅命中泛化词，则将它们从“直接”降为“不可归因”；句子仍可作为更上层价值组合的间接体验证据。

## 7. 评论严格归因算法

处理单位为去重后的 `source_comment_key + sentence_seq`：

1. 排除 `service_fulfillment_excluded`；
2. 负向或 contradict 先记入反向；
3. 命中单元直接技术/参数/唯一功能词 -> `direct`；
4. 未命中直接词，但命中明确场景 + 结果 -> `indirect`；
5. 只有“清晰、不错、很好、流畅”等泛化词 -> `unattributable`；
6. 同一句命中多个同源技术点时，只在价值组合计一次；
7. 保留最多 3 条正向、2 条反向证据示例及 evidence ID。

`user_perception_weight` 为描述性比例：

```text
(direct + 0.5 * indirect) / eligible_product_experience_sentences
```

它只表示评论中的可感知重量，不表示选择贡献或支付金额。分母不足时为 `null`。

## 8. 市场量化设计

### 8.1 方法等级

| 等级 | 方法 | 最低门槛 | 可输出 |
| --- | --- | --- | --- |
| L0 | M07 截面描述 | 目标有 M07 | 价格/销量池位置 |
| L1 | 直接竞品同周同平台原始比较 | 至少 1 对、>=4 有效单元 | 近同价观察/原始条件选择份额 |
| L2 | 直接竞品条件选择曲线 | 至少 2 对可用曲线，单对 >=6 单元、>=3 个价差箱 | 同价选择优势方向与竞品间区间 |
| L3 | 稳定条件销量承接曲线汇总 | M14 原生 `direct_fight` 与 `price_volume_pressure` 两类对照均为强样本且方向一致；扩展池存在 3 对以上时允许至少 2 个强样本、方向一致率 >=2/3 | 当前价格承接状态、选择保持价差和价格情景 |

### 8.2 周平台池构造

- SKU 范围：目标 + M14 已选直接竞品；M14 缺失时只使用现有竞品 SOP 给出的候选 ID；
- 批次：每个 SKU 的周度行只从其当前 M07 画像对应的权威批次读取，不跨重导批次合并；
- 单元格：`period_week_index × platform_type`；
- 行过滤：active、quality ok、价格和销量非空、销量非负；
- 数值对照只允许同精确尺寸、同/邻价带且存在平台重叠的竞品；邻尺寸仅作事实观察；
- 每个目标—竞品对按共同在售单元计算相对价差率和两款条件选择份额；
- 单边零销量不进入主模型，单列敏感性说明，避免把缺货当拒绝；
- 单元按两款合计销量加权，权重在 P90 截尾，避免单一大促周支配结果。
- 角色门槛：`direct_fight/price_volume_pressure/primary_direct/strong_direct/price_adjacent` 可进入价格曲线；标杆、上探、下探和情景参照只作事实观察。

### 8.3 直接竞品条件选择曲线

每个共同在售周平台单元：

```text
x = (target_price - competitor_price) / competitor_price
y = target_sales / (target_sales + competitor_sales)
```

按 2 个百分点相对价差分箱，以两款合计销量为权重求箱内 `y`。随后使用纯 Python PAVA 将曲线约束为单调不增：本品相对更贵时，拟合选择份额不能反而被算法抬高。PAVA 合并块保留 `x_min/x_max`，块内使用同一拟合值，块与块之间才插值；只在历史观察到的 `x` 范围内求值，禁止向范围外外推。

组合隔离等级只控制单项卖点归因，不阻断整机价格承接：

- A：除焦点价值组合外无其他主要配置差异，可写“与该组合相关”；
- B：另有 1 个主要组合差异，只能写“以该组合为核心的整机方案结果”；
- C：差异更多或事实未知，只展示整机结果，不能归给卖点。

参数比较先将刷新率、HDMI 2.1 接口数、色域、声道以及真实 M03B 的 `ram_gb/storage_gb` 等同义编码归一到统一键。双方已知键集合必须完全一致，且至少有 2 个可比较参数；任一关键参数只在单侧缺失时，整个价值组合关系降为 `unknown`，不能以剩余共有参数形成“本品更强”。数值只按参数专属档位比较，例如 300Hz 与 288Hz 同属 240Hz 以上档，不因原始数值高 3% 就判为不同等级。影院声场、护眼等当前 M03B 未稳定提供的价值单元可合法保持未知，但不再因此否定由 M14 角色、精确尺寸和市场样本支持的整机价格曲线。

单对强样本：>=8 个有效周平台单元、>=6 个不同周、>=4 个价差箱、价差跨度 >=8%；中样本：>=6 单元、>=3 箱、跨度 >=5%；弱样本只展示原始观察。

### 8.4 同价选择优势

在每条可用 pair 曲线上读取 `x=0` 时的 `share_same_price`：

```text
pair_advantage_pp = (share_same_price - 0.50) * 100
```

只有 0 落在该 pair 历史价差范围内，且同价附近有直接观察点或两侧最近价差箱均在 5 个百分点内、相邻空洞不超过 8 个百分点，才给归一数值；仅仅“最小值小于 0、最大值大于 0”不能跨空洞插值。最近观察点距 0 不超过 3 个百分点时可降级为“近同价观察”，不能冒充同价归一。多竞品主值使用证据质量加权中位数，P25–P75 只称为“竞品间区间”，不称统计置信区间。

### 8.5 选择保持价差

当 L3 成立且同价条件选择份额高于 50%，在每条 pair 曲线的已观察区间内寻找份额首次回落至 50% 的相对价差交点：

```text
hold_price_gap = crossing_price_gap_ratio * competitor_reference_price
```

至少 2 条 pair 有区间内、局部样本支持的有限交点才给金额区间。只有 L3、整机同价方向为正且至少 2 条 pair 都在样本上沿仍高于 50% 时，才允许写保守的“样本内至少保持到 +X%”，并取这些下界中的最小值；非 L3 或单一竞品观察不形成整机边界。同价份额不高于 50% 时写“当前未观察到正向保持价差”。业务定义固定为“竞品价格不变时，两款模型选择约回到五五开”，不得改写成单卖点愿付金额。

### 8.6 价格情景

以目标近 4 周加权成交价为当前价，生成 `-5%/-3%/当前/+3%/+5%` 并取整到业务价格粒度。对每条 pair 固定竞品参考价，将新价格映射回 pair 曲线；超出该 pair 历史观察范围或该档附近没有局部样本支持时，该 pair 不参与。当前价与新价格使用同一组有效 pair，至少 2 条 pair 且有效权重覆盖 >=60% 才展示：

- 对比选择份额；
- 选择指数（当前价 = 100）；
- 对比销售额指数（固定对照规模、当前价 = 100，仅作方向观察）。

若门槛不成立，仍展示当前价基准；其他档位为 `null` 并写明需要补充价格变化或价格实验。

### 8.7 当前价格承接状态

首页必须直接回答“现价是否已经消耗整机优势”，但只有 L3 且同价位置与当前价附近均有局部样本支持时才判断：

- 同价条件销量份额不高于 50%：`未观察到可承接优势`；
- 当前价条件销量份额 >=55%：`仍有承接空间`；
- 当前价条件销量份额 48%–55%：`价格已基本承接`；
- 当前价条件销量份额 <48%：`价格可能承接过度`；
- 其他情况：`无法判断`。

该状态只描述整机在历史直接竞品条件下的销量承接，不是单项卖点金额、建议售价或用户愿付金额测量。

## 9. 价值单元与整机市场量化的连接

整机同价选择优势不能按评论或内部得分分摊给每个卖点。连接规则为：

- `E1/E2`：价值单元只显示产品/用户证据；
- `E3`：必须同时有直接选购表达、可隔离的产品差异和稳定市场方向；仅有购后好评不得升级；
- `E4`：只有该单元具备独立配置反事实时允许单项价格测试；否则为组合测试；
- 市场量化份额和金额始终留在 `market_pricing`，不回填到单元行；单元行只显示选购角色和测试准备度。

## 10. 产品决策规则

| 条件 | 动作 |
| --- | --- |
| 产品事实冲突 | 先修数据/规格口径，不做价格判断 |
| 产品成立、用户无明确结果 | 改成用户场景语言并做体验验证 |
| 用户结果明确、无市场优势 | 保留为门槛或检查是否已被价格吃掉 |
| 产品差异 + 用户结果 + 同价优势 | 进入组合价格测试 |
| 有独立档位反事实 + 稳定价格响应 | 进入单项价格测试 |
| 竞品更强且用户结果明确 | 补强规格或调整战场，不复制竞品文案 |
| 负向体验集中 | 优先修产品，不做宣传放大 |

## 11. 报告与飞书发布

复用现有 `_publish_report` 与本地 Markdown 回退。报告标题默认：

`{品牌}{型号} 用户卖点称重与价格承接报告`

短答最多 600 字，只包含：数据是否可用、最重的 2–3 个价值单元、当前价格承接状态、价格结论、3 条动作和报告链接。飞书卡片使用 `sellpoint_value_pm_dashboard_v1`，不复用旧版“Top 支付价值金额”组件。业务页只显示“能否单独比较、条件销量份额、销量承接指数”等业务语言；L0–L3、M03B/M04C、A/B/C 等方法编码只保留在底层 JSON 审计字段。

## 12. 错误与降级

- 目标无法唯一解析：`not_found/ambiguous`；
- M03B 或 M07 缺失：`blocked`，只给补数动作；
- M04C 冲突：`partial`，受影响单元阻断；
- M05C 缺失：感知重量为空，市场层可继续；
- M14 缺失：回退并标记，回退失败则无竞品对照；
- 周度市场不足：降到 L0/L1，不输出价差；
- 飞书发布失败：返回本地 Markdown 路径和清晰错误；
- 所有异常信息不得包含数据库密码、飞书 token 等敏感信息。

## 13. 测试设计

至少覆盖：

1. 价值组合注册与独立卖点识别；
2. 泛化“画质清晰”不可直接归因 MiniLED；
3. “白天不反光/暗场有层次”可间接归入组合；
4. 负向评论优先；
5. M03B/M04C 冲突触发单元阻断；
6. L0/L1/L2/L3 各级降级；
7. 弹性为正、价格方差不足、促销污染时价差为空；
8. M14 竞品优先与回退；
9. 报告不出现旧版分摊金额和禁用术语；
10. CLI、路由、短答、Markdown、飞书发布 mock；
11. 65E7Q 固定业务验收 fixture。

## 14. 审计字段

每次输出记录：`generated_at`、`project_id`、`category_code`、`batch_id`、`target_sku_code`、`schema_version`、`method_level`、`source_versions`、`sample_summary`、`evidence_ids`、`review_required`、`review_reasons`。
