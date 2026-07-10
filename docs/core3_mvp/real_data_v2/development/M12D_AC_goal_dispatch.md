# M12D AC 与竞品智能体 Goal 调度队列

## 1. 调度目标

本文件是 AC M12D 与竞品智能体 AC 消费验收的定时器调度入口。它只负责选择下一个 pending 任务，并约束每次 heartbeat 只执行一个 goal。

当前自动调度频率：每 10 分钟触发一次，每次只允许推进一个任务编号。

## 2. 调度文档

| 任务链 | 文件 |
| --- | --- |
| AC M12D SKU成交理由画像 | `docs/core3_mvp/real_data_v2/development/M12D_AC_development_tasks.md` |
| AC M12D 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M12D_AC_sku_purchase_reason_profile_requirements.md` |
| AC M12D 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_AC_sku_purchase_reason_profile_design.md` |
| 竞品智能体通用任务链 | `docs/core3_mvp/real_data_v2/development/CATFORGE_ANALYST_competitor_answer_development_tasks.md` |

## 3. 总调度顺序

### 阶段 A：AC M12D 独立资产生产

必须先完成 AC M12D 的证据审计、taxonomy 提炼、实现、小批量验证、全量生成和版本发布。

| 顺序 | 任务编号 | 状态 | 任务 |
| ---: | --- | --- | --- |
| 1 | AC-M12D-G01 | completed | 上游证据审计与样本确认 |
| 2 | AC-M12D-G02 | completed | AC 价值主题/购买理由候选提炼脚本 |
| 3 | AC-M12D-G03 | completed | AC 标准 taxonomy v0.1 人审草案固化 |
| 4 | AC-M12D-G04 | completed | taxonomy loader 和 candidate generator 支持 AC |
| 5 | AC-M12D-G05 | completed | AC 证据强度评分和角色判定 |
| 6 | AC-M12D-G06 | completed | AC 单 SKU CLI 与 Markdown 预览 |
| 7 | AC-M12D-G07 | completed | AC 小批量验证与规则修正 |
| 8 | AC-M12D-G08 | completed | AC 全量 batch 生成 |
| 9 | AC-M12D-G09 | completed | 发布 AC M12D 版本与下游契约冻结 |

### 阶段 B：竞品智能体消费 AC M12D

AC-M12D-G09 已完成，阶段 B 可从 AC-CA-G01 开始。竞品智能体仍不得生成 M12D 或修改 AC 锚点角色。

| 顺序 | 任务编号 | 状态 | 任务 |
| ---: | --- | --- | --- |
| 10 | AC-CA-G01 | completed | 竞品智能体 AC M12D 消费验收 |

## 4. 定时器选择规则

每次定时器触发时：

1. 读取本文件、AC 任务链、AC 需求和 AC 详细设计。
2. 优先选择阶段 A 中第一个 `pending` 的 AC-M12D-Gxx。
3. 只有 AC-M12D-G09 已完成后，才选择阶段 B 中第一个 `pending` 的 AC-CA-Gxx。
4. 每次只执行一个任务，创建一个 goal。
5. 不跨任务继续实现。
6. 不复用 TV taxonomy 作为 AC 标准锚点。
7. 不把 M12D 生产逻辑写进竞品智能体。
8. 完成后更新：
   - 本文件对应任务状态。
   - `M12D_AC_development_tasks.md` 中对应任务状态。
   - 产物路径、测试结果和下一个任务。
9. 如果任务阻塞，标为 `blocked`，写明阻塞原因，不跳过到下一个正式任务。

## 5. 定时器 Prompt 模板

