# M12D SKU成交理由画像开发任务链

## 1. 任务链定位

M12D 是独立资产生产链路，不属于竞品分析智能体的内部步骤。本任务链把 M12D 拆成多个可单独 goal 执行、可定时器调度、可逐步验收的小任务。

每次 goal 只执行一个任务编号，不跨任务继续实现。任务完成后必须更新本文件中的状态、产物和下一个任务。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| M12D 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M12D_sku_purchase_reason_profile_requirements.md` |
| M12D 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_sku_purchase_reason_profile_design.md` |
| M12C 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M12C_claim_value_quantification_requirements.md` |
| M12C 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M12C_claim_value_quantification_design.md` |
| 竞品智能体消费设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/CATFORGE_ANALYST_competitor_answer_design.md` |

## 3. 总体边界

M12D 负责：

- 单 SKU 成交理由画像。
- 核心价值锚点角色、证据强度、置信度和风险。
- 小批量验证、TV 全量生成、质量报告和版本发布。

M12D 不负责：

- 选择竞品。
- 计算 pair 级关键价值锚点可替代性。
- 计算替代压力。
- 生成竞品报告或飞书卡片。

## 4. 任务链总览

| 编号 | 状态 | 任务 | 主要产物 | 可并行 |
| --- | --- | --- | --- | --- |
| M12D-G01 | completed | 上游证据审计与样本确认 | `docs/core3_mvp/real_data_v2/current_implementation/M12D_evidence_audit_20260708.md` | 否 |
| M12D-G02 | completed | Schema、存储和发布版本设计落地 | model、migration、typed schema、repository、schema/repository 测试 | 否 |
| M12D-G03 | completed | ContextBuilder 输入读取 | 单 SKU 上下文构建服务和测试 | 否 |
| M12D-G04 | completed | 标准锚点族配置和候选生成 | TV 标准锚点 taxonomy/config、候选生成器和测试 | 否 |
| M12D-G04R1 | completed | 价值主题与购买理由候选提炼修正 | 205 只读候选提炼脚本、候选报告、标准草案 | 否 |
| M12D-G04R2 | completed | 修正价值主题/购买理由 taxonomy 与候选契约 | 两层 taxonomy、候选生成器契约修正和测试 | 否 |
| M12D-G05 | completed | 证据强度评分和角色判定 | scorer/classifier 和边界测试 | 否 |
| M12D-G06 | completed | 单 SKU CLI 与 Markdown 预览 | `sku-purchase-reason` 命令和预览 | 可在 G05 后 |
| M12D-G07 | completed | 小批量验证与规则修正 | 10-20 SKU 验证报告和规则调整 | 否 |
| M12D-G08 | completed | 全量 TV batch 生成 | 全量结果、失败清单、质量统计 | 否 |
| M12D-G09 | completed | 发布版本与下游契约冻结 | `m12d_profile_version`、消费契约验收 | 否 |

## 5. 单任务执行模板

每个 goal 使用以下模板：

```text
目标：执行 M12D-Gxx，只完成该编号任务。
工作区：/Users/sjs/catforge
边界：不做后续任务，不改竞品智能体下游逻辑，除非该任务明确要求。
输入文档：
- docs/core3_mvp/real_data_v2/development/M12D_development_tasks.md
- docs/core3_mvp/real_data_v2/sop_requirements/M12D_sku_purchase_reason_profile_requirements.md
- docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_sku_purchase_reason_profile_design.md
完成后：
- 运行相关测试或说明未运行原因。
- 更新 M12D_development_tasks.md 中该任务状态、产物和下一个任务。
- 不 stage/commit，除非用户明确要求。
```

## 6. 任务明细

### M12D-G01 上游证据审计与样本确认

状态：已完成。

完成记录：

- 产物：`docs/core3_mvp/real_data_v2/current_implementation/M12D_evidence_audit_20260708.md`
- 只读核查时间：2026-07-08 14:31 CST。
- 结论：TV 事实层可启动 M12D；M09C/M10C/M11C 当前为 293/377，M11D/M12C 当前为 182，需要在 M12D 中显式降级。
- 样本：`TV00029112`、`TV00029936`、`TV00027801`、`TV00029020`、`TV00028829`。
- 下一任务：M12D-G02 Schema、存储和发布版本设计落地。

目标：

- 读取当前 TV 样本中 M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D/M12C 的可用情况。
- 固定小批量验证 SKU：65E7Q、65A7H PRO、65Q9L PRO、小米 L65MC-SP、65A6F ULTRA 等。
- 确认 `budget_value`、厂家主张、服务信号、弱评论和 M12C 缺失的处理边界。

产物：

- `docs/core3_mvp/real_data_v2/current_implementation/M12D_evidence_audit_YYYYMMDD.md`
- 样本 SKU 清单、上游证据覆盖表、待确认规则清单。

验收：

- 明确哪些证据能支撑 `core_payment`。
- 明确哪些只能是 `weak_expression`。
- 明确 M12C 缺失时如何降级。

### M12D-G02 Schema、存储和发布版本设计落地

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/models/entities.py`
  - `apps/api-server/alembic/versions/0042_core3_purchase_reason_profile.py`
  - `apps/api-server/app/services/core3_real_data/constants.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_repositories.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 测试：
  - `python -m pytest tests/core3_real_data/test_m12d_purchase_reason_profile.py`：3 passed, 23 warnings。
  - `python -m compileall app/models/entities.py app/services/core3_real_data/constants.py app/services/core3_real_data/purchase_reason_profile_schemas.py app/services/core3_real_data/purchase_reason_profile_repositories.py alembic/versions/0042_core3_purchase_reason_profile.py`：通过。
  - `git diff --check -- apps/api-server/app/models/entities.py apps/api-server/app/services/core3_real_data/constants.py apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py apps/api-server/app/services/core3_real_data/purchase_reason_profile_repositories.py apps/api-server/alembic/versions/0042_core3_purchase_reason_profile.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py docs/core3_mvp/real_data_v2/development/M12D_development_tasks.md docs/core3_mvp/real_data_v2/development/M12D_COMPETITOR_goal_dispatch.md`：通过。
- 契约：M12D 画像版本、SKU 画像和理由锚点均具备 `category_code`、`project_id`、`version`、`batch_id`、发布状态、current 标记和审计字段；仓储读取默认只返回已发布 current 版本，未发布版本不会被下游读取。
- 下一任务：M12D-G03 ContextBuilder 输入读取。

目标：

- 落地 `SkuPurchaseReasonProfile`、`PurchaseReasonAnchor` 等 typed schema。
- 设计或新增存储表。
- 定义 `m12d_profile_version`、current 版本和发布状态。

产物：

- schema/model/migration。
- repository 基础接口。
- schema 测试。

验收：

- 每条结果包含 `category_code`、`project_id`、`version`、`batch_id`、`sku_code` 和审计字段。
- 未发布版本不会被下游读取。

### M12D-G03 ContextBuilder 输入读取

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 测试：
  - `python -m pytest tests/core3_real_data/test_m12d_purchase_reason_profile.py`：5 passed, 57 warnings。
  - `python -m compileall app/services/core3_real_data/purchase_reason_profile_schemas.py app/services/core3_real_data/purchase_reason_context_builder.py tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `git diff --check -- apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py docs/core3_mvp/real_data_v2/development/M12D_development_tasks.md docs/core3_mvp/real_data_v2/development/M12D_COMPETITOR_goal_dispatch.md`：通过。
