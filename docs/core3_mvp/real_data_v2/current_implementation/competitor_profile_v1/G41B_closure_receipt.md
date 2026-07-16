# G41B AC 单 SKU 草稿验收回执

状态：completed

日期：2026-07-16

## 1. 结论

G41B 选择现有竞品分析智能体的 AC complete 样本 `AC00026378 / 小米 KFR-26GW/V1A1`，完成一次 agent snapshot v2 草稿生成和全消费链验收。画像保存的是原智能体实际分析的 16 款候选，不是 155 款 AC 全品类扫描，也没有重新使用 TV 候选或 TV 分析规则。

Repository、Reader、Adapter 和竞品分析智能体 preview 均能恢复原始候选顺序、分析顺序、角色、业务得分和 Top 3；读取端现场召回、分析、打分、角色分配、排序和选择均为 0。G41B 通过，允许创建 G41C。

本 Goal 未生成其他 SKU，未执行 review、publish、current 或 deprecated，未重跑 M03B—M12D，未修改旧 M12/M13/M14 或旧画像。

## 2. 验收 SKU 与上游

- 目标 SKU：`AC00026378`；
- 品牌/型号：小米 `KFR-26GW/V1A1`；
- AC 产品层级：`wall_hp_1_or_below`；
- 当前正式 AC 采购理由画像：`m12d_ac_purchase_reason_profile_v0_4`；
- authority id：`m12d_ver_58797b2bb888a566216896d0`；
- batch：`m00_20260624000202_1150a669`；
- authority result hash：`f4007c13877cc46d36bd16a77b5cec3c6b2f2c51df28b29dbecced723dce70cc`；
- 当前 AC authority 共 155 款，其中 ready 143 款；目标 SKU 存在唯一 published/current 画像。

该 SKU 已在 G28 作为 `published_ready` 的正式 AC complete fixture，默认调用实际返回 16 款候选并形成 Top 3，因此适合验证 AC 完整路径。

## 3. 正式验收草稿

- version id：`e89c4575-f137-4917-9c3d-ead871a6b335`；
- profile version：`competitor_profile_agent_snapshot_v2_ac_26378_g41b_20260716_r1`；
- release scope：`d8d2245b-358b-4a64-95cc-9d7f2341bd26:AC:c5566f83fdfb5d8e5ce4bf9f`；
- method version：`competitor_profile_agent_snapshot_v2`；
- 状态：`success / draft / non-current`；
- 数据范围：目标 1 款、候选 16 款、共享 SKU snapshot 17 份、profile 1 份、pair 16 份、selection 3 份、relation 0 份；
- 原智能体分析结果 hash：`sha256:competitor_set_legacy_analysis_result_v1:56f4ef43be967d20218cf42760a41fec5f9e0f1a615462a3cfe06ceca35c6142`；
- 画像结果 hash：`sha256:competitor_profile_agent_profile_result_v2:d6fd8ba8cb729e550cac002f8f32ba012b25dd937df9546a4a631b95d89942f4`。

## 4. 原智能体结果一致性

原始候选池顺序与画像回读顺序逐项一致：

`AC00034712, AC00039346, AC00036170, AC00038680, AC00038373, AC00039161, AC00039126, AC00038750, AC00038752, AC00036257, AC00038477, AC00036778, AC00035276, AC00035345, AC00034716, AC00039204`

原始分析顺序与画像恢复顺序逐项一致：

`AC00034712, AC00036257, AC00039161, AC00036170, AC00038680, AC00036778, AC00039126, AC00034716, AC00038477, AC00039346, AC00038373, AC00038750, AC00038752, AC00035276, AC00039204, AC00035345`

Top 3 与 G28 旧智能体正式基线一致：

1. `AC00034712`，奥克斯 `KFR-26GW/BPR3AQS1(B1)`，`primary_direct`；
2. `AC00039161`，格力 `KFR-26GW/NHGT1BGJ`，`strong_direct`；
3. `AC00038373`，晶弘 `KFR-26GW/JHFNHAA1BJ`，`scenario_alternative`。

16 个 pair 的 source rank、角色、完整业务得分、top3 eligibility、已算过程和结论均与旧智能体 fixture 逐项一致。每个 pair 均保存并恢复以下非空结果：基础比较、语义重合、参数/卖点重合、量价重合、价值锚点、替代压力、采购压力、购买池、加权重合、分维度命中、市场验证、选择门禁、排序轨迹和共同业务语境。