```text
继续 /Users/sjs/catforge 中的 CatForge AC M12D 与竞品智能体任务链。

请先读取：
- docs/core3_mvp/real_data_v2/development/M12D_AC_goal_dispatch.md
- docs/core3_mvp/real_data_v2/development/M12D_AC_development_tasks.md
- docs/core3_mvp/real_data_v2/sop_requirements/M12D_AC_sku_purchase_reason_profile_requirements.md
- docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_AC_sku_purchase_reason_profile_design.md

按调度规则选择下一个 pending 任务，只执行一个任务。

要求：
- 使用 goal 模式执行该任务。
- 不跨任务实现。
- 不复用 TV taxonomy 作为 AC 标准锚点。
- 不把 M12D 生产逻辑写进竞品智能体。
- 不 stage/commit，除非用户明确要求。
- 完成后更新任务状态、产物路径、测试结果和下一个任务。
- 如果阻塞，标记 blocked 并说明阻塞条件。
```

## 6. 当前下一个任务

```text
暂无 pending 任务。AC M12D 与竞品智能体 AC 消费验收任务链已完成。
```

## 7. 最近完成记录

### AC-CA-G01 竞品智能体 AC M12D 消费验收

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/sop_orchestrators.py`
  - `apps/api-server/app/services/core3_real_data/analyst/anchor_substitutability.py`
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py`
  - `apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/AC_CA_G01_m12d_consumption_validation_20260708.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/AC_CA_G01_competitor_set_AC00032338_20260708.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/AC_CA_G01_competitor_set_AC00032338_20260708_summary.json`
- 实现内容：
  - `competitor-set` SOP 消费 published M12D 下游合约，调用既有锚点可替代性和替代压力算法。
  - 目标 M12D 缺失时只记录降级，不覆盖旧事实维度评分；目标有 M12D、候选缺失时候选锚点维度明确 blocked。
  - 报告层保留 M12D 的空锚点结果，不再用旧参数/卖点 fallback 冒充 AC 成交理由。
- 真实验收：
  - 目标 SKU：`AC00032338`，格力 `KFR-35GW/(35551)FNHAA-B1`。
  - M12D 消费状态：`consumed_with_review`。
  - 目标合约：`published_degraded` / `degraded_pair_scoring`，`m12d_profile_version=m12d_ac_purchase_reason_profile_v0_1_draft`。
  - Top 3 报告展示关键价值锚点可替代性和替代压力；当前 AC M12D 质量口径要求复核，不输出无条件强替代结论。