- 契约：`SkuPurchaseReasonContextBuilder` 为单 SKU 输出 `param_profile`、`claim_fact_profile`、`comment_profile`、`market_profile`、`semantic_profile`、`semantic_market_profile`、`claim_value_profile` 七类状态化快照；缺失输入保留 `missing`，不当作 false。
- 用户设计澄清：标准关键价值锚点族应由 Codex/业务基于评论、参数画像、卖点画像、价值战场、任务/客群和样本审计先行提炼，经人工评审后固化为品类级 taxonomy/config。程序只读取该 taxonomy 并匹配 SKU 证据，不在运行时自动生成标准锚点族。
- 下一任务：M12D-G04 标准锚点族配置和候选生成。

目标：

- 实现 `SkuPurchaseReasonContextBuilder`。
- 读取单 SKU 所需上游资产，保持 unknown 不等于 false。

产物：

- context builder 服务。
- 单 SKU fixture 和缺失输入测试。

验收：

- 能为 65E7Q 组装完整上下文。
- M12C 缺失时上下文带缺失状态，不抛业务结论错误。

### M12D-G04 标准锚点族配置和候选生成

状态：已完成。

完成记录：

- 产物：
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_tv_standard_anchor_taxonomy_v0_1.md`
  - `apps/api-server/app/services/core3_real_data/constants.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_anchor_taxonomy.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_anchor_candidate_generator.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 测试：
  - `python -m pytest tests/core3_real_data/test_m12d_purchase_reason_profile.py`：7 passed, 75 warnings。
  - `python -m compileall app/services/core3_real_data/constants.py app/services/core3_real_data/purchase_reason_profile_schemas.py app/services/core3_real_data/purchase_reason_anchor_taxonomy.py app/services/core3_real_data/purchase_reason_anchor_candidate_generator.py tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `git diff --check -- apps/api-server/app/services/core3_real_data/constants.py apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py docs/core3_mvp/real_data_v2/development/M12D_development_tasks.md docs/core3_mvp/real_data_v2/development/M12D_COMPETITOR_goal_dispatch.md`：通过。
  - `rg -n "[ \t]+$" ...`：无尾随空白命中。
- 契约：TV 标准锚点族是品类级、版本化、Codex/业务提炼并经人工评审后固化的 taxonomy/config；运行时程序只读取 taxonomy 并匹配 SKU 证据，不自动生成标准锚点族。
- 候选生成边界：`AnchorCandidateGenerator` 只生成标准锚点候选和弱表达上限，不做最终证据强度评分或角色判定；最终 `core_payment`、`supporting`、`weak_expression`、`risk_drag` 判定留给 G05。
- 弱表达规则：`value_price` / `price_value` 等仅厂家卖点/位置标签命中时，候选被封顶为 `weak_expression`，不能直接成为核心支付理由。
- 下一任务：M12D-G04R1 价值主题与购买理由候选提炼修正。

目标：

- 固化 TV 标准关键价值锚点族 taxonomy/config。标准锚点族由 Codex/业务读取评论、参数画像、卖点画像、价值战场、任务/客群和样本审计后提炼，并经人工评审确认；程序不在运行时自动生成标准锚点族。
- 实现标准锚点 taxonomy/config 读取。
- 从参数、卖点、评论、M12C、战场、任务、客群和市场中生成 SKU 对标准锚点族的候选命中。

产物：

- TV 标准锚点 taxonomy/config。
- `AnchorCandidateGenerator`。
- 同源同参合并测试。

验收：

- 65E7Q 能生成高端画质、游戏流畅、智能互联、预算价值等候选。
- `value_price` / `price_value` 只能生成弱表达候选，不能直接生成核心支付理由。
- TV 和空调等不同品类使用不同标准锚点族，不跨品类复用解释。

### M12D-G04R1 价值主题与购买理由候选提炼修正

状态：已完成。

完成记录：

- 产物：
  - `scripts/m12d_g04r1_extract_tv_reason_candidates.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G04R1_tv_value_theme_purchase_reason_candidates.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G04R1_tv_value_theme_purchase_reason_candidate_report.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_tv_standard_value_theme_taxonomy_v0_1_draft.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_tv_standard_purchase_reason_taxonomy_v0_1_draft.md`
- 数据源：205 `catforge_dev`，`project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`，`category_code=TV`，脚本使用 `TV%` SKU 前缀过滤并只执行 SELECT。
- 当前覆盖：M03B 377 SKU、M04C 328 SKU、M05C 348 SKU、M07 377 SKU、M09C/M10C 348 SKU、M11C 368 SKU、M12C 259 SKU。
- 关键结论：
  - 价值主题候选应表达用户可感知获得感，例如 `picture_upgrade_perception`、`dynamic_stability_perception`、`budget_configuration_efficiency`。
  - 标准购买理由必须是选择逻辑型，例如 `picture_upgrade_justifies_price`、`same_price_core_config_gain`、`gaming_device_fit_reduces_risk`。
  - 标准购买理由草案已从 7 个扩大为 13 个，其中 10 个为 `draft_accept`，3 个为 `review`。
  - G04 当前 `高端画质/游戏流畅/智能互联` 等不应直接作为购买理由，应降级为价值主题或 theme family。
- 测试/验证：
  - `apps/api-server/.venv/bin/python -m compileall scripts/m12d_g04r1_extract_tv_reason_candidates.py`：通过。
  - 205 只读脚本运行成功并生成 4 个报告/草案文件。
  - `rg -n "AC[0-9]|KFR-|空调" ...`：无命中，确认报告未混入 AC 样本。
- 下一任务：M12D-G04R2 修正价值主题/购买理由 taxonomy 与候选契约。

背景：

- G04 产出的 `高端画质`、`游戏流畅`、`智能互联` 等更接近价值主题或价值战场子类，不足以直接作为“购买理由”。
- 标准购买理由必须回答“为什么这个 SKU 值得被选择”，需要包含用户任务、价格/尺寸/竞品取舍、SKU 证据和市场/支付承接。
- 标准价值主题也需要从事实和感知层重新提炼，避免直接复制 M09C/M10C/M11C。

目标：

- 基于 205 当前 TV 结果，生成可复现的价值主题和购买理由候选报告。
- 明确候选来自哪些证据域：M03B 参数、M04C 卖点事实、M05C 评论事实、M07 市场、M09C/M10C/M11C 语义参照、M11D 语义市场、M12C 支付价值。
- 将现有 G04 的“标准锚点族”修正为两层结构草案：
  - 标准价值主题：用户获得的可感知价值类型。
  - 标准购买理由：选择逻辑型成交解释。
- 只生成候选和草案，不进入 G05 最终评分。

产物：

- 205 只读候选提炼脚本。
- 候选提炼原始 JSON/Markdown 报告。
- TV 标准价值主题 v0.1 草案。
- TV 标准购买理由 v0.1 草案。
- 对 G04 taxonomy 的修正建议。

验收：

- 候选报告能说明每个候选主题/理由的来源证据域、覆盖 SKU、关联 claim/参数/评论词、M12C 支撑和市场承接。
- 价值主题不直接复制价值战场；购买理由不退化成“高端画质/游戏流畅”这类主题标签。
- 明确哪些只适合做价值主题，哪些可以升级为购买理由。
- G05 继续执行前，必须以 G04R1 的标准草案为输入。

### M12D-G04R2 修正价值主题/购买理由 taxonomy 与候选契约

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_anchor_taxonomy.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_anchor_candidate_generator.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_tv_standard_anchor_taxonomy_v0_1.md`
  - `docs/core3_mvp/real_data_v2/sop_requirements/M12D_sku_purchase_reason_profile_requirements.md`
  - `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_sku_purchase_reason_profile_design.md`
