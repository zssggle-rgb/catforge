# 03b 真实数据抽取框架

## 1. 目标

本设计说明如何从真实 PostgreSQL 数据里抽取参数、卖点、评论主题、任务、客群、价值战场和证据。预制知识只是识别框架；SKU 结果必须由数据激活。

主链路：

```text
raw_sku_master / raw_sku_param / raw_sku_claim / raw_sku_comment / raw_market_fact
  -> 字段画像与数据剖析
  -> 预制别名匹配
  -> 参数值解析与单位归一
  -> 宣传文本切句与卖点命中
  -> 评论切句、主题分类、情感判断
  -> 未映射字段/短语/主题发现
  -> SKU 特征快照
  -> 任务/客群/战场派生
  -> evidence graph
```

## 2. 字段画像

抽取前先 profiling，不直接按固定字段读取。

### 2.1 参数字段画像

对 `raw_sku_param.raw_param_name` 聚合：

- 出现次数。
- 覆盖 SKU 数。
- 非空率。
- 唯一值数量。
- top raw values。
- 是否包含数字和单位。
- 与预制 alias 的匹配结果。

输出：

```json
{
  "raw_param_name": "峰值亮度",
  "sku_coverage": 0.62,
  "non_empty_rate": 0.94,
  "top_values": ["1200nits", "1600尼特"],
  "matched_param_code": "peak_brightness_nits",
  "match_confidence": 0.92,
  "status": "mapped"
}
```

### 2.2 宣传文本画像

对 `claim_title` 和 `claim_text`：

- 分句。
- 高频短语。
- 可解析数值片段。
- 与预制 claim keywords 匹配。
- 覆盖 SKU 数。
- 与参数、价格、销量、评论主题的共现关系。

### 2.3 评论文本画像

对 `comment_text`：

- 分句。
- 产品体验句 vs 服务体验句。
- 主题命中。
- 正/负/中性情感。
- 高频未映射短语。
- 样例句。

## 3. 参数抽取

### 3.1 来源优先级

默认优先级：

```text
raw_param exact alias
  > raw_param fuzzy alias
  > claim_text numeric extraction
  > model_name extraction
  > comment weak hint
```

评论只能作为弱提示，不能直接证明硬参数。

### 3.2 字段名匹配

步骤：

1. 标准化字段名：去空格、大小写统一、全角半角统一、符号清理。
2. 精确 alias 匹配。
3. 包含 alias 匹配。
4. token 匹配。
5. 同义词匹配。
6. 高覆盖未知字段进入候选别名。

置信度：

| 匹配方式 | 置信度 |
| --- | --- |
| 精确 alias | 0.95 |
| 包含 alias | 0.85 |
| token 同义 | 0.75 |
| 文本数值抽取 | 0.65-0.85 |
| 评论弱提示 | 0.30-0.50 |

### 3.3 值解析器

必须实现：

| parser | 示例 | 输出 |
| --- | --- | --- |
| `inch` | `85英寸`, `85"` | `85` |
| `hz` | `144Hz`, `120赫兹` | `144` |
| `nits` | `1600nits`, `1600尼特` | `1600` |
| `zones` | `1296分区`, `千级分区` | `1296` 或区间 |
| `gb` | `4GB+64GB` | RAM/ROM 分拆 |
| `ports` | `2个HDMI2.1` | `2` |
| `resolution` | `4K`, `3840*2160`, `8K` | `4K` / `8K` |
| `percentage` | `95% DCI-P3` | `95` + standard |
| `watt` | `60W` | `60` |
| `ms` | `8ms` | `8` |
| `boolean_keyword` | `支持VRR`, `无频闪` | true |
| `enum_keyword` | `OLED`, `Mini LED` | enum |

### 3.4 冲突处理

同一 SKU 同一参数多个候选值：

1. 来源优先级高者优先。
2. 同来源下置信度高者优先。
3. 数值冲突大时标记 `conflict`。
4. 可共存口径拆成不同 param_code，例如原生刷新率和系统刷新率。

输出：

```json
{
  "param_code": "peak_brightness_nits",
  "normalized_value": 1600,
  "unit": "nits",
  "source": "raw_param",
  "confidence": 0.92,
  "evidence_ids": [],
  "candidates": [],
  "conflicts": []
}
```

## 4. 卖点抽取与激活

卖点激活由三类证据合成：

- 参数证据。
- 宣传证据。
- 评论证据。

### 4.1 参数证据

例如 `CLAIM_HIGH_BRIGHTNESS_HDR`：

```text
peak_brightness_nits >= 1000 -> param_score 0.75
peak_brightness_nits >= 2000 -> param_score 0.90
peak_brightness_nits >= 3000 -> param_score 1.00
```

### 4.2 宣传证据

对 `claim_text` 分句后匹配：

- keyword。
- numeric pattern。
- phrase pattern。
- 否定词窗口。

否定词：

- 不支持
- 非
- 无
- 不是

命中句子进入 evidence。

