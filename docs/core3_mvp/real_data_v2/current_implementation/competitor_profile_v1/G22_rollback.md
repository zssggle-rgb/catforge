# G22 RC 回滚说明

日期：2026-07-14

## 1. 当前状态

G22 仅形成本地代码和文档提交；没有连接 205、没有部署、没有运行远程 migration、没有生成画像、没有改变 published/current。因此当前回滚只需撤销本次 Git 提交，不涉及数据恢复。

## 2. G23 部署后的回滚

1. 在没有任何竞品画像数据时，可将 0046 downgrade 到 0045；migration 会按 selection → relation → pair → profile → version 的逆序删空表。
2. 任一表已有数据时，0046 downgrade 会拒绝执行，不会静默删数据。此时先停止新画像写入，保留旧 M12/M13/M14 和现有智能体服务，评估导出/迁移或 forward-fix；删除数据必须单独授权。
3. 代码回滚到 G22 前提交时，不改变旧竞品智能体和用户卖点价值链，因为 G22 未切换它们。
4. health/ready 或 migration 失败时，G23 立即停止，不得继续 G24 单 SKU 生成。

## 3. 发布保护

本 RC 没有任何自动 publish/current 行为。后续即使 draft 验收通过，review、publish 和 set-current 仍是三个独立授权动作；失败不得覆盖旧 current。