- 契约：
  - `M12DAnchorTaxonomy` 拆为 `value_themes` 和 `purchase_reasons` 两层。
  - `AnchorCandidateGenerator.generate()` 输出 `M12DAnchorCandidateSet`，包含 `value_theme_candidates` 与 `purchase_reason_candidates`。
  - 购买理由定义包含 `related_value_theme_codes`、`required_logic_cn`、`weak_boundary_cn`、`decision_question_cn` 和 `candidate_gate_domain_groups`。
  - G05 只消费 `purchase_reason_candidates` 做证据强度和角色判定；价值主题只做解释维度和证据归因。
- 测试：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：7 passed, 76 warnings。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py apps/api-server/app/services/core3_real_data/purchase_reason_anchor_taxonomy.py apps/api-server/app/services/core3_real_data/purchase_reason_anchor_candidate_generator.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
- 下一个任务：M12D-G05 证据强度评分和角色判定。

目标：

- 将 G04R1 草案固化为两层 taxonomy：
  - `value_theme_code`：用户可感知价值主题。
  - `purchase_reason_code`：选择逻辑型标准购买理由。
- 修正当前 G04 中的 `M12DAnchorTaxonomy`、候选生成器和测试，避免把价值主题直接当作购买理由。
- 保留弱表达边界：`value_price` / `price_value` 只能弱支撑 `same_price_core_config_gain`，不能直接变成核心成交理由。

