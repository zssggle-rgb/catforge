# CatForge Analyst 竞品问答消费 M12D 开发任务链

## 1. 任务链定位

本任务链只覆盖竞品分析智能体在已发布 M12D `SKU成交理由画像` 基础上的消费改造。M12D 生产链路由 `M12D_development_tasks.md` 负责。

每次 goal 只执行一个任务编号，不跨任务实现。任务完成后必须更新本文件中的状态、产物和下一个任务。

## 2. 前置条件

正式实现前必须满足：

- M12D 已有可消费的 `m12d_profile_version`。
- 目标 SKU 和候选 SKU 能按 `category_code + project_id + batch_id + m12d_profile_version + sku_code` 读取画像。
- M12D 输出 schema 已冻结：`core_payment_anchors`、`supporting_anchors`、`weak_expression_anchors`、`risk_drag_anchors`、`anchors[]`、`profile_confidence`。

当前已满足的 M12D 前置：

- 批次：`m00_20260623014631_c8630747`
- 已发布版本：`m12d_tv_purchase_reason_profile_v0_1_draft`
- 契约 fixture：`docs/core3_mvp/real_data_v2/current_implementation/M12D_G09_published_contract_fixture.json`
- 契约报告：`docs/core3_mvp/real_data_v2/current_implementation/M12D_G09_published_contract_report.md`
- CA-G01 可以开始实现读取契约，但仍不得在竞品智能体中生成 M12D 或修改锚点角色。

允许的提前工作：

- 使用固定 fixture 模拟已发布 M12D，做 reader、pair 匹配、报告结构和卡片 payload 的单元测试。

禁止：

- 在竞品智能体里生成 M12D。
- 在竞品智能体里修改 M12D 锚点角色。
- 用 fallback 文案补写“技术型高端体验”“场景型高端体验”等未被 M12D 支撑的成交理由。

## 3. 设计引用

| 类型 | 文件 |
| --- | --- |
| 竞品问答需求 | `docs/core3_mvp/real_data_v2/sop_requirements/CATFORGE_ANALYST_competitor_answer_requirements.md` |
| 竞品问答详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/CATFORGE_ANALYST_competitor_answer_design.md` |
| M12D 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M12D_sku_purchase_reason_profile_requirements.md` |
| M12D 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_sku_purchase_reason_profile_design.md` |

## 4. 任务链总览

| 编号 | 状态 | 任务 | 主要产物 | 前置 |
| --- | --- | --- | --- | --- |
| CA-G01 | completed | M12D 读取契约和 fixture | reader interface、fixture、缺失行为测试 | M12D schema |
| CA-G02 | completed | 关键价值锚点可替代性算法 | `anchor_substitutability` 和测试 | CA-G01 |
| CA-G03 | completed | 替代压力评分改造 | 10 分分项、主/辅压力类型和测试 | CA-G02 |
| CA-G04 | completed | 综合分和 Top 3 选择门槛 | 排序、硬门槛、角色调整和测试 | CA-G03 |
| CA-G05 | completed | 报告结构改造成维度目录 | 2.1-2.9 分节 Markdown 和测试 | CA-G04 |
| CA-G06 | completed | Dashboard/Card/short_answer 输出 | payload、卡片、短摘要和测试 | CA-G04 |
| CA-G07 | completed | 小奥 Skill 路由和输出边界 | Skill prompt/命令/错误边界 | CA-G06 |
| CA-G08 | completed | 端到端验证和 205 部署 | 65E7Q 飞书报告、小奥入口验证 | CA-G05/06/07 |

## 5. 单任务执行模板

```text
目标：执行 CA-Gxx，只完成该编号任务。
工作区：/Users/sjs/catforge
边界：
- 不生成 M12D。
- 不修改 M12D 锚点角色。
- 不跨任务实现后续报告/Skill/部署内容。
输入文档：
- docs/core3_mvp/real_data_v2/development/CATFORGE_ANALYST_competitor_answer_development_tasks.md
- docs/core3_mvp/real_data_v2/sop_requirements/CATFORGE_ANALYST_competitor_answer_requirements.md
- docs/core3_mvp/real_data_v2/sop_detailed_design/CATFORGE_ANALYST_competitor_answer_design.md
完成后：
- 运行相关测试或说明未运行原因。
- 更新本任务文档中该任务状态、产物和下一个任务。
- 不 stage/commit，除非用户明确要求。
```

## 6. 任务明细

### CA-G01 M12D 读取契约和 fixture

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/purchase_reason_profile_reader.py`
  - `apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py`
  - 复用 M12D-G09 fixture：`docs/core3_mvp/real_data_v2/current_implementation/M12D_G09_published_contract_fixture.json`
