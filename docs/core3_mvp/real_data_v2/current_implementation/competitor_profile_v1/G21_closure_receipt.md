# 竞品画像 V1 G21 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_quality_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_quality.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_diff.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_lifecycle.py` 的 G21 只读入口；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_quality.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_diff.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_lifecycle.py` 的 G21 只读集成测试。

## 2. 研究过的现有模式

实现前对照了三类以上现有模式：

1. G04 detailed design §8.3、§10、§14：版本质量、stale、diff 和发布边界；
2. 既有 `competitor_profile_lifecycle.py`：复用 scope、状态计数、七关系、selection rank 和 readback hash 完整性门禁，不复制发布状态机；
3. `sellpoint_value_profile_lifecycle.py`：复用确定性 version diff、业务字段变化与 hash-only 变化分离；
4. `purchase_reason_release_quality.py`：复用品类隔离、完整覆盖、系统性阻断和 typed quality assessment；
5. G20 materializer/read DTO：质量和 diff 只消费已形成的 draft/readback，不重新召回、评分、选择或生成业务结论。

## 3. 版本质量评估

`CompetitorProfileQualityService.assess_version` 同时支持：

- G20 `MaterializedCompetitorProfile`；
- `CompetitorProfileDraftBundle`；
- repository `CompetitorProfileReadBundle`。

质量状态严格区分：

| 状态 | 条件 |
| --- | --- |
| `ready` | 权威 SKU 全覆盖、生成完成、全部 profile ready、无失败和 P0/P1/P2 问题 |
| `limited` | 覆盖完整且生成完成，但存在 partial、review-required 或 stale profile 等可复核问题 |
| `blocked` | 已完成后漏 SKU、生成失败、跨项目/品类、清单或 materialized hash 冲突、状态/子项计数冲突等 P0/P1 问题 |
| `unassessed` | 尚未完成生成，且没有独立 P0/P1 阻断问题 |

评估保存：权威/已评估/缺失/意外 SKU 清单，ready/partial/blocked/failed 和 pair/relation/selection 实际计数，稳定 issue 清单、review 标记与 result hash。

确定性门禁包括：

- authoritative manifest 去重、计数和 production hash；
- 完成后 SKU 全覆盖；
- 失败 SKU 明细与 failed count 一致；
- target、project、category 和 SKU prefix 隔离；
- G20 materialized result hash 回算；
- version ready/partial/blocked/pair/relation/selection 计数与实际结果一致；
- 每个 pair 七关系完整；
- 输入顺序变化不改变 assessment hash。

## 4. Freshness 判断

`assess_freshness` 只比较版本锁定的 `ServingScope` 与当前 scope：

- source authority 的 profile/schema/rule/taxonomy/source batch/result hash 变化；
- analysis population、market window、taxonomy、storage/source batch、SKU prefix、authoritative manifest 和 release scope 变化；
- 当前 scope 不可获得或 authority 缺失时返回 `unknown`；
- 存在已确认变化时返回 `stale`；
- 完全一致时返回 `current`。

该方法是只读判断：不改写 version、profile、pair、relation、selection，不改变 `release_status`、`is_current`、published/current 或 analytical result hash。跨项目、跨 TV/AC freshness 比较直接拒绝。

## 5. Version diff

`CompetitorProfileDiffService.diff_profiles` 在同一 project/category/target SKU 内解释：

- candidate 新增、移除、状态和 competitor/reference/selected membership 变化；
- 七类关系的 status、primary、confidence 和问题可用性变化；
- weighted price、weekly volume、价差/量比和 comparability 变化；
- 重点竞品新增、移除、rank、决策主题和关系角色变化；
- 主画像 analysis/conclusion/freshness/confidence/review 状态变化；
- 市场摘要、候选/关系统计、优势、可替代价值、量价压力、同品牌、配置决策、证据和限制等业务分区变化。

输出稳定中文变化摘要和 diff hash。仅 result hash 变化而业务字段未变化时明确写为 hash-only change，不虚构候选、关系或产品结论变化。relation 输入顺序变化不会产生假 diff。

`CompetitorProfileLifecycleService` 新增三个只读入口：

- `assess_version_quality`；
- `assess_version_freshness`；
- `diff_profiles`。

repository readback diff 锁定明确的两个 profile version，不读取旧 M12/M13/M14，也不 fallback 现场 `competitor-set`。

## 6. 验证

- G21 新增专项：15 项通过；
- G21 quality/diff/lifecycle 相关集合：25 项通过；
- G05—G21 全链：247 项通过；
- G21 quality、quality schemas、diff 与 lifecycle 联合覆盖率：91%；
- `competitor_profile_diff.py`：95%；
- `competitor_profile_quality.py`：89%；
- `competitor_profile_quality_schemas.py`：92%；
- `competitor_profile_lifecycle.py`：90%；
- Ruff check：通过；
- Ruff format check：通过；
- compileall：通过。

已覆盖正常、partial、blocked、in-progress unknown、生成失败、缺 SKU、重复、清单冲突、materialized hash 冲突、状态计数冲突、跨品类、输入顺序反转、hash-only diff、跨 target diff 和只读不变性。

## 7. 状态变化与边界

- 本地持久化业务数据写入：无；
- 205 连接、数据库写入和 migration：无；
- review/publish/current/deprecated：均未执行；
- 旧 M12/M13/M14：未修改；
- 部署：无；
- Git 暂存/提交：无。

G21 只完成质量、新鲜度和版本变化的确定性判断及只读服务入口。卡片、报告、问答、用户卖点价值消费切换、205 部署和 SKU 草稿生成均不属于本 Goal。

## 8. 下一 Goal

允许创建 G22：执行本地综合测试、方法/工程/业务评审和精确提交。G22 不允许部署 205、运行 migration、生成画像或切换任何 published/current 状态。
