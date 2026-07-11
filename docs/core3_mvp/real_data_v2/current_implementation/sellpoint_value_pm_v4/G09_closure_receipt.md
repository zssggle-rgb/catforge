# G09 关闭回执：RC、205 默认关闭影子验收与回滚演练

## Objective

以 G08R1 closure commit `1653bff` 为唯一代码基线，形成不可变 RC，在 205 保持默认关闭完成真实数据、跨载体、性能、写边界、V2 回归和回滚演练；只给出 G10 准入判断，不进入 G10。

## 结果

`G09 completed; default-off shadow passed; G10 default route not recommended`。

## 完成证据

1. RC package SHA-256 `8c1b62ddde63add4196cb424856a06269870c4720fbcba55a2d46b45d0925b95`，9/9 运行时文件主机与容器 hash 一致；
2. 回滚 package SHA-256 `dba311341c081840a78a69179e365bc48882be74470c5c97c4172f0e0a1d3f0a`，旧态恢复、V2 验证、RC 再恢复全链通过；
3. health/ready 和容器 healthy 通过，无 flag 查询为 0 并拒绝，自然语言默认路由未变；
4. 65E7Q 与 C01-C05 连续双跑 input/result/full JSON 全部一致；
5. JSON、短答、Markdown、飞书卡片与真实飞书文档回读同源；
6. Q5 config v2、M12C 旧金额隔离、纯负向/正反并存/事实冲突分离通过；
7. 已解析上下文 17 queries，默认 latest 权威解析另 10 queries；4 并发稳定；
8. V2 业务结果一致，唯一非业务差异为 `audit.generated_at`；
9. 数据库 tuple inserted/updated/deleted 前后完全不变；
10. 205 最终保持 RC 影子态，V4 默认关闭。

## Commits

- RC 清单与部署前基线：`295f575`；
- 影子验收与回滚证据：`dd30e0b`；
- 本关闭回执与 artifact manifest：本文件所在 closure commit。

## 产品经理样例

真实 [65E7Q 用户卖点价值账](https://my.feishu.cn/docx/JWIIdYSPEo4lBpxJdqXcyG7tn4c) 已生成并回读：8 笔价值账中 6 笔为部分感知、2 笔尚未观察；战场空间可见，但由于线谱冲突和基础价值反事实缺失，选择贡献与支付金额保持为空。

这正是当前功能应该给产品经理的答案：不是用评论多少自证卖点，也不是在数据不足时给价格动作，而是逐笔告诉他哪些设计投入已被用户感知、哪些尚未观察、哪些具备市场空间，以及当前为什么还不能把它们换算成卖点 WTP。

## G10 准入

`G10 denied for now`。需要先对齐发布画像与当前事实 source hash、恢复基础/同价值/上探反事实，并取得至少一组通过 Q5 全部门禁的真实回放样本。默认路由切换仍必须由用户单独批准。
