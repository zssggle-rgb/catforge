# M12D AC SKU成交理由画像开发任务链

## 1. 任务链定位

本文件是空调品类 AC M12D 的独立开发任务链。它从 AC 标准价值主题/购买理由提炼开始，到 AC SKU 成交理由画像生成、验证、全量发布，再到竞品智能体消费 AC M12D 为止。

每次 goal 只执行一个任务编号，不跨任务继续实现。任务完成后必须更新本文件中的状态、产物、测试结果和下一个任务。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| AC M12D 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M12D_AC_sku_purchase_reason_profile_requirements.md` |
| AC M12D 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_AC_sku_purchase_reason_profile_design.md` |
| 通用 M12D 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M12D_sku_purchase_reason_profile_requirements.md` |
| 通用 M12D 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_sku_purchase_reason_profile_design.md` |
| 竞品智能体需求 | `docs/core3_mvp/real_data_v2/sop_requirements/CATFORGE_ANALYST_competitor_answer_requirements.md` |
| 竞品智能体详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/CATFORGE_ANALYST_competitor_answer_design.md` |

## 3. 总体边界

AC M12D 负责：

- AC 标准价值主题和标准购买理由 taxonomy。
- AC 单 SKU 成交理由画像。
- AC 核心价值锚点角色、证据强度、置信度和风险。
- AC 小批量验证、全量生成、质量报告和版本发布。

AC M12D 不负责：

- 选择竞品。
- 计算 pair 级关键价值锚点可替代性。
- 计算替代压力。
- 生成竞品报告或飞书卡片。
- 把 TV taxonomy 复用为 AC taxonomy。

竞品智能体只在 AC M12D 发布后消费 AC M12D。

## 4. 任务链总览

| 编号 | 状态 | 任务 | 主要产物 | 可并行 |
| --- | --- | --- | --- | --- |
| AC-M12D-G01 | completed | 上游证据审计与样本确认 | `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_evidence_audit_20260708.md` | 否 |
| AC-M12D-G02 | completed | AC 价值主题/购买理由候选提炼脚本 | `scripts/m12d_ac_g02_extract_reason_candidates.py`；G02 候选 JSON/Markdown 报告 | 否 |
| AC-M12D-G03 | completed | AC 标准 taxonomy v0.1 人审草案固化 | `M12D_AC_standard_anchor_taxonomy_v0_1.md`；JSON 草案 | 否 |
| AC-M12D-G04 | completed | taxonomy loader 和 candidate generator 支持 AC | AC taxonomy loader/config、候选生成器支持和测试 | 否 |
| AC-M12D-G05 | completed | AC 证据强度评分和角色判定 | scorer/classifier AC 规则和边界测试 | 否 |
| AC-M12D-G06 | completed | AC 单 SKU CLI 与 Markdown 预览 | `sku-purchase-reason` AC 预览和测试 | 否 |
| AC-M12D-G07 | completed | AC 小批量验证与规则修正 | 10-20 个 AC SKU 验证报告和规则修正 | 否 |
| AC-M12D-G08 | completed | AC 全量 batch 生成 | AC 全量结果、失败清单和质量统计 | 否 |
| AC-M12D-G09 | completed | 发布 AC M12D 版本与下游契约冻结 | 已发布 AC 版本、消费 fixture 和质量报告 | 否 |
| AC-CA-G01 | completed | 竞品智能体 AC M12D 消费验收 | AC 竞品分析端到端验收报告 | 否 |

## 5. 单任务执行模板

每个 goal 使用以下模板：

```text
目标：执行 AC-M12D-Gxx，只完成该编号任务。
工作区：/Users/sjs/catforge
边界：
- 不做后续任务。
- 不复用 TV taxonomy 作为 AC 标准锚点。
- 不改竞品智能体下游逻辑，除非任务编号为 AC-CA-G01。
- 不把 M12D 生产逻辑写进竞品智能体。
输入文档：
- docs/core3_mvp/real_data_v2/development/M12D_AC_development_tasks.md
- docs/core3_mvp/real_data_v2/sop_requirements/M12D_AC_sku_purchase_reason_profile_requirements.md
- docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_AC_sku_purchase_reason_profile_design.md
完成后：
- 运行相关测试或说明未运行原因。
- 更新 M12D_AC_development_tasks.md 中该任务状态、产物和下一个任务。
- 更新 M12D_AC_goal_dispatch.md 中对应状态。
- 不 stage/commit，除非用户明确要求。
```

## 6. 任务明细

### AC-M12D-G01 上游证据审计与样本确认

状态：completed。

完成记录：

- 产物：`docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_evidence_audit_20260708.md`
- 只读核查时间：2026-07-08 21:59 CST。
- 数据源：205 `catforge_dev`，`project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`，`category_code=AC`，当前批次 `m00_20260624000202_1150a669`。
- 覆盖结论：AC market scope 155 SKU；M03B/M04C/M07 覆盖 155，M05C/M09C/M10C/M11C 覆盖 144，M11D fact-complete 与 M12C 覆盖 140。
- 启动结论：AC M12D 可以继续推进到 G02；但 15 个缺 M12C SKU 必须降级，且 M03B 必须过滤 `category_code=AC`，避免读入 AC 前缀的 TV 旧批次记录。
- 固定样本：`AC00038063`、`AC00028640`、`AC00029751`、`AC00036139`、`AC00038662`、`AC00028642`、`AC00036739`、`AC00036333`、`AC00035996`、`AC00036020`、`AC00038680`、`AC00034731`、`AC00039165`、`AC00038066`、`AC00034959`。
- 测试/验证：
  - `scripts/check-env.sh dev`：SSH 可连，host PostgreSQL ready，容器内 `healthz` 正常；公网 `:8000` 直连返回 empty reply，本次审计使用 205 本机容器和数据库完成。
  - 205 API 容器内 SQLAlchemy 只读 SELECT 覆盖查询：通过。
  - `git diff --check -- docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_evidence_audit_20260708.md docs/core3_mvp/real_data_v2/development/M12D_AC_development_tasks.md docs/core3_mvp/real_data_v2/development/M12D_AC_goal_dispatch.md`：通过。
  - `rg -n "[ \t]+$" ...`：无尾随空白命中。
- 下一任务：AC-M12D-G02 AC 价值主题/购买理由候选提炼脚本。

目标：

- 只读核查当前 AC SKU 的 M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D/M12C 覆盖。
- 固定 10-20 个小批量验证 SKU，覆盖挂机、柜机、大匹数、一级能效、新风/静音/柔风/自清洁、低价和高价场景。
- 明确 AC 中哪些证据能支撑 `core_payment`，哪些只能是 `weak_expression`。

建议样本起点：

- `AC00038063`，`KFR-88LW/N8KS1-1U`
- `AC00028640`，`KFR-72LW/BDN8Y-YH200`
- `AC00029751`，`KFR-72LW/N8MXA1`

产物：

- `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_evidence_audit_YYYYMMDD.md`
- AC 样本 SKU 清单。
- 上游证据覆盖表。
- 弱表达和证据缺口清单。

验收：

- 明确 AC M12D 能否启动。
- 明确 M12C 缺失时如何降级。
- 明确哪些 AC 卖点需要补证后才能成为核心购买理由。

### AC-M12D-G02 AC 价值主题/购买理由候选提炼脚本

状态：completed。

目标：

- 编写只读脚本，从 205 或本地可用数据源提取 AC 参数、卖点、评论、语义和市场候选。
- 按 AC 数据证据聚合价值主题候选和购买理由候选。
- 输出候选报告供人工审阅，不直接发布 taxonomy。

产物：

- `scripts/m12d_ac_g02_extract_reason_candidates.py`
- `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G02_value_theme_purchase_reason_candidates.json`
- `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G02_value_theme_purchase_reason_candidate_report.md`

验收：

- 脚本只执行 SELECT 或读取本地快照，不写库。
- 候选报告覆盖 AC 主要证据域。
- 不混入 TV SKU 或 TV taxonomy。

完成记录：

- 产物：
  - `scripts/m12d_ac_g02_extract_reason_candidates.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G02_value_theme_purchase_reason_candidates.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G02_value_theme_purchase_reason_candidate_report.md`
- 只读运行时间：2026-07-08 22:18 CST。
- 数据源：205 `catforge_dev`，`project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`，`category_code=AC`，当前批次 `m00_20260624000202_1150a669`。
- 脚本契约：只读 SELECT；不写数据库；不发布 taxonomy；不生成 M12D 画像；不修改竞品智能体；查询限定 AC，不复用 TV taxonomy。
- 覆盖结论：M03B/M04C/M07 覆盖 155 SKU，M05C/M09C/M10C/M11C 覆盖 144 SKU，M11D 覆盖 140 SKU/1489 行，M12C 覆盖 140 SKU/6303 行。
- 就绪分层：140 个 `ready_strong_candidate`，11 个 `facts_market_only_comment_missing`，4 个 `other_degraded`。
- 候选结论：
  - 价值主题候选 9 个，均进入 G03 人审草案输入；但 G03 仍需按 AC 用户决策语言合并、拆分和命名。
  - 购买理由候选 13 个，整体为 `review`，不是直接发布；M12C 角色分布中 `high_price_competitor_intercept`、`opportunity_gap`、`weak_user_perception_claim` 占比较高，说明 G03 必须保留弱表达上限和风险降级规则。
  - 可直接进入草案讨论的方向包括匹数空间匹配、冷暖效果解释更高价格、长期省电抵消更高价格、同价位能效/能力获得感、卧室睡眠安静舒适、柔风不直吹、新风/净化、安装适配、智能控制、低价核心冷暖体验等。
- 运行修正：首次运行发现当前 205 `core3_semantic_market_sku_contribution` 无 `allocation_value_type` 字段；G02 脚本已按当前表结构读取 `allocation_role`、`relation_status` 和分配销量/金额字段，不改变生产逻辑。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m compileall scripts/m12d_ac_g02_extract_reason_candidates.py`：通过。
  - `apps/api-server/.venv/bin/python scripts/m12d_ac_g02_extract_reason_candidates.py --database-url "$LOCAL_DB_URL"`：通过，生成 JSON/Markdown 产物。
  - `rg -n "TV000|picture_upgrade|高端画质|游戏流畅|tv_claim" ...`：无命中。
