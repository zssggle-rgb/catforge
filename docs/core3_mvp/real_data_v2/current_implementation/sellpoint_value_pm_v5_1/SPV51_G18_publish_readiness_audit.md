# SPV51-G18 用户卖点价值画像发布准备审计

状态：审计完成；当前不允许发布

日期：2026-07-17

环境：205

## 1. 总结论

这批画像的数据结果已经达到“有限可用”的发布标准，但现有发布状态机还不能正确发布 V5.1。因此当前结论分为两层：

1. **画像结果可用**：TV 377 款、AC 155 款全部生成，492 款能返回完整或部分产品结论，40 款明确返回数据不足；生成失败、无效画像、完整性错误均为 0。
2. **当前发布操作不可执行**：发布完整性校验仍沿用旧 V5 的状态计数，未把 V5.1 的 `partial_conclusion` 和 `no_conclusion` 计入完整 SKU。TV 只校验到 282/377，AC 只校验到 138/155，实际发布调用会被拒绝。

因此，产品和数据层面的结论是 `limited，可正式消费`；工程发布准备结论是 `blocked，必须先修复发布门禁`。

现在不应批准 review、publish 或 current。下一步应先完成一个小范围发布状态机修复，部署后重新执行本审计，再向用户申请明确发布批准。

## 2. V5.1 是否解决了旧 V5 的核心问题

解决了。

| 品类 | 旧 V5 | V5.1 | 业务变化 |
| --- | --- | --- | --- |
| TV | blocked；1 款真正可直接使用，347 款要求复核，29 款阻断 | limited；282 款完整结论，66 款部分结论，29 款数据不足，0 款复核 | 348 款可直接形成产品结论，不再被局部缺证据拦住 |
| AC | blocked；144 款要求复核，11 款阻断 | limited；138 款完整结论，6 款部分结论，11 款数据不足，0 款复核 | 144 款可直接形成产品结论，不再被局部缺证据拦住 |

逐 SKU 对照显示：

- 旧 V5 中 TV 的 281 款 partial，V5.1 转成 244 款完整结论和 37 款部分结论；
- 旧 V5 中 TV 的 67 款 ready，V5.1 转成 38 款完整结论和 29 款部分结论；
- 旧 V5 中 AC 的 144 款 partial，V5.1 转成 138 款完整结论和 6 款部分结论；
- 旧 V5 中 TV 29 款、AC 11 款 blocked，V5.1 均转成明确的数据不足，不再冒充系统异常。

V5.1 还补齐了旧 V5 没有的正式竞品来源锁：

- TV 锁定正式竞品画像 `288b6ce0-b632-478c-9705-8297103da730`；
- AC 锁定正式竞品画像 `eed759a8-a666-4257-8c4d-3405621a4244`；
- 两个来源当前均为 `published + current`，结果 hash 与 V5.1 保存版本一致；
- 正式竞品、市场参考、用户价值项和产品结论均已按版本保存，不需要智能体现场重算。

## 3. 40 款数据不足到底缺什么

这 40 款不是因为找不到竞品：

- AC 11 款每款都有 20 款正式竞品和 37～76 款市场参考；
- TV 29 款每款有 3～20 款正式竞品和 3～87 款市场参考。

真正原因是：**旧 V5 没有为这些 SKU 形成任何用户价值项**。竞品只能帮助比较已经成立的用户价值，不能替代目标 SKU 的用户价值事实。V5.1 因此没有用竞品量价反推不存在的卖点价值，而是返回“现有数据不足，暂不能形成该 SKU 的用户卖点价值结论”。

这 40 款与旧 V5 的 40 款 blocked 完全一一对应，不是 V5.1 新增的数据损失。

### AC 11 款

| SKU | 产品 |
| --- | --- |
| AC00034959 | 美的 KFR-72LW/QJ201-1 |
| AC00036098 | TCL KFR-35GW/JD61+B1 |
| AC00036116 | 美的 KFR-35GW/MJD2-1 |
| AC00036291 | 奥克斯 KFR-35GW/BPR3AEG28(B1) |
| AC00036763 | 美的 KFR-35GW/MJ1P |
| AC00036792 | 美的 KFR-72LW/MJ1P |
| AC00036924 | 美的 KFR-35GW/JY1 |
| AC00038686 | 美的 KFR-72LW/MJ2 |
| AC00039044 | 统帅 KFR-35GW/LTB2-1 |
| AC00039082 | 晶弘 KFR-35GW/JH5K1FNHAEB1 |
| AC00039655 | 小米 KFR-35GW-PG15/N2A1 |

### TV 29 款

| SKU | 产品 |
| --- | --- |
| TV00009549 | 康佳 LED32E330CE |
| TV00023850 | 酷开 50P31 |
| TV00026983 | TCL 75S11-JN |
| TV00027638 | 长虹 85JD900F-G1 |
| TV00027973 | 海尔 75D50C |
| TV00028213 | 创维 100H5F PRO |
| TV00028330 | 海信 98D60QD |
| TV00028377 | 海信 100D70QD |
| TV00028418 | 长虹 75JD700H |
| TV00028712 | 酷开 40P3F |
| TV00029030 | 康佳 J40ES |
| TV00029031 | 酷开 32K3 |
| TV00029032 | 酷开 43K3 |
| TV00029101 | 长虹 50P6S-F |
| TV00029202 | 海信 75D68S |
| TV00029226 | 海尔 65D50CN |
| TV00030163 | 海信 75D30S |
| TV00030366 | 红米 L100RC-AP |
| TV00030532 | VIDDA 75VX5S |
| TV00030533 | VIDDA 85VX5S |
| TV00030547 | 海信 85E5S-PRO |
| TV00030549 | 酷开 50K3 |
| TV00030612 | 海信 85E52S-PRO |
| TV00030613 | 海信 75E5S |
| TV00030614 | 海信 100E5S-PRO |
| TV00030615 | 海信 85E7S |
| TV00030618 | 海信 85E5S |
| TV00030619 | 海信 100E7S |
| TV00030696 | 酷开 55P3H |

