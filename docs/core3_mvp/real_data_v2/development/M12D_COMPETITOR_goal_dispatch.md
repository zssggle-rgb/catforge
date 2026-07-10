# M12D 与竞品智能体 Goal 调度队列

## 1. 调度目标

本文件是定时器调度入口，用来把 M12D 和竞品分析智能体改造拆成多个可独立执行的 goal。

定时器每次触发只执行一个任务，不跨任务连续推进。任务完成后更新对应任务文档状态，再等待下一次定时器。

当前自动调度频率：每 10 分钟触发一次，每次只允许推进一个任务编号。

## 2. 调度文档

| 任务链 | 文件 |
| --- | --- |
| M12D SKU成交理由画像 | `docs/core3_mvp/real_data_v2/development/M12D_development_tasks.md` |
| 竞品智能体消费 M12D | `docs/core3_mvp/real_data_v2/development/CATFORGE_ANALYST_competitor_answer_development_tasks.md` |

## 3. 总调度顺序

### 阶段 A：M12D 独立资产生产

必须先完成 M12D 的分析、实现、小批量验证、全量生成和版本发布。

| 顺序 | 任务编号 | 状态 | 任务 |
| ---: | --- | --- | --- |
| 1 | M12D-G01 | completed | 上游证据审计与样本确认 |
| 2 | M12D-G02 | completed | Schema、存储和发布版本设计落地 |
| 3 | M12D-G03 | completed | ContextBuilder 输入读取 |
| 4 | M12D-G04 | completed | 标准锚点族配置和候选生成 |
| 5 | M12D-G04R1 | completed | 价值主题与购买理由候选提炼修正 |
| 6 | M12D-G04R2 | completed | 修正价值主题/购买理由 taxonomy 与候选契约 |
| 7 | M12D-G05 | completed | 证据强度评分和角色判定 |
| 8 | M12D-G06 | completed | 单 SKU CLI 与 Markdown 预览 |
| 9 | M12D-G07 | completed | 小批量验证与规则修正 |
| 10 | M12D-G08 | completed | 全量 TV batch 生成 |
| 11 | M12D-G09 | completed | 发布版本与下游契约冻结 |

### 阶段 B：竞品智能体消费 M12D

M12D-G09 已完成，阶段 B 可从 CA-G01 开始。竞品智能体仍不得生成 M12D 或修改 M12D 锚点角色。

| 顺序 | 任务编号 | 状态 | 任务 |
| ---: | --- | --- | --- |
| 12 | CA-G01 | completed | M12D 读取契约和 fixture |
| 13 | CA-G02 | completed | 关键价值锚点可替代性算法 |
| 14 | CA-G03 | completed | 替代压力评分改造 |
| 15 | CA-G04 | completed | 综合分和 Top 3 选择门槛 |
| 16 | CA-G05 | completed | 报告结构改造成维度目录 |
| 17 | CA-G06 | completed | Dashboard/Card/short_answer 输出 |
| 18 | CA-G07 | completed | 小奥 Skill 路由和输出边界 |
| 19 | CA-G08 | completed | 端到端验证和 205 部署 |

## 4. 定时器选择规则

每次定时器触发时：

1. 读取本文件和两个任务链文件。
2. 优先选择阶段 A 中第一个 `pending` 的 M12D-Gxx。
3. 只有 M12D-G09 已完成后，才选择阶段 B 中第一个 `pending` 的 CA-Gxx。
4. 如果需要提前做竞品侧 fixture，必须明确只执行 CA-G01，且不得把它作为正式集成完成。
5. 每次只执行一个任务，创建一个 goal。
6. 完成后更新：
   - 本文件对应任务状态。
   - 对应任务链文件中的任务状态。
   - 产物路径、测试结果和下一个任务。
7. 如果任务阻塞，标为 `blocked`，写明阻塞原因，不跳过到下一个正式任务。

## 5. 定时器 Prompt 模板

