# M12D-QF-11 TV/AC Anchor Scoring Shadow

- 生成时间：`2026-07-11T10:36:38.456598+00:00`
- 范围：只比较锚点评分、置信度和角色；不写画像、状态、复核或发布结果。

| 品类 | SKU | 锚点 | 评分业务字段变化 | 非目标字段变化 | 移除全局 missing 风险 |
| --- | ---: | ---: | ---: | ---: | ---: |
| TV | 377 | 3542 | 2433 | 0 | 749 |
| AC | 155 | 1879 | 1776 | 0 | 154 |

## TV

- 角色迁移：`{'core_payment->core_payment': 632, 'core_payment->supporting': 434, 'core_payment->weak_expression': 40, 'risk_drag->core_payment': 82, 'risk_drag->risk_drag': 242, 'risk_drag->supporting': 211, 'risk_drag->weak_expression': 161, 'supporting->core_payment': 93, 'supporting->supporting': 948, 'supporting->weak_expression': 157, 'weak_expression->supporting': 31, 'weak_expression->weak_expression': 511}`
- 强度迁移：`{'insufficient->insufficient': 245, 'insufficient->medium': 211, 'insufficient->strong': 82, 'insufficient->weak': 197, 'medium->insufficient': 4, 'medium->medium': 946, 'medium->strong': 93, 'medium->weak': 152, 'strong->medium': 420, 'strong->strong': 648, 'strong->weak': 41, 'weak->insufficient': 2, 'weak->medium': 31, 'weak->weak': 470}`
- 应用的 scoped issue：`{'comment_claim_contradiction': 998, 'm09c_primary_relation_unavailable': 71, 'm10c_primary_relation_unavailable': 707, 'm11c_primary_relation_unavailable': 390, 'm12c_related_claim_negative': 440, 'market_pool_insufficient': 8, 'price_band_sample_insufficient': 20, 'size_pool_insufficient': 20, 'size_pool_limited': 25}`
- 新全局 missing 风险：`0`
- info 误影响：`0`
- blocking 成为 core：`0`
- 非目标字段回归样本：`20`

## AC

- 角色迁移：`{'core_payment->core_payment': 70, 'risk_drag->core_payment': 410, 'risk_drag->risk_drag': 191, 'risk_drag->supporting': 594, 'risk_drag->weak_expression': 298, 'supporting->core_payment': 55, 'supporting->supporting': 63, 'supporting->weak_expression': 5, 'weak_expression->supporting': 45, 'weak_expression->weak_expression': 148}`
- 强度迁移：`{'insufficient->insufficient': 208, 'insufficient->medium': 553, 'insufficient->strong': 451, 'insufficient->weak': 295, 'medium->medium': 50, 'medium->strong': 33, 'medium->weak': 5, 'strong->medium': 3, 'strong->strong': 102, 'weak->medium': 45, 'weak->weak': 134}`
- 应用的 scoped issue：`{'comment_claim_contradiction': 462, 'm09c_primary_relation_unavailable': 7, 'm10c_primary_relation_unavailable': 115, 'm11c_primary_relation_unavailable': 10, 'm12c_related_claim_negative': 468, 'market_pool_insufficient': 87, 'market_pool_limited': 87, 'price_band_sample_insufficient': 9, 'size_pool_insufficient': 9}`
- 新全局 missing 风险：`0`
- info 误影响：`0`
- blocking 成为 core：`0`
- 非目标字段回归样本：`20`

## 验收

- M12D 持久化表未变化：`True`
- 候选锚点集合、source refs、支持摘要和 input fingerprint 不变；评分域可因剔除无关 M12C 而变化。
- `missing_or_partial_inputs` 不再进入锚点风险、分数或置信度。
- TV/AC 使用各自 taxonomy；本任务未写 current/published。
