# G08 方法识别独立评审

## 结论

`FAIL`。当前实现可以输出“用户价值是否被购后体验观察到”和观察性的同价选择关联，也能在多数不足场景中保持金额为空；但 Q5 的市场隐含支付区间尚未完整实现 G02 冻结的稳定性与区间合同，不能以“严格门禁已通过”的名义进入 G09。

## 已验证成立的方法边界

1. 选择曲线复用同周同平台 pair、2pp 价差箱、P90 合计销量截尾、PAVA 单调不增和局部支持检查；
2. 不在观测价差范围外外推，价差空洞、单周、促销疑似、单边零销量和异常方向均会降级；
3. Q5 至少要求两个 A 级 base pair、两个显式 model family、完整用户价值、可比购后体验、负向价格方向和 leave-one-week-out 全周稳定；
4. 同价值-only、单 pair、同产品族、完全共线、版本冲突、价值未观察或仅部分观察时金额为空；
5. 所有金额对象固定 `causal_claim=false`、`psychological_max_price=false`，产品经理文案也明确写“市场关联，不是心理最高价”；
6. M12C 旧金额不进入 V4，M11D 分配值没有被直接当成消费者选择归因。

## 阻断项

### M01：Q5 稳定性和区间算法未完成

- 冻结合同：详细设计 12.2 第 12 条要求 bootstrap 与 leave-one-week-out 联合稳定性；12.3 要求多 pair 使用质量加权中心，并用 pair dispersion 与 leave-one-week-out/cluster bootstrap 形成联合保守包络；
- 当前实现：`_market_implied_wtp()` 只检查 leave-one-week-out；可用金额直接取合格 pair WTP 的 `min/max`，没有 cluster bootstrap、质量权重或联合包络；
- 影响：两个表面平滑但 cluster 依赖、质量差异很大或 bootstrap 跨过零/局部支持边界的 pair，仍可能被写成 Q5；
- 处置：必须在独立修复 Goal 中完成算法、配置版本、敏感性输出和确定性测试，修复前不得输出 Q5 金额。

### M02：同版本、同批次但事实 hash 改变时线谱会误判 aligned

- 当前 gate 在 `rule_version` 相同且 batch 有交集时直接通过，没有比较 `source_hash`；
- 影响：上游在同一版本和批次内重算/替换记录后，M12D 发布时事实与当前事实已经不同，V4 仍可能继续量化；
- 处置：同版本同批次也必须比较规范化 hash；hash 不同应局部阻断，缺失应 unresolved。

### M03：M11D 解释权重未进入战场样本权重

- 冻结合同允许 M11D weight 作为战场样本权重，但禁止改变真实销量或作为购买归因；
- 当前 curve 只用 target/candidate 合计真实销量加权，`battlefield_allocation_weight` 被读取后没有参与任何样本权重；
- 影响：多战场 SKU 的整机销量可能完全主导某一战场曲线，战场级选择关联与 WTP 口径不一致；
- 处置：明确且测试“真实销量不改、样本权重乘以解释权重”的公式，并在缺失权重时降级或记录边界。

### M04：候选池过早截断造成识别偏差

- 冻结预算是召回不超过 30、完整 snapshot 不超过 12、最终每角色不超过 3；
- 当前 M14 和 fallback 都在角色/可比性判断前截为总计 3 个；
- 影响：第 4 名以后可能存在第二个 base pair 或第二个 model family，却永远无法进入门禁，结果受 M14 排名结构而不是识别质量支配；
- 处置：先召回、再按角色和可比性选入 snapshot，最后按角色封顶。

## 方法验收限制

- 65E7Q 脱敏 fixture 没有原始评论 atoms 和逐周平台 cells，只能验证“不补造价值和金额”，不能验证 G02 追溯表里预期的 Q3；
- G01 五 cohort 测试目前只核对 cohort ID 后重建合成上下文，没有按 frozen payload/hash 真实回放，因此不能证明固定 cohort 没有漂移；
- 当前 synthetic 400-500 元样例只能证明已实现算法在理想输入下返回两个 pair 极值，不能证明冻结 Q5 方法已经完整识别。

## 方法准入决定

`G09 not allowed`。修复后必须重新运行 synthetic positive、bootstrap unstable、same-value-only、base missing、单周、完全共线、版本冲突和 65E7Q 边界回放，并由 G08R1 重新出具方法评审。