- 下一任务：AC-M12D-G03 AC 标准 taxonomy v0.1 人审草案固化。

### AC-M12D-G03 AC 标准 taxonomy v0.1 人审草案固化

状态：completed。

目标：

- 基于 G01/G02 证据和候选报告，固化 AC 标准价值主题和标准购买理由草案。
- 对每个购买理由写清楚必要证据、弱表达上限、冲突降级规则和示例。
- 形成可进入代码配置的 taxonomy 草案。

产物：

- `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_standard_anchor_taxonomy_v0_1.md`
- 可选 JSON/YAML 配置草案。

验收：

- taxonomy 明确 `category_code=AC` 和版本。
- 每个 purchase reason 都是用户决策语言，不是参数名或卖点名。
- 业务可读，能解释为什么这些是空调购买理由。

完成记录：

- 产物：
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_standard_anchor_taxonomy_v0_1.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_standard_anchor_taxonomy_v0_1.json`
- 固化时间：2026-07-08 22:21 CST。
- 输入依据：
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_evidence_audit_20260708.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G02_value_theme_purchase_reason_candidates.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G02_value_theme_purchase_reason_candidate_report.md`
- taxonomy 边界：
  - `category_code=AC`，`taxonomy_version=m12d_ac_purchase_reason_anchor_taxonomy_v0.1`。
  - `taxonomy_status=human_review_draft`，不是已发布版本，竞品智能体不得消费。
  - 不复用 TV taxonomy；只借鉴既有文档组织方式，不复用 TV 价值主题或购买理由。
  - 本任务未实现 loader、candidate generator、scorer、SKU 画像生成或竞品智能体逻辑。
