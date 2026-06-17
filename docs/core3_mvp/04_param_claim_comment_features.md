# 04 参数、卖点、评论特征模块

## 1. 模块目标

把原始参数、宣传卖点和评论转换成 SKU 级语义特征。该模块不把少量枚举写死到 SKU 上，而是：

1. 加载完整彩电预制知识资产。
2. 对真实数据做字段画像和文本画像。
3. 从 raw 数据抽取参数值、卖点证据、评论主题。
4. 发现未映射字段、短语、主题候选。
5. 形成可追溯的 SKU 特征快照。

依赖设计：

- [彩电预制知识资产目录](03a_preset_asset_catalog.md)
- [真实数据抽取框架](03b_real_data_extraction.md)

## 2. 输入输出

输入：

- `Core3RunContext`
- `PresetAssetCatalog`
- `ParamInput[]`
- `ClaimInput[]`
- `CommentInput[]`
- `MarketProfileBySku`

输出：

- `standard_params`
- `claim_activations`
- `comment_topics`
- `candidate_param_aliases`
- `candidate_claims`
- `candidate_comment_topics`
- `core3_sku_feature_profile`
- param / claim / comment evidence

## 3. 预制与抽取边界

预制知识提供：

- 标准参数 code、别名、解析器、单位、阈值。
- 标准卖点定义、支撑参数、关键词、映射任务/战场。
- 评论主题定义、关键词、产品/服务类型。

真实数据抽取提供：

- raw 字段是否映射到标准参数。
- SKU 参数值是多少。
- SKU 是否激活某个卖点，激活分是多少。
- 哪些评论句命中主题，情感如何。
- 哪些 raw 字段、宣传短语、评论主题是新候选。

SKU 级输出必须包含真实 evidence，不能只有预制 code。

## 4. 参数抽取子流程

### 4.1 字段画像

对 `raw_sku_param.raw_param_name` 先聚合：

- 覆盖 SKU 数。
- 非空率。
- top raw values。
- 数值/单位形态。
- 与 seed alias 的匹配置信度。

字段画像用于：

- 自动映射高置信字段。
- 把未知高覆盖字段放进 `candidate_param_aliases`。

### 4.2 字段名匹配

匹配顺序：

1. 精确 alias。
2. 包含 alias。
3. token 同义词。
4. 文本相似。
5. 未映射候选。

匹配结果：

```json
{
  "raw_param_name": "峰值亮度",
  "matched_param_code": "peak_brightness_nits",
  "match_type": "exact_alias",
  "confidence": 0.95,
  "coverage": 0.62,
  "examples": ["1200nits", "1600尼特"]
}
```

### 4.3 参数值解析

调用 parser：

- `inch`
- `hz`
- `nits`
- `zones`
- `gb`
- `ports`
- `resolution`
- `percentage`
- `watt`
- `ms`
- `boolean_keyword`
- `enum_keyword`

同一参数多来源时按来源优先级和置信度合并：

```text
raw_param exact alias
  > raw_param fuzzy alias
  > claim_text numeric extraction
  > model_name extraction
  > comment weak hint
```

### 4.4 冲突处理

冲突类型：

- 同一参数不同数值。
- 同一宣传文本包含多个口径。
- raw 参数和宣传文本矛盾。

处理：

- 可共存口径拆成不同 param_code。
- 不可共存冲突记录到 `conflicts`。
- 冲突降低 `feature_confidence`。
- 冲突 evidence 仍保留，供复核。

## 5. 卖点激活子流程

### 5.1 三类证据分

每个标准卖点都拆成：

- `param_score`
- `promo_score`
- `comment_score`

示例：

```json
{
  "claim_code": "CLAIM_HIGH_BRIGHTNESS_HDR",
  "activation_score": 0.86,
  "param_score": 0.90,
  "promo_score": 0.82,
  "comment_score": 0.40,
  "evidence_ids": [],
  "missing_signals": []
}
```

### 5.2 参数证据

来自标准参数：

