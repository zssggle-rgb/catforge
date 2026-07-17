# SPV51-G10 状态、confidence 与版本质量关闭回执

状态：completed

日期：2026-07-17

## 1. question → value

- 每个问题保存 `conclusion_available / partial_conclusion / no_conclusion / invalid`、局部 confidence、limitations、review、证据和来源 hash；
- 同一用户价值中只要有真实 invalid，该价值自身 invalid；否则有 conclusion 即 conclusion，有 partial 即 partial，其余 no_conclusion；
- synthetic、strict WTP、unknown investment 或其他增强项 no_conclusion 不覆盖同价值内已经成立的直接量价或用户价值结论；
- review 只允许附着在 invalid 问题和该价值自身，不再生成 `linked_investment_review`。

## 2. value → SKU

- 一个价值 invalid、另一个价值 conclusion/partial 时，SKU 仍输出 conclusion/partial，局部冲突只保存在 `invalid_value_codes / local_review_value_codes`；
- 所有价值 invalid，或存在结构、范围、hash 等 SKU 级错误时，SKU 才为 invalid；
- 合法但全无结论的 SKU 为 `no_conclusion / data_insufficient`，可正式返回“数据不足，无结论”，不 review；
- partial SKU 为 `usable_partial`，conclusion SKU 为 `usable_conclusion`，两者都可被下游正式消费。

## 3. confidence

- 只收集实际形成 conclusion/partial 的问题级直接 confidence；no_conclusion、invalid、unknown investment 不按 0 计入；
- value 和 SKU 保存原始 confidence 分布、最小值和中位数，不取全部投入项 confidence 平均值；
- 结论已成立但 confidence 缺失时保持 None，不触发 review、不改变 SKU 状态、不阻断 ready。

## 4. SKU → version

- `ready`：权威 SKU 全部生成，全部有正式结论，无真实 invalid、完整性错误或局部 review；
- `limited`：完整性通过，但存在 partial、no_conclusion 或可用 SKU 内的局部 review；limited 仍可进入后续 review/publish 流程；
- `blocked`：只由 coverage mismatch、generation failure、invalid profile、跨 scope、重复 SKU、悬空/意外引用、hash mismatch 等真实完整性错误触发；
- 可选增强失败及其技术限制不自动进入版本门禁。

## 5. 验证

- G10 aggregation、V5.1 schema、G07 investments、G08 market comparison、G09 enhancements 必要回归共 92 项通过；
- 覆盖四状态优先级、增强失败局部化、confidence 分布、局部 invalid 不跨 value、全 invalid、结构 invalid、partial/no_conclusion 正式消费、TV/AC 隔离、ready/limited 和七类 blocked 完整性错误、确定性；
- touched Python files 的 ruff、py_compile、format 和 diff check 通过；
- 未实现 G11 materializer/repository/generation/fingerprint，未做完整回归，未写数据库或 205；完整质量评审仍集中在 SPV51-G13。

## 6. 下一步

SPV51-G11 将 G05—G10 的正式竞品来源、两池、局部分析与聚合结果装配成一个 V5.1 draft，写入 G04 新表并完整回读；fingerprint 必须绑定竞品画像 version/hash，单 SKU 失败只回滚自身。