- 固化结果：
  - 标准价值主题：9 个，包括冷暖能力、长期用电成本、睡眠静音、舒适风/健康空气、大空间覆盖、安装空间适配、操作维护省心、预算配置效率、季节可靠性。
  - 标准购买理由：13 个，均为用户决策语言，并逐条写明必要证据、弱表达上限和冲突降级。
  - 全局角色上限：缺 M12C/M11D、缺评论语义、单一厂家表达、价格/补贴-only、服务履约-only、M12C 风险/弱角色主导时不得强判 `core_payment`。
- 测试/验证：
  - JSON 解析与结构断言通过：`category_code=AC`，价值主题 9 个，购买理由 13 个，`published=false`，`competitor_agent_consumable=false`，`tv_taxonomy_reuse=false`。
  - TV 典型污染词检查：`picture_upgrade|高端画质|游戏流畅|TV000` 无命中。
  - Markdown 草案人工读取检查：每个 purchase reason 均包含成立逻辑、弱表达上限和冲突降级。
- 下一任务：AC-M12D-G04 taxonomy loader 和 candidate generator 支持 AC。

### AC-M12D-G04 taxonomy loader 和 candidate generator 支持 AC

状态：completed。

目标：

- 让通用 taxonomy loader 读取 AC taxonomy。
- 让 candidate generator 支持 AC 候选生成。
- 保持 TV 规则不变。

