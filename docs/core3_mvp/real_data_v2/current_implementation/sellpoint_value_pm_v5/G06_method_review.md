# V5-G06 价格兑现、销量兑现与增量分账复核

## 结论

`PASSED — G07 ALLOWED`。

P0=0，P1=0，P2=2。

## 产品经理业务检查

- 价格兑现和销量兑现是两本账，任何一项缺失都不会用另一项补齐；
- M11D 战场销量仅解释本 SKU 已有销量分布，不表示卖点带来的新增销量；
- 市场合成对照的销量差只进入“观察性毛增量”，不包装成因果增量；
- 没有同品牌内部蚕食量时，净新增保持不可识别；只有毛增量与蚕食量单位一致时才计算保守净区间；
- 战场市场空间、M11D 分配量和旧 M12C 金额均不能进入增量账户；
- 卖点组合金额仅复用已经通过 V4 全部门槛的严格市场隐含区间，不生成单卖点心理最高支付价；
- 65E7Q 当前证据边界仍为“严格金额不可用、M11D 分配非增量、市场合成可作为观察性基线但不可直接声称新增”。

## 方法检查

- `RealizationAccountingInput/Result` 为 extra-forbid typed contract；
- `PriceRealization`、`VolumeRealization`、`BattlefieldAllocation`、`IncrementDecomposition`、`BundlePriceInterval` 独立建模；
- gross − cannibalization 的区间采用保守传播：中心相减、下界减对方上界、上界减对方下界；
- M11D 分配合计偏离当前销量 1% 以上会写入限制，不静默修正；
- V4 非 available 状态只能得到 blocked/unidentifiable 金额状态；
- 输出哈希对同一输入稳定；实现为纯函数，无数据库、网络和 205 写入。

## 工程检查

- G06 实现拆入独立 `claim_value_pm_v5_realization.py`，未污染 G04 市场合成和 G05 战场组合的源码边界；
- 前序“不得输出严格金额”和“不得把市场空间转成增量”的源码护栏继续通过；
- G06 tests 9 passed；V5 tests 53 passed；V4 + M11D related 30 passed；
- V5 overall coverage 93%，G06 realization 98%，service 91%；ruff passed；
- database/205 writes：0/0。

## P2

1. 当前 cannibalization 只有 typed 输入合同，没有生产数据源，因此 G07/G08 必须如实展示净新增不可识别，不得默认填 0。
2. 市场合成销量单位为 `sales_per_cell`；进入跨周期或累计销量口径前必须先增加显式换算合同，不能在渲染层换算。