- 边界：
  - 未生成 M12D，未修改 M12D 生产逻辑，未修改 AC 锚点角色，未复用 TV taxonomy，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py -q`：82 passed。
  - `apps/api-server/.venv/bin/pytest apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py -q`：19 passed。
  - 205 `competitor-set` AC 真实验收命令：通过，产出 Markdown 和 summary JSON。
- 下一个任务：暂无 pending 任务，AC M12D 与竞品智能体 AC 消费验收任务链完成。

### AC-M12D-G09 发布 AC M12D 版本与下游契约冻结

- 状态：completed。
- 产物：
  - `scripts/m12d_g09_publish_and_export_contract.py`
  - `scripts/m12d_ac_g09_publish_and_export_contract.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G09_published_contract_fixture.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G09_published_contract_report.md`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 实现内容：
  - 复用通用 M12D G09 发布契约函数，同时参数化任务名、缺失 SKU 和报告标题，保持 TV 默认行为不变。
  - 新增 AC G09 发布脚本，固定 AC 批次、AC profile version 和 AC 文件名；自动从 AC 草稿画像中选择 fixture 样本。
  - 导出 AC 下游读取契约，明确 `published_ready`、`published_degraded`、`published_unusable`、`not_found` 的消费动作。
- 205 发布结果：
  - 批次：`m00_20260624000202_1150a669`。
  - 发布版本：`m12d_ac_purchase_reason_profile_v0_1_draft`。
  - version：`published/is_current=true`，`published_by=codex-ac-m12d-g09`。
  - profile：155/155 为 `published/current`，`product_category=AC`。
  - anchor：1879/1879 为 `published/current`，`product_category=AC`。
- 发布质量口径：
  - 发布决策：`publish_current_with_degraded_consumption_contract`。
  - SKU 155，ready 50，需复核 155，低置信 136，核心成交理由缺失 136，失败 0。
  - current 只表示下游可以读取冻结契约；低置信、需复核或缺核心理由的 SKU 必须以 `published_degraded` 降级消费。
- 下游 fixture：
  - 样本：`AC00026378`、`AC00032338`、`AC00028640`、`AC00028642`。
  - 样本覆盖核心锚点、辅助锚点、弱表达、风险拖拽和核心缺失。
  - 样本状态均为 `published_degraded` / `degraded_pair_scoring`。
  - 缺失 SKU 与未发布版本 fixture 均为 `not_found` / `block_target_or_drop_candidate`。
- 边界：
  - 未进入 AC-CA-G01，未修改竞品智能体，未把 M12D 生产逻辑写入竞品智能体。
  - 未复用 TV taxonomy 作为 AC 标准锚点，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m compileall scripts/m12d_g09_publish_and_export_contract.py scripts/m12d_ac_g09_publish_and_export_contract.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：26 passed。
  - `apps/api-server/.venv/bin/python scripts/m12d_ac_g09_publish_and_export_contract.py --database-url "$DB_URL" --publish`：205 发布和 fixture 导出通过。
  - `python3 -m json.tool docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G09_published_contract_fixture.json`：通过。
- 下一个任务：AC-CA-G01 竞品智能体 AC M12D 消费验收。

### AC-M12D-G08 AC 全量 batch 生成

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_runner.py`
  - `scripts/m12d_ac_g08_generate_full_batch.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G08_full_batch_generation.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G08_full_batch_generation_report.md`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 实现内容：
  - 通用 `PurchaseReasonProfileBatchGenerator` 支持 AC batch 草稿生成，同时保持 TV/AC taxonomy 品类隔离校验。
  - 新增 AC G08 全量生成脚本，按 M07 AC 当前 batch 选择 155 个 SKU，调用 M12D 通用画像生成链路写入 draft 三表。
  - 输出 AC 全量 JSON/Markdown 报告，包含失败、低置信、低证据/核心缺失、需复核、锚点角色分布和 DB 写入计数。
- 全量生成结果：
  - 读取批次/入库批次：`m00_20260624000202_1150a669`。
  - 草稿版本：`m12d_ac_purchase_reason_profile_v0_1_draft`。
  - SKU 数 155，成功率 1.0000，失败 0。
  - 低置信 136，低证据/核心成交理由缺失 136，有核心成交理由 19，需复核 155。
  - 写入记录：version 1、profile 155、anchor 1879。
  - DB 校验：version 为 `draft/is_current=false`，profile/anchor 均为 `product_category=AC`，published 记录数为 0。
