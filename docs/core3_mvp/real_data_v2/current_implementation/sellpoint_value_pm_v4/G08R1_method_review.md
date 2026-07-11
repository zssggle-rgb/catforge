# G08R1 方法识别复审

## 结论

`PASS`。G08 方法评审确认的 Q5、lineage、候选选择和战场权重缺口均已修复。当前金额仍然是观察性的市场隐含支付区间，不是因果效应、心理最高价或可直接执行的定价建议。

## Q5 config v2

1. 方法版本已升级为 `sellpoint_value_pm_v4_matched_wtp_config_v2`，v1 对象不能通过当前 schema；
2. 每个 pair 在既有 strong curve、负向价格方向、局部 crossing 和 leave-one-week-out 全覆盖之外，运行 200 次确定性 week-cluster bootstrap；
3. seed 由 `input_hash + relation_hash + candidate_sku_code + config_version` 生成，相同输入的 bootstrap summary、WTP 和 result hash 完全一致；
4. bootstrap 成功率必须 >=80%，P10/P90 必须为正且联合 crossing span 不超过版本化阈值；
5. leave-one-week-out、bootstrap 或联合区间任一不稳，pair 不进入金额；最终不足两个 A 级 base pair 或两个 model family 时金额为空；
6. 多 pair 计算 cell/week/direction/bootstrap 质量权重和 weighted median center；
7. `estimate_low/high` 取 pair point、LOO low/high、bootstrap P10/P90 的联合保守包络，并由 schema 强制包含 weighted center；
8. sensitivity summary 保存 seed hash、成功率、pair weights、weighted center 和全部区间组成。

## 反事实和市场单元

- 候选先召回 <=30，再按 declared role 覆盖进入 <=12 个完整 snapshot，完成事实和可比性判断后每个 computed role <=3；
- Q5 仍要求两个独立 A 级 base pair、两个 model family、完整用户价值和可比购后体验；
- weekly rows 在 DB 侧最多读取 2,001 条，超限只保留完整周/平台/渠道 group，并显式阻断金额；
- M11D allocation 只乘到 observation sample weight，不改变真实销量、选择份额分子分母，也不作为购买归因；
- 同价值-only、base missing、完全共线、单周、促销、零销量、价差空洞、异常方向、版本冲突和 bootstrap unstable 均保持金额为空。

## Lineage

- 同版本、同批次也必须比较规范化 source hash；
- hash 不同为局部 `stale_conflict`，缺 hash 为 `unresolved`；
- authority refs 在 hash 前排序，相同事实不同 DB 返回顺序产生同一 input/result hash。

## 验证

- synthetic stable：两个 family，pair crossing 8%/10%，保守区间 400-500 元；
- synthetic bootstrap unstable：WTP null；
- v1 schema、single pair、same family、same-value-only、base missing：WTP null；
- G01 五 cohort 按 frozen payload 回放，整个 cohort manifest SHA 与 G01 artifact receipt 一致；
- 65E7Q 脱敏 fixture 继续只证明“不补造用户价值和金额”。

## 方法准入

`PASS for G09 shadow validation`。G09 仍只能显式启用、默认关闭，并需要在真实数据上重新验证耗时、连续两次 hash 和金额边界。
