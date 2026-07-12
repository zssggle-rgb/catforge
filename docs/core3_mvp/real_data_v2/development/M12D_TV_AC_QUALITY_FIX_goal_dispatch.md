# M12D TV/AC 系统质量修复 Goal 调度

## 1. 当前状态

- 调度状态：`completed`
- 自动执行：heartbeat `catforge-m12d-tv-ac-quality` 已删除；QF15 发布门槛未通过，避免重复重跑
- 每次执行上限：一个模块闭环任务
- 当前任务：`M12D-RP-G10`（等价承接 M12D-QF-19）已完成；任务链结束
- 启动条件：已满足，用户于 2026-07-11 明确批准开始实施

当前任务链已执行完成。用户已授权提交、部署、正式重跑和 `current/published` 切换不再单独审批；质量门槛和分品类阻断规则继续有效。

## 2. 必读文档

- `docs/core3_mvp/real_data_v2/development/M12D_TV_AC_QUALITY_FIX_goal_dispatch.md`
- `docs/core3_mvp/real_data_v2/development/M12D_TV_AC_QUALITY_FIX_development_tasks.md`
- `docs/core3_mvp/real_data_v2/current_implementation/M12D_TV_system_quality_audit_20260711.md`
- `docs/core3_mvp/real_data_v2/sop_requirements/M12D_sku_purchase_reason_profile_requirements.md`
- `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_sku_purchase_reason_profile_design.md`
- `docs/core3_mvp/real_data_v2/sop_requirements/M12D_AC_sku_purchase_reason_profile_requirements.md`
- `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_AC_sku_purchase_reason_profile_design.md`
- `docs/core3_mvp/real_data_v2/development/M12D_AC_development_tasks.md`

## 3. 选择规则

1. 选择任务总览中第一个 `pending` 且前置任务均 `completed` 的任务。
2. 每个 goal 只完成一个模块闭环，不继续下一模块。
3. M12D-QF-02 至 M12D-QF-13 必须在同一任务内分别审计、修复、测试和重跑 TV/AC。
4. TV/AC 必须使用各自 taxonomy、阈值、市场池、购买理由和版本，不能交叉复用。
5. 上游模块任务不得顺带修改 M12D 评分；M12D 任务不得反向改写上游业务画像。
6. 代码提交、部署、正式重跑和 `current/published` 切换按测试、备份和回滚门槛直接执行，不再单独审批。
7. 阻塞时更新当前任务为 `blocked`，不得跳过到下一模块。

## 4. 阶段门槛

| 阶段 | 任务 | 进入下一阶段条件 |
| --- | --- | --- |
| 公共契约和双品类基线 | M12D-QF-01 | TV/AC 当前基线、typed contract 和 shadow 工具完成 |
| 上游模块闭环 | M12D-QF-02 至 M12D-QF-09 | 每个模块 TV/AC 均完成修复、测试、draft 重跑和报告 |
| M12D 生产逻辑 | M12D-QF-10 至 M12D-QF-13 | 输入传播、锚点评分、画像决策和发布控制在两个品类通过 |
| 验证与消费 | M12D-QF-14 至 M12D-QF-17 | TV/AC 全量 draft、竞品回归和类别隔离通过 |
| 部署 | M12D-QF-18 | 用户批准，提交范围、备份和回滚点确认 |
| 生产重跑和发布 | M12D-QF-19 | TV/AC 分别过门槛后分别切换，不允许合并平均 |

## 5. 强制停止条件

出现以下任一情况，当前任务停止：

- TV 或 AC 任一品类中，同一新增 blocking 问题覆盖超过 20%。
- TV 或 AC 的未影响回归 SKU 出现未声明业务变化。
- 需要降低强证据门槛或加入 SKU/品牌白名单才能通过。
- TV taxonomy、阈值、市场池或购买理由进入 AC，或反向串用。
- 任一品类影子结果偏离自身基线预期超过 5pp 且无法解释。
- 一个品类未达标，却试图用另一个品类的通过结果继续发布。

## 6. Goal Prompt

```text
继续 /Users/sjs/catforge 中的 M12D TV/AC 系统质量修复任务链。

先读取调度文件、任务链、TV/AC 需求和详细设计、TV 系统审计及 AC 既有任务记录。
选择第一个可执行 pending 任务，只执行一个模块闭环。

要求：
- 使用 goal 模式。
- 共享模块必须同时处理 TV 和 AC。
- 执行前分别记录两个品类的影响集合、允许迁移和未影响回归集合。
- 执行后分别测试、分别重跑该模块 draft、分别输出前后报告。
- 不跨任务，不提前发布，不把 M12D 生产逻辑写进竞品智能体。
- 不 stage/commit，除非用户明确要求。
- 完成后更新任务状态、产物、测试、双品类影响计数和下一个任务。
```

## 7. 当前指针

```text
HISTORICAL: M12D-QF-15 旧混合口径下 TV/AC 发布质量均为 limited；该 blocked 事实保留。
COMPLETED: `M12D-RP-G01` 至 `M12D-RP-G08` 已完成；新口径下 TV/AC 全量影子均为 ready，QF16/QF17 已由 RP-G07/G08 完成。
COMPLETED: M12D-RP-G09 / M12D-QF-18 已提交部署，205 revision 为 adeab0a，Alembic 为 0044。
COMPLETED: M12D-RP-G10 / M12D-QF-19 已完成 TV/AC 独立全量重跑、发布切换和线上验收。
```