产物：

- 两层 taxonomy/config。
- 候选生成器契约修正。
- 单测更新。

验收：

- 价值主题、价值战场、用户任务和购买理由在 schema 与报告中有清晰边界。
- 65E7Q 输出的是购买理由候选，例如“画质配置解释加价”“同价位核心配置获得感”，而不是只输出“高端画质”。
- G05 scorer/classifier 明确消费 `purchase_reason_code`，不消费旧的名词型锚点作为最终购买理由。

### M12D-G05 证据强度评分和角色判定

前置条件：

- 必须先完成 M12D-G04R2，并将现有“标准锚点族”修正为“标准价值主题 + 标准购买理由”两层结构。

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 契约：
  - `EvidenceStrengthScorer` 只对 `purchase_reason_candidates` 打分，不消费价值主题作为最终购买理由。
  - `ReasonRoleClassifier` 输出 `core_payment`、`supporting`、`weak_expression`、`risk_drag`。
  - `ProfileConfidenceScorer` 汇总 SKU 级画像置信度、角色桶、风险标记和复核原因。
  - `value_price` / `price_value` 等仅价格价值表达会被 `role_cap=weak_expression` 封顶。
  - 评论负向占优或 M12C 拖累信号会降为 `risk_drag`。
- 测试：
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：10 passed, 112 warnings。
- 下一个任务：M12D-G06 单 SKU CLI 与 Markdown 预览。