```text
peak_brightness_nits >= 1000 -> param_score 0.75
peak_brightness_nits >= 2000 -> param_score 0.90
peak_brightness_nits >= 3000 -> param_score 1.00
```

### 5.3 宣传证据

对 `claim_text` 分句后匹配：

- keyword。
- phrase pattern。
- numeric pattern。
- 否定词窗口。

命中句子生成 evidence。

### 5.4 评论证据

评论只作为体验验证，不替代硬规格。

例如：

- “看球不卡”增强高刷体验感知。
- “画面很亮”增强亮度感知。
- 但不能单独证明 `refresh_rate_hz=120` 或 `peak_brightness_nits=1000`。

### 5.5 缺失重归一

```text
known_weight_sum = sum(weights where signal is known)
activation_score = weighted_known_score / known_weight_sum
confidence = base_confidence * known_weight_sum / total_weight
```

unknown 不当成 0。

## 6. 新卖点候选发现

候选来源：

- 高频宣传短语。
- 高频未映射数值表达。
- 与高价/高销量 SKU 强共现的短语。
- 与评论主题强共现的短语。

进入候选条件：

- 覆盖 SKU 数 >= 5。
- 与现有 claim 相似度低。
- 有样例 SKU 和样例句。
- 能给出建议 claim group。

候选不参与高置信结论，除非人工批准或映射到已有 claim。

## 7. 评论主题子流程

### 7.1 评论切句

按中文标点、换行和长度切分。每句保留：

- `comment_id`
- `sentence_index`
- `sku_code`
- 原句

### 7.2 产品/服务分类

先分：

- `product_experience`
- `service_experience`
- `logistics_installation`
- `price_value`
- `unknown`

服务体验不直接激活产品卖点。

### 7.3 主题分类

使用 seed topic keywords 和同义词做多标签分类。一个句子最多保留 top3 topic。

输出：

```json
{
  "topic_code": "TOPIC_GAMING_SMOOTHNESS",
  "mention_count": 12,
  "mention_rate": 0.18,
  "positive_rate": 0.72,
  "negative_rate": 0.06,
  "sample_sentences": [],
  "evidence_ids": []
}
```

### 7.4 情感判断

第一版用规则词典：

- 正向：好、清晰、流畅、满意、舒服、方便、够用。
- 负向：卡、慢、刺眼、反光、漏光、拖影、麻烦、广告多。
- 否定窗口：不、没有、无、没。

无法判断则 `neutral`。

### 7.5 新主题候选

未映射评论短语进入 `candidate_comment_topics`，条件：

- 覆盖 SKU 数 >= 5。
- 与现有 topic 相似度低。
- 有产品/服务类型判断。
- 有正负样例句。

## 8. 特征快照落库

`core3_sku_feature_profile` 字段：

- `standard_params`
- `claim_activations`
- `comment_topics`
- `task_scores`，本模块先空。
- `target_group_scores`，本模块先空。
- `battlefield_scores`，本模块先空。
- `feature_evidence_ids`
- `extraction_diagnostics`
- `missing_signals`
- `confidence`

`extraction_diagnostics` 包含：

- 字段映射摘要。
- 参数冲突。
- candidate aliases。
- candidate claims。
- candidate topics。

## 9. 模块置信度

```text
feature_confidence =
  param_coverage * 0.35
  + claim_evidence_coverage * 0.30
  + comment_coverage * 0.20
  + conflict_penalty_adjusted * 0.15
```

其中：

- `param_coverage = known_core_param_count / core_param_count`
- `claim_evidence_coverage = activated_claims_with_evidence / activated_claims`
- `comment_coverage = 1 if comments exist else 0`
- 有严重冲突时降低最后一项。

## 10. 验收

- 参数值来自 raw 参数、宣传文本或型号解析，不是写死。
- 卖点激活能拆出 `param_score`、`promo_score`、`comment_score`。
- 评论主题能展示样例句和情感。
- 评论缺失不把主题或卖点判 false。
- 未映射字段、短语、主题能进入候选诊断。
- 每个激活卖点至少带参数、宣传或评论 evidence。