产物：

- AC taxonomy 配置。
- AC candidate generator 支持代码。
- 单元测试。

验收：

- `category_code=AC` 能加载 AC taxonomy。
- TV taxonomy 不会污染 AC。
- 一级能效、新风、静音、柔风、低价等只有厂家表达时生成弱候选或有角色上限。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/constants.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_anchor_taxonomy.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 实现时间：2026-07-08 22:30 CST。
- 实现内容：
  - 新增 `CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION=m12d_ac_purchase_reason_anchor_taxonomy_v0.1`。
  - `M12DAnchorTaxonomyLoader` 增加 `product_category=AC` + AC taxonomy version 加载分支。
  - 增加 `ac_purchase_reason_anchor_taxonomy_v0_1()`，固化 9 个 AC value themes 和 13 个 AC purchase reasons。
  - AC 证据 pattern 覆盖 M03B/M04C/M05C/M07/M09C-M10C-M11C/M12C；安装/服务信号只作为 `service_signal` 辅助或弱表达输入。
  - 一级能效、新风、静音、柔风、防直吹、自清洁、智能、低价/补贴等单一厂家表达使用 `weak_expression_only=True`，候选生成器在只有这类证据时给出 `role_cap=weak_expression`。
  - `AnchorCandidateGenerator` 核心算法未改；其通用 taxonomy 驱动能力已通过 AC 测试覆盖。
