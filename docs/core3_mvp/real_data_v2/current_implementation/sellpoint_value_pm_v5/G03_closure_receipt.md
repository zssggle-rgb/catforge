# V5-G03 关闭回执

## 结论

`PASSED — V5-G04 ALLOWED`。

V5 typed schemas 和多层反事实 resolver 已实现。direct、同预算、同品牌同尺寸、参数梯度、同宣称不同兑现、自身价格曲线和市场合成 broad donor 都进入统一 typed contract；召回、筛选、可用和拒绝状态分离。

## 关键行为

- M14/direct authority 不合格时停在 screened，不阻断其他方法；
- same-budget/brand/tier/claim 只输出各自允许的描述性比较；
- unknown tier 不作为 lower-value baseline；
- own curve 不满足 8 周/2 平台/价格变化时 rejected；
- market synthetic 只输出 `recalled + balanced=false` donor pool，不计算 effect；
- 输入 universe 顺序变化不改变候选顺序或 set hash；
- legacy M12C amount、sales lift、strict amount 方法未进入 resolver。

## 验收

- V5 tests：24 passed；
- V4/V5 related：47 passed；
- 两个新增运行文件合计 coverage：94%；
- ruff：passed；
- G02 全模型字段与 G03 required-field addendum 一致；
- G01 C01-C08 和 65E7Q coverage fixture 已回放；
- 主提交：`d930be2efe8718afdcc93e1c7f9f2efbe7c71088`；
- 只精确提交 6 个 G03 文件，未包含工作区其他任务改动。

## G04 范围

允许在 `claim_value_pm_v5_service.py` 实现 market synthetic balance/effect 和 out-of-fold high/low performance archetype，并新增对应测试；不得实现 battlefield portfolio、严格金额、PM renderer 或默认路由。