- 边界：
  - 未执行 G09 发布，未改发布状态，未让竞品智能体消费草稿版本。
  - 未修改竞品智能体，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：25 passed。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_profile_runner.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py scripts/m12d_ac_g08_generate_full_batch.py`：通过。
  - `apps/api-server/.venv/bin/python scripts/m12d_ac_g08_generate_full_batch.py --database-url "$DB_URL" --limit 5`：dry-run 通过。
  - `apps/api-server/.venv/bin/python scripts/m12d_ac_g08_generate_full_batch.py --database-url "$DB_URL" --write`：205 全量草稿写入通过。
- 下一个任务：AC-M12D-G09 发布 AC M12D 版本与下游契约冻结。

### AC-M12D-G07 AC 小批量验证与规则修正

- 状态：completed。
- 产物：
  - `scripts/m12d_ac_g07_validate_purchase_reason_profiles.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G07_small_batch_validation.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G07_small_batch_validation_report.md`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 实现内容：
  - 新增 AC 小批量验证脚本，默认跑 G01 固定 15 个 AC 样本，只读调用 M12D 单 SKU 预览，不写生产表。
  - 修正 ContextBuilder 的上游版本路由：`product_category=AC` 使用 AC M03B/M04C/M05C/M09C/M10C/M11C 版本，避免真实库 AC 证据被误判缺失。
  - 修正 AC 评分硬阻断口径：`partial` 输入只降置信和触发复核，不再等同 `missing` 阻断核心；`missing/unknown` 仍阻断 M12C/场景/市场核心门槛。
  - 报告按 SKU 展示核心、支撑、弱表达、风险、非 ready 输入和验证旗标。
- 小批量验证结果：
  - 15 个样本预览失败 0。
  - 低置信 14，需复核 15。
  - 有核心成交理由 1，有风险拖拽 8。
  - 3 个缺 M12C 样本均未进入 `core_payment`。
  - 2 个负评样本均识别为风险拖拽，未出现负评样本核心误判。
- 边界：
  - 未执行 G08 全量 batch 生成，未写 M12D profile 表，未发布版本，未修改竞品智能体，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：24 passed。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py scripts/m12d_ac_g07_validate_purchase_reason_profiles.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `apps/api-server/.venv/bin/python scripts/m12d_ac_g07_validate_purchase_reason_profiles.py --database-url "$DB_URL"`：通过，生成 JSON/Markdown 产物。
- 下一个任务：AC-M12D-G08 AC 全量 batch 生成。

### AC-M12D-G06 AC 单 SKU CLI 与 Markdown 预览

- 状态：completed。
- 产物：
  - `apps/api-server/app/cli/catforge_analyst.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_preview.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 实现内容：
  - `sku-purchase-reason` 支持 `product_category=ac` 时默认选择 `m12d_ac_purchase_reason_anchor_taxonomy_v0.1`。
  - 单 SKU Markdown 预览放开 AC 品类，仍保留 `category_code` 与 `product_category` 一致性校验，以及 taxonomy loader 的品类隔离错误。
  - Markdown 增加品类字段，AC 输出按购买理由、证据域、支撑/弱表达/风险和输入覆盖展示。
  - `SkuPurchaseReasonContextBuilder` 的 M03B 快照补充 `param_values_json`，使 AC 能读取匹数、APF、新风量、噪音、自清洁、智控等参数事实。
  - 新增 AC 单 SKU CLI/Markdown fixture，验证 AC 强证据链可生成业务可读预览。
- 边界：
  - 未实现 G07 小批量验证。
  - 未批量生成 AC M12D SKU 画像，未写数据库，未发布版本，未修改竞品智能体，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：23 passed。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/cli/catforge_analyst.py apps/api-server/app/services/core3_real_data/purchase_reason_profile_preview.py apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
- 下一个任务：AC-M12D-G07 AC 小批量验证与规则修正。

### AC-M12D-G05 AC 证据强度评分和角色判定

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 实现内容：
  - 在通用 M12D scorer/classifier 中增加 AC 专属门槛，不改变 TV taxonomy 和 TV 既有评分路径。
  - AC `core_payment` 必须满足强证据、至少 2 个证据域、至少 1 个强证据域、具备场景匹配，且无 AC 核心阻断旗标。
  - M12C 缺失、场景/语义市场输入缺失、市场承接弱或缺失、M12C 风险/弱角色占优、服务/安装/补贴-only 均阻断 AC 核心成交理由。
  - 评论负向占优或 M12C `drag_factor` 继续进入 `risk_drag`。
  - 在 `role_reason_json` 中记录 AC 输入状态、M12C 角色和核心阻断旗标，便于业务追溯评分依据。
- 边界：
  - 未实现 G06 的 AC 单 SKU CLI 与 Markdown 预览。
  - 未生成 AC SKU 画像，未写数据库，未修改竞品智能体，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：22 passed。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
- 下一个任务：AC-M12D-G06 AC 单 SKU CLI 与 Markdown 预览。