- 契约：
  - 新增 `PurchaseReasonProfileReader` protocol，作为竞品智能体消费 M12D 的只读边界。
  - `RepositoryPurchaseReasonProfileReader` 按 `category_code + project_id + batch_id + m12d_profile_version + sku_code` 调用 M12D published contract，只读取已发布画像。
  - `FixturePurchaseReasonProfileReader` 解析 G09 固化的 `M12DDownstreamReadContract`，用于 CA 后续任务的 deterministic fixture 测试。
  - `decide_target_m12d_usage` 固定目标缺失/未发布/不可用时阻断强排序，目标低置信时只允许降级评分。
  - `decide_candidate_m12d_usage` 固定候选缺失/未发布/不可用时退出 Top 3 或复核，候选低置信时降级参与 pair scoring。
  - 本任务未接入 `ValueAnchorMatcher`、替代压力、综合排序或报告渲染；不生成 M12D、不修改 M12D 锚点角色。
- 测试：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py -q`：6 passed, 12 warnings。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：14 passed, 204 warnings。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/analyst/purchase_reason_profile_reader.py apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py`：通过。
- 下一个任务：CA-G02 关键价值锚点可替代性算法。

目标：

- 新增 `PurchaseReasonProfileReader` 接口。
- 支持从 repository 或 fixture 读取已发布 M12D。
- 固定目标缺失、候选缺失、低置信、未发布版本的降级行为。

产物：

- reader interface。
- M12D fixture。
- 缺失/未发布/低置信测试。

验收：

- `competitor-set` 不生成 M12D。
- 目标 M12D 缺失时不输出强排序结论。
- 候选 M12D 缺失时该候选锚点可替代性降置信度或退出 Top 3。

### CA-G02 关键价值锚点可替代性算法

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/anchor_substitutability.py`
  - `apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py`
- 契约：
  - 新增 `ValueAnchorMatcher`，输入目标和候选 `M12DDownstreamReadContract`，不读取参数/卖点 code 临时拼接成交理由。
  - 输出 `anchor_substitutability_score`（0-15）、`anchor_substitutability_level`、五项 `score_breakdown`、`shared_core_anchors`、`target_only_anchors`、`candidate_stronger_anchors`、`weak_expression_anchors`、`candidate_only_anchors`、`risk_drag_anchors`、`match_details` 和业务摘要。
  - 评分分项：目标核心锚点覆盖 5 分、证据强度对等 4 分、候选相对优势 3 分、场景/任务/客群一致 2 分、市场与评论验证 1 分，再扣除弱表达、风险拖累和 M12D 降级 penalty。
  - `weak_expression` 只进入弱表达说明，不推高分数；候选仅以 `supporting` 覆盖目标核心锚点时只给局部替代分，并设置 `primary_direct_eligible=false`。
  - 目标或候选 M12D 缺失/未发布时阻断 pair scoring；低置信/降级画像可评分但必须 `requires_review=true`。
  - 提供 `to_legacy_value_anchor()` 兼容旧 dashboard/报告字段，但本任务未接入综合排序、Top 3 或报告渲染。
- 测试：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py -q`：5 passed, 1 warning。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py -q`：6 passed, 12 warnings。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：14 passed, 204 warnings。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/analyst/anchor_substitutability.py apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py`：通过。
- 下一个任务：CA-G03 替代压力评分改造。

目标：

- 改造 `ValueAnchorMatcher`。
- 从目标和候选 M12D 读取核心锚点、辅助锚点、弱表达和风险锚点。
- 输出 15 分 `anchor_substitutability`。

产物：

- matcher 实现。
- 得分分项和 match_details。
- 边界测试。

验收：

- 目标 `core_payment` 覆盖高于辅助锚点覆盖。
- `weak_expression` 不能推高可替代性。
- 候选只覆盖辅助锚点时不能成为首选直接竞品。

