# M12D-QF-15A TV 139 个无核心 SKU 证据缺口与门槛反事实审计

- 生成时间：`2026-07-11T14:46:12.037421+00:00`
- 口径：沿用 QF15 当前真实参数、卖点、评论、市场和语义证据，只读重算。
- 禁止项：未补造评论、未修改生产评分、未写数据库、未发布 current、未运行竞品智能体。
- 基线：TV `377` 个；状态 `{'ready': 238, 'ready_limited': 94, 'weak_expression_only': 45}`；无核心 `139` 个。

## 1. 反事实测算

| 方案 | 新增核心 SKU | 其中证据越界 | 需抽检 | ready率 | ready+limited率 | 无核心率 | 改动既有 ready 核心 | 重点 SKU 变化 | 过发布门槛 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 现行门槛 | 0 | 0 | 0 | 0.6313 | 0.8806 | 0.3687 | 0 | 0 | 否 |
| 强证据分数 9.0 降至 8.5，其余门槛不变 | 0 | 0 | 0 | 0.6313 | 0.8806 | 0.3687 | 0 | 0 | 否 |
| 强证据分数 9.0 降至 8.0，其余门槛不变 | 47 | 25 | 47 | 0.7560 | 0.8912 | 0.2440 | 56 | 0 | 否 |
| 仅无核心 SKU 启用 8.0 分兜底，并排除冲突、负向和样本风险 | 29 | 0 | 29 | 0.7082 | 0.8859 | 0.2918 | 0 | 0 | 否 |
| 仅客观性价比理由使用参数+市场+场景替代价格价值门槛 | 0 | 0 | 0 | 0.6313 | 0.8806 | 0.3687 | 0 | 0 | 否 |
| 客观性价比门槛分型，并将强证据分数降至 8.5 | 0 | 0 | 0 | 0.6313 | 0.8806 | 0.3687 | 0 | 0 | 否 |
| 所有价格理由取消价格价值门槛，并将强证据分数降至 8.0 | 48 | 27 | 48 | 0.7586 | 0.8939 | 0.2414 | 57 | 0 | 否 |

## 2. 审计结论

- 逐 SKU 建议分布：`{'不应放宽': 110, '可谨慎放宽': 29}`。
- `可谨慎放宽` 使用无核心画像专属的 8 分兜底：仍要求至少两个强证据域和场景成立，价格理由仍保留现行支付证据门槛，并逐锚点排除评论冲突、M12C 负向和市场样本不足。
- 评论感知必须在 M05C 原始事实中存在与购买理由同维度的正向评论；泛化好评、服务评论或其他体验维度不能替代。
- 单独放宽客观性价比价格门槛新增 0 个 SKU，因此没有必要修改价格门槛。
- 画质升级值不值、是否愿意多付等主观支付理由仍要求 M12C，或评论感知与市场承接同时成立，不能用参数和销量替代用户支付意愿。
- 单纯把强证据分数从 9.0 降到 8.5/8.0 的新增结果标记为人工抽检，不自动判定安全。
- 任何包含真实拖累、评论冲突、M12C 负向或样本不足的新增核心均计为证据越界。

## 3. 可谨慎放宽 SKU

| SKU | 产品 | 当前状态 | 放宽后核心理由 | 入选分数 | 入选证据域 |
| --- | --- | --- | --- | --- | --- |
| TV00026106 | 小米 L75MA-SPL | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00027511 | 红米 L65RB-APE | ready_limited | same_size_picture_step_up、living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00027523 | 海信 55E5Q | ready_limited | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00027541 | 海信 65E5Q | ready_limited | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade、living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00027737 | 红米 L50RB-RAE | ready_limited | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00027780 | 创维 85V58F | ready_limited | same_size_picture_step_up | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00027999 | 海信 98E3Q-PRO | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00028078 | 海信 50E5Q | ready_limited | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00028205 | 海信 50D30QD | ready_limited | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00028425 | 创维 85A5F MINI | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00028426 | VIDDA 100VX3Q | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00028546 | 海信 65D30QD | weak_expression_only | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00028556 | 酷开 43P3F | ready_limited | low_price_core_experience_intact | 8.0000 | claim_position、comment_perception、market_acceptance、param_fact |
| TV00028569 | 创维 75A7F | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00028775 | 长虹 43Z60H | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00028902 | 长虹 100Z60H | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00028905 | 创维 100A6F ULTRA | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00029099 | VIDDA 100VX5Q | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00029111 | 海信 65E3QH-PRO | ready_limited | same_size_picture_step_up、living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00029113 | 海信 75E3QH-PRO | weak_expression_only | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade、living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00029193 | 海信 55E3QH-PRO | ready_limited | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00029204 | 创维 100A5F MINI | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00029783 | 红米 L75RC-RX | ready_limited | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade、living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00029937 | 创维 75A7H | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00030137 | 海信 65E3S-PRO+ | ready_limited | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade、living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00030138 | 海信 75E3S-PRO+ | ready_limited | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade、living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00030199 | 海信 100E7S-PRO | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00030314 | TCL 75T7M ULTRA | ready_limited | living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |
| TV00030361 | 创维 85AC11H | ready_limited | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade、living_room_upgrade_one_step | 8.0000 | comment_perception、market_acceptance、param_fact、semantic_scene |

## 4. 边界说明

- JSON 保留 139 个 SKU 的全部候选理由、证据域、分数、风险标记和各方案结果。
- CSV 提供逐 SKU 主结论，便于业务抽检。
- 本审计只回答门槛可否放宽，不代表 QF15 已解除阻塞；生产改动必须另立任务并通过抽检回归。