- 边界：
  - 未实现 AC evidence scoring。
  - 未实现 AC `core_payment/supporting/weak_expression/risk_drag` 最终角色判定。
  - 未生成 SKU 画像，未写数据库，未修改竞品智能体，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_anchor_taxonomy.py apps/api-server/app/services/core3_real_data/constants.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `apps/api-server/.venv/bin/pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -k "ac_anchor_taxonomy or standard_ac_anchors or single_energy_claim or tv_anchor_taxonomy or standard_tv_anchors"`：5 passed。
  - `apps/api-server/.venv/bin/pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：17 passed。
  - taxonomy smoke：AC 可加载 9 个 value themes / 13 个 purchase reasons；TV 专属画质/游戏购买理由未进入 AC taxonomy。
- 下一任务：AC-M12D-G05 AC 证据强度评分和角色判定。

### AC-M12D-G05 AC 证据强度评分和角色判定

状态：completed。

目标：

- 实现 AC 证据域评分和冲突扣分。
- 实现 AC `core_payment/supporting/weak_expression/risk_drag` 角色判定规则。
- 补齐边界测试。

产物：

- scorer/classifier AC 规则。
- AC fixture 和测试。

验收：

- 无补证的一级能效、新风、静音、柔风不会成为 `core_payment`。
- 评论负向或市场未承接会降低角色或生成风险。
- M12C 缺失时不会强判核心支付理由。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 实现时间：2026-07-08 22:52 CST。
- 实现内容：
  - 增加 AC 专属核心成交理由门槛：强证据、至少 2 个证据域、至少 1 个强证据域、场景匹配、无 AC 核心阻断旗标。
  - 增加 AC 核心阻断旗标：`ac_missing_m12c_core_cap`、`ac_scene_input_missing`、`ac_market_acceptance_weak_or_missing`、`ac_claim_value_risk_role_dominant`、`ac_service_signal_only`。
  - M12C 缺失、场景/语义市场缺失、市场承接弱、M12C 风险/弱角色占优时只能降级为 supporting/weak，不能进入 `core_payment`。
  - 评论负向占优或 M12C `drag_factor` 继续进入 `risk_drag`。
  - `role_reason_json` 输出 AC 输入状态、M12C 角色和核心阻断旗标，便于业务追溯评分过程。
- 边界：
  - 未实现 G06 的 AC 单 SKU CLI 和 Markdown 预览。
  - 未生成 AC SKU 画像，未写数据库，未修改竞品智能体，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：22 passed。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
- 下一任务：AC-M12D-G06 AC 单 SKU CLI 与 Markdown 预览。

### AC-M12D-G06 AC 单 SKU CLI 与 Markdown 预览

状态：completed。

目标：

- 支持 `sku-purchase-reason` 对 AC 单 SKU 生成预览。
- Markdown 预览按 AC 购买理由、证据域、弱表达和风险展示。
- taxonomy 未配置或未发布时输出明确错误。

产物：

- CLI 支持。
- Markdown 预览。
- CLI/preview 测试。

验收：

- 可对样本 AC SKU 生成业务可读预览。
- 缺失 M12C 或语义资产时有降级说明。

完成记录：

- 产物：
  - `apps/api-server/app/cli/catforge_analyst.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_preview.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 实现时间：2026-07-08 23:02 CST。
- 实现内容：
  - `sku-purchase-reason` 对 `product_category=ac` 自动选择 AC M12D taxonomy version，不再误用 TV 默认 taxonomy。
  - 单 SKU preview 支持 AC，保留 `category_code`/`product_category` 一致性校验和 taxonomy loader 品类隔离错误。
  - Markdown 预览展示品类、核心成交理由、支撑理由、弱表达、风险、价值主题和输入覆盖。
  - M03B context snapshot 补充 `param_values_json`，支撑 AC 参数事实匹配。
  - 新增 AC 单 SKU fixture，覆盖强证据链生成 `cooling_heating_performance_justifies_price` 核心成交理由和 Markdown 输出。
- 边界：
  - 未运行 G07 小批量验证。
  - 未批量生成 AC SKU 画像，未写数据库，未发布版本，未修改竞品智能体，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：23 passed。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/cli/catforge_analyst.py apps/api-server/app/services/core3_real_data/purchase_reason_profile_preview.py apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
- 下一任务：AC-M12D-G07 AC 小批量验证与规则修正。

### AC-M12D-G07 AC 小批量验证与规则修正

状态：completed。

目标：

