# M12D-QF-13 TV/AC Release Quality Shadow

- 生成时间：`2026-07-11T11:29:47.380897+00:00`
- 范围：只评估版本发布质量和发布守卫；不修改画像、锚点或 current/published。

| 品类 | SKU | 画像状态 | 旧版本质量 | 未做重点验证 | 假设重点验证全过 |
| --- | ---: | --- | --- | --- | --- |
| TV | 377 | `{'ready': 238, 'ready_limited': 94, 'weak_expression_only': 45}` | unassessed | limited | limited |
| AC | 155 | `{'ready': 130, 'ready_limited': 23, 'weak_expression_only': 2}` | unassessed | limited | limited |

## TV

- 指标：`{'expected_sku_count': 377, 'profile_count': 377, 'unique_sku_count': 377, 'status_counts': {'failed': 0, 'missing_input': 0, 'ready': 238, 'ready_limited': 94, 'weak_expression_only': 45}, 'ready_count': 238, 'ready_limited_count': 94, 'review_required_count': 0, 'missing_input_count': 0, 'failed_count': 0, 'profile_gap_count': 0, 'core_payment_missing_count': 139, 'focus_validation_evaluated': False, 'focus_validation_count': 0, 'generation_success_rate': '1.0000', 'ready_rate': '0.6313', 'ready_or_limited_rate': '0.8806', 'review_required_rate': '0.0000', 'missing_or_failed_rate': '0.0000', 'core_payment_missing_rate': '0.3687', 'focus_sku_pass_rate': None}`
- 未通过项：`['ready_rate', 'ready_or_limited_rate', 'core_payment_missing_rate', 'focus_sku_pass_rate']`
- 假设重点 SKU 全过后的未通过项：`['ready_rate', 'ready_or_limited_rate', 'core_payment_missing_rate']`
- blocking 覆盖：`[]`
- release-level system issue：`[]`
- 画像字段未变化：`True`
- 未影响回归样本：`20`

## AC

- 指标：`{'expected_sku_count': 155, 'profile_count': 155, 'unique_sku_count': 155, 'status_counts': {'failed': 0, 'missing_input': 0, 'ready': 130, 'ready_limited': 23, 'weak_expression_only': 2}, 'ready_count': 130, 'ready_limited_count': 23, 'review_required_count': 0, 'missing_input_count': 0, 'failed_count': 0, 'profile_gap_count': 0, 'core_payment_missing_count': 25, 'focus_validation_evaluated': False, 'focus_validation_count': 0, 'generation_success_rate': '1.0000', 'ready_rate': '0.8387', 'ready_or_limited_rate': '0.9871', 'review_required_rate': '0.0000', 'missing_or_failed_rate': '0.0000', 'core_payment_missing_rate': '0.1613', 'focus_sku_pass_rate': None}`
- 未通过项：`['ready_rate', 'core_payment_missing_rate', 'focus_sku_pass_rate']`
- 假设重点 SKU 全过后的未通过项：`['ready_rate', 'core_payment_missing_rate']`
- blocking 覆盖：`[]`
- release-level system issue：`[]`
- 画像字段未变化：`True`
- 未影响回归样本：`20`

## 验收

- M12D 持久化表未变化：`True`
- TV/AC 分母、taxonomy、版本和结果完全隔离，没有跨品类平均。
- 当前两个品类均应保持 limited；即使假设重点 SKU 全过，现有画像门槛仍未全部通过。
- 当前真实数据没有 blocking issue，因此不生成虚假系统阻断；20%/21% 边界由单元测试覆盖。
- blocked/unassessed 发布拒绝、limited 人工批准和下游降级由 repository/contract 测试覆盖。
- 历史已发布 unassessed 版本保持原画像级消费行为，避免仅部署代码就先改变线上排序；新 unassessed 版本仍禁止发布。
