# G41A 海信 65E7Q 单 SKU 草稿验收回执

状态：completed

日期：2026-07-16

## 1. 结论

海信 65E7Q 的竞品画像已按纠偏后的目标完成：把现有竞品分析智能体一次分析得到的实际候选、逐款分析、顺序、角色和 Top 3 保存为可复用草稿。后续智能体读取这份草稿时不再重新召回全市场 SKU，也不再重新分析、打分、排序或选择竞品。

G41A 通过，允许创建 G41B；本 Goal 未执行 AC 生成、批量生成、review、publish、current 或 deprecated 操作。

## 2. 正式验收草稿

- 目标 SKU：`TV00029112`（海信 65E7Q）；
- version id：`99c944ba-6ff4-467b-9ab3-93fccfff1b19`；
- profile version：`competitor_profile_agent_snapshot_v2_tv_65e7q_g41a_20260716_r16`；
- method version：`competitor_profile_agent_snapshot_v2`；
- 状态：`success / draft / non-current`；
- 数据范围：目标 SKU 1 款、实际候选 20 款、共享 SKU snapshot 21 份、profile 1 份、pair 20 份、selection 3 份、relation 0 份；
- 原智能体分析结果 hash：`sha256:competitor_set_legacy_analysis_result_v1:cd894eaa9c42a7fdb4af99af1c3fe4af5fea29e523a3e011d398e234568285b6`；
- 画像结果 hash：`sha256:competitor_profile_agent_profile_result_v2:0c9e63b1ceb496540348680caaaa31b2faeffb4b43a91781583e1d9d9f2e676e`。

首次 agent snapshot v1 草稿 `1b11f56b-544a-4374-a602-1c475b7fda29` 因重复保存约 40MB 成熟分析数据、耗时 42.15 秒而判定不通过，保持不可变且不得发布。G41A 的通过结论只对应上述 method v2 草稿。

## 3. 与现有竞品分析智能体一致

落盘候选不是 353 款全品类 SKU，也不是重新设计的候选宇宙，而是现有智能体实际分析的 default20：

`TV00029020, TV00029936, TV00027801, TV00028909, TV00027912, TV00028166, TV00028829, TV00027861, TV00027541, TV00027899, TV00027027, TV00028099, TV00028546, TV00030053, TV00026065, TV00028423, TV00029169, TV00028082, TV00029120, TV00030137`

画像保存并恢复的分析顺序为：

`TV00028909, TV00027912, TV00027801, TV00028166, TV00027899, TV00027541, TV00028829, TV00029936, TV00029020, TV00029169, TV00028099, TV00026065, TV00028423, TV00027861, TV00027027, TV00030053, TV00028082, TV00030137, TV00029120, TV00028546`

Top 3 与原智能体逐项一致：

1. `TV00027801`，TCL 65Q9L PRO；
2. `TV00028909`，华为 VISION 智慧屏 5 PRO 65；
3. `TV00029936`，创维 65A7H PRO。

v1 与 v2 的 source hash、20 个 pair 的 source rank、角色、业务得分和 selected 状态逐项相同。

## 4. 存储与性能

v2 将每款 SKU 的重事实、卖点价值和采购理由数据压缩后只保存一次，profile 和 pair 只保存引用及 pair 专属过程/结论：

- profile payload：505,665 bytes；
- 21 份共享 snapshot 合计：6,638,701 bytes；
- compact readback：0.005 秒，3 条 SQL，未读取重 profile/snapshot payload；
- full readback：0.557 秒，4 条 SQL，无 N+1；
- Adapter 恢复完整 20 款智能体输入：1.755 秒；
- 保存画像后的完整竞品智能体 preview 答复：3.522 秒；
- 首次 v2 单 SKU 一次性容器生成：13.01 秒，包含容器启动、原智能体分析与一次事务落盘；
- 同版本幂等重跑：3.94 秒，返回 `reused`，未重新分析和写入重复结果。

本地同一真实 payload 的纯画像构建由 v1 的 11.64 秒降至 v2 的约 2.57 秒；205 首次生成不再出现 10 分钟级全品类装载。

## 5. 智能体零重算验收

验收时把以下四条现场计算路径替换为立即报错的禁止桩：

- 逐款 enrichment；
- Top 角色分配；
- Top 竞品选择；
- 旧 `competitor-set` 现场分析入口。

在四条路径均不可调用的条件下，竞品分析智能体仍从指定 draft 输出相同的 20 款候选和 Top 3。实际 SOP 只有：

1. `competitor-profile-read`；
2. `competitor-profile-adapter`；
3. `competitor-profile-render`。

`resolve-sku` 为 skipped，run count 为 0；其余三个步骤各执行一次。由此确认画像读取路径没有现场召回、分析、打分、排序或选择。

## 6. 数据边界

验收前后以下受保护数据行数完全一致：

- 旧竞品画像 V1：version 2、profile 532、pair 148,309、relation 1,038,163、selection 71；
- 采购理由画像：version 7、profile 1,751、anchor 17,899；
- 用户卖点价值画像：version 7、profile 691、candidate 45,070、item 3,123。

验收结束时活动数据库 writer 为 0。未修改旧 M12/M13/M14，未重跑 M03B—M12D，未生成其他 SKU，未执行任何发布状态切换。

## 7. 代码与验证

- 兼容与落盘纠偏提交：`d3a3220ce0edf74af6ff422d950d5f0201ca33c0`；
- 共享 snapshot 性能纠偏提交：`b491bd070b4515da98e02a7055066a9427b4605c`；
- 205 当前代码：`b491bd070b4515da98e02a7055066a9427b4605c`；
- migration head：`0047_core3_competitor_profile_v1_1`；
- 精确 staged-index 回归：130 passed；
- Python compileall：passed；
- API：healthy / ready，restart count 0。

## 8. 下一 Goal

G41B：只选择一个 AC SKU，按相同 agent snapshot v2 路径生成并验收单 SKU draft；在 G41B 通过前禁止创建 G41C 或生成 TV/AC 全量草稿。
