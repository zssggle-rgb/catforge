# M02 Evidence 原子层

## M02 Evidence 原子层

### 1. 模块目标

把清洗后的参数、卖点、评论、市场事实转成可复用的 evidence 原子，支撑后续所有业务判断。

### 2. 上游依赖

- `core3_clean_market_fact`
- `core3_clean_param_fact`
- `core3_clean_claim_fact`
- `core3_clean_comment_fact`
- `core3_data_quality_issue`

### 3. 本模块不做什么

- 不判断卖点是否成立。
- 不判断用户任务。
- 不判断价值战场。
- 不判断竞品。

### 4. 输入数据契约

清洗规范表中的每条有效事实。

### 5. Evidence 类型

| 类型 | 说明 |
|---|---|
| param_raw | 参数原始事实 |
| promo_raw | 宣传原始文本 |
| comment_raw | 评论原文 |
| comment_sentence | 评论短句 |
| market_fact | 价格、销量、渠道事实 |
| quality_issue | 数据质量问题 |
| rule | 后续规则 evidence |

### 6. 处理流程

1. 为每个清洗事实生成 `evidence_id`。
2. 保存来源表、来源行、原始字段、原始值。
3. 生成 source_ref。
4. 根据 quality_status 给初始 confidence。
5. 写入 evidence 表。

### 7. 输出数据契约

#### `core3_evidence_atom`

| 字段 | 说明 |
|---|---|
| evidence_id | 证据 ID |
| batch_id | 批次 |
| sku_code | SKU |
| source_type | param_raw/promo_raw/comment_raw/market_fact |
| source_table | 来源表 |
| source_row_id | 来源行 |
| raw_field | 原始字段 |
| raw_value | 原始值 |
| normalized_text | 规范化文本 |
| evidence_time | 证据发生时间 |
| channel_type | 渠道 |
| confidence | 初始置信度 |
| quality_status | 数据质量 |
| asset_version | 资产版本 |
| created_at | 时间 |

### 8. 置信度规则

| 数据质量 | 初始 confidence |
|---|---:|
| ok | 0.95 |
| warn | 0.70 |
| error | 0.30 |
| missing/unknown | 不生成或生成 unknown evidence |

### 9. 增量重算策略

若 M01 清洗行 hash 变化：

```text
失效旧 evidence
生成新 evidence
下游按 evidence_id 依赖图重算
```

### 10. 给下游的数据承诺

- 下游所有结论必须引用 evidence_id。
- evidence 不直接等于业务结论。
- evidence 可以追溯到原始 source_row_id。

### 11. 验收标准

| 验收项 | 标准 |
|---|---|
| 有效清洗事实都有 evidence | 100% |
| evidence 可追溯源行 | 100% |
| confidence 受数据质量影响 | 必须 |
| 旧 evidence 不直接物理删除 | 推荐逻辑失效 |