```text
你正在 /Users/sjs/catforge 中继续 CatForge M12D 与竞品智能体任务链。

请先读取：
- docs/core3_mvp/real_data_v2/development/M12D_COMPETITOR_goal_dispatch.md
- docs/core3_mvp/real_data_v2/development/M12D_development_tasks.md
- docs/core3_mvp/real_data_v2/development/CATFORGE_ANALYST_competitor_answer_development_tasks.md

按调度规则选择下一个 pending 任务，只执行一个任务。

要求：
- 使用 goal 模式执行该任务。
- 不跨任务实现。
- 不把 M12D 生产逻辑写进竞品智能体。
- 不 stage/commit，除非用户明确要求。
- 完成后更新任务状态、产物路径、测试结果和下一个任务。
- 如果阻塞，标记 blocked 并说明阻塞条件。
```

## 6. 当前下一个任务

```text
无 pending 任务。M12D 与竞品智能体任务链已完成。
```

## 7. 最近完成记录

### CA-G08 端到端验证和 205 部署

- 状态：completed。
- 产物：
  - `docs/core3_mvp/real_data_v2/current_implementation/CA_G08_65E7Q_e2e_205_validation_20260708.md`
  - 205 远端验证结果：`/opt/catforge/tmp/ca_g08/65e7q_competitor_answer.json`
  - 205 远端 Markdown 验证结果：`/opt/catforge/tmp/ca_g08/65e7q_competitor_answer_markdown.json`
  - 本地拉回验证副本：`tmp/ca_g08/65e7q_competitor_answer_205.json`
  - 本地拉回报告 Markdown 副本：`tmp/ca_g08/65e7q_competitor_report_markdown_205.md`
- 飞书报告：
  - `https://my.feishu.cn/docx/P8MAds7qToUJWGxOwXQc12ohnLt`
- 部署：
  - 使用 `scripts/hotfix-api.sh dev` 热修复 205 API 源码并重启 API。
  - 同步小奥 OpenClaw Skill/Agent 到 `/opt/catforge/tools/openclaw/...` 和 `/home/deploy/.openclaw/...` 运行目录。
  - 205 本机 `readyz` 返回 `{"status":"ready","database":"ok"}`。
- 验收：
  - 65E7Q Top 3 顺序：创维 65A7H PRO、TCL 65Q9L PRO、华为 VISION智慧屏 5 PRO 65。
  - `top_competitors`、`dashboard_payload`、短摘要、卡片 payload 和 Markdown/飞书报告排序一致。
  - 飞书报告状态为 `created`。
  - 报告 `## 二、分析过程` 包含 2.1-2.9 维度目录，候选池只在 2.9 附录。
  - 小奥飞书卡片入口 `--feishu-card-only` 返回非空、脱敏的卡片发送状态；无效消息 ID 验证输出为 `飞书卡片发送失败：当前消息 ID 不可回复或已失效。`
  - 本任务未生成 M12D、未修改 M12D 锚点角色、未 stage/commit。
- 测试：
  - `scripts/check-env.sh dev`：SSH、Docker、PostgreSQL、容器状态可用；公网 `:8000` 直连不可用，验收使用 205 本机和容器内 CLI。
  - 205 容器内 `python -m compileall app/cli/catforge_analyst.py app/services/core3_real_data/analyst/competitor_answer.py`：通过。
  - 205 容器内 `competitor-set --query 65E7Q --format json --answer-style xiaoao --with-report feishu-doc`：ok，报告 created。
  - 205 容器内 `competitor-set --query 65E7Q --format json --answer-style xiaoao --with-report markdown`：ok，报告结构通过。
  - 205 容器内 `competitor-set --query 65E7Q --format text --answer-style xiaoao --with-report none`：ok，与 no-report JSON short_answer 一致。
- 下一个任务：无 pending 任务，任务链完成。

### CA-G07 小奥 Skill 路由和输出边界

