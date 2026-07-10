# M12D-G07 小批量验证与规则修正记录

- 生成时间 UTC：2026-07-08T09:14:24.902273+00:00
- 项目：d8d2245b-358b-4a64-95cc-9d7f2341bd26 / TV
- 请求批次：latest
- 解析批次：serving-scope:TV:m00_20260623014631_c8630747,m00_20260619084551_857df63b,m00_20260613004311_d548f6dc
- 样本数：12
- 口径：只读当前 Core3 TV 结果；本脚本只调用 M12D 单 SKU 预览服务，不写入生产表。

## 汇总

- 低置信 SKU：6
- 需复核 SKU：12
- 有核心成交理由 SKU：6
- 有风险拖拽 SKU：0
- 预算价值误判为核心：0

## SKU 明细

| SKU | 产品 | 状态 | 置信度 | 核心成交理由 | 弱表达 | 风险 | 非 ready 输入 |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| TV00029112 | 海信 65E7Q | 可用但降级 | 50% | 画质配置解释加价、同尺寸画质越级获得感、贵得值的体验升级、影音用户愿为画质升级付费 | 同价位核心配置获得感、家庭多设备使用更省操作 | - | 参数事实:冲突、卖点事实:部分可用、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:部分可用 |
| TV00029936 | 创维 65A7H PRO | 可用但降级 | 50% | 画质配置解释加价、同尺寸画质越级获得感、贵得值的体验升级、影音用户愿为画质升级付费 | 家庭多设备使用更省操作、新家客厅审美适配 | - | 参数事实:冲突、卖点事实:部分可用、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:部分可用 |
| TV00027801 | TCL 65Q9L PRO | 可用但降级 | 50% | 画质配置解释加价、同尺寸画质越级获得感、贵得值的体验升级 | 家庭多设备使用更省操作、新家客厅审美适配 | - | 参数事实:冲突、卖点事实:部分可用、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:部分可用 |
| TV00029020 | 小米 L65MC-SP | 可用但降级 | 50% | 画质配置解释加价、同尺寸画质越级获得感、贵得值的体验升级、影音用户愿为画质升级付费 | 新家客厅审美适配 | - | 参数事实:冲突、卖点事实:部分可用、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:部分可用 |
| TV00028829 | 创维 65A6F ULTRA | 可用但降级 | 50% | 画质配置解释加价、同尺寸画质越级获得感、贵得值的体验升级、影音用户愿为画质升级付费 | 家庭多设备使用更省操作、新家客厅审美适配 | - | 参数事实:冲突、卖点事实:部分可用、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:部分可用 |
| TV00027774 | 红米 L70RB-RAE | 可用但降级 | 30% | - | - | - | 参数事实:冲突、卖点事实:部分可用、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:缺失 |
| TV00027914 | 海信 100E5Q-PRO | 可用但降级 | 30% | - | 家庭多设备使用更省操作 | - | 参数事实:冲突、卖点事实:缺失、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:缺失 |
| TV00028108 | 创维 50A3F | 可用但降级 | 50% | 画质配置解释加价、低价不明显牺牲核心体验、同价位核心配置获得感、贵得值的体验升级、影音用户愿为画质升级付费 | 家庭多设备使用更省操作 | - | 参数事实:冲突、卖点事实:部分可用、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:部分可用 |
| TV00028200 | 创维 T60D | 可用但降级 | 30% | - | 家庭多设备使用更省操作 | - | 参数事实:冲突、卖点事实:部分可用、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:缺失 |
| TV00028205 | 海信 50D30QD | 可用但降级 | 30% | - | 家庭多设备使用更省操作 | - | 参数事实:冲突、卖点事实:缺失、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:缺失 |
| TV00027887 | 海信 85E5Q-PRO | 可用但降级 | 30% | - | 家庭多设备使用更省操作 | - | 参数事实:冲突、卖点事实:缺失、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:缺失 |
| TV00027552 | 红米 L43RA-RAE | 可用但降级 | 30% | - | - | - | 参数事实:冲突、卖点事实:部分可用、评论感知:部分可用、市场承接:部分可用、任务/客群/战场语义:部分可用、支付价值:缺失 |

## 低置信与复核清单

### 低置信 SKU
- TV00027774 红米 L70RB-RAE：30%，core=-
- TV00027914 海信 100E5Q-PRO：30%，core=-
- TV00028200 创维 T60D：30%，core=-
- TV00028205 海信 50D30QD：30%，core=-
- TV00027887 海信 85E5Q-PRO：30%，core=-
- TV00027552 红米 L43RA-RAE：30%，core=-
### 需复核 SKU
- TV00029112 海信 65E7Q：50%，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture
- TV00029936 创维 65A7H PRO：50%，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture
- TV00027801 TCL 65Q9L PRO：50%，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade
- TV00029020 小米 L65MC-SP：50%，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture
- TV00028829 创维 65A6F ULTRA：50%，core=picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture
- TV00027774 红米 L70RB-RAE：30%，core=-
- TV00027914 海信 100E5Q-PRO：30%，core=-
- TV00028108 创维 50A3F：50%，core=picture_upgrade_justifies_price、low_price_core_experience_intact、same_price_core_config_gain、worth_paying_more_for_experience_upgrade、av_user_willing_to_pay_for_picture
- TV00028200 创维 T60D：30%，core=-
- TV00028205 海信 50D30QD：30%，core=-
- TV00027887 海信 85E5Q-PRO：30%，core=-
- TV00027552 红米 L43RA-RAE：30%，core=-
### 风险拖拽 SKU
- 无

## 65E7Q 预算价值检查

- 状态：passed
- 结论：65E7Q 的同价位核心配置获得感保持为弱表达，未误判为强核心成交理由。

## 规则修正记录

### serving_scope_context_lookup
- 状态：fixed_in_g07
- 发现：G07 验证发现 latest 会解析为 serving-scope 组合批次；M12D ContextBuilder 需要识别组合批次并按顺序读取第一个可用记录。
- 修正：已修正 ContextBuilder 批次过滤逻辑，并新增 serving-scope 回归测试。
- 证据：本轮 resolved_batch_id=serving-scope:TV:m00_20260623014631_c8630747,m00_20260619084551_857df63b,m00_20260613004311_d548f6dc。

### budget_value_65e7q_core_guardrail
- 状态：passed_no_rule_change
- 发现：65E7Q 的同价位核心配置获得感保持为弱表达，未误判为强核心成交理由。
- 修正：未修改评分规则；保留 value_price/price_value 仅弱表达封顶规则。
- 证据：65E7Q 的 same_price_core_config_gain 未进入 core_payment。

### core_anchor_with_degraded_profile
- 状态：audit_gate_recorded
- 发现：部分 SKU 存在 core_payment 锚点，但 SKU 级画像置信度仍低于 ready 门槛。
- 修正：本轮不降级锚点角色；报告消费时必须同时展示 profile_status/profile_confidence。
- 证据：详见 sample_results 中 status!=ready 且 core_payment_anchors 非空的样本。