### AC-M12D-G04 taxonomy loader 和 candidate generator 支持 AC

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/constants.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_anchor_taxonomy.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 实现内容：
  - 新增 AC taxonomy version 常量。
  - `M12DAnchorTaxonomyLoader` 支持 `product_category=AC` 加载 `m12d_ac_purchase_reason_anchor_taxonomy_v0.1`。
  - 新增 AC taxonomy 代码配置，包含 9 个 value themes 和 13 个 purchase reasons。
  - AC evidence patterns 覆盖参数、事实卖点、评论、市场、语义和 M12C。
  - 单一厂家表达如一级能效、新风、静音、柔风、防直吹、自清洁、智能、低价/补贴会生成弱候选或 `role_cap=weak_expression`。
  - 候选生成器核心算法保持通用，不写 AC 专用生产逻辑到竞品智能体。
- 边界：
  - 未做 G05 的证据强度评分。
  - 未做最终角色判定。
  - 未生成 SKU 画像，未写数据库，未修改竞品智能体，未 stage/commit。
- 测试/验证：
  - `compileall`：通过。
  - `pytest ... -k "ac_anchor_taxonomy or standard_ac_anchors or single_energy_claim or tv_anchor_taxonomy or standard_tv_anchors"`：5 passed。
  - `pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：17 passed。
  - taxonomy smoke：AC 可加载 9 个 value themes / 13 个 purchase reasons；TV 专属画质/游戏购买理由未进入 AC taxonomy。
- 下一个任务：AC-M12D-G05 AC 证据强度评分和角色判定。

### AC-M12D-G03 AC 标准 taxonomy v0.1 人审草案固化

- 状态：completed。
- 产物：
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_standard_anchor_taxonomy_v0_1.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_standard_anchor_taxonomy_v0_1.json`
- 输入依据：
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_evidence_audit_20260708.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G02_value_theme_purchase_reason_candidates.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G02_value_theme_purchase_reason_candidate_report.md`
- 固化结果：
  - 9 个 AC 标准价值主题。
  - 13 个 AC 标准购买理由。
  - 每个购买理由均写明成立逻辑、必要证据、弱表达上限和冲突降级。
  - 全局角色上限覆盖 M12C/M11D 缺失、评论语义缺失、单一厂家表达、价格/补贴-only、服务履约-only、M12C 风险/弱角色主导等情况。
- 边界：
  - 本任务只固化人审草案和 JSON 配置草案。
  - 未实现 AC taxonomy loader，未实现 candidate generator，未实现 scorer，未生成 SKU 画像，未修改竞品智能体，未 stage/commit。
  - 草案 `published=false`，`competitor_agent_consumable=false`。
- 测试/验证：
  - JSON 解析与结构断言通过：`category_code=AC`，价值主题 9 个，购买理由 13 个。
  - TV 典型污染词检查：`picture_upgrade|高端画质|游戏流畅|TV000` 无命中。
  - Markdown 草案人工读取检查：purchase reason 均为用户决策语言，不是参数名或卖点名。
- 下一个任务：AC-M12D-G04 taxonomy loader 和 candidate generator 支持 AC。

### AC-M12D-G02 AC 价值主题/购买理由候选提炼脚本

- 状态：completed。
- 产物：
  - `scripts/m12d_ac_g02_extract_reason_candidates.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G02_value_theme_purchase_reason_candidates.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G02_value_theme_purchase_reason_candidate_report.md`
- 只读运行：
  - 数据源：205 `catforge_dev`，`project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`，`category_code=AC`。
  - 当前批次：`m00_20260624000202_1150a669`。
  - 覆盖：M03B/M04C/M07 155 SKU，M05C/M09C/M10C/M11C 144 SKU，M11D 140 SKU/1489 行，M12C 140 SKU/6303 行。
  - 分层：140 个 `ready_strong_candidate`，11 个 `facts_market_only_comment_missing`，4 个 `other_degraded`。
- 候选输出：
  - 价值主题候选 9 个，作为 G03 人审草案输入，不等于已发布 taxonomy。
  - 购买理由候选 13 个，整体进入 `review`；M12C 风险/弱感知角色较多，G03 必须按证据强度和弱表达上限合并、拆分或降级。
  - 代表候选方向：匹数空间匹配、冷暖效果解释更高价格、长期省电抵消更高价格、同价位能效/能力获得感、卧室睡眠安静舒适、柔风不直吹、新风/净化、安装适配、智能控制、低价核心冷暖体验。
- 边界：
  - 本任务只生成候选 JSON/Markdown 报告。
  - 未发布 AC taxonomy，未生成 AC M12D SKU 画像，未修改竞品智能体，未 stage/commit。
  - 不复用 TV taxonomy，TV 关键词污染检查无命中。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m compileall scripts/m12d_ac_g02_extract_reason_candidates.py`：通过。
  - `apps/api-server/.venv/bin/python scripts/m12d_ac_g02_extract_reason_candidates.py --database-url "$LOCAL_DB_URL"`：通过。
  - `rg -n "TV000|picture_upgrade|高端画质|游戏流畅|tv_claim" ...`：无命中。
