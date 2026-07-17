# SPV51-G18 发布准备审计关闭回执

状态：completed；发布准备结论为 blocked

日期：2026-07-17

## 1. 已完成

已只读完成：

- TV 377、AC 155 个 G17 draft 的版本、覆盖、结论状态和来源 hash 复核；
- V5→V5.1 逐 SKU 状态迁移核对；
- 40 个 no_conclusion SKU 的完整清单和原因定位；
- 正式读取、preview 报告和问答的消费边界复核；
- 当前发布完整性门禁的真实只读调用；
- 首次正式启用的发布顺序、回退目标和发布前门禁设计。

## 2. 审计结论

画像数据已达到 `limited` 可用标准：

- 532/532 完整生成；
- 420 款完整结论、72 款部分结论、40 款数据不足；
- invalid、failure、integrity error 均为 0；
- review_required SKU 为 0；
- 正式竞品源均为 current published 且 hash 一致。

但当前代码不能发布 V5.1：

- TV 旧公式只计 282/377，实际 V5.1 状态覆盖 377/377；
- AC 旧公式只计 138/155，实际 V5.1 状态覆盖 155/155；
- 两者都被 `status_count_mismatch, limited_release_counts_invalid` 拒绝。

根因是 `SellpointValueProfileRepository._assert_publish_completeness` 仍使用旧 V5 的 ready/review/blocked/failed 计数，没有按 method version 使用 V5.1 的四种 conclusion 状态。

## 3. 40 款无结论

- TV 29 款、AC 11 款；
- 与旧 V5 的 blocked SKU 完全一致；
- 每款都已经有正式竞品和市场参考；
- 每款旧 V5 用户价值项数量均为 0。

因此它们是“目标 SKU 用户价值事实不足”，不是“竞品不足”，也不是 V5.1 新增的数据损失。

## 4. 当前正式消费状态

TV、AC 当前用户卖点价值画像 published/current 均为 0，正式读取返回 `profile_unavailable`。

锁定 G17 draft 的 preview 仍正常：

- 65E7Q 的画像、报告、问答共同锁定 `fdc4720e…442b1d`；
- AC39187 的画像、报告、问答共同锁定 `2c46a4d5…b4f3f`；
- 两者均为可用完整结论。

## 5. 未执行

本 Goal：

- 没有 review、publish、current 或 deprecated；
- 没有数据库写入；
- 没有部署；
- 没有重生成画像；
- 没有重跑或修改 M03B—M12D、旧 M12/M13/M14、旧 V5 或正式竞品画像。

205 运行状态：healthz=ok、readyz=ready、OOM=false、restart=0。

## 6. 后续门禁

任务链在 G18 停止。当前不请求用户批准发布。

若用户同意继续，应另建一个小范围 Goal：

1. 按 method version 修复 V5.1 publish completeness；
2. 保持旧 V5 发布合同不变；
3. 增加真实 TV/AC limited 分布和首次启用回退测试；
4. 部署但不重生成画像；
5. 重跑 G18 只读审计；
6. 审计通过后，再由用户明确批准两个版本的 limited review/publish/current。

完整审计：`SPV51_G18_publish_readiness_audit.md`。

结构化证据：`SPV51_G18_publish_readiness_evidence.json`。
