# V5-G08 独立方法复核

## 结论

`PASSED FOR DEFAULT-OFF SHADOW`。

P0=0，P1=0，P2=2。

## 通过项

- 18 个冻结 SKU 双跑的报告 DTO 与 result hash 全部一致；
- 16/18 SKU 至少具备同预算反事实，10/18 具备“同宣传、不同用户兑现”反事实；
- 广义市场池没有被直接冒充“无/弱价值”对照；弱价值档位、共同市场和平衡门槛未通过时，合成销量差为空；
- 价值是否存在、相对价值、价格承接、销量承接、当前销量分配、毛/净增量保持分账；
- M11D 分配未转成增量，市场空间未转成销量 lift；
- 0 个严格金额、0 个合成销量差、0 个净新增、0 个 eligible 新战场均符合当前证据；
- observed positive、partial、mixed、negative、not observed 五类用户价值状态在真数 cohort 中保持分离；
- stale lineage 作为亮点总门禁，18 个 blocked 报告均为 0 亮点。

## P2

1. 完整证据快照受 80 MB 门禁限制为 3 个，当前不能同时支持 5 个完整 synthetic donor；未来应增加轻量市场 donor contract，而不是重新放大完整 evidence payload。
2. 当前所有冻结 SKU 都被发布线谱冲突阻断，无法用真实数据验证“非阻断亮点”和严格金额的业务合理性；继续默认关闭。