- 下一个任务：AC-M12D-G03 AC 标准 taxonomy v0.1 人审草案固化。

### AC-M12D-G01 上游证据审计与样本确认

- 状态：completed。
- 产物：
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_evidence_audit_20260708.md`
- 只读核查：
  - 数据源：205 `catforge_dev`，`project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`，`category_code=AC`。
  - 当前批次：`m00_20260624000202_1150a669`。
  - 覆盖：AC market scope 155；M03B/M04C/M07 155，M05C/M09C/M10C/M11C 144，M11D fact-complete/M12C 140。
  - 分层：140 个 strong candidate，11 个事实/市场-only 缺评论语义，4 个额外缺 M11D/M12C。
- 固定样本：
  - `AC00038063`、`AC00028640`、`AC00029751`、`AC00036139`、`AC00038662`、`AC00028642`、`AC00036739`、`AC00036333`、`AC00035996`、`AC00036020`、`AC00038680`、`AC00034731`、`AC00039165`、`AC00038066`、`AC00034959`。
- 边界：
  - M03B 必须过滤 `category_code=AC`，避免 AC 前缀旧 TV 批次污染。
  - M12C 缺失或仅有弱/风险角色时不得生成 `core_payment`。
  - 本任务未生成 taxonomy、未实现 AC M12D 生产逻辑、未修改竞品智能体、未 stage/commit。
- 测试/验证：
  - `scripts/check-env.sh dev`：SSH 可连，host PostgreSQL ready，容器内 `healthz` 正常；公网 `:8000` 直连返回 empty reply，本次审计使用 205 本机容器和数据库完成。
  - 205 API 容器内 SQLAlchemy 只读 SELECT 覆盖查询：通过。
  - `git diff --check -- ...`：通过。
  - `rg -n "[ \t]+$" ...`：无尾随空白命中。
- 下一个任务：AC-M12D-G02 AC 价值主题/购买理由候选提炼脚本。

### AC 需求、详细设计、任务链和调度入口创建

- 状态：completed。
- 产物：
  - `docs/core3_mvp/real_data_v2/sop_requirements/M12D_AC_sku_purchase_reason_profile_requirements.md`
  - `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_AC_sku_purchase_reason_profile_design.md`
  - `docs/core3_mvp/real_data_v2/development/M12D_AC_development_tasks.md`
  - `docs/core3_mvp/real_data_v2/development/M12D_AC_goal_dispatch.md`
- 边界：
  - 仅完成 AC M12D 设计和任务拆分。
  - 未实现 AC M12D 生产逻辑。
  - 未修改竞品智能体生产逻辑。
  - 未 stage/commit。
- 下一个任务：AC-M12D-G01 上游证据审计与样本确认。
