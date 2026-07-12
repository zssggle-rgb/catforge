# M12D 购买理由成立度与购买阻力分层 Goal 调度

日期：`2026-07-11`

## 1. 当前状态

- 调度状态：`paused_for_publish_approval`
- 自动化：`catforge-m12d-10`
- 周期：每 10 分钟一次 heartbeat
- 单次上限：一个 goal、一个模块闭环任务
- 当前任务：`M12D-RP-G09` 已完成；等待用户明确批准 `M12D-RP-G10` 正式全量重跑和发布
- 旧链路：QF15 旧口径 blocked 结论保留为历史记录；当前阻塞已由 G06-G08 新口径验收解除，QF16/QF17 分别由 G07/G08 完成

## 2. 必读文档

- `docs/core3_mvp/real_data_v2/sop_requirements/M12D_reason_establishment_pressure_requirements.md`
- `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_reason_establishment_pressure_design.md`
- `docs/core3_mvp/real_data_v2/development/M12D_REASON_PRESSURE_development_tasks.md`
- `docs/core3_mvp/real_data_v2/development/M12D_TV_AC_QUALITY_FIX_goal_dispatch.md`
- `docs/core3_mvp/real_data_v2/development/M12D_TV_AC_QUALITY_FIX_development_tasks.md`
- `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF15A_tv_no_core_threshold_audit_report.md`

## 3. 调度规则

1. 先调用 `get_goal`；存在 active goal 时只继续该 goal。
2. 没有 active goal 时，选择任务表中第一个满足前置条件的 pending 任务并创建 goal。
3. 每次 heartbeat 只处理一个任务，不自动开始下一任务。
4. 完成后更新任务状态、产物、测试、TV/AC 影响集合和下一任务。
5. 阻塞时按 goal 规则处理，不跳过前置任务。
6. 不把 M12D 生产逻辑写进竞品智能体。
7. 不低于 7 分，不使用 SKU/品牌白名单。
8. 代码提交、migration 和部署不再要求单独审批，但必须保留精确提交范围、测试、备份、回滚点和上线验证。
9. G10 正式全量重跑、切换 current/published 或其他生产数据发布仍需明确批准，不由 heartbeat 自动执行。

## 4. Goal Prompt

```text
继续 /Users/sjs/catforge 中的 M12D 购买理由成立度与购买阻力分层任务链。

先读取：
- docs/core3_mvp/real_data_v2/development/M12D_REASON_PRESSURE_goal_dispatch.md
- docs/core3_mvp/real_data_v2/development/M12D_REASON_PRESSURE_development_tasks.md
- docs/core3_mvp/real_data_v2/sop_requirements/M12D_reason_establishment_pressure_requirements.md
- docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_reason_establishment_pressure_design.md

执行规则：
1. 先检查当前 goal；有未完成 goal 时只继续该 goal。
2. 没有未完成 goal时，选择第一个满足前置条件的 pending 任务并使用 goal 模式创建。
3. 每次只处理一个模块闭环任务，不跨任务。
4. 共享模块必须同时审计、修复和测试 TV/AC，使用各自 taxonomy、理由边界、市场池和版本。
5. 购买理由成立度与购买阻力必须分离；普通负面不得删除已成立理由。
6. proposition_only 不得输出为用户购买理由，但不得使整个 SKU 不可消费。
7. 不把 M12D 生产逻辑写进竞品智能体，不低于 7 分，不使用白名单。
8. 提交和部署按任务门槛直接执行；正式全量重跑、切换 current/published 或其他生产数据发布仍需用户明确批准。
9. 完成后更新任务状态、产物、测试结果、双品类影响计数和下一个任务。
```

## 5. 当前指针

```text
COMPLETED: M12D-RP-G01 TV/AC 双品类基线与验收样本。
COMPLETED: M12D-RP-G02 Typed contract 和兼容层。
COMPLETED: M12D-RP-G03 购买阻力独立计算和同锚点证据作用域。
COMPLETED: M12D-RP-G04 产品价值主张、用户承接和 9/8/7 成立门槛。
COMPLETED: M12D-RP-G05 锚点角色、SKU 状态、版本质量和按 SKU 消费。
COMPLETED: M12D-RP-G06 TV/AC 全量 shadow、业务审计和发布门槛复算。
COMPLETED: M12D-RP-G07 竞品智能体消费、Top 3 和报告业务语言回归。
COMPLETED: M12D-RP-G08 跨品类集成验收、QF15/QF16 回填和上线前结论。
COMPLETED: M12D-RP-G09 已提交并部署到 205，migration 升至 0044，服务和数据守卫验证通过。
PAUSED: M12D-RP-G10 正式全量重跑和切换 current/published 需要明确发布批准。
```
