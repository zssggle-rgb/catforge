# 06 候选池与组件评分模块

## 1. 模块目标

从项目内全量 SKU 中，为每个目标 SKU 召回可比较候选，并为每个候选计算组件分和三槽位分。该模块不最终选三竞品，只产生候选排序基础。

## 2. 输入输出

输入：

- 目标 `Core3SkuSnapshot`
- 全量候选 `Core3SkuSnapshot[]`
- `MarketProfileBySku`
- `tv_core3_mvp_rules.json`

输出：

- `Core3CandidateCard[]`
- `core3_competitor_candidate` 行

## 3. 候选池召回

### 3.1 硬过滤

过滤规则：

1. 同 `category_code`。
2. 排除同一 `sku_code`。
3. 候选有 SKU 主数据。
4. 屏幕尺寸差默认不超过 15 英寸，缺尺寸则不因尺寸过滤，但标记降级。
5. 价格窗口默认为目标加权均价 ±35%；benchmark 候选允许 +80%。
6. 保留目标主/次战场相同或相近的候选。
7. 候选上限默认 200。

### 3.2 候选状态

- `eligible`：可进入槽位评分。
- `insufficient`：信息不足，保留诊断但不作为高置信输出。
- `filtered`：被过滤，不落库或仅在 debug 模式落库。

### 3.3 gate_reasons

常见原因：

- `same_sku`
- `missing_candidate_identity`
- `missing_target_price`
- `missing_candidate_price`
- `missing_target_sales`
- `missing_candidate_sales`
- `outside_price_window`
- `outside_size_window`
- `no_shared_battlefield`
- `insufficient_param_signal`
- `insufficient_claim_signal`

## 4. 组件分总表

所有分值为 `0..1`，unknown 组件不当作 0，进入重归一或降级。

| 组件 | 类型 | 主要用途 |
| --- | --- | --- |
| `price_similarity` | 相似 | direct |
| `channel_overlap` | 相似 | 三槽位 |
| `size_similarity` | 相似 | direct |
| `claim_similarity` | 相似 | direct |
| `task_similarity` | 相似 | direct/pressure |
| `battlefield_similarity` | 相似 | direct/benchmark |
| `price_advantage` | 压力 | pressure |
| `sales_strength` | 压力 | direct/pressure |
| `price_drop_signal` | 压力 | pressure/benchmark |
| `param_superiority` | 标杆 | benchmark |
| `claim_superiority` | 标杆 | benchmark |
| `sales_or_amount_strength` | 标杆 | benchmark |
| `price_premium_or_downshift` | 标杆 | benchmark |

## 5. 相似组件

`price_similarity`

```text
if price unknown:
  unknown
else:
  max(0, 1 - abs(candidate_price - target_price) / (target_price * 0.35))
```

`channel_overlap`

```text
sum(min(target_share[channel], candidate_share[channel]))
```

`size_similarity`

```text
max(0, 1 - abs(candidate_size - target_size) / 15)
```

`claim_similarity`

```text
sum(min(target_claim_score, candidate_claim_score) for shared claims)
/ sum(target_claim_score for target claims)
```

`task_similarity` 和 `battlefield_similarity` 同上，用任务/战场得分加权。

## 6. 压力组件

`price_advantage`

```text
if candidate_price < target_price:
  min(1, (target_price - candidate_price) / (target_price * 0.25))
else:
  0
```

`sales_strength`

```text
max(
  candidate_sales_percentile,
  min(1, candidate_sales_volume_12m / max(target_sales_volume_12m, 1))
)
```

`price_drop_signal`

```text
max(0, candidate_price_drop_rate_3m)
```

## 7. 标杆组件

`param_superiority`

比较参数：

- `oled_flag`
- `mini_led_flag`
- `refresh_rate_hz`
- `peak_brightness_nits`
- `dimming_zones`
- `hdmi_2_1_ports`
- `eye_care_flag`

候选强于目标则按权重加分；目标或候选缺失时该项 unknown，不按 false 处理。

`claim_superiority`

候选高价值卖点激活分高于目标时加分。

`sales_or_amount_strength`

```text
max(candidate_sales_percentile, candidate_sales_amount_percentile)
```

`price_premium_or_downshift`

成立条件之一：

- 候选价格高于目标 15% 以上且参数/卖点更强。
- 候选 3 个月降价后进入目标价格 ±20%。

## 8. 槽位分

`direct_slot_score`

```text
battlefield_similarity * 0.25
+ claim_similarity * 0.20
+ price_similarity * 0.15
+ channel_overlap * 0.10
+ size_similarity * 0.10
+ task_similarity * 0.10
+ sales_strength * 0.10
```

`pressure_slot_score`

```text
task_similarity * 0.25
+ price_advantage * 0.25
+ sales_strength * 0.20
+ channel_overlap * 0.10
+ battlefield_similarity * 0.10
+ price_drop_signal * 0.10
```

`benchmark_slot_score`

```text
param_superiority * 0.25
+ claim_superiority * 0.20
+ battlefield_similarity * 0.20
+ sales_or_amount_strength * 0.15
+ price_premium_or_downshift * 0.15
+ channel_overlap * 0.05
```

## 9. 落库

`core3_competitor_candidate`

关键字段：

- `target_sku_code`
- `candidate_sku_code`
- `battlefield_code`
- `gate_status`
- `gate_reasons`
- `component_scores`
- `slot_scores`
- `evidence_ids`
- `confidence`

唯一约束：

- `(run_id, target_sku_code, candidate_sku_code)`

## 10. 验收

- 候选池不会包含目标自身。
- 缺价格不会崩溃，但相关组件 unknown 且置信度降级。
- 修改候选销量会影响 `sales_strength`。
- 修改候选价格会影响 `price_similarity` 和 `price_advantage`。
- 每个 eligible 候选有可解释的 gate 和 component scores。