目标：

- 实现 `EvidenceStrengthScorer`、`ReasonRoleClassifier` 和 `ProfileConfidenceScorer`。
- 输出 `core_payment`、`supporting`、`weak_expression`、`risk_drag`。

产物：

- scoring/classifier 服务。
- 边界单测。

验收：

- 只有厂家主张或位置标签时封顶 `weak_expression`。
- 评论负向、价格压力、样本不足能降低角色或置信度。
- 服务、安装、售后不进入产品核心成交理由。

### M12D-G06 单 SKU CLI 与 Markdown 预览

目标：

- 新增 `sku-purchase-reason` CLI。
- 输出 JSON 和 Markdown 预览。

产物：

- CLI 命令。
- 单 SKU 预览报告。
- CLI 测试。

验收：

- `海信 65E7Q` 能输出画像。
- Markdown 解释业务可读，不暴露内部 SQL、原始 JSON 或调试字段。

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/cli/catforge_analyst.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_preview.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 契约：
  - 新增 `sku-purchase-reason` CLI，支持 `--sku-code`、`--model-name`、`--query`。
  - 预览只消费 G03-G05 的上下文、标准 taxonomy、候选生成和评分结果，不写入 M12D 生产表。
  - `--format json` 输出结构化画像，`--format markdown` 输出业务可读预览。
  - Markdown 展示核心成交理由、支撑/弱表达/风险、价值主题和输入覆盖，不暴露内部 SQL、原始 JSON 或调试字段。
