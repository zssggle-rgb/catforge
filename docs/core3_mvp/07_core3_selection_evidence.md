# 07 核心三竞品选择与证据卡模块

## 1. 模块目标

从候选池中按业务角色选择三个核心竞品，并为每个结果生成理由、置信度和证据卡。这个模块负责最终结果的“少而准”和“可解释”。

## 2. 输入输出

输入：

- `Core3CandidateCard[]`
- 目标 `Core3SkuSnapshot`
- 候选 `Core3SkuSnapshot[]`

输出：

- `Core3ResultCard[]`
- `core3_competitor_result`
- `core3_evidence_card`

## 3. 槽位硬门槛

### `direct`

必须满足：

- `battlefield_similarity >= 0.55`
- `claim_similarity >= 0.45`
- `price_similarity >= 0.45`
- evidence category 至少 3 类。

### `pressure`

必须满足：

- `task_similarity >= 0.45`
- `price_advantage >= 0.25` 或 `sales_strength >= 0.70`
- 至少有价格或销量证据。

### `benchmark_potential`

必须满足：

- `param_superiority >= 0.35` 或 `claim_superiority >= 0.35`
- `battlefield_similarity >= 0.35`
- 价格更高、销额更强或出现下探信号三者至少一个成立。

## 4. 选择流程

```text
for role in [direct, pressure, benchmark_potential]:
  candidates = eligible candidates passing role gates
  sort candidates by role slot score desc
  remove candidates already selected
  remove near duplicate series when possible
  apply brand diversification rule
  select first candidate
  if none:
    create empty role result with insufficient_reasons
```

## 5. 去重规则

### 5.1 SKU 去重

同一 `competitor_sku_code` 不得重复出现在三个角色中。

### 5.2 系列去重

系列重复判断：

- `series` 相同且尺寸差小于等于 2 英寸。
- 或型号去除尺寸数字后文本相似。

同系列候选只保留得分最高者。

### 5.3 品牌分散

如果三个候选都会来自同一品牌：

- 若当前槽位次高候选得分与最高候选差距 `<= 0.08`，选次高。
- 若差距更大，保留最高候选，但结果标记 `brand_concentration`。

## 6. 不足结果

不能硬凑。

当某角色没有合格候选时，仍写入一条结果：

```json
{
  "role": "pressure",
  "competitor_sku_code": null,
  "score": 0,
  "confidence": 0,
  "confidence_level": "low",
  "review_flag": true,
  "insufficient_reasons": ["weak_pressure", "missing_target_price"]
}
```

常见不足原因：

- `weak_direct`
- `weak_pressure`
- `weak_benchmark_potential`
- `insufficient_comparable_pool`
- `missing_target_price`
- `missing_target_sales`
- `less_than_three_evidence_categories`

## 7. 业务理由生成

`direct`

```text
与目标 SKU 在 {battlefield} 战场重合，价格带接近，核心卖点重合度 {claim_similarity}，渠道重合度 {channel_overlap}，适合作为正面对打竞品。
```

`pressure`

```text
与目标 SKU 面向相似用户任务，但候选具备 {price_advantage_or_sales_strength}，会形成价格/销量挤压。
```

`benchmark_potential`

```text
候选在 {superior_params_or_claims} 上强于目标，且 {premium_or_downshift_signal}，可作为高端标杆或潜在下探竞品。
```

理由必须来自组件分和 evidence，不允许生成没有数据支撑的业务话术。

## 8. 置信度

证据类型：

- `price`
- `sales`
- `channel`
- `param`
- `claim`
- `task_battlefield`
- `comment`

公式：

```text
confidence =
  slot_score * 0.45
  + evidence_coverage_score * 0.25
  + target_profile_confidence * 0.15
  + candidate_profile_confidence * 0.15
```

其中：

```text
evidence_coverage_score = min(1, evidence_category_count / 5)
```

等级：

- `high`: `confidence >= 0.78` 且证据类型 >= 4。
- `medium`: `confidence >= 0.55` 且证据类型 >= 3。
- `low`: 其他。

降级：

- 缺目标价格：最高 `medium`。
- 缺目标销量：最高 `medium`。
- 证据类型少于 3：最高 `low`。
- 未满足硬门槛：最高 `low`。

## 9. 证据卡结构

```json
{
  "target": {},
  "competitor": {},
  "role": "direct",
  "reason_summary": "",
  "component_scores": {},
  "price_comparison": {},
  "sales_comparison": {},
  "channel_overlap": {},
  "param_comparison": {},
  "claim_comparison": {},
  "task_battlefield_similarity": {},
  "comment_evidence": {},
  "evidence_categories": ["price", "sales", "channel"],
  "evidence_ids": []
}
```

证据卡最少包含：

- 目标与候选身份。
- 角色。
- 组件分。
- 业务理由。
- 证据类型。
- evidence ids。

## 10. EvidenceItem 回溯

每个 evidence_id 必须能查询到：

- `source_type`
- `source_file_id`
- `raw_row_id`
- `field_name`
- `raw_value`
- `normalized_value`
- `source_ref`
- `confidence`

证据卡中不直接展示内部规则配置或 prompt。

## 11. 落库

`core3_competitor_result`

唯一约束：

- `(run_id, target_sku_code, role)`

`core3_evidence_card`

一个非空结果一张 evidence card；空结果也可生成一张不足说明卡。

## 12. 验收

- 每个目标最多三个角色结果，角色固定且顺序固定。
- 三个非空竞品不重复 SKU。
- 无合格候选时不硬凑。
- 高置信结果至少有 4 类证据。
- 每条业务理由能从组件分和 evidence 中解释。
- evidence card 可独立导出 JSONL。

