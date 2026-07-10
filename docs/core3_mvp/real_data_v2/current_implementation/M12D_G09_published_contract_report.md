# M12D-G09 发布版本与下游契约冻结报告

- 生成时间 UTC：2026-07-08T09:53:51.169345+00:00
- 项目：d8d2245b-358b-4a64-95cc-9d7f2341bd26 / TV
- 批次：m00_20260623014631_c8630747
- 版本：m12d_tv_purchase_reason_profile_v0_1_draft
- 发布模式：publish
- 版本状态：published / current=True
- Profile：377/377 已发布 current
- Anchor：3299/3299 已发布 current

## 下游读取契约

- 读取键：`category_code + project_id + batch_id + m12d_profile_version + sku_code`
- 目标 SKU `not_found` 或 `published_unusable`：阻断强排序，不临时生成成交理由。
- 候选 SKU `not_found` 或 `published_unusable`：退出强替代判断或退出 Top 3。
- `published_degraded`：可降级消费，但必须展示置信度和降级原因。
- 下游不得修改 M12D 原始锚点角色。

## Fixture 样本

| SKU | 产品 | 状态 | 下游动作 | 置信度 | 核心锚点 | 降级原因 |
| --- | --- | --- | --- | ---: | --- | --- |
| TV00029112 | 海信 65E7Q | published_degraded | degraded_pair_scoring | 0.5000 | picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture | review_required、profile_status_ready_degraded、missing_or_partial_inputs |
| TV00029936 | 创维 65A7H PRO | published_degraded | degraded_pair_scoring | 0.5000 | picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture | review_required、profile_status_ready_degraded、missing_or_partial_inputs |
| TV00027801 | TCL 65Q9L PRO | published_degraded | degraded_pair_scoring | 0.5000 | picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade | review_required、profile_status_ready_degraded、missing_or_partial_inputs |
| TV00029020 | 小米 L65MC-SP | published_degraded | degraded_pair_scoring | 0.5000 | picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture | review_required、profile_status_ready_degraded、missing_or_partial_inputs |
| TV00028829 | 创维 65A6F ULTRA | published_degraded | degraded_pair_scoring | 0.5000 | picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture | review_required、profile_status_ready_degraded、missing_or_partial_inputs |

## 缺失/未发布 Fixture

- 缺失 SKU：not_found / block_target_or_drop_candidate
- 未发布版本：not_found / block_target_or_drop_candidate

## 下一步

- CA-G01 可以基于本 fixture 实现竞品智能体侧 M12D reader。
- CA-G01 不得在竞品智能体中生成或修正 M12D。
