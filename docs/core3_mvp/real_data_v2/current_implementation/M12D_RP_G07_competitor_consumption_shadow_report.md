# M12D-RP-G07 竞品智能体消费与 Top 3 回归

- 生成时间：`2026-07-11T18:53:56.997343+00:00`
- M12D 来源：只消费 G06 validated fixture；未生成、未修正、未发布 M12D。

## TV

- 目标 SKU：`10`；竞品 pair：`90`。
- proposition 画像：`2`；命中目标核心 pair：`0`；误计购买理由重合：`0`；业务语言失败：`0`。
- 替代压力/购买阻力未分开：`0`；Top 3 追溯失败：`0`。
- PM 业务语言失败：`0`。
- 检查项：`{"target_coverage": true, "tv_65e7q_covered": true, "proposition_sample_covered": true, "proposition_never_scores_as_shared_reason": true, "proposition_business_language": true, "replacement_and_purchase_pressure_separate": true, "top3_trace_complete": true, "pm_business_language_clean": true}`。

## AC

- 目标 SKU：`18`；竞品 pair：`306`。
- proposition 画像：`5`；命中目标核心 pair：`10`；误计购买理由重合：`0`；业务语言失败：`0`。
- 替代压力/购买阻力未分开：`0`；Top 3 追溯失败：`0`。
- PM 业务语言失败：`0`。
- 检查项：`{"target_coverage": true, "tv_65e7q_covered": true, "proposition_sample_covered": true, "proposition_never_scores_as_shared_reason": true, "proposition_business_language": true, "replacement_and_purchase_pressure_separate": true, "top3_trace_complete": true, "pm_business_language_clean": true}`。

## 海信 65E7Q 真实候选池回放

- 旧 Top 3：`['TV00029936', 'TV00027801', 'TV00028909']`。
- G06 消费后 Top 3：`['TV00029936', 'TV00027801', 'TV00028829']`。
- G06 validated fixture 未覆盖、因此本轮不能使用购买理由维度进入 Top 3 的候选：`['TV00028909', 'TV00027541', 'TV00027912', 'TV00028166', 'TV00027899', 'TV00027861']`。该状态只代表 G07 fixture 范围，不代表正式全量发布后缺少画像。
- 检查项：`{"three_candidates_selected": true, "fixture_uncovered_not_in_top3": true, "ranking_trace_complete": true, "no_version_wide_degradation": true, "replacement_and_purchase_pressure_separate": true, "no_threat_contradiction": true, "pm_business_language_clean": true}`。

## 总体验收

- G07：`通过`。
- 未通过项：`[]`。