- 运行 10-20 个 AC SKU 小批量验证。
- 人工检查核心购买理由、证据强度、弱表达、风险和置信度。
- 只做必要规则修正，不进入全量生成。

产物：

- `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G07_small_batch_validation.json`
- `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G07_small_batch_validation_report.md`

验收：

- 低置信、冲突和需复核 SKU 有清单。
- 规则修正有测试覆盖。
- 用户能看懂每个 SKU 为什么是这些成交理由。

完成记录：

- 产物：
  - `scripts/m12d_ac_g07_validate_purchase_reason_profiles.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G07_small_batch_validation.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G07_small_batch_validation_report.md`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 只读运行时间：2026-07-08 23:17 CST。
- 数据源：205 `catforge_dev`，`project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`，`category_code=AC`，当前批次 `m00_20260624000202_1150a669`。
- 样本：G01 固定 15 个 AC SKU，覆盖挂机、柜机、大匹数、低价/高价、负评样本和缺 M12C 样本。
- 规则修正：
  - `SkuPurchaseReasonContextBuilder` 按 `product_category=AC` 自动读取 AC 上游版本，不再用 TV M04C/M05C/M09C/M10C/M11C 默认版本导致真实 AC 证据误判缺失。
  - AC 评分中 `partial` 输入不再等同于 `missing` 做核心硬阻断；`partial` 保留为置信度扣分和复核原因，只有 `missing/unknown` 才触发 M12C/场景/市场硬阻断。
- 验证结果：
  - 样本数 15；预览失败 0。
  - 低置信 14；需复核 15。
  - 有核心成交理由 1；有风险拖拽 8。
  - 3 个缺 M12C 样本均未进入 `core_payment`，门槛通过。
  - 2 个负评样本均识别为风险拖拽，未出现负评样本核心误判。
- 边界：
  - 未执行 G08 全量 AC batch 生成。
  - 未写入 M12D profile 数据表，未发布 AC M12D 版本，未修改竞品智能体，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py scripts/m12d_ac_g07_validate_purchase_reason_profiles.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：24 passed。
  - `apps/api-server/.venv/bin/python scripts/m12d_ac_g07_validate_purchase_reason_profiles.py --database-url "$DB_URL"`：通过，生成 JSON/Markdown 产物。
- 下一任务：AC-M12D-G08 AC 全量 batch 生成。

### AC-M12D-G08 AC 全量 batch 生成

状态：completed。

目标：

- 对当前 AC batch 全量 SKU 生成 M12D 草稿画像。
- 输出成功数、失败数、低置信数、低证据数和需复核清单。
- 不发布 current 版本。

产物：

- `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G08_full_batch_generation.json`
- `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G08_full_batch_generation_report.md`

验收：

- 全量执行可重复。
- 失败和低置信原因可追溯。
- 没有把 TV taxonomy 写入 AC 结果。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_runner.py`
  - `scripts/m12d_ac_g08_generate_full_batch.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G08_full_batch_generation.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G08_full_batch_generation_report.md`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 205 运行：
  - 数据源：205 `catforge_dev`，`project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`，`category_code=AC`。
  - 读取批次/入库批次：`m00_20260624000202_1150a669`。
  - M12D 草稿版本：`m12d_ac_purchase_reason_profile_v0_1_draft`。
  - taxonomy：`m12d_ac_purchase_reason_anchor_taxonomy_v0.1`。
  - 写入模式：`write`，版本保持 `draft`，未发布 current。
- 全量生成结果：
  - SKU 数：155。
  - 成功率：1.0000，失败 SKU：0。
  - 低置信 SKU：136，低置信率：0.8774。
  - 低证据/核心成交理由缺失 SKU：136，缺失率：0.8774。
  - 有核心成交理由 SKU：19。
  - 需复核 SKU：155，需复核率：1.0000。
  - 写入记录：`core3_purchase_reason_profile_version=1`、`core3_sku_purchase_reason_profile=155`、`core3_sku_purchase_reason_anchor=1879`。
  - 锚点角色记录分布：`core_payment=155`、`supporting=208`、`weak_expression=326`、`risk_drag=1190`。
- DB 校验：
  - `core3_purchase_reason_profile_version.release_status=draft`，`is_current=false`。
  - AC 草稿 profile 155 行、anchor 1879 行，`product_category=AC`。
  - AC 草稿 profile/anchor published 记录数均为 0。
- 边界：
  - 未执行 G09 发布，未改发布状态，未让竞品智能体消费草稿版本。
  - 未修改竞品智能体，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_profile_runner.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py scripts/m12d_ac_g08_generate_full_batch.py`：通过。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：25 passed。
  - `apps/api-server/.venv/bin/python scripts/m12d_ac_g08_generate_full_batch.py --database-url "$DB_URL" --limit 5`：dry-run 通过。
  - `apps/api-server/.venv/bin/python scripts/m12d_ac_g08_generate_full_batch.py --database-url "$DB_URL" --write`：205 全量草稿写入通过。
  - `python3 -m json.tool docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G08_full_batch_generation.json`：通过。