- 状态：completed。
- 产物：
  - `apps/api-server/app/cli/catforge_analyst.py`
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py`
  - `apps/api-server/tests/core3_real_data/test_competitor_answer_feishu_publish.py`
  - `tools/openclaw/skills/xiaoao-home-appliance-market-analysis/SKILL.md`
  - `tools/openclaw/agents/xiaoao-home-appliance-market-analyst/AGENTS.md`
- 契约：
  - 小奥竞品列表飞书入口继续只调用 `catforge_analyst competitor-set --format text --answer-style xiaoao --with-report feishu-doc --feishu-card-only`，不解析卡片 JSON、不重写结论。
  - CLI 在同时传入 `feishu_chat_id` 和 `feishu_reply_message_id` 时优先向主会话发卡片；主会话发送失败后用 `message_id` 回退回复。
  - text stdout 优先返回飞书卡片发送状态；卡片失败时输出非空、脱敏的短中文状态，不回退为短摘要，不暴露 scope、配置路径、堆栈或原始 stdout/stderr。
  - 本任务未改 M12D 生产逻辑、竞品报告结构、Dashboard payload 或 205 部署。
- 测试：
  - `python -m pytest tests/core3_real_data/test_competitor_answer_feishu_publish.py -q`：16 passed。
  - `python -m pytest tests/core3_real_data/test_catforge_analyst_cli.py -q -k "competitor_set_xiaoao_answer_prioritizes_business_pressure or competitor_dashboard_payload_and_feishu_card_include_report_action or competitor_set_text_uses_xiaoao_short_answer or list_abilities_returns_agent_contract"`：4 passed, 438 warnings。
  - `python -m compileall app/cli/catforge_analyst.py app/services/core3_real_data/analyst/competitor_answer.py`：通过。
- 下一个任务：CA-G08 端到端验证和 205 部署。

### CA-G06 Dashboard/Card/short_answer 输出

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py`
  - `apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`
- 契约：
  - `dashboard_payload.competitors[]` 新增 `anchor_substitutability_cn`、`pressure_breakdown_cn`、`anchor_substitutability` 和 `pressure_breakdown`，仅面向 Top 3 竞品。
  - 飞书卡片新增“关键价值锚点与替代压力”段落，展示 Top 3 的锚点可替代性摘要和替代压力摘要；卡片仍不展示全量候选池。
  - Markdown 看板首屏同步展示“关键价值锚点与替代压力”表格。
  - `short_answer` 不再用“参数/卖点替代压力”补写未被 M12D/锚点支撑的成交理由；语义证据缺失时按购买池、关键价值锚点可替代性和替代压力降级说明。
  - 本任务未改小奥 Skill 路由、飞书发送命令或 205 部署。
- 测试：
  - `pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py -q`：81 passed, 8387 warnings。
  - `pytest apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py -q`：13 passed。
  - `python -m compileall apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`：通过。
- 下一个任务：CA-G07 小奥 Skill 路由和输出边界。

### CA-G05 报告结构改造成维度目录

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py`
  - `apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`
- 契约：
  - `## 二、分析过程` 固定为 2.1-2.9：综合评分总览、购买池比较、价值战场比较、用户任务比较、目标客群比较、关键价值锚点可替代性比较、替代压力比较、市场验证比较、候选池与未选原因附录。
  - 每个主维度章节均包含判断口径、本品 + Top 3 横向表格和业务结论。
  - 候选池与未选原因只保留在 2.9 附录，不再作为主分析前置章节；旧“关键价值锚点、替代压力和市场验证依据”合并章节移除。
  - 本任务只改 Markdown 报告结构，未改 Dashboard/Card/short_answer、Skill 或部署逻辑。
- 测试：
  - `pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py -q`：81 passed, 8387 warnings。
  - `pytest apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py -q`：13 passed。
  - `python -m compileall apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`：通过。
- 下一个任务：CA-G06 Dashboard/Card/short_answer 输出。

