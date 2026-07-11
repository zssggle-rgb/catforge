# G06 选择关联、整机价格承接与市场隐含 WTP 进度

- Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`
- Goal 状态：`completed`
- 定时器：`catforge-v4-g06-10`
- 前置 G05 artifact commit：`5db2f7d`
- 前置 G05 closure commit：`5b5b3d2`
- 允许修改：V4 schemas/service、G06 tests/fixture/回执
- 禁止事项：repository/DB 写入、结构化需求模型、旧金额分摊、PM renderer、CLI/路由、205

## 当前门禁

| 门禁 | 状态 |
| --- | --- |
| 复核 G02 量化合同和 G01 固定边界 | completed |
| 复核 V2 pair curve/PAVA/不外推实现 | completed |
| ChoiceAssociation/MarketImpliedWtp/QuantificationResult 合同 | completed |
| 2pp 分箱、P90 截尾、同价/近同价互斥 | completed |
| 相对体验与市场选择关联分离 | completed |
| 整机价格承接、不拆单项 | completed |
| 两 A pair、两 model family Q5 总门禁 | completed |
| 价格方向与 leave-one-week-out 稳定性 | completed |
| synthetic 400-500 区间恢复 | completed |
| 65E7Q/C01-C05 降级回放与 V2 回归 | completed |

## 硬边界

1. G02 已明确退出结构化需求模型；现有数据缺少库存真值、促销真值、工具变量和 outside option；
2. M11D 分配权重不是购买归因，M12C 旧金额不是监督标签；
3. pair curve 只使用同战场、同周、同平台的有效价格和正销量，促销疑似单元排除；
4. 同价或 near-same-price 只在观测范围和局部样本支持内读取，绝不外推；
5. Q5 必须两条独立 A 级 base pair、跨两个明确 model family；单 pair 或未知 family 均不足；
6. 价格方向异常、crossing 缺失、leave-one-week-out 不稳定时金额必须为 null；
7. 完全共线只允许 bundle WTP，不得拆给 MiniLED、亮度、分区等成员；
8. 输出固定 `causal_claim=false`、`psychological_max_price=false`；
9. 65E7Q 因 same-value-only、base 降级和版本冲突，WTP 必须为 null；
10. G06 不生成涨降价、增减配或下一步工作清单。

## 实现结果

1. 新增 `ChoiceAssociation`、`MarketImpliedWtp`、`QuantificationResult`，字段和 required 集合与 G02 frozen contract 精确一致；
2. 复用 V2 已验证的 2pp 分箱、P90 权重截尾、PAVA、局部支持、不外推和 crossing 纯函数；
3. G06 pair 只读取 G05 eligible 的 base/same 候选，stretch 不进入目标 SKU 的选择/WTP；
4. 相对体验只确认同一购后价值主题是否可比，明确 `not_ranked_from_comment_counts`，不按评论数量排强弱；
5. 用户价值未成立或相对体验不可比时，即使市场曲线完整也不能越级成为卖点选择贡献；
6. choice 只在 exact same-price 或互斥的 near-same-price 局部观测上输出；价差空洞不插值；
7. 整机当前价格承接单独标记 `whole_product_only`，不拆给 bundle 成员；
8. Q5 需要至少两条 A 级 base pair、两个明确 model family、strong exact curve、负向价格方向、局部 crossing 和全部 leave-one-week-out 稳定；
9. 合成数据的两条 crossing 为 8% 和 10%，基准价 5000 元，确定性恢复区间 400-500 元；
10. 同 family、单 pair、same-value-only、stretch-only、单周、促销污染、零销量、价差空洞、正向价格方向、留一周不稳、价值 partial/not-observed、版本冲突均返回 null 金额；
11. available WTP 固定 `causal_claim=false`、`psychological_max_price=false`，并明示库存、品牌及未观察差异限制；
12. 未读取 M12C 旧金额或 M11D 分配权重，未新增 repository/DB/CLI/router/renderer，未连接 205。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| G06 quantification tests | 19 passed |
| G03 + G04 + G05 + G06 + V2 定向回归 | 74 passed |
| G04-G06 service coverage | 92% |
| G06 runtime schema vs G02 contract | exact match |
| synthetic identified | crossing 8%/10%；WTP 400-500；2 pairs/2 families |
| synthetic unstable | amount null；精确失败原因 |
| 65E7Q fixture | lineage blocked；金额 null；不拆单项 |
| Ruff | passed |
| py_compile | passed |
| `git diff --check` | passed |
| forbidden source scan | 无 M12C 旧金额、M11D 权重分摊或自动产品动作 |

## 下一步

G06 已完成，允许进入 G07。G07 只把已经成立的战场、采购理由、用户实际价值、卖点组合和量化边界翻译成产品经理业务 DTO、短答、主表、下钻、CLI 与显式 feature flag；渲染器不得重新推导结论。
