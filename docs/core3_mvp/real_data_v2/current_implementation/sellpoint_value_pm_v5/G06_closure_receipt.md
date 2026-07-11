# V5-G06 关闭回执

## 结论

`PASSED — V5-G07 ALLOWED`。

V5 已形成互不代填的价格兑现、销量兑现、M11D 当前销量分配、观察性毛增量/蚕食/净增量与严格组合金额五本账。

## 验收结果

- 价格与销量状态独立，缺失不互补；
- M11D allocation 明确为当前销量的语义分配，永不作为 increment；
- synthetic sales difference 只能进入 observational gross；
- cannibalization 缺失时 net 保持不可识别，单位不一致时阻断；
- 只有已通过 V4 完整门槛的 `MarketImpliedWtp` 才能映射严格组合金额；
- 旧 M12C amount、市场空间、M11D allocation 均未进入增量计算；
- 65E7Q 当前边界回归通过，不强行生成金额或净新增；
- G06 9 passed、V5 53 passed、V4 + M11D related 30 passed；
- overall coverage 93%、realization 98%、service 91%、ruff passed；
- 主提交：`c365bef33e9a084ceebf43950b1937532616562b`；
- database/205 writes：0/0。

## 边界

G07 只能把这些独立账户转成产品经理可理解的 DTO 和报告，不得在渲染层补数字、换口径或把观察性差异改写成因果结论。