### CA-G04 综合分和 Top 3 选择门槛

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py`
  - `apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py`
  - `apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`
- 契约：
  - 综合分调整为购买池 20、价值战场 25、用户任务 15、目标客群 15、关键价值锚点 15、替代压力 10；市场验证退出综合分，只作为置信和排序校验。
  - `build_competitor_answer()` 优先消费候选上已有的 CA-G02 `value_anchor/anchor_substitutability` 和 CA-G03 `replacement_pressure` 结果，没有时保留旧参数/卖点兜底。
  - Top 3 增加硬门槛：锚点可替代性低于 7/15 不得升级为直接首选；替代压力低于 5/10 不得输出强替代角色；购买池 P3/P4 且市场验证弱的候选不能进入 Top 3。
- 测试：
  - `pytest apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py -q`：13 passed。
  - `pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py -q`：81 passed, 8387 warnings。
- 下一个任务：CA-G05 报告结构改造成维度目录。

### M12D-G02 Schema、存储和发布版本设计落地

- 状态：completed。
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
  - `git diff --check -- ...`：通过。
- 下一个任务：M12D-G03 ContextBuilder 输入读取。

### M12D-G03 ContextBuilder 输入读取

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 测试：
  - `python -m pytest tests/core3_real_data/test_m12d_purchase_reason_profile.py`：5 passed, 57 warnings。
  - `python -m compileall app/services/core3_real_data/purchase_reason_profile_schemas.py app/services/core3_real_data/purchase_reason_context_builder.py tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `git diff --check -- ...`：通过。
- 设计澄清：G04 的标准锚点族不是程序运行时自动生成，而是 Codex/业务基于多源画像和样本审计提炼、人审后固化为品类级 taxonomy/config；程序只负责读取 taxonomy 并匹配 SKU 证据。
- 下一个任务：M12D-G04 标准锚点族配置和候选生成。

### M12D-G04 标准锚点族配置和候选生成

- 状态：completed。
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
  - `git diff --check -- ...`：通过。
  - `rg -n "[ \t]+$" ...`：无尾随空白命中。
- 契约：TV 标准锚点族已作为品类级版本化 taxonomy/config 固化；运行时程序只做 SKU 证据匹配，不自动生成标准锚点族。
- 候选生成边界：候选生成器只输出候选和弱表达上限，证据强度评分与最终角色判定留给 G05。
- 修正说明：经业务讨论，G04 的锚点更接近价值主题候选，不能直接等同标准购买理由；需先执行 G04R1，从 205 结果生成价值主题与购买理由候选提炼报告，再修正 taxonomy。
- 下一个任务：M12D-G04R1 价值主题与购买理由候选提炼修正。

### M12D-G04R1 价值主题与购买理由候选提炼修正

- 状态：completed。
- 产物：
  - `scripts/m12d_g04r1_extract_tv_reason_candidates.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G04R1_tv_value_theme_purchase_reason_candidates.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G04R1_tv_value_theme_purchase_reason_candidate_report.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_tv_standard_value_theme_taxonomy_v0_1_draft.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_tv_standard_purchase_reason_taxonomy_v0_1_draft.md`
- 数据源：205 `catforge_dev` 当前 TV 结果，只读 SELECT，`TV%` SKU 前缀过滤。
- 当前覆盖：M03B 377 SKU、M04C 328 SKU、M05C 348 SKU、M07 377 SKU、M09C/M10C 348 SKU、M11C 368 SKU、M12C 259 SKU。
- 结论：G04 中名词型锚点应拆为“价值主题”和“购买理由”两层；购买理由必须是选择逻辑型。标准购买理由草案已扩大为 13 个，其中 10 个为 `draft_accept`，3 个为 `review`。
- 验证：
  - `apps/api-server/.venv/bin/python -m compileall scripts/m12d_g04r1_extract_tv_reason_candidates.py`：通过。
  - 205 脚本运行成功并生成报告。
  - `rg -n "AC[0-9]|KFR-|空调" ...`：无命中。
- 下一个任务：M12D-G04R2 修正价值主题/购买理由 taxonomy 与候选契约。

