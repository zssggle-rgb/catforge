# G01 关闭回执：数据可行性与真实 cohort 冻结

## Objective

只读核验 CatForge 用户卖点价值分析 V4 的现有数据可行性，冻结字段/版本矩阵、65E7Q、代表性 cohort、三类反事实候选和输入 manifest；不写运行代码，不修改数据库或 205 数据。

## 前置输入

- G00 需求和任务链 commit：`d8f972b`；
- 需求文档：`CATFORGE_ANALYST_sellpoint_value_pm_v4_requirements.md`；
- Goal 调度：`CATFORGE_ANALYST_sellpoint_value_pm_v4_goal_dispatch.md`；
- G01 Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`；
- G01 timer：`catforge-v4-g01-10`。

## 实际产物

- `G01_progress.md`；
- `G01_data_feasibility_matrix.md`；
- `G01_65E7Q_fixture.json`；
- `G01_cohort_manifest.json`；
- 本关闭回执；
- `G01_artifact_manifest.json`。

未修改运行代码、数据库 schema、205 文件、路由、V2/V3 或其他任务文件。

## 数据来源与版本

- 环境：205 `catforge_dev`；
- source batches：`m00_20260623014631_c8630747`、`m00_20260619084551_857df63b`、`m00_20260613004311_d548f6dc`；
- 最新事实/语义版本：M03B v0.2、M04C v0.2、M05C v0.2、M07 v2、M09C v0.3、M10C v0.3、M11C v0.4、M12C v0.2；
- M11D：v0.1；
- 已发布 M12D：`m12d_tv_purchase_reason_profile_v0_1_draft`；
- M14：只覆盖旧批次 84 个目标，65E7Q 无 M14 run。

## 验证命令与结果

| 验证 | 结果 |
| --- | --- |
| 205 `healthz` / `readyz` | `ok` / `database ok` |
| 所有 SQL 连接先执行 `SET TRANSACTION READ ONLY` | 通过 |
| `jq -e . G01_65E7Q_fixture.json` | 通过 |
| `jq` 检查 5 个 cohort 均有 manifest hash | 通过 |
| `git diff --check` | 通过 |
| 精确暂存检查 | 仅 G00/G01 文件，无其他任务文件 |

## 业务门禁

- 价值战场、市场空间、采购理由假设、用户实际体验、卖点组合和 SKU 量价表现均有真实字段：通过；
- 基础价值、同价值和上探三类反事实候选存在：通过；
- 65E7Q 当前量化上限明确：通过；
- 无数据的促销、库存未被补写：通过；
- 没有生成自动增减配、涨降价或通用工作清单：通过。

## 方法门禁

- 五类 cohort 已冻结：通过；
- 价值成立与量化程度分离：通过；
- M11D 分配未当作真实购买归因：通过；
- M12C 旧金额未当作 WTP：通过；
- 只有同价值竞品时禁止卖点增量 WTP：通过；
- 版本线谱冲突可被识别：通过。

## 工程门禁

- G01 未写运行代码：通过；
- 未写 205 或数据库：通过；
- fixture 脱敏且带 source aggregate hash：通过；
- 每个 cohort 有输入 manifest hash：通过；
- 工作区其他脏改动保持未暂存：通过。

## 关键结论

65E7Q 当前可以输出用户价值成立和整机同价选择关联。它只有一个强直接价格对照，基础价值对照尚未进入现有价格曲线，且高亮、控光、MiniLED、高刷随整机共同变化；因此不得输出任何单卖点或高端画质组合 WTP。

同时，已发布 M12D 仍引用旧版 M03B/M04C/M12C，而当前上游已升级。G02/G03 必须实现显式版本线谱闸门，不能用 `is_current=true` 静默混读。

## 已知限制

- 没有可用库存字段；
- 原始促销标记覆盖不足，只有 M07 派生促销疑似标记；
- M11D 与已发布 M12D 生成时间早于 7 月 11 日最新上游；
- C01 是“可识别候选”，不是已完成的 WTP 估计；
- 65E7Q 没有 M14 run，竞品角色来自 fallback。

## Commit

- G00 前置文档：`d8f972b`；
- G01 核心产物：`26aaf84`；
- 本关闭回执和 manifest：本文件所在的独立 closure commit。

## 下一 Goal 准入

`G02 allowed`。G02 只允许做详细设计、typed schema、算法/状态机和测试计划，不得提前写运行代码。