## 4. 为什么当前代码一定发布失败

现有发布校验仍使用旧 V5 公式：

```text
ready_count + review_required_count + blocked_count + failed_count
```

V5.1 的正式完整性公式应是：

```text
conclusion_available_count
+ partial_conclusion_count
+ no_conclusion_count
+ invalid_count
```

205 只读调用实际得到：

| 品类 | 旧公式 | V5.1 公式 | 实际发布完整性结果 |
| --- | ---: | ---: | --- |
| TV | 282/377 | 377/377 | `status_count_mismatch, limited_release_counts_invalid` |
| AC | 138/155 | 155/155 | `status_count_mismatch, limited_release_counts_invalid` |

这说明即使 review 完成、显式允许 limited，`publish_version` 仍会拒绝两个版本。该问题必须在发布前修复，不能用手工改状态绕过。

### 最小修复范围

1. V5.1 发布完整性改用四种 conclusion 状态覆盖权威 SKU；
2. `partial_conclusion` 和 `no_conclusion` 允许构成 limited，不要求伪造 `review_required_count`；
3. `invalid`、generation failure、完整性错误或覆盖不完整仍阻断；
4. 旧 V5 继续使用旧计数合同，不改变历史行为；
5. 增加与本次真实分布一致的 TV `282/66/29/0`、AC `138/6/11/0` 发布门禁测试；
6. 修复只涉及发布判定，不重生成画像，不改变任何业务结论或 hash。

## 5. 当前智能体消费状态

当前数据库中 TV、AC 都没有任何用户卖点价值画像处于 `published + current`，所以正式读取按设计返回 `profile_unavailable`；这不是运行故障，而是尚未获得发布批准。

显式锁定 G17 草稿做 preview 时：

| 品类 | 样例 | 画像、报告、问答 |
| --- | --- | --- |
| TV | 海信 65E7Q | 三者共同消费 `fdc4720e…442b1d`，状态为可用完整结论 |
| AC | 海信 KFR-35GW/E5E1-1 | 三者共同消费 `2c46a4d5…b4f3f`，状态为可用完整结论 |

正式读取与 preview 的差异只来自发布状态；preview 没有现场调用竞品分析、旧 M12/M13/M14、量价计算或卖点分类。

## 6. 修复后应如何发布

修复、部署和复核通过后，仍需用户再次明确批准以下动作和两个精确版本：

- TV：`37f2ef77-187a-4ee6-b0a7-87708a21856f`；
- AC：`38d86772-cd31-4b0c-bf4c-cccc64de6aee`；
- 明确允许 `release_quality_status=limited`；
- 明确 review 人、publish 人和发布说明。

建议执行顺序：

1. 只读复核两个版本 id、result hash、正式竞品 source hash 和 532 款覆盖；
2. 在一个受控事务中 review 两个版本；
3. 再在一个受控事务中 publish 两个版本并切 current；任一品类失败则整个事务回滚；
4. 提交后立即验证 65E7Q、AC39187 和两款数据不足样例的正式报告、卡片与问答；
5. 验证 TV/AC 正式 current 各 1 个、旧 V5 和竞品画像未变化。

## 7. 回退目标与步骤

当前 TV、AC 的用户卖点价值画像均没有旧的 published/current 版本。因此这次发布是第一次正式启用，**回退目标不是旧 V5，而是恢复为“没有正式 current 用户卖点价值画像”**。

发布前必须准备并演练一个受控回退事务：

1. 锁定两个 source batch 和两个目标版本；
2. 将两个目标版本及其 profile、candidate、value item 的 `is_current` 同时改为 false；
3. 保留 published 版本和全部 hash，不删除、不覆盖，便于审计和后续修复；
4. 事务提交后验证 TV/AC current published 均为 0；
5. 验证正式智能体恢复 `profile_unavailable`，preview 仍可锁定保存结果做问题定位；
6. 不把 blocked 的旧 V5 切为 current。

当前 repository 没有公开的“撤销首个 current”生命周期方法。发布修复 Goal 应同时提供或冻结上述回退命令，避免上线后只能临时手改数据库。

## 8. 发布前必须重新通过的门禁

- V5.1 发布完整性只读模拟：TV、AC 均通过；
- 旧 V5 发布门禁回归不变；
- 两个版本仍为原 draft id 和原 result hash；
- TV 377、AC 155，missing/invalid/failure/integrity error 均为 0；
- 正式竞品画像仍是当前 published/current 且 hash 未变；
- review、publish、current 和首发回退均有事务级测试；
- 205 部署后 healthz、readyz、OOM、restart 正常；
- 用户重新明确批准 limited 发布。

在这些条件全部满足前，发布准备状态保持 `blocked`。

## 9. 审计边界

本 Goal 只执行只读数据库事务、保存画像 preview、代码合同检查和运行状态检查：

- 没有 review、publish、current 或 deprecated；
- 没有写数据库；
- 没有重跑或修改 M03B—M12D、旧 M12/M13/M14、旧 V5 或正式竞品画像；
- 没有部署；
- 205 `/healthz=ok`、`/readyz=ready`、OOM=false、restart=0。

结构化证据见 `SPV51_G18_publish_readiness_evidence.json`。
