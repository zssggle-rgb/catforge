# M08 SKU 综合信号画像

## M08 SKU 综合信号画像

### 1. 模块目标

将参数、卖点、评论、市场信号合并成 SKU 级统一画像，作为任务、客群、战场、候选池和竞品评分的唯一上游特征接口。

### 2. 上游依赖

- M03 标准参数
- M04 标准卖点激活
- M06 评论下游信号
- M07 市场画像

### 3. 本模块不做什么

- 不生成新业务结论。
- 不重新读取原始表。
- 不修改上游评分。

### 4. 输入数据契约

读取所有 `sku_code` 级标准化特征。

### 5. 输出数据契约

#### `core3_sku_signal_profile`

| 字段 | 说明 |
|---|---|
| sku_code | SKU |
| brand/model/category | 主信息 |
| core_params_json | 核心参数 |
| activated_claims_json | 激活卖点 |
| comment_signals_json | 评论信号 |
| market_profile_json | 市场画像 |
| data_completeness_score | 数据完整度 |
| evidence_ids | 关键证据 |
| feature_version | 特征版本 |

### 6. 处理流程

1. 合并 SKU 主数据。
2. 汇总核心参数。
3. 汇总激活卖点 TopN。
4. 汇总评论信号。
5. 汇总市场画像。
6. 计算数据完整度。
7. 生成特征版本和 hash。

### 7. 数据完整度

```text
data_completeness_score =
  param_completeness * 0.30
+ claim_completeness * 0.20
+ comment_completeness * 0.20
+ market_completeness * 0.30
```

### 8. 给下游的数据承诺

下游模块只消费 M08 画像和各自专用表，不直接回读原始表。

### 9. 验收标准

| 验收项 | 标准 |
|---|---|
| 每个有效 SKU 有画像 | ≥95% |
| 缺失维度有标记 | 必须 |
| 下游所需特征齐全 | 必须 |
| profile_hash 可用于增量 | 必须 |
