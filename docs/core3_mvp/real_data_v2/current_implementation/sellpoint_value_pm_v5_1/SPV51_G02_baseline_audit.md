# SPV51-G02 205 只读兼容基线审计

状态：completed

日期：2026-07-17

## 1. 结论

205 上 V5 未发布的两个主要原因已被当前数据再次确认：

1. **候选源错误**：旧 V5 对 65E7Q 只保存 51 款 `reference`，正式竞品为 0；新竞品画像已经稳定提供 20 款正式候选和 Top 3；
2. **门槛全局传播**：旧 V5 已经算出大量直接量价结果，但投入复核、低平均 confidence 和严格 WTP 失败被传播到价值项、SKU 和整个版本。

因此 V5.1 不能只“换一个候选表”，必须同时更换正式竞品来源并重构问题级资格、局部 review、SKU 状态和版本质量。

## 2. 新竞品画像可直接消费

- TV：377 SKU、7,300 pair、1,131 selection，`published / limited / current`；
- AC：155 SKU、2,774 pair、461 selection，`published / limited / current`；
- 65E7Q：20 个候选；Top 3 为 `TV00027801 / TV00028909 / TV00029936`；
- compact read 保存 source rank、selected rank、role、business score 和 result hash；
- V5.1 formal 路径不需要也不允许重新执行 competitor-set 或旧 M12/M13/M14。

## 3. 旧 V5 有内容，但被门槛压成不可用

| 品类 | 价值项 | 已有直接量价结果 | value review | 严格 WTP 成立 | 版本质量 |
| --- | ---: | ---: | ---: | ---: | --- |
| TV | 1,231 | 283 | 1,101 | 0 | blocked |
| AC | 936 | 212 | 936 | 0 | blocked |

这说明“严格 WTP 为 0”不能代表用户卖点价值没有量化，也不能继续作为发布门槛。直接竞品/参考组周均量价差应成为主量化结果，严格 WTP 只在成立时补充。

## 4. 65E7Q 基线

- 旧候选：0 个 competitor、51 个 reference，全部 `limited`；
- 画像：`partial / review_required`，confidence `0.5971`；
- 5 个价值项中 4 个已有直接价格和销量差；
- 5 个价值项全部仅因 `linked_investment_review` 被标为 review；
- 4 个已有量价比较使用 1—3 个对照，价格差约 4.61%—7.74%，周均销量差约 22.23%—43.20%；
- 每个价值项的严格 WTP 都是 blocked，但这与已有直接量价结果并不矛盾。

这正是 V5.1 的首个回归门禁：换用 20 个正式竞品后，局部投入 unknown 不得再把已成立的 4 个量价结果整体禁用。

## 5. 全量门槛根因

### TV

- 293/377 个 SKU 被标记 `competitor_universe_unavailable`；
- 271 个 SKU 被标记 `profile_confidence_low`；
- 投入中 `unknown=2,768`，对应 `decision_not_identified=2,768`；
- `comparison_scope_incomplete=3,118`、`decision_signal_conflicted=1,704`。

### AC

- 155/155 个 SKU 被标记 `competitor_universe_unavailable`；
- 133 个 SKU 被标记 `profile_confidence_low`；
- 投入中 `unknown=1,557`，对应 `decision_not_identified=1,557`；
- `comparison_scope_incomplete=1,703`、`decision_signal_conflicted=1,085`。

这些状态应保留在对应问题/投入的证据边界中，但不能继续自动传播到已成立的其他价值、SKU 或整版发布质量。

## 6. 后续 golden baseline

G03—G12 必须保持：

1. formal 候选源只读取 agent snapshot v2 current published；
2. 65E7Q 候选 20、Top 3 和 source/selected rank 不丢失；
3. 正式路径对旧 candidate universe、M12、M13、M14 和 live competitor-set 的调用计数为 0；
4. 直接量价最低 1 个合法对照可形成方向性结论；
5. strict WTP=0 不改变 direct gap、value、SKU 和 version 可用性；
6. unknown/review 只影响直接使用该冲突字段的问题；
7. AC 不再因旧 M12/M13 为空而整类 unavailable。

机器可读基线见 `SPV51_G02_205_baseline.json`。

## 7. 只读性能记录

首版审计误用 ORM 全量装载 532 个画像大 JSON，独立审计进程因内存限制 exit 137；没有数据库写入，API、healthz、readyz 均正常。修正后改为数据库侧聚合，只对 65E7Q 读取单行明细，并用竞品画像 compact reader 取 20 个索引，完整审计约 15 秒完成。

后续全量质量统计必须沿用数据库聚合/compact read，不得重新装载整版 payload。