## 5. AC 语义与 TV 串线验收

完整 Reader + Adapter 恢复后验证：

- 目标和 16 款候选 SKU 均为 `AC`，不存在 TV SKU；
- 目标与候选 `screen_size_inch` 均为 null，未把电视尺寸当作 AC 分层；
- 目标层级为 `wall_hp_1_or_below`；
- 产品形态包含 `installation_type`；
- 能力段包含 `horsepower_hp`、`cooling_capacity_w` 等 AC 参数；
- 用户任务、目标客群和价值战场均存在，包含 `TASK_ENERGY_SAVING_LONG_USE`、`TG_FAMILY_LONG_USE_SAVER`、`BF_WALL_SMALL_ENTRY_VALUE` 等 AC 语义；
- 价值锚点包含“长期省电抵消更高价格”“同价位能效/能力获得感”“远程/智能控制减少操作摩擦”等 AC 购买价值；
- 共恢复 19 个 `ac_claim_*` claim code；
- 结构化 payload 中不存在 `tv_claim_*`、HDMI、MiniLED、刷新率或画质参数；
- 最终智能体业务答案不存在电视、画质、HDMI、游戏或 MiniLED 话术。

原始用户评论中存在一条包含“电视”字样的用户原话；它作为证据原文保留，不属于 taxonomy、参数、任务、战场、卖点或最终业务结论，因此不构成 TV 规则串线。

## 6. 量价与完整消费

- 目标 SKU 保存加权均价和周均销量；
- 16 款候选全部保存 `price_wavg` 和 `avg_weekly_sales_volume`；
- pair 的 `sales_overlap`、`market_validation` 和购买压力均为非空已算结果；
- full Reader 恢复 17 份共享 snapshot；
- Adapter 恢复完整 16 款候选事实、卖点价值、采购理由和 pair 结论。

由此确认 AC 的量价、产品形态、能力段和用户价值均来自 AC 数据，不是只验证 SKU 前缀。

## 7. 性能与幂等

- 首次单 SKU 生成：6.883 秒，包含一次性容器启动、原智能体分析和一次事务落盘；
- 同版本重跑：3.681 秒，返回 `reused`，version id、source hash、profile hash、候选顺序和 Top 3 均不变；
- profile payload：428,332 bytes；
- 17 份共享 snapshot 合计：1,172,013 bytes；
- compact readback：0.0047 秒，3 条 SQL，未读取重 profile/snapshot payload；
- full readback：0.210 秒，4 条 SQL，无 N+1；
- Adapter：0.418 秒；
- 完整竞品分析智能体 preview：0.742 秒。

## 8. 智能体零重算

验收时把逐款 enrichment、Top 角色分配、Top 竞品选择和旧 `competitor-set` 现场分析入口全部替换为立即报错的禁止桩。四条路径均不可调用时，智能体仍从指定 draft 输出相同的 16 款候选、顺序、角色和 Top 3。

实际 SOP 仅包含：

1. `resolve-sku`：skipped，run count 0；
2. `competitor-profile-read`：ok，run count 1；
3. `competitor-profile-adapter`：ok，run count 1；
4. `competitor-profile-render`：ok，run count 1。

## 9. 数据保护与运行态

验收前后受保护数据行数完全一致：

- 旧竞品画像 V1：version 2、profile 532、pair 148,309、relation 1,038,163、selection 71；
- 采购理由画像：version 7、profile 1,751、anchor 17,899；
- 用户卖点价值画像：version 7、profile 691、candidate 45,070、item 3,123。

agent snapshot v2 的变化严格等于本次一个 AC 草稿：总计由 1 个 TV version、21 snapshots、1 profile、20 pairs、3 selections，变为 2 个 TV/AC version、38 snapshots、2 profiles、36 pairs、6 selections；relations 仍为 0。验收结束时活动数据库 writer 为 0。

205 运行态：

- 代码：`b491bd070b4515da98e02a7055066a9427b4605c`；
- migration：`0047_core3_competitor_profile_v1_1 (head)`；
- API：healthy；
- ready：database ok；
- restart count：0。

## 10. 下一 Goal

G41C：只生成 TV/AC 全量 agent snapshot v2 draft 并做全量只读复核。在 G42 获得新的明确批准前，G41C 仍不得执行 review、publish、current 或 deprecated。