### M12D-G04R2 修正价值主题/购买理由 taxonomy 与候选契约

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_anchor_taxonomy.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_anchor_candidate_generator.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_tv_standard_anchor_taxonomy_v0_1.md`
  - `docs/core3_mvp/real_data_v2/sop_requirements/M12D_sku_purchase_reason_profile_requirements.md`
  - `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_sku_purchase_reason_profile_design.md`
- 契约：
  - TV taxonomy 固化为 7 个标准价值主题 + 13 个标准购买理由。
  - 候选生成器输出 `value_theme_candidates` 与 `purchase_reason_candidates` 两层。
  - `worth_paying_more_for_experience_upgrade / 贵得值的体验升级` 需要价格位置、体验证据和评论/M12C/市场承接门槛。
  - G05 只消费购买理由候选做证据强度和角色判定。
- 测试：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：7 passed, 76 warnings。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py apps/api-server/app/services/core3_real_data/purchase_reason_anchor_taxonomy.py apps/api-server/app/services/core3_real_data/purchase_reason_anchor_candidate_generator.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
- 下一个任务：M12D-G05 证据强度评分和角色判定。

### M12D-G05 证据强度评分和角色判定

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 契约：
  - `EvidenceStrengthScorer` 对购买理由候选计算证据域分、冲突扣分和证据强度。
  - `ReasonRoleClassifier` 判定 `core_payment`、`supporting`、`weak_expression`、`risk_drag`。
  - `ProfileConfidenceScorer` 汇总 SKU 级置信度、角色桶、风险标记和复核原因。
  - 价值主题不进入最终购买理由角色判定。
- 测试：
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：10 passed, 112 warnings。
- 下一个任务：M12D-G06 单 SKU CLI 与 Markdown 预览。

### M12D-G06 单 SKU CLI 与 Markdown 预览

- 状态：completed。
- 产物：
  - `apps/api-server/app/cli/catforge_analyst.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_preview.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 契约：
  - `sku-purchase-reason` CLI 支持单 SKU 成交理由画像预览。
  - 可用 `--query "海信 65E7Q"`、`--model-name` 或 `--sku-code` 定位 SKU。
  - JSON 输出结构化结果；Markdown 输出业务可读预览，隐藏内部 SQL、原始 JSON 和调试字段。
  - 只消费 M12D G03-G05 服务，不实现批量生产，不改竞品智能体。
- 测试：
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/cli/catforge_analyst.py apps/api-server/app/services/core3_real_data/purchase_reason_profile_preview.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：11 passed, 130 warnings。
  - `git diff --check -- apps/api-server/app/cli/catforge_analyst.py apps/api-server/app/services/core3_real_data/purchase_reason_profile_preview.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
- 下一个任务：M12D-G07 小批量验证与规则修正。

### M12D-G07 小批量验证与规则修正

- 状态：completed。
- 产物：
  - `scripts/m12d_g07_validate_purchase_reason_profiles.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G07_small_batch_validation.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G07_small_batch_validation_report.md`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 验证结果：
  - 205 当前 TV serving-scope 小批量样本数：12。
  - 低置信 SKU：6。
  - 需复核 SKU：12。
  - 有核心成交理由 SKU：6。
  - 风险拖拽 SKU：0。
  - 65E7Q 预算价值误判为核心：0。
- 修正：
  - 修复 M12D ContextBuilder 对 `serving-scope:*` 组合批次读取为空的问题。
  - 新增 serving-scope 回归测试。
  - 65E7Q 的 `same_price_core_config_gain` 保持弱表达，不修改预算价值封顶规则。
  - 记录下游消费门槛：有 core 锚点但 profile 为 `ready_degraded` 时，必须展示 `profile_status/profile_confidence`，不能只凭锚点角色输出强结论。
- 测试：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：12 passed, 148 warnings。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/purchase_reason_context_builder.py apps/api-server/app/cli/catforge_analyst.py scripts/m12d_g07_validate_purchase_reason_profiles.py apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`：通过。
  - `CATFORGE_DATABASE_URL=... apps/api-server/.venv/bin/python scripts/m12d_g07_validate_purchase_reason_profiles.py --sample-size 12`：通过。
  - `git diff --check -- ...`：通过。
- 下一个任务：M12D-G08 全量 TV batch 生成。