- 残余风险：
  - 全量结果需复核率 1.0000，G09 发布前必须明确降级语义和发布口径，不能把草稿结果直接作为竞品智能体正式消费依据。
  - 低置信/核心缺失比例高，主要应在 G09 发布验收中决定是否发布、部分发布或继续规则/上游质量修正。
- 下一任务：AC-M12D-G09 发布 AC M12D 版本与下游契约冻结。

### AC-M12D-G09 发布 AC M12D 版本与下游契约冻结

状态：completed。

目标：

- 将通过质量门槛的 AC M12D 版本发布为 current。
- 输出下游读取 fixture。
- 冻结 AC M12D 消费契约。

产物：

- AC `m12d_profile_version` 发布记录。
- `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G09_published_contract_fixture.json`
- `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G09_published_contract_report.md`

验收：

- Repository 只读取已发布 current AC 版本。
- 下游 fixture 包含目标 SKU、核心锚点、辅助锚点、弱表达和风险。
- 未发布草稿不会被竞品智能体读取。

完成记录：

- 产物：
  - `scripts/m12d_g09_publish_and_export_contract.py`
  - `scripts/m12d_ac_g09_publish_and_export_contract.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G09_published_contract_fixture.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G09_published_contract_report.md`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 205 发布：
  - 数据源：205 `catforge_dev`，`project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`，`category_code=AC`。
  - 批次：`m00_20260624000202_1150a669`。
  - 发布版本：`m12d_ac_purchase_reason_profile_v0_1_draft`。
  - 发布状态：`core3_purchase_reason_profile_version.release_status=published`，`is_current=true`，`published_by=codex-ac-m12d-g09`。
  - 发布记录：profile 155/155 为 `published/current`，anchor 1879/1879 为 `published/current`，`product_category=AC`。
- 发布质量口径：
  - 本次发布为 `publish_current_with_degraded_consumption_contract`。
  - 发布为 current 只表示下游可以读取冻结契约；低置信、需复核或缺核心理由的 SKU 必须以 `published_degraded` 降级消费，不得输出无条件强替代结论。
  - 版本统计：SKU 155，ready 50，需复核 155，低置信 136，核心成交理由缺失 136，失败 0。
- 下游契约：
  - 读取键：`category_code + project_id + batch_id + m12d_profile_version + sku_code`。
  - fixture 自动选择 4 个 AC 样本：`AC00026378`、`AC00032338`、`AC00028640`、`AC00028642`。
  - 样本覆盖：有核心锚点、有辅助锚点、有弱表达、无核心低置信、风险拖拽。
  - 样本消费状态均为 `published_degraded` / `degraded_pair_scoring`，体现 AC G08 全量质量限制。
  - 缺失 SKU fixture 和未发布版本 fixture 均为 `not_found` / `block_target_or_drop_candidate`。