### CA-G03 替代压力评分改造

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/replacement_pressure.py`
  - `apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py`
- 契约：
  - 新增 `ReplacementPressureClassifier`，消费购买池、CA-G02 `anchor_substitutability`、价格/配置冲击、场景心智、市场验证和风险/置信修正。
  - 输出 `replacement_pressure_score`（0-10）、`replacement_pressure_level`、六项 `score_breakdown`、`primary_pressure_type`、最多两个 `auxiliary_pressure_types`、`strong_pressure_allowed`、`requires_review` 和业务说明。
  - 评分分项：购买池压力 2 分、成交理由替代强度 3 分、价格或配置冲击 2 分、场景心智迁移 1 分、市场分流验证 1 分、置信修正 -1 到 +1。
  - 主压力类型只选一个，辅助压力类型最多两个；低于 5/10 或锚点 pair scoring 被阻断时，禁止输出强替代话术。
  - 压力类型支持 `value_substitution`、`price_suppression`、`configuration_benchmark`、`scenario_mindshare`、`brand_ecosystem`、`downtrade_diversion`、`uptrade_alternative`，并用 `low_pressure_review` 作为低压复核兜底。
  - 提供 `to_legacy_replacement_pressure()` 兼容旧字段，但本任务未接入综合分、Top 3 或报告渲染。
- 测试：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py -q`：5 passed, 1 warning。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py -q`：5 passed, 1 warning。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py -q`：6 passed, 12 warnings。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：14 passed, 204 warnings。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/analyst/replacement_pressure.py apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py`：通过。
- 下一个任务：CA-G04 综合分和 Top 3 选择门槛。

目标：

- 改造 `ReplacementPressureClassifier`。
- 输出 10 分分项、主压力类型、最多两个辅助压力类型。

产物：

- pressure scorer。
- 压力类型选择器。
- 单元测试。

验收：

- 替代压力消费购买池、成交理由替代强度、价格/配置冲击、场景心智、市场验证和置信修正。
- 主压力类型只选一个。
- 低于 5/10 不输出强替代话术。

### CA-G04 综合分和 Top 3 选择门槛

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py`
  - `apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py`
  - `apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`
- 契约：
  - 综合分权重改为购买池 20、价值战场 25、用户任务 15、目标客群 15、关键价值锚点 15、替代压力 10，市场验证不再计入综合分，只用于置信和排序校验。
  - 竞品回答优先消费候选上已有的 CA-G02 `value_anchor/anchor_substitutability` 与 CA-G03 `replacement_pressure` 兼容字段；没有时保留旧参数/卖点兜底，不生成 M12D。
  - Top 3 选择新增硬门槛：锚点可替代性低于 7/15 不得升级为直接首选；替代压力低于 5/10 不得升级强替代角色；购买池 P3/P4 且市场验证弱的候选不能进入 Top 3。
  - 价格最近但锚点替代不足的候选可作为价格贴身参考，但不能排首选直接竞品。
- 测试：
  - `pytest apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py -q`：3 passed。
  - `pytest apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py -q`：13 passed。
  - `pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py -q`：81 passed, 8387 warnings。
- 下一个任务：CA-G05 报告结构改造成维度目录。

目标：

- 将 `anchor_substitutability_score` 和新的 `replacement_pressure_score` 接入综合分。
- 增加硬门槛和排序降级逻辑。

产物：

- 评分聚合改造。
- Top 3 选择测试。

验收：

- 价格最近但锚点替代不足的候选不能排首选。
- 市场验证不足不清零，但与购买池偏离叠加时不能进入 Top 3。

### CA-G05 报告结构改造成维度目录

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py`
  - `apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`
- 契约：
  - `render_competitor_report()` 的 `## 二、分析过程` 改为固定 2.1-2.9 维度目录。
  - 2.1-2.9 顺序为：综合评分总览、购买池比较、价值战场比较、用户任务比较、目标客群比较、关键价值锚点可替代性比较、替代压力比较、市场验证比较、候选池与未选原因附录。
  - 购买池、价值战场、用户任务、目标客群、关键价值锚点、替代压力和市场验证章节均包含判断口径、本品 + Top 3 横向表格、业务结论。
  - 候选池与未选原因只保留在 2.9 附录；旧 `关键价值锚点、替代压力和市场验证依据` 合并章节已移除。
  - 本任务未改 Dashboard payload、飞书卡片、short_answer、Skill 路由或部署逻辑。