### M12D-G08 全量 TV batch 生成

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_runner.py`
  - `scripts/m12d_g08_generate_full_tv_batch.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G08_full_tv_batch_generation.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G08_full_tv_batch_generation_report.md`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 205 全量结果：
  - 读取批次：`serving-scope:TV:m00_20260623014631_c8630747,m00_20260619084551_857df63b,m00_20260613004311_d548f6dc`
  - 入库批次：`m00_20260623014631_c8630747`
  - 草稿版本：`m12d_tv_purchase_reason_profile_v0_1_draft`
  - SKU 数：377；失败：0；低置信：201；`core_payment` 缺失：120；需复核：377。
  - DB 记录：version 1、profile 377、anchor 3299。
  - 版本状态：`release_status=draft`、`is_current=false`，未发布。
- 测试：
  - `python -m compileall app/services/core3_real_data/purchase_reason_profile_runner.py tests/core3_real_data/test_m12d_purchase_reason_profile.py ../../scripts/m12d_g08_generate_full_tv_batch.py`：通过。
  - `python -m pytest tests/core3_real_data/test_m12d_purchase_reason_profile.py`：13 passed, 183 warnings。
  - `CATFORGE_DATABASE_URL=... uv run python ../../scripts/m12d_g08_generate_full_tv_batch.py --limit 5`：dry-run 通过。
  - `CATFORGE_DATABASE_URL=... uv run python ../../scripts/m12d_g08_generate_full_tv_batch.py --write`：205 全量草稿写入通过。
  - 205 DB 校验：version/profile/anchor 计数与报告一致。
- 说明：
  - 本轮仅为 G08 草稿生成；G09 前竞品智能体不得正式消费该版本。
  - 205 执行前只把已存在的 G02 M12D 迁移升级到 `0042_core3_m12d_purchase_reason`。
- 下一个任务：M12D-G09 发布版本与下游契约冻结。

### M12D-G09 发布版本与下游契约冻结

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_contract.py`
  - `scripts/m12d_g09_publish_and_export_contract.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G09_published_contract_fixture.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_G09_published_contract_report.md`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py`
- 205 发布结果：
  - 批次：`m00_20260623014631_c8630747`
  - 发布版本：`m12d_tv_purchase_reason_profile_v0_1_draft`
  - 版本状态：`published/current`
  - DB 记录：version 1、profile 377、anchor 3299；profile/anchor 均为 `published/current`。
- 下游契约：
  - 读取键：`category_code + project_id + batch_id + m12d_profile_version + sku_code`
  - 状态：`published_ready`、`published_degraded`、`published_unusable`、`not_found`
  - 动作：`normal_pair_scoring`、`degraded_pair_scoring`、`block_target_or_drop_candidate`
  - 缺失或未发布不得临时生成/补写成交理由；下游不得修改 M12D 原始锚点角色。
- Fixture：
  - 样本 SKU：`TV00029112`、`TV00029936`、`TV00027801`、`TV00029020`、`TV00028829`
  - 样本状态：5 个样本均为 `published_degraded`，动作均为 `degraded_pair_scoring`。
  - 缺失 SKU 和未发布版本 fixture 均为 `not_found` / `block_target_or_drop_candidate`。
- 测试：
  - `python -m compileall app/services/core3_real_data/purchase_reason_profile_schemas.py app/services/core3_real_data/purchase_reason_profile_contract.py tests/core3_real_data/test_m12d_purchase_reason_profile.py ../../scripts/m12d_g09_publish_and_export_contract.py`：通过。
  - `python -m pytest tests/core3_real_data/test_m12d_purchase_reason_profile.py`：14 passed, 203 warnings。
  - `CATFORGE_DATABASE_URL=... uv run python ../../scripts/m12d_g09_publish_and_export_contract.py --publish`：205 发布和 fixture 导出通过。
  - 205 DB readback：version/profile/anchor 发布状态和报告一致。
- 下一个任务：CA-G01 M12D 读取契约和 fixture。

### CA-G01 M12D 读取契约和 fixture

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/purchase_reason_profile_reader.py`
  - `apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py`
  - 复用 M12D-G09 fixture：`docs/core3_mvp/real_data_v2/current_implementation/M12D_G09_published_contract_fixture.json`
