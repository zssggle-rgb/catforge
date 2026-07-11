# G08R1 Repair Contract

## 1. 目标

只修复 G08 已证实的 B01-B08，不扩大功能范围，不生成自动定价或产品动作。修复后的功能仍然回答：用户购后实际感知到什么价值；该价值在市场选择和价格上最多被观察到哪一层。

## 2. Lineage 与确定性 hash

1. 同 module、同 rule version、同 serving batch 只有在规范化 `source_hash` 也相同时才能 `aligned`；
2. rule version 不同但规范化 hash 相同可 `stale_revalidated`；
3. hash 缺失为 `unresolved`，hash 不同为局部 `stale_conflict`；
4. 所有 authority refs 在 hash 前按 `(module_code, record_type, record_id, result_hash, batch_id)` 排序；
5. 同一数据库内容不同返回顺序必须产生相同 input/result hash。

## 3. 候选分层预算

1. M14/fallback recall cap：30；
2. 进入完整 snapshot：最多 12；选择时保留 declared role 覆盖、model family 多样性和排名；
3. 完成事实、角色和可比性判断后，每个 `base_value/same_value/stretch_benchmark` 最多保留 3；
4. 截断必须确定性，不能在总计 3 个候选处提前停止；
5. Q5 仍要求至少两个独立 A 级 base pair、至少两个 model family。

## 4. Market cell 与 M11D 边界

1. DB 查询最多读取 2,001 个合格 weekly rows，用第 2,001 个判断超限；
2. 超限时按最新完整 `(period_week_index, platform_type)` cell group 保留不超过 2,000 行，不保留半个 group；
3. 结果必须记录 `market_cells_truncated`，且默认阻断 Q5，避免静默改变识别窗口；
4. M11D allocation 不改变 target/candidate 真实销量和选择份额分子分母；
5. pair curve 的 observation weight 使用 `P90 capped total sales × battlefield sample weight`；sample weight 由 target/candidate allocation 的保守组合得到，缺失时记边界；
6. M11D weight 永远不写成用户购买归因。

## 5. Q5 config v2

配置版本升级为 `sellpoint_value_pm_v4_matched_wtp_config_v2`。v1 结果不得继续标记为新 Q5。

每个候选 pair 必须同时通过：

1. 既有 strong curve、负向价格方向、局部 crossing、8 周 leave-one-week-out 全覆盖且 crossing span <=4pp；
2. 以周为 cluster、确定性 seed 的 bootstrap；seed 来自 `input_hash + relation_hash + candidate_sku_code + config_version`；
3. 至少 200 次重采样，成功 crossing 比例 >=80%；
4. bootstrap crossing 的 P10/P90 均为正、位于原观测范围且局部支持；
5. bootstrap/LOO 联合 crossing span 不超过版本化阈值；
6. 不通过任一门禁则该 pair 不进入金额，最终不足两个 pair/两个 family 时 WTP amount 为 null。

多 pair：

- point center 使用按 cell、week、direction consistency、bootstrap success 形成的质量权重加权中位数；
- `estimate_low/high` 取所有合格 pair 的 point dispersion、LOO range 与 bootstrap P10/P90 的联合保守包络；
- weighted center、pair weights、bootstrap success、LOO 和区间组成全部进入 `sensitivity_summary`；
- 输出仍固定 `causal_claim=false`、`psychological_max_price=false`。

## 6. 用户体验状态

Typed contract 明确区分：

- `established`：购后正向结果完整成立；
- `partial`：只观察到部分正向结果；
- `negative`：只观察到负向体验，产品能力不等于价值已兑现；
- `mixed`：正向与负向体验并存；
- `not_observed`：没有可归因的购后结果；
- lineage/data conflict 继续由 `LineageGate/LinkStatus` 表达，不得伪装成用户体验 mixed。

PM 文案分别写“用户实际获得的是负向体验”“不同用户/场景体验分化”“事实版本冲突，当前不能判断”。negative/mixed 均不得进入 Q1+ 或金额。

## 7. PM 市场空间范围

市场空间数值同时显示目标尺寸档和 market window 的中文范围；平台覆盖只从实际 market cells 汇总。不能补造未记录的全市场范围。

## 8. 版本与兼容

1. 只修改 V4 typed contract 和 config version；V2 schema、命令和自然语言路由不变；
2. CLI 仍必须显式 `--enable-v4`；
3. M12C 只提供 pool/tier/sample facts，任何旧 estimated/allocated amount 禁止进入 V4；
4. G09 在 G08R1 全部验收通过前保持禁止。