### 4.3 评论证据

评论只作为体验验证。

例如：

- 多条“看球不卡”评论可增强 `CLAIM_HIGH_REFRESH_RATE` 的 comment_score。
- 但不能在没有参数/宣传证据时直接证明 120Hz。

### 4.4 激活分

```text
activation_score =
  normalized_known(param_score * param_weight
  + promo_score * promo_weight
  + comment_score * comment_weight)
```

默认权重：

- 技术型：参数 0.55，宣传 0.35，评论 0.10。
- 体验型：参数 0.30，宣传 0.30，评论 0.40。
- 市场型：市场 0.50，宣传 0.20，评论 0.30。

## 5. 新卖点发现

从宣传文本中发现未映射候选卖点。

进入候选的条件：

- 高频短语覆盖 SKU 数 >= 5。
- 与现有 claim 相似度低。
- 与某些参数或评论主题共现。
- 对价格或销量有区分度。

输出：

```json
{
  "candidate_claim_code": "CAND_CLAIM_AI_PICTURE_CHIP",
  "raw_phrase": "AI画质芯片",
  "coverage": 0.18,
  "example_skus": [],
  "cooccur_params": [],
  "suggested_group": "picture",
  "review_status": "pending"
}
```

候选卖点不参与高置信结论，除非人工批准或映射到已有 claim。

## 6. 评论主题抽取

### 6.1 切句

按中文标点、换行和长度切分。

保留：

- `comment_id`
- `sentence_index`
- 原句。
- SKU。

### 6.2 产品/服务分类

分类：

- `product_experience`
- `service_experience`
- `logistics_installation`
- `price_value`
- `unknown`

服务体验不直接激活产品卖点。

### 6.3 多标签主题分类

规则：

1. seed topic keywords 命中。
2. 同义词命中。
3. 负面词窗口识别。
4. 一个句子最多保留 top3 topic。

输出：

```json
{
  "topic_code": "TOPIC_GAMING_SMOOTHNESS",
  "sentence": "接游戏主机很流畅，没有明显延迟",
  "sentiment": "positive",
  "confidence": 0.82,
  "evidence_id": "..."
}
```

### 6.4 情感判断

第一版用规则：

- 正向词：好、清晰、流畅、满意、舒服、方便、够用。
- 负向词：卡、慢、刺眼、反光、漏光、拖影、麻烦、广告多。
- 否定窗口：不、没有、无、没。

无法判断则 `neutral`。

### 6.5 新主题发现

未映射评论句中发现候选主题：

- 高频短语或聚类覆盖 SKU 数 >= 5。
- 与现有 topic 低相似。
- 具备明确产品/服务类型。
- 有正/负情感样例。

候选主题只进入复核，不自动进入正式评分。

## 7. 任务、客群、战场派生

任务、客群、战场不从原始文本直接抽标签，而是从数据证据派生。

### 7.1 任务

例如 `TASK_GAMING_ENTERTAINMENT`：

```text
claim_signal = avg(CLAIM_HIGH_REFRESH_RATE, CLAIM_HDMI_2_1_GAMING, CLAIM_GAMING_LOW_LATENCY)
param_signal = avg(refresh_rate_hz, hdmi_2_1_ports, vrr_flag, input_lag_ms)
comment_signal = TOPIC_GAMING_SMOOTHNESS positive mention rate
market_signal = online channel share + sales percentile in gaming candidate pool
```

### 7.2 客群

```text
TG_GAMER =
  TASK_GAMING_ENTERTAINMENT * 0.70
  + online_channel_fit * 0.15
  + price_band_fit * 0.15
```

### 7.3 战场

```text
BF_GAMING_SPORTS =
  semantic_score * 0.65
  + market_score * 0.35
```

market_score 必须由价格、销量、渠道、趋势组成。

## 8. Evidence graph

每个最终结论要能追溯：

```text
raw row -> evidence_item -> normalized param / claim activation / topic -> task/group/battlefield -> competitor result
```

证据分层：

- raw evidence：来自原始行。
- derived evidence：来自聚合指标或规则计算。
- rule_ref：来自 seed asset，不算 evidence_id，但要记录 rule_version。

## 9. 候选资产输出

抽取会产生三类候选：

- `candidate_param_alias`
- `candidate_claim`
- `candidate_comment_topic`

字段：

- raw phrase / raw field。
- coverage。
- examples。
- suggested mapping。
- confidence。
- evidence ids。
- review status。

第一版可放入 `core3_pipeline_run.diagnostics` 或 `core3_sku_feature_profile.extraction_diagnostics`，后续再独立建表。

## 10. 验收

- 参数值来自 raw 参数或文本解析，不是硬编码 SKU 结果。
- 卖点激活能拆出 param/promo/comment 分。
- 评论主题能展示样例句。
- 新字段、新短语、新主题能进入候选，不自动生效。
- 任务、客群、战场由 SKU 证据派生，不是写死在 SKU 上。

