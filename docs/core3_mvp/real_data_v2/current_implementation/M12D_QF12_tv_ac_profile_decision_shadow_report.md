# M12D-QF-12 TV/AC Profile Decision Shadow

- 生成时间：`2026-07-11T11:03:51.910737+00:00`
- 范围：只比较核心锚点收敛、画像置信度、状态和复核；不修改锚点评分或发布控制。

| 品类 | SKU | 受影响 SKU | 旧状态 | 新状态 | 旧复核 | 新复核 |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| TV | 377 | 377 | `{'ready': 178, 'ready_degraded': 117, 'review_required': 64, 'weak_expression_only': 18}` | `{'ready': 238, 'ready_limited': 94, 'weak_expression_only': 45}` | 203 | 0 |
| AC | 155 | 155 | `{'ready': 74, 'ready_degraded': 29, 'review_required': 52}` | `{'ready': 130, 'ready_limited': 23, 'weak_expression_only': 2}` | 76 | 0 |

## TV

- 状态迁移：`{'ready->ready': 178, 'ready_degraded->ready': 28, 'ready_degraded->ready_limited': 74, 'ready_degraded->weak_expression_only': 15, 'review_required->ready': 32, 'review_required->ready_limited': 20, 'review_required->weak_expression_only': 12, 'weak_expression_only->weak_expression_only': 18}`
- 复核迁移：`{'false->false': 174, 'true->false': 203}`
- 核心数量分布：`{'0': 139, '1': 40, '2': 42, '3': 51, '4': 49, '5': 26, '6': 9, '7': 19, '8': 1, '9': 1}` -> `{'0': 139, '1': 67, '2': 79, '3': 92}`
- 锚点角色迁移：`{'core_payment->core_payment': 501, 'core_payment->supporting': 306, 'risk_drag->risk_drag': 242, 'supporting->supporting': 1624, 'weak_expression->weak_expression': 869}`
- 非目标锚点字段变化：`0`
- 非法状态：`0`
- 核心上限/同族违规：`0` / `0`
- 置信度公式违规：`0`
- 复核门槛违规：`0`
- 未影响回归样本：`20`

## AC

- 状态迁移：`{'ready->ready': 74, 'ready_degraded->ready': 7, 'ready_degraded->ready_limited': 20, 'ready_degraded->weak_expression_only': 2, 'review_required->ready': 49, 'review_required->ready_limited': 3}`
- 复核迁移：`{'false->false': 79, 'true->false': 76}`
- 核心数量分布：`{'0': 25, '1': 13, '2': 30, '3': 22, '4': 14, '5': 12, '6': 12, '7': 14, '8': 7, '9': 6}` -> `{'0': 25, '1': 16, '2': 37, '3': 77}`
- 锚点角色迁移：`{'core_payment->core_payment': 321, 'core_payment->supporting': 214, 'risk_drag->risk_drag': 191, 'supporting->supporting': 702, 'weak_expression->weak_expression': 451}`
- 非目标锚点字段变化：`0`
- 非法状态：`0`
- 核心上限/同族违规：`0` / `0`
- 置信度公式违规：`0`
- 复核门槛违规：`0`
- 未影响回归样本：`20`

## 验收

- M12D 持久化表未变化：`True`
- 核心锚点按分数、置信度、强域数和 taxonomy priority 稳定排序，同 family 去重且最多 3 个。
- 画像置信度只来自已选核心；无核心时辅助置信度单独记录，不伪装成核心置信度。
- 风险锚点、普通 warning、低置信和输入缺失不自动触发复核。
- TV/AC 使用各自 taxonomy；本任务未写 current/published，也未进入发布门禁。

## 发布门槛预检（仅观察）

本节不实现 QF-13 发布控制，只提前暴露当前画像分布是否满足既定门槛，禁止据此切换 current/published。

| 品类 | ready | ready + limited | review | missing + failed | 无核心 | 预检 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| TV | 238/377（63.13%） | 332/377（88.06%） | 0/377（0%） | 0/377（0%） | 139/377（36.87%） | 未通过 |
| AC | 130/155（83.87%） | 153/155（98.71%） | 0/155（0%） | 0/155（0%） | 25/155（16.13%） | 未通过 |

- TV 未达到 `ready >= 85%`、`ready + limited >= 95%` 和无核心 `<= 15%`。
- AC 未达到 `ready >= 85%` 和无核心 `<= 15%`，其余观察项通过。
- 该偏差不是 QF-12 状态机额外降级造成的：新版 `ready` 数等于 QF-11 后仍至少有一个核心锚点的 SKU 数；QF-12 只将同族或超过 3 个的额外核心降为辅助，没有让任何 SKU 失去全部核心。
- QF-13 必须按品类独立计算并如实判定，不能降低门槛；QF-14/QF-15 需继续解释 QF-11 后 TV 139 个、AC 25 个无核心 SKU 以及 TV 45 个弱画像，未解释前不得发布。
