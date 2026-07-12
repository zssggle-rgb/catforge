# M12D-RP-G08 跨品类集成验收与上线前结论

- 生成时间：`2026-07-11T19:05:14.345262+00:00`
- 集成回归：`378 passed`。
- 数据边界：复用 G06 全量只读影子结果和 G07 竞品消费收据；未写库、未部署、未发布。

## TV

- 结论：`go_to_g09`。
- 全量 SKU：`377`；状态分布：`{"failed": 0, "missing_input": 0, "ready": 335, "ready_limited": 13, "weak_expression_only": 29}`。
- ready 比例：`0.8886`；可消费比例：`1.0000`；无核心理由比例：`0.1114`。
- 重点 SKU：`10`；未影响回归：`20`；竞品回归目标/pair：`10/90`。
- 品类 taxonomy：`m12d_tv_purchase_reason_anchor_taxonomy_v0.1`；类别隔离：`通过`。
- 检查项：`{"taxonomy_isolated": true, "sku_prefix_isolated": true, "full_scope_complete": true, "release_quality_ready": true, "all_release_thresholds_passed": true, "sku_consumable_rate_complete": true, "unaffected_regression_20": true, "focus_validation_complete": true, "g06_business_checks_passed": true, "g07_competitor_checks_passed": true}`。

## AC

- 结论：`go_to_g09`。
- 全量 SKU：`155`；状态分布：`{"failed": 0, "missing_input": 0, "ready": 143, "ready_limited": 1, "weak_expression_only": 11}`。
- ready 比例：`0.9226`；可消费比例：`1.0000`；无核心理由比例：`0.0774`。
- 重点 SKU：`18`；未影响回归：`20`；竞品回归目标/pair：`18/306`。
- 品类 taxonomy：`m12d_ac_purchase_reason_anchor_taxonomy_v0.1`；类别隔离：`通过`。
- 检查项：`{"taxonomy_isolated": true, "sku_prefix_isolated": true, "full_scope_complete": true, "release_quality_ready": true, "all_release_thresholds_passed": true, "sku_consumable_rate_complete": true, "unaffected_regression_20": true, "focus_validation_complete": true, "g06_business_checks_passed": true, "g07_competitor_checks_passed": true}`。

## QF15/QF16 回填

- QF15 历史结论：旧口径下 blocked 结论保留为历史记录；旧口径把购买理由成立度、购买阻力和版本级消费能力混在一起，不能改写成当时已通过。
- QF15 当前状态：completed_superseded_by_m12d_rp_g06_g08；新批准口径下 TV/AC 分别全量影子重算并达到 ready。
- QF16 前置：satisfied；竞品消费和 Top 3 回归已由 M12D-RP-G07 完成。
- QF17：completed_by_m12d_rp_g08；共享链路和跨品类隔离回归通过。

## 上线前结论

- G08：`通过`；失败项：`[]`。
- G09 提交部署候选：`go`。
- 当前发布：`no_go_pending_g09_g10`。
- 说明：TV/AC 均通过本地集成和影子发布门槛，可申请进入 G09 提交部署；代码尚未提交部署，205 尚未正式全量重跑，因此当前仍不可发布。