- 测试：
  - `pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py::test_competitor_set_xiaoao_answer_prioritizes_business_pressure -q`：1 passed, 146 warnings。
  - `pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py -q`：81 passed, 8387 warnings。
  - `pytest apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py -q`：13 passed。
  - `python -m compileall apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`：通过。
- 下一个任务：CA-G06 Dashboard/Card/short_answer 输出。

目标：

- 改造 `CompetitorReportRenderer`。
- `## 二、分析过程` 固定为 2.1-2.9。
- 每个维度章节包含判断口径、本品 + Top 3 表格、差异解释和业务结论。

产物：

- Markdown renderer 改造。
- 报告结构测试。

验收：

- 不再出现“关键价值锚点、替代压力和市场验证依据”合并章节。
- 候选池与未选原因只出现在附录/折叠区。

### CA-G06 Dashboard/Card/short_answer 输出

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py`
  - `apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`
- 契约：
  - `dashboard_payload.competitors[]` 新增 `anchor_substitutability_cn`、`pressure_breakdown_cn`、`anchor_substitutability` 和 `pressure_breakdown`。
  - 飞书卡片新增“关键价值锚点与替代压力”段落，展示 Top 3 的锚点可替代性摘要和替代压力摘要。
  - Markdown 看板首屏同步新增“关键价值锚点与替代压力”表格。
  - 卡片仍只展示 Top 3，不输出全量候选池；产品对比链接仍只携带本品 + Top 3。
  - `short_answer` 不再用“参数/卖点替代压力”补写未被 M12D/锚点支撑的成交理由；语义证据缺失时明确按购买池、关键价值锚点可替代性和替代压力降级判断。
  - 本任务未改 Skill 路由、飞书发送命令或部署逻辑。
- 测试：
  - `pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py::test_competitor_set_xiaoao_answer_prioritizes_business_pressure -q`：1 passed, 146 warnings。
  - `pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py::test_competitor_dashboard_payload_and_feishu_card_include_report_action -q`：1 passed。
  - `pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py::test_xiaoao_short_answer_downgrades_when_semantic_evidence_missing -q`：1 passed。
  - `pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py -q`：81 passed, 8387 warnings。
  - `pytest apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py -q`：13 passed。
  - `python -m compileall apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`：通过。
- 下一个任务：CA-G07 小奥 Skill 路由和输出边界。

目标：

- `dashboard_payload` 增加 `anchor_substitutability_cn` 和 `pressure_breakdown_cn`。
- 飞书卡片展示关键价值锚点可替代性摘要和替代压力摘要。
- 短摘要不补写未被 M12D 支撑的成交理由。

产物：

- payload builder 改造。
- card renderer 改造。
- short answer 测试。

验收：

- 卡片仍只展示 Top 3，不展示全量候选池。
- 短摘要不超过 600 字，不出现内部字段或 Mxx。

### CA-G07 小奥 Skill 路由和输出边界

状态：已完成。

完成记录：

- 产物：
  - `apps/api-server/app/cli/catforge_analyst.py`
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py`
  - `apps/api-server/tests/core3_real_data/test_competitor_answer_feishu_publish.py`
  - `tools/openclaw/skills/xiaoao-home-appliance-market-analysis/SKILL.md`
  - `tools/openclaw/agents/xiaoao-home-appliance-market-analyst/AGENTS.md`
- 契约：
  - 小奥竞品列表飞书入口只调用稳定 CLI text 命令，stdout 作为可见回复；不解析新 JSON、不复制卡片 payload、不重写排序或报告结论。
  - CLI 优先发送主会话卡片，主会话失败时用 `message_id` 回退回复。
  - 卡片发送成功或失败都返回非空短中文状态；失败状态脱敏，不暴露 scope、配置路径、堆栈、原始 stdout/stderr 或命令文本。
  - 本任务未改 M12D 生产逻辑、竞品报告结构、Dashboard payload 或部署。
- 测试：
  - `python -m pytest tests/core3_real_data/test_competitor_answer_feishu_publish.py -q`：16 passed。
  - `python -m pytest tests/core3_real_data/test_catforge_analyst_cli.py -q -k "competitor_set_xiaoao_answer_prioritizes_business_pressure or competitor_dashboard_payload_and_feishu_card_include_report_action or competitor_set_text_uses_xiaoao_short_answer or list_abilities_returns_agent_contract"`：4 passed, 438 warnings。
  - `python -m compileall app/cli/catforge_analyst.py app/services/core3_real_data/analyst/competitor_answer.py`：通过。
