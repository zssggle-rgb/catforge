# 05 任务、客群、价值战场评分模块

## 1. 模块目标

基于市场画像、标准参数、卖点激活和评论主题，推导目标 SKU 的用户任务、目标客群和价值战场。

任务、客群、战场是预制业务本体，但 SKU 是否进入这些任务/客群/战场必须由真实数据证据派生，不能按 SKU 或型号写死。

依赖：

- [彩电预制知识资产目录](03a_preset_asset_catalog.md)
- [真实数据抽取框架](03b_real_data_extraction.md)

## 2. 输入输出

输入：

- `MarketProfile`
- `standard_params`
- `claim_activations`
- `comment_topics`
- `PresetAssetCatalog`

输出：

- `task_scores`
- `target_group_scores`
- `battlefield_scores`
- task/group/battlefield evidence
- 更新 `core3_sku_feature_profile`

## 3. 预制与派生边界

预制：

- 任务定义。
- 任务需要的参数、卖点、评论主题和市场信号。
- 任务到客群、战场的映射。
- 战场语义权重和量价权重。

派生：

- 某 SKU 的任务得分。
- 某 SKU 的目标客群得分。
- 某 SKU 的价值战场得分。
- 得分原因、缺失信号和 evidence。

预制规则本身记录为 `rule_ref` 和 `rule_version`，不算 evidence_id。

## 4. 用户任务派生

任务分由四类信号计算：

```text
task_score =
  claim_signal * claim_weight
  + param_signal * param_weight
  + comment_signal * comment_weight
  + market_signal * market_weight
```

每个任务可以在 seed 中覆盖权重。默认：

```text
claim 0.40
param 0.25
comment 0.20
market 0.15
```

示例 `TASK_GAMING_ENTERTAINMENT`：

```text
claim_signal =
  avg(CLAIM_HIGH_REFRESH_RATE, CLAIM_HDMI_2_1_GAMING, CLAIM_GAMING_LOW_LATENCY)

param_signal =
  avg(native_refresh_rate_hz level, hdmi_2_1_ports level, vrr_flag, input_lag_ms inverse level)

comment_signal =
  TOPIC_GAMING_SMOOTHNESS positive mention rate

market_signal =
  online channel share + sales percentile in gaming candidate pool
```

输出：

```json
{
  "task_code": "TASK_GAMING_ENTERTAINMENT",
  "score": 0.81,
  "relation_level": "main",
  "reason": "高刷、HDMI 2.1、游戏评论和线上渠道共同支持",
  "evidence_ids": [],
  "missing_signals": []
}
```

## 5. 目标客群派生

客群由任务和市场位置推导，不从 raw 文本直接抽标签。

默认公式：

```text
group_score =
  source_task_score * 0.60
  + price_channel_fit * 0.20
  + comment_validation * 0.20
```

示例：

```text
TG_GAMER =
  TASK_GAMING_ENTERTAINMENT * 0.70
  + online_channel_fit * 0.15
  + price_band_fit * 0.15
```

```text
TG_VALUE_BUYER =
  TASK_VALUE_PURCHASE * 0.60
  + low_price_percentile_fit * 0.20
  + high_sales_percentile_fit * 0.20
```

## 6. 价值战场派生

价值战场由语义分和市场分共同决定。只有语义信号而没有量价市场支撑时，不能输出高置信战场。

```text
final_battlefield_score =
  semantic_score * semantic_weight
  + market_score * market_weight
```

战场权重来自预制知识。示例：

| battlefield_code | semantic_weight | market_weight |
| --- | --- | --- |
| `BF_PREMIUM_PICTURE` | 0.70 | 0.30 |
| `BF_FAMILY_VIEWING_UPGRADE` | 0.65 | 0.35 |
| `BF_GAMING_SPORTS` | 0.65 | 0.35 |
| `BF_LARGE_SCREEN_VALUE` | 0.55 | 0.45 |
| `BF_FAMILY_EYE_CARE` | 0.70 | 0.30 |
| `BF_SENIOR_EASE_OF_USE` | 0.70 | 0.30 |
| `BF_SMART_SYSTEM_EXPERIENCE` | 0.60 | 0.40 |
| `BF_CINEMA_AUDIO_IMMERSION` | 0.65 | 0.35 |
| `BF_DESIGN_HOME_FIT` | 0.55 | 0.45 |
| `BF_SERVICE_ASSURANCE` | 0.45 | 0.55 |

## 7. 战场语义分

```text
semantic_score =
  core_task_score * 0.40
  + core_claim_combo_score * 0.35
  + comment_validation_score * 0.15
  + target_group_score * 0.10
```

`core_claim_combo_score` 由每个战场预制规则定义：

- 高端画质：Mini LED/OLED + 高亮度 + 精细分区 + 画质评论。
- 游戏体育：高刷 + HDMI 2.1 + 低延迟 + 运动/游戏评论。
- 家庭观影：大屏 + HDR + 音效 + 家庭观影评论。
- 大屏性价比：尺寸 + 价格/英寸 + 销量 + 性价比评论。
- 家庭护眼：护眼参数 + 护眼评论 + 负面低。
- 长辈易用：语音/长辈模式 + 易用评论 + 系统风险低。

## 8. 战场市场分

```text
market_score =
  price_position_fit * 0.30
  + sales_validation * 0.25
  + channel_fit * 0.15
  + trend_signal * 0.15
  + comparable_pool_strength * 0.15
```

说明：

- 高端画质：高价格分位、销额不弱、卖点能支撑价格。
- 游戏体育：线上渠道、高刷池销量、价格性能比、近期增长。
- 大屏性价比：同尺寸价格吸引力、销量强、降价下探。
- 护眼/长辈：评论支持、销量稳定、价格不过高。
- 服务保障：服务评论、安装风险、渠道稳定性。

## 9. 关系级别

```text
main: final_score >= 0.75
secondary: 0.55 <= final_score < 0.75
weak: 0.35 <= final_score < 0.55
```

低于 0.35 不输出正式战场，但可以进入 diagnostics。

## 10. 证据

每个任务、客群、战场汇总 evidence：

- 参数 evidence。
- 卖点 evidence。
- 评论 evidence。
- 市场画像 evidence。

输出必须说明：

- 哪些信号支持。
- 哪些信号缺失。
- 哪些信号冲突。

## 11. 更新落库

更新 `core3_sku_feature_profile`：

- `task_scores`
- `target_group_scores`
- `battlefield_scores`
- `feature_evidence_ids`
- `missing_signals`
- `confidence`

## 12. 验收

- 任务、客群、战场不能以 SKU code 维度写死。
- 价值战场必须包含 `semantic_score` 和 `market_score`。
- 修改价格/销量后，战场最终分应变化。
- 修改参数/卖点/评论后，对应任务和语义分应变化。
- 任务和战场输出必须带 evidence。
- 没有量价时不能输出高置信战场。
- 目标 SKU 至少能得到主战场或明确不足原因。

