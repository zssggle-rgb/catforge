# 03 SKU 市场画像模块

## 1. 模块目标

把 `raw_market_fact` 中的分渠道量价数据转换成 SKU 级市场画像，为价值战场和竞品选择提供市场证据。

## 2. 输入输出

输入：

- `Core3RunContext`
- `MarketFactInput[]`
- `SkuMasterInput[]`

输出：

- `MarketProfileBySku`
- `core3_sku_market_profile` 行
- 价格、销量、渠道、趋势 evidence

## 3. 输出结构

```python
@dataclass
class MarketProfile:
    sku_code: str
    brand: str | None
    model_name: str | None
    series: str | None
    price_wavg_12m: float | None
    price_latest: float | None
    sales_volume_12m: float | None
    sales_amount_12m: float | None
    channel_share: dict[str, float]
    price_drop_rate_3m: float | None
    sales_growth_3m: float | None
    price_percentile: float | None
    sales_percentile: float | None
    sales_amount_percentile: float | None
    evidence_ids: list[str]
    missing_signals: list[str]
    confidence: float
```

## 4. 时间窗口

默认窗口：

- 读取项目内所有 period。
- 能解析日期时取最近 12 个自然月或周期。
- 不能解析时按字符串排序取最后 12 个 period。

诊断：

- period 解析失败时记录 `period_parse_failed`。
- period 少于 3 个时记录 `insufficient_market_window`。

## 5. 指标公式

`sales_volume_12m`

```text
SUM(sales_volume)
```

`sales_amount_12m`

```text
SUM(sales_amount)
```

`price_wavg_12m`

```text
SUM(sales_amount) / NULLIF(SUM(sales_volume), 0)
```

如果 `sales_amount` 或 `sales_volume` 缺失，但 `avg_price` 存在：

```text
fallback_price = weighted average avg_price by sales_volume if possible
```

`price_latest`

```text
latest_period_sales_amount / NULLIF(latest_period_sales_volume, 0)
```

若 latest period 的 amount/volume 不足，用 latest period 的 `avg_price`。

`channel_share`

```text
channel_sales_volume / total_sales_volume
```

如果销量缺失但销额存在：

```text
channel_sales_amount / total_sales_amount
```

`price_drop_rate_3m`

```text
(avg_price_prev_3m - avg_price_latest_3m) / avg_price_prev_3m
```

`sales_growth_3m`

```text
(volume_latest_3m - volume_prev_3m) / volume_prev_3m
```

## 6. 分位数

在同项目、同 category 的有效 SKU 内计算：

- `price_percentile`
- `sales_percentile`
- `sales_amount_percentile`

方法：

```python
percentile = rank(value) / count(valid_values)
```

用途：

- 高端画质战场：价格分位高、销额不弱。
- 价格/销量挤压：候选销量或销额分位高。
- benchmark：候选价格、销额、参数更强。

## 7. Evidence 生成

每个 profile 至少尝试生成以下 evidence：

- `market.price_wavg_12m`
- `market.price_latest`
- `market.sales_volume_12m`
- `market.sales_amount_12m`
- `market.channel_share`
- `market.price_drop_rate_3m`
- `market.sales_growth_3m`

`source_ref`：

```json
{
  "table": "raw_market_fact",
  "sku_code": "TV00029115",
  "period_window": ["2025-01", "2025-12"],
  "aggregation": "sum_or_weighted_average",
  "run_id": "..."
}
```

## 8. 画像置信度

```text
confidence = 1.0
- 0.25 if price_wavg_12m unknown
- 0.25 if sales_volume_12m unknown or zero
- 0.15 if channel_share empty
- 0.10 if period_count < 3
- 0.10 if price_latest unknown
min 0.1
```

`missing_signals`：

- `missing_price`
- `missing_sales`
- `missing_channel`
- `insufficient_periods`
- `missing_latest_price`

## 9. 落库表

`core3_sku_market_profile`

唯一约束：

- `(run_id, sku_code)`

字段重点：

- `price_wavg_12m`
- `price_latest`
- `sales_volume_12m`
- `sales_amount_12m`
- `channel_share`
- `price_drop_rate_3m`
- `sales_growth_3m`
- `price_percentile`
- `sales_percentile`
- `evidence_ids`
- `confidence`

## 10. 验收

- 有量价的 SKU 能生成完整画像。
- 没有销量但有价格时不崩溃，置信度降级。
- 没有评论不影响市场画像。
- 修改候选销量后，`sales_percentile` 和后续 pressure 分会变化。
- evidence 能回溯到市场事实聚合来源。