- 边界：
  - 未进入 AC-CA-G01。
  - 未修改竞品智能体，未让竞品智能体生产或修正 AC M12D。
  - 未复用 TV taxonomy 作为 AC 标准锚点，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m compileall scripts/m12d_g09_publish_and_export_contract.py scripts/m12d_ac_g09_publish_and_export_contract.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：26 passed。
  - `apps/api-server/.venv/bin/python scripts/m12d_ac_g09_publish_and_export_contract.py --database-url "$DB_URL" --publish`：205 发布与 fixture 导出通过。
  - `python3 -m json.tool docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_G09_published_contract_fixture.json`：通过。
  - DB 回读确认 version/profile/anchor 均为 AC `published/current`，未发布版本和缺失 SKU 仍不可读取。
- 下一任务：AC-CA-G01 竞品智能体 AC M12D 消费验收。

### AC-CA-G01 竞品智能体 AC M12D 消费验收

状态：completed。

目标：

- 在 AC M12D-G09 完成后，验证竞品智能体能读取 AC M12D。
- 对一个 AC 目标 SKU 运行竞品分析，检查关键价值锚点可替代性和替代压力维度。
- 不在竞品智能体中生产 AC M12D。

产物：

- `docs/core3_mvp/real_data_v2/current_implementation/AC_CA_G01_m12d_consumption_validation_YYYYMMDD.md`
- 可选本地 JSON/Markdown 验收副本。

验收：

- 报告中展示本品和 Top 3 在 AC 购买理由上的差异。
- AC M12D 缺失时有明确降级，不会使用 TV fallback。
- 本任务不修改 M12D 生产逻辑。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/sop_orchestrators.py`
  - `apps/api-server/app/services/core3_real_data/analyst/anchor_substitutability.py`
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py`
  - `apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/AC_CA_G01_m12d_consumption_validation_20260708.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/AC_CA_G01_competitor_set_AC00032338_20260708.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/AC_CA_G01_competitor_set_AC00032338_20260708_summary.json`
- 实现内容：
  - `competitor-set` SOP 读取 published M12D 下游合约，调用既有关键价值锚点可替代性和替代压力算法，把结果注入竞品报告输入。
  - 目标 M12D 缺失时不覆盖旧事实维度评分，只记录降级；候选 M12D 缺失时该候选锚点维度 blocked 且不使用 TV fallback。
  - `to_legacy_value_anchor()` 输出 `pair_scoring_allowed` 和 `gate_reasons`；报告层不再把 M12D 空 shared anchors 回退成旧参数/卖点锚点。
- 真实验收：
  - 目标 SKU：`AC00032338`，格力 `KFR-35GW/(35551)FNHAA-B1`。
  - M12D 消费状态：`consumed_with_review`。
  - 目标合约：`published_degraded` / `degraded_pair_scoring`，`m12d_profile_version=m12d_ac_purchase_reason_profile_v0_1_draft`。
  - Top 3 展示 AC 购买理由锚点差异和替代压力；当前 AC M12D 版本质量要求复核，不输出无条件强替代结论。
- 边界：
  - 未在竞品智能体中生成 M12D。
  - 未修改 M12D 生产逻辑或 AC 锚点角色。
  - 未复用 TV taxonomy，未 stage/commit。
- 测试/验证：
  - `apps/api-server/.venv/bin/pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py -q`：82 passed。
  - `apps/api-server/.venv/bin/pytest apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py -q`：19 passed。
  - 205 `competitor-set` AC 真实验收命令：通过，产出 Markdown 和 summary JSON。
- 下一任务：暂无 pending 任务，AC M12D 与竞品智能体 AC 消费验收任务链完成。

## 7. 当前下一个任务

```text
暂无 pending 任务。AC M12D 与竞品智能体 AC 消费验收任务链已完成。
```