- 测试：
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/cli/catforge_analyst.py apps/api-server/app/services/core3_real_data/purchase_reason_profile_preview.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：11 passed, 130 warnings。
  - `git diff --check -- apps/api-server/app/cli/catforge_analyst.py apps/api-server/app/services/core3_real_data/purchase_reason_profile_preview.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
- 下一个任务：M12D-G07 小批量验证与规则修正。

### M12D-G07 小批量验证与规则修正

目标：

- 跑 10-20 个 SKU。
- 人工审计核心理由、弱表达、证据强度和置信度。
- 根据审计结果修正规则。

产物：

- 小批量验证报告。
- 规则修正记录。
- 回归测试。

验收：

- 低置信、需复核、强核心理由都有清单。
- 65E7Q 的预算价值表达不被误判为强核心成交理由。

状态：已完成。

完成记录：

- 产物：
  - `scripts/m12d_g07_validate_purchase_reason_profiles.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G07_small_batch_validation.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G07_small_batch_validation_report.md`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 验证样本：
  - 205 当前 TV serving-scope：`serving-scope:TV:m00_20260623014631_c8630747,m00_20260619084551_857df63b,m00_20260613004311_d548f6dc`
  - 样本数：12。
  - 低置信 SKU：6。
  - 需复核 SKU：12。
  - 有核心成交理由 SKU：6。
  - 风险拖拽 SKU：0。
  - 预算价值误判为核心：0。
- 规则修正记录：
  - 修复 serving-scope 组合批次导致 M12D ContextBuilder 全输入缺失的问题。
  - 新增 serving-scope 回归测试。
  - 65E7Q 的 `same_price_core_config_gain` 保持为 `weak_expression`，未进入 `core_payment`，无需修改预算价值封顶规则。
  - 有 core 锚点但 profile 仍为 `ready_degraded` 的样本必须在下游报告展示 `profile_status/profile_confidence`，不能只读锚点角色强行输出强结论。
- 测试：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：12 passed, 148 warnings。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py apps/api-server/app/cli/catforge_analyst.py scripts/m12d_g07_validate_purchase_reason_profiles.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `CATFORGE_DATABASE_URL=... apps/api-server/.venv/bin/python scripts/m12d_g07_validate_purchase_reason_profiles.py --sample-size 12`：通过并生成报告。
  - `git diff --check -- ...`：通过。
- 下一个任务：M12D-G08 全量 TV batch 生成。

### M12D-G08 全量 TV batch 生成

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_runner.py`
  - `scripts/m12d_g08_generate_full_tv_batch.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G08_full_tv_batch_generation.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G08_full_tv_batch_generation_report.md`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 205 运行前置：
  - 205 alembic 从 `0041_core3_m04c_wtp_gate` 升级到 `0042_core3_m12d_purchase_reason`，只应用 G02 已落地的 M12D 三表迁移。
- 全量生成结果：
  - 读取批次：`serving-scope:TV:m00_20260623014631_c8630747,m00_20260619084551_857df63b,m00_20260613004311_d548f6dc`
  - 入库批次：`m00_20260623014631_c8630747`
  - M12D 草稿版本：`m12d_tv_purchase_reason_profile_v0_1_draft`
  - SKU 数：377。
  - 成功率：1.0000，失败 SKU：0。
  - 低置信 SKU：201，低置信率：0.5332。
  - `core_payment` 缺失 SKU：120，缺失率：0.3183。
  - 需复核 SKU：377，需复核率：1.0000。
  - 写入记录：`core3_purchase_reason_profile_version=1`、`core3_sku_purchase_reason_profile=377`、`core3_sku_purchase_reason_anchor=3299`。
  - 版本状态：`release_status=draft`，`is_current=false`；G08 未发布，下游正式消费仍需等待 G09。
- 测试：
  - `python -m compileall app/services/core3_real_data/purchase_reason_profile_runner.py tests/core3_real_data/test_m12d_purchase_reason_profile.py ../../scripts/m12d_g08_generate_full_tv_batch.py`：通过。
  - `python -m pytest tests/core3_real_data/test_m12d_purchase_reason_profile.py`：13 passed, 183 warnings。
  - `CATFORGE_DATABASE_URL=... uv run python ../../scripts/m12d_g08_generate_full_tv_batch.py --limit 5`：dry-run 通过。
  - `CATFORGE_DATABASE_URL=... uv run python ../../scripts/m12d_g08_generate_full_tv_batch.py --write`：205 全量写入草稿通过。
  - 205 DB 校验：版本 1 行、profile 377 行、anchor 3299 行，计数与报告一致。
