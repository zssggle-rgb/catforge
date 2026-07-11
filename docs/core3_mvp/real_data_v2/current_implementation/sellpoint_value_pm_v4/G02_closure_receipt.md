# G02 关闭回执：V4 详细设计与合同冻结

## Objective

基于已批准的 V4 需求和 G01 真实数据边界，冻结用户卖点价值分析 V4 的详细设计、typed schema、关系层、反事实合同、量化识别等级、产品经理结果合同、错误/降级状态机、需求追溯、测试计划和性能预算；不写运行代码，不修改数据库或 205。

## 前置输入

- G00 需求和任务链 commit：`d8f972b`；
- G01 artifact commit：`26aaf84`；
- G01 closure commit：`6c3525c`；
- G02 Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`；
- G02 timer：`catforge-v4-g02-10`。

## 实际产物

- `CATFORGE_ANALYST_sellpoint_value_pm_v4_design.md`；
- `G02_schema_contract.json`；
- `G02_requirements_traceability.md`；
- `G02_test_plan.md`；
- `G02_progress.md`；
- 本关闭回执；
- `G02_artifact_manifest.json`。

未修改运行代码、数据库 schema、205 文件、路由、V2/V3 或其他任务文件。

## 冻结的工程决策

1. V4 是 analyst 层的只读分析，不重建 M11C、M11D 或 M12D；
2. 新增运行文件不超过 3 个，新增能力只有关系层与识别层；
3. 权威来源使用 published lineage 与 current validation lineage 双时间面，冲突局部阻断；
4. 输出关系固定为采购理由到用户实际价值再到卖点组合；
5. base、same-value、stretch 三类反事实及其来源必须显式保存；
6. 价值成立、量化层级、产品角色和价格兑现分别建模，不压成总分；
7. Q5 仅允许 matched equal-choice price gap，且至少两条独立 A 级 pair、跨两个 model family；
8. M12C 旧分摊金额永不进入 V4 WTP；
9. 65E7Q 当前封顶 Q3，WTP 必须为空；
10. 产品经理主表不生成增减配、涨降价或通用下一步工作清单。

## 方法范围收缩

首版不实现多 SKU 结构需求模型。G01 已确认当前缺少完整促销、库存、外生工具变量、消费者级选择集和 outside option，无法可靠处理价格内生性与未观测产品质量。该方法不是延期但默认可做，而是当前证据边界下明确不准做。

## 验证与评审

| 验证 | 结果 |
| --- | --- |
| `jq -e . G02_schema_contract.json` | 通过 |
| typed invariant 必备项检查 | 通过 |
| 65E7Q / synthetic / M12C / no-N+1 测试覆盖检查 | 通过 |
| 行尾空白与 `git diff --check` | 通过 |
| plan-eng-review | clean，0 unresolved，0 critical gaps |
| 工程评审发现 | 1 项，已将跨 pair/model-family 门槛同步进 schema、测试和追溯 |

## 测试边界

- 单元测试覆盖 schema、关系、反事实、pair curve、状态机、渲染；
- 集成测试覆盖 authority、lineage、批量读取、CLI/flag 和 V2 回归；
- 固定回放覆盖 G01 五 cohort 与 65E7Q；
- synthetic positive fixture 才允许验证有界 WTP；
- 所有算法测试确定性运行，不调用外部 LLM 或网络。

## 性能预算

- 首页 SQL queries 不超过 20；
- 候选召回不超过 30，完整 snapshot 不超过 12；
- market cells 不超过 2,000；
- 本地 fixture P95 不超过 1 秒，205 read-only JSON P95 不超过 8 秒；
- 禁止逐 SKU、逐评论 N+1。

## Commit

- G02 核心设计产物：`f62b68f`；
- 本关闭回执、manifest 和完成状态：本文件所在的独立 closure commit。

## 下一 Goal 准入

`G03 allowed`。G03 只允许实现只读 context adapters、版本/线谱闸门和 typed schema，不得提前生成价值、反事实、量化或产品经理结论。