- 契约：
  - `PurchaseReasonProfileReader` 作为竞品侧只读接口，支持 repository 读取已发布 M12D，也支持 fixture 读取冻结契约。
  - `FixturePurchaseReasonProfileReader` 只解析 G09 的 `M12DDownstreamReadContract`，不生成画像。
  - `RepositoryPurchaseReasonProfileReader` 只调用 M12D published contract，不导入 M12D runner。
  - 目标缺失/未发布阻断强排序；目标低置信降级评分且禁止无条件强结论；候选缺失/未发布退出 Top 3 或进入复核；候选低置信降级参与后续 pair scoring。
- 测试：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py -q`：6 passed, 12 warnings。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：14 passed, 204 warnings。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/analyst/purchase_reason_profile_reader.py apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py`：通过。
- 下一个任务：CA-G02 关键价值锚点可替代性算法。

### CA-G02 关键价值锚点可替代性算法

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/anchor_substitutability.py`
  - `apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py`
- 契约：
  - 新增 `ValueAnchorMatcher`，输入目标/候选 `M12DDownstreamReadContract`，输出 15 分 `anchor_substitutability`。
  - 分项为：目标核心锚点覆盖 5 分、证据强度对等 4 分、候选相对优势 3 分、场景/任务/客群一致 2 分、市场与评论验证 1 分，并扣除弱表达/风险/低置信降级 penalty。
  - 输出 `shared_core_anchors`、`target_only_anchors`、`candidate_stronger_anchors`、`weak_expression_anchors`、`candidate_only_anchors`、`risk_drag_anchors`、`match_details`、`primary_direct_eligible` 和 `anchor_substitution_summary_cn`。
  - `weak_expression` 不推高可替代性；候选只覆盖目标辅助/支持锚点时不能成为首选直接竞品；目标或候选 M12D 缺失时阻断 pair scoring。
  - 本任务未接入替代压力、综合排序、Top 3 或报告渲染；旧 `_value_anchor()` 的替换留给后续 CA-G04/CA-G05。
- 测试：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py -q`：5 passed, 1 warning。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py -q`：6 passed, 12 warnings。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：14 passed, 204 warnings。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/analyst/anchor_substitutability.py apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py`：通过。
- 下一个任务：CA-G03 替代压力评分改造。

### CA-G03 替代压力评分改造

- 状态：completed。
- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/replacement_pressure.py`
  - `apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py`
- 契约：
  - 新增 `ReplacementPressureClassifier`，输入购买池、CA-G02 `anchor_substitutability`、价格/配置冲击、语义重合、市场验证和风险标记。
  - 输出 10 分 `replacement_pressure_score`，分项为购买池压力 2 分、成交理由替代强度 3 分、价格或配置冲击 2 分、场景心智迁移 1 分、市场分流验证 1 分、置信修正 -1 到 +1。
  - 主压力类型只选一个；辅助压力类型最多两个。
  - 支持 `value_substitution`、`price_suppression`、`configuration_benchmark`、`scenario_mindshare`、`brand_ecosystem`、`downtrade_diversion`、`uptrade_alternative` 和低压复核兜底。
  - 低于 5/10 或锚点 pair scoring 被阻断时，`strong_pressure_allowed=false`，不得输出强替代话术。
  - 本任务未接入综合分、Top 3 排序或报告渲染；旧 `_replacement_pressure()` 的替换留给 CA-G04/CA-G05。
- 测试：
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py -q`：5 passed, 1 warning。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py -q`：5 passed, 1 warning。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py -q`：6 passed, 12 warnings。
  - `apps/api-server/.venv/bin/python -m pytest apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_profile.py -q`：14 passed, 204 warnings。
  - `apps/api-server/.venv/bin/python -m compileall apps/api-server/app/services/core3_real_data/analyst/replacement_pressure.py apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py`：通过。
- 下一个任务：CA-G04 综合分和 Top 3 选择门槛。