- 残余风险：
  - 全量 runner 当前为逐 SKU 查询与逐条 upsert，377 SKU 全量写入耗时偏长；G08 先保证可审计草稿产物，性能批处理后续再优化。
  - 全量结果全部 `review_required`，主要由 `core_payment_missing`、低置信和缺失/部分输入触发；G09 发布前需要明确下游降级语义，不在 G08 临时调整评分规则。
- 下一个任务：M12D-G09 发布版本与下游契约冻结。

目标：

- 对当前 TV batch 全量 SKU 生成 M12D。
- 输出质量统计和失败清单。

产物：

- 全量运行脚本或 runner。
- 质量报告。
- 失败/低置信/需复核清单。

验收：

- 全量成功率、低置信率、`core_payment` 缺失率可见。
- 失败 SKU 不影响已成功 SKU 发布。

### M12D-G09 发布版本与下游契约冻结

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_contract.py`
  - `scripts/m12d_g09_publish_and_export_contract.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G09_published_contract_fixture.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G09_published_contract_report.md`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 发布结果：
  - 批次：`m00_20260623014631_c8630747`
  - 发布版本：`m12d_tv_purchase_reason_profile_v0_1_draft`
  - 版本状态：`release_status=published`、`is_current=true`
  - 发布人：`codex-m12d-g09`
  - 发布记录：version 1 行、profile 377 行、anchor 3299 行。
  - 发布后 DB 校验：377/377 profile 为 `published/current`，3299/3299 anchor 为 `published/current`。
- 下游契约冻结：
  - 读取键：`category_code + project_id + batch_id + m12d_profile_version + sku_code`
  - 状态：`published_ready`、`published_degraded`、`published_unusable`、`not_found`
  - 下游动作：`normal_pair_scoring`、`degraded_pair_scoring`、`block_target_or_drop_candidate`
  - `not_found` 或 `published_unusable`：目标阻断强排序，候选退出强替代判断或退出 Top 3。
  - `published_degraded`：可降级消费，但必须展示置信度和降级原因，不能输出无条件强结论。
  - 下游不得修改 M12D 原始锚点角色，不能临时生成或补写成交理由。
- Fixture：
  - 样本 SKU：`TV00029112`、`TV00029936`、`TV00027801`、`TV00029020`、`TV00028829`
  - 样本状态：5 个样本均为 `published_degraded` / `degraded_pair_scoring`。
  - 缺失 SKU fixture：`not_found` / `block_target_or_drop_candidate`。
  - 未发布版本 fixture：`not_found` / `block_target_or_drop_candidate`。
- 测试：
  - `python -m compileall app/services/core3_real_data/purchase_reason_profile_schemas.py app/services/core3_real_data/purchase_reason_profile_contract.py tests/core3_real_data/test_m12d_purchase_reason_profile.py ../../scripts/m12d_g09_publish_and_export_contract.py`：通过。
  - `python -m pytest tests/core3_real_data/test_m12d_purchase_reason_profile.py`：14 passed, 203 warnings。
  - `CATFORGE_DATABASE_URL=... uv run python ../../scripts/m12d_g09_publish_and_export_contract.py --publish`：205 发布和 fixture 导出通过。
  - 205 DB readback：version/profile/anchor 发布状态和报告一致。
- 下一个任务：CA-G01 M12D 读取契约和 fixture。

目标：

- 发布可被下游读取的 `m12d_profile_version`。
- 冻结读取接口和降级语义。

产物：

- 发布版本记录。
- 下游消费 fixture。
- 契约测试。

验收：

- 竞品分析智能体可以用 fixture 读取目标和候选 M12D。
- 未发布、缺失、低置信画像有明确降级行为。

## 7. 定时器选择规则

每次定时器触发时：

1. 读取本文件。
2. 找到第一个 `pending` 的 M12D-Gxx。
3. 只执行该任务。
4. 完成后把状态改成 `completed`，并记录产物路径。
5. 如果阻塞，改成 `blocked`，写明阻塞条件和需要的输入。