- 下一个任务：CA-G08 端到端验证和 205 部署。

目标：

- 更新小奥 Skill 中竞品问答路由。
- 确保 Skill 只调用 CLI，不解析新 JSON、不重写结论。

产物：

- Skill 文档/脚本改造。
- CLI 错误边界测试。

验收：

- 飞书入口优先返回卡片发送状态。
- 卡片失败时不空回复、不暴露内部错误。

### CA-G08 端到端验证和 205 部署

状态：已完成。

完成记录：

- 产物：
  - `docs/core3_mvp/real_data_v2/current_implementation/CA_G08_65E7Q_e2e_205_validation_20260708.md`
  - 205 远端验证结果：`/opt/catforge/tmp/ca_g08/65e7q_competitor_answer.json`
  - 205 远端 Markdown 验证结果：`/opt/catforge/tmp/ca_g08/65e7q_competitor_answer_markdown.json`
  - 本地拉回验证副本：`tmp/ca_g08/65e7q_competitor_answer_205.json`
  - 本地拉回报告 Markdown 副本：`tmp/ca_g08/65e7q_competitor_report_markdown_205.md`
- 飞书报告：`https://my.feishu.cn/docx/P8MAds7qToUJWGxOwXQc12ohnLt`
- 部署：
  - `scripts/hotfix-api.sh dev` 已完成，205 API 本机 `readyz` 返回 `{"status":"ready","database":"ok"}`。
  - 小奥 OpenClaw Skill/Agent 已同步到 `/opt/catforge/tools/openclaw/...` 和 `/home/deploy/.openclaw/...` 运行目录。
- 验收：
  - 65E7Q Top 3 为：创维 65A7H PRO、TCL 65Q9L PRO、华为 VISION智慧屏 5 PRO 65。
  - 小奥入口、短摘要、卡片 payload、Markdown 报告和飞书报告排序一致。
  - 报告 `## 二、分析过程` 包含 2.1-2.9 维度目录，每个主维度能横向比较本品和 Top 3，候选池只在 2.9 附录。
  - 飞书卡片入口 `--feishu-card-only` 失败边界返回非空、脱敏短中文状态，不暴露内部错误。
  - 本任务未生成 M12D、未修改 M12D 锚点角色、未 stage/commit。
- 测试：
  - `scripts/check-env.sh dev`：SSH、Docker、PostgreSQL、容器状态可用；公网 `:8000` 直连不可用，验收使用 205 本机和容器内 CLI。
  - 205 容器内 `python -m compileall app/cli/catforge_analyst.py app/services/core3_real_data/analyst/competitor_answer.py`：通过。
  - 205 容器内 `competitor-set --query 65E7Q --format json --answer-style xiaoao --with-report feishu-doc`：ok，报告 created。
  - 205 容器内 `competitor-set --query 65E7Q --format json --answer-style xiaoao --with-report markdown`：ok，报告结构通过。
  - 205 容器内 `competitor-set --query 65E7Q --format text --answer-style xiaoao --with-report none`：ok，与 no-report JSON short_answer 一致。
- 下一个任务：无 pending 任务，任务链完成。

目标：

- 用海信 65E7Q 验证 Top 3、锚点可替代性、替代压力、报告结构和小奥入口。
- 部署到 205 并生成飞书报告。

产物：

- E2E 验证记录。
- 205 部署记录。
- 飞书文档链接。

验收：

- 小奥入口、短摘要、卡片和飞书报告排序一致。
- 报告中每个维度都能横向比较本品和 Top 3。

## 7. 定时器选择规则

每次定时器触发时：

1. 如果 M12D 尚未发布，只能执行 CA-G01 的 fixture/契约类任务，不能做正式集成。
2. M12D 发布后，按 CA-G01 到 CA-G08 顺序选择第一个 `pending` 任务。
3. 每次只执行一个任务。
4. 完成后把状态改成 `completed`，并记录产物路径。
5. 阻塞时改成 `blocked`，写明缺少的 M12D 版本、fixture 或上游结果。
