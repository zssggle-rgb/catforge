# M12D-RP-G03 TV/AC 购买阻力影子测算

- 生成时间：`2026-07-11T16:43:59.241141+00:00`
- 性质：205 当前发布范围只读测算；未写生产表、未发布新版本。
- 评论口径：完整维度统计负责量化，原始评论及 evidence_id 负责举证。
- 不变量：购买阻力与理由成立分离，压力不得修改旧评分、角色和画像决策。

## TV

- SKU：`377`；命中阻力：`339`。
- 阻力锚点：`1921`；旧结果变化：`0`。
- 无来源阻力标签：`0`。
- 压力等级：`{"critical": 230, "high": 816, "low": 82, "medium": 793, "none": 1621}`。
- 压力类型：`{"evidence_misalignment": 230, "localized_negative": 749, "m12c_value_headwind": 1159, "market_uncertainty": 45, "mixed_feedback": 1176, "negative_dominant": 31}`。
- 比较限制：`{"comment_subdimension_distribution_unavailable": 1059, "m12c_amount_not_quantifiable": 871, "m12c_relative_comparison_limited": 448, "market_pool_insufficient": 8, "price_band_sample_insufficient": 20, "size_pool_insufficient": 20, "size_pool_limited": 25}`。
- 未影响回归样本：`20`；无压力样本：`20`。

## AC

- SKU：`155`；命中阻力：`144`。
- 阻力锚点：`1215`；旧结果变化：`0`。
- 无来源阻力标签：`0`。
- 压力等级：`{"critical": 35, "high": 802, "low": 10, "medium": 368, "none": 664}`。
- 压力类型：`{"evidence_misalignment": 35, "localized_negative": 778, "m12c_value_headwind": 982, "market_uncertainty": 104, "mixed_feedback": 1062, "negative_dominant": 15}`。
- 比较限制：`{"comment_subdimension_distribution_unavailable": 736, "m12c_amount_not_quantifiable": 975, "m12c_relative_comparison_limited": 174, "market_pool_insufficient": 48, "market_pool_limited": 56, "price_band_sample_insufficient": 4, "size_pool_insufficient": 4}`。
- 未影响回归样本：`20`；无压力样本：`11`。

## 验收

- 三张 M12D 表前后快照一致：`True`。
- G03 验收：`通过`。
- 未通过项：`[]`。
