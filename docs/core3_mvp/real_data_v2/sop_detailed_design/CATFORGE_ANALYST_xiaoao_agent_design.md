# CatForge Analyst 与小奥家电市场分析专家详细设计

## 1. 设计目标

本文把 [CatForge Analyst 与小奥家电市场分析专家需求](../sop_requirements/CATFORGE_ANALYST_xiaoao_agent_requirements.md) 转换为工程设计。

核心设计目标：

1. `catforge_analyst` 同时支持原子分析能力和 SOP 编排能力。
2. 小奥 Skill 可以稳定路由常见问题，也能组合原子能力处理开放问题。
3. 小奥 Agent 只负责业务表达，不直接绕过 CLI 做数据库分析。
4. 所有复合分析都能输出中间步骤、证据、限制和可复核的结构化 JSON。
5. 小奥最终回答必须是业务专家语言，不暴露 CLI、Mxx 模块、内部代码、字段名、批次号、JSON、命令或调试错误。

## 2. 模块边界

### 2.1 本模块负责

- 定义和实现 `catforge_analyst` CLI。
- 复用 `catforge_insight` 查询能力和 M00-M11D 结果。
- 实现原子分析能力注册表。
- 实现高频 SOP 编排能力。
- 生成小奥 Skill 和 Agent 需要消费的结构化分析包。
- 提供自然语言路由 `ask`，但不把复杂计算交给 LLM。

### 2.2 本模块不负责

- 不生成或修改 M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D 结果。
- 不直接读取原始四张表得出业务结论。
- 不调用 LLM 做确定性计算。
- 不替代小奥 Agent 生成最终长文回答。
- 不处理广告、库存、促销等当前缺数据的因果分析。

## 3. 总体架构

```text
OpenClaw 用户问题
  -> 小奥 Agent
  -> xiaoao-home-appliance-market-analysis Skill
  -> catforge_analyst ask / sop / atom
       -> AnalystRouter
       -> AbilityRegistry
       -> AtomicHandlers
       -> SopOrchestrators
       -> InsightClient / RepositoryReaders
  -> catforge_insight
  -> M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D
```

工程上新增：

```text
apps/api-server/app/cli/catforge_analyst.py
apps/api-server/app/services/core3_real_data/analyst/
  __init__.py
  ability_registry.py
  analyst_schemas.py
  analyst_repository.py
  analyst_service.py
  atomic_handlers.py
  sop_orchestrators.py
tools/openclaw/skills/xiaoao-home-appliance-market-analysis/SKILL.md
tools/openclaw/agents/xiaoao-home-appliance-market-analyst/AGENTS.md
```

## 4. CLI 结构

`catforge_analyst` 采用一个 CLI、多类子命令。

```bash
python -m app.cli.catforge_analyst ask "海信 65E7Q 的竞品是谁" --format json
```

原子能力：

```bash
python -m app.cli.catforge_analyst resolve-sku --query 65E7Q --product-category tv --format json
python -m app.cli.catforge_analyst sku-fact-brief --query 65E7Q --product-category tv --format json
python -m app.cli.catforge_analyst same-size-price-candidates --query 65E7Q --product-category tv --format json
python -m app.cli.catforge_analyst semantic-overlap --sku-code TV00029112 --candidate-sku-code TV00030247 --format json
python -m app.cli.catforge_analyst sales-overlap --sku-code TV00029112 --candidate-sku-code TV00030247 --format json
python -m app.cli.catforge_analyst param-claim-overlap --sku-code TV00029112 --candidate-sku-code TV00030247 --format json
python -m app.cli.catforge_analyst comment-support --sku-code TV00029112 --format json
python -m app.cli.catforge_analyst semantic-dimension-space --dimension-type battlefield --dimension-code BF_PREMIUM_PICTURE_UPGRADE --format json
python -m app.cli.catforge_analyst opportunity-gaps --sku-code TV00029112 --format json
```

SOP 编排：

```bash
python -m app.cli.catforge_analyst competitor-set --query 65E7Q --product-category tv --format json
python -m app.cli.catforge_analyst why-sales-diff --sku-code TV00029112 --competitor-sku-code TV00030247 --format json
python -m app.cli.catforge_analyst premium-claim-drivers --query 65E7Q --product-category tv --format json
python -m app.cli.catforge_analyst battlefield-space --dimension-code BF_PREMIUM_PICTURE_UPGRADE --format json
python -m app.cli.catforge_analyst battlefield-opportunity --query 65E7Q --product-category tv --format json
python -m app.cli.catforge_analyst sku-business-brief --query 65E7Q --product-category tv --format json
```

## 5. 通用输出 schema

所有命令输出统一结构：

```json
{
  "status": "ok",
  "command": "competitor-set",
  "question_type": "competitor_set",
  "project_id": "d8d2245b-358b-4a64-95cc-9d7f2341bd26",
  "category_code": "TV",
  "product_category": "TV",
  "batch_id": "m00_...",
  "analysis_population": "fact_complete_with_comment",
  "market_window": "full_observed_window",
  "target": {},
  "sop_steps": [],
  "atoms_used": [],
  "result": {},
  "evidence": [],
  "limitations": [],
  "answer_outline": []
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `status` | `ok`、`ambiguous`、`not_found`、`unsupported`、`error`。 |
| `question_type` | 业务问题类型。 |
| `target` | 目标 SKU、品牌、型号、尺寸、价格带。 |
| `sop_steps` | SOP 每一步输入、输出、证据和状态。 |
| `atoms_used` | 调用过的原子能力 code 和摘要。 |
| `result` | 当前命令核心结果。 |
| `evidence` | evidence id、来源模块、字段、说明。 |
| `limitations` | 数据口径、缺失、不能推出的结论。 |
| `answer_outline` | 给 Agent 的中文回答提纲。 |

## 6. 能力注册表设计

`AbilityRegistry` 用 YAML/JSON 或 Python 常量维护，禁止散落在 prompt 中。

能力定义：

```json
{
  "code": "same-size-price-candidates",
  "type": "atom",
  "description_cn": "按同尺寸、同价格带和邻近价格带找候选 SKU",
  "intent_examples": ["这款电视和谁竞争", "同价位竞品"],
  "required_inputs": ["sku_code"],
  "optional_inputs": ["product_category", "batch_id", "price_band_expand"],
  "required_sources": ["M07", "M11D"],
  "output_keys": ["candidate_skus", "pool_summary", "limitations"],
  "limitations": ["只基于当前批次和市场窗口"]
}
```

SOP 能力定义：

```json
{
  "code": "competitor-set",
  "type": "sop",
  "intent_examples": ["竞品是谁", "和谁竞争"],
  "steps": [
    "resolve-sku",
    "same-size-price-candidates",
    "semantic-overlap",
    "param-claim-overlap",
    "sales-overlap"
  ],
  "fallback_atoms": ["semantic-dimension-space"],
  "unsupported_conditions": []
}
```

## 7. 原子能力详细设计

### 7.1 `resolve-sku`

输入：

- `query`
- `sku_code`
- `product_category`
- `batch_id`

数据源：

- M07 市场画像。
- M03B 参数画像。
- M04C 卖点画像。
- M05C 评论画像。
- M11D allocation。

规则：

1. 如果输入是 SKU code，精确匹配。
2. 如果输入是型号，先 exact，再包含匹配。
3. 同型号多品牌或多 SKU 时返回 `ambiguous`。
4. 返回候选时包含品牌、型号、尺寸、价格带、是否有 M11D allocation。

输出：

- `resolved_sku`
- `candidates`
- `ambiguity_reason`

### 7.2 `sku-fact-brief`

输入：

- `sku_code` 或 `query`

数据源：

- M03B 参数画像。
- M04C 卖点事实画像。
- M05C 评论事实画像。
- M07 市场画像。
- M09C 用户任务画像。
- M10C 目标客群画像。
- M11C 价值战场画像。
- M11D 销量分配。

输出：

- `sku_identity`
- `param_summary`
- `claim_summary`
- `comment_summary`
- `market_summary`
- `user_task_summary`
- `target_group_summary`
- `battlefield_summary`
- `sales_allocation_summary`
- `evidence`
- `limitations`

### 7.3 `same-size-price-candidates`

输入：

- `sku_code`
- `price_band_expand`: 默认 `adjacent`
- `max_candidates`: 默认 30

数据源：

- M07 市场画像。
- M03B 尺寸事实。
- M11D included population。

规则：

1. 优先 exact screen size。
2. 次优先 M03B 五档尺寸 `size_tier`。
3. 价格优先同 `price_band_in_size_tier`。
4. 可扩展邻近价格带。
5. 输出候选分桶：
   - `same_size_same_price_band`
   - `same_size_adjacent_price_band`
   - `same_tier_same_price_band`
   - `same_tier_adjacent_price_band`
6. 销量接近只作为展示字段，不作为候选优先级第一依据。

输出候选字段：

- `sku_code`
- `brand_name`
- `model_name`
- `screen_size`
- `size_tier`
- `price_band_in_size_tier`
- `weighted_price`
- `avg_weekly_sales_volume`
- `candidate_bucket`

### 7.4 `semantic-overlap`

输入：

- `sku_code`
- `candidate_sku_codes`

数据源：

- M09C scores。
- M10C scores。
- M11C scores。
- M11D allocation。

规则：

1. 分别计算用户任务、目标客群、价值战场重合。
2. 主关系重合权重大于辅关系，辅关系大于用户观察。
3. 输出重合项、关系状态、allocation weight、score。
4. 三层结果分别输出，不跨层相加。

输出：

- `user_task_overlap`
- `target_group_overlap`
- `battlefield_overlap`
- `semantic_overlap_score`
- `shared_primary_dimensions`

### 7.5 `sales-overlap`

输入：

- `sku_code`
- `candidate_sku_code`

数据源：

- M01 clean weekly market rows。
- M07 市场画像。

规则：

1. 只使用两 SKU 都在售的重叠周。
2. 计算重叠周周均销量、周均销额、均价。
3. 计算平台覆盖差异。
4. 累计销量只展示，不参与输赢判断。
5. 若重叠周不足，输出样本不足风险。

输出：

- `overlap_week_count`
- `target_avg_weekly_sales_volume`
- `candidate_avg_weekly_sales_volume`
- `target_avg_weekly_sales_amount`
- `candidate_avg_weekly_sales_amount`
- `target_win_rate_by_week`
- `price_gap`
- `platform_overlap`
- `sample_status`

### 7.6 `param-claim-overlap`

输入：

- `sku_code`
- `candidate_sku_codes`

数据源：

- M03B 参数画像。
- M04C 卖点事实画像。
- 标准参数/标准卖点 taxonomy。

规则：

1. 比较核心参数和关键档位。
2. 比较卖点事实和卖点位置。
3. 标记目标 SKU 独有、竞品独有、共同具备、双方缺失。
4. 缺失按 unknown 处理，不能直接当 false，除非对应 taxonomy 明确缺失判否。

输出：

- `shared_params`
- `target_param_advantages`
- `candidate_param_advantages`
- `shared_claims`
- `target_claim_advantages`
- `candidate_claim_advantages`
- `unknown_or_review_required`

### 7.7 `comment-support`

输入：

- `sku_code`
- 可选 `claim_code`、`param_code`、`task_code`、`target_group_code`、`battlefield_code`

数据源：

- M05C 评论事实画像。
- M05C 维度 coverage。

规则：

1. 评论正向优先解释用户选择。
2. 评论负向表示未满足需求或拖后腿。
3. 品牌信任/复购是品牌力，不单独等同目标客群。
4. 服务履约、物流安装、售后作为服务风险，不进入产品价值战场。

输出：

- `positive_support`
- `negative_support`
- `neutral_context`
- `evidence_sentences`
- `service_context`

### 7.8 `semantic-dimension-space`

输入：

- `dimension_type`: `user_task`、`target_group`、`battlefield`
- `dimension_code`
- 可选品牌、尺寸、价格带过滤。

数据源：

- M11D dimension summary。
- M11D contributions。
- M11D allocations。

输出：

- `dimension_summary`
- `top_skus`
- `brand_distribution`
- `size_price_distribution`
- `estimated_sales_volume`
- `estimated_avg_weekly_sales_volume`
- `estimated_sales_amount`
- `estimated_avg_weekly_sales_amount`
- `allocation_coverage_rate`

### 7.9 `opportunity-gaps`

输入：

- `sku_code`

数据源：

- M11C score/profile。
- M11D allocation。
- M03B/M04C/M05C/M07。

规则：

1. 读取当前主/辅战场。
2. 读取机会战场、用户观察战场、拖后腿战场。
3. 对每个候选战场拆解：
   - 价格/尺寸门槛。
   - 参数缺口。
   - 卖点缺口。
   - 评论支持或负向。
   - 市场验证。
4. 输出动作建议，但必须标明是假设性策略，不是预测。

输出：

- `current_battlefields`
- `opportunity_battlefields`
- `user_observed_needs`
- `drag_factors`
- `gap_breakdown`
- `action_candidates`

## 8. SOP 编排详细设计

### 8.1 `competitor-set`

步骤：

1. `resolve-sku`
2. `sku-fact-brief`
3. `same-size-price-candidates`
4. 对候选调用 `semantic-overlap`
5. 对前 N 个候选调用 `param-claim-overlap`
6. 对前 N 个候选调用 `sales-overlap`
7. 分桶和排序

排序原则采用分层排序，不采用简单加权一把算：

1. 候选桶优先级：
   - same exact size + same price band
   - same exact size + adjacent price band
   - same size tier + same price band
   - same size tier + adjacent price band
2. 同桶内再按：
   - 价值战场重合。
   - 用户任务/目标客群重合。
   - 参数/卖点重合。
   - 重叠周周均销量接近或强弱。

输出：

- `direct_competitors`
- `price_pressure_competitors`
- `uptrade_alternatives`
- `downgrade_alternatives`
- `excluded_candidates`
- `sop_steps`
- `limitations`

### 8.2 `why-sales-diff`

步骤：

1. `resolve-sku` 解析目标和竞品。
2. `sales-overlap` 判断重叠周表现。
3. `semantic-overlap` 判断任务/客群/战场重合与差异。
4. `param-claim-overlap` 判断产品能力和卖点差异。
5. `comment-support` 判断用户声音差异。
6. 形成原因分组。

原因分组：

- `price_and_position_reasons`
- `semantic_market_reasons`
- `param_reasons`
- `claim_reasons`
- `comment_reasons`
- `channel_reasons`
- `not_supported_reasons`

必须输出：

- 使用重叠周周均销量/销额。
- 样本充分性。
- 不能判断的因素。

### 8.3 `premium-claim-drivers`

步骤：

1. `sku-fact-brief`
2. 读取 M04C claim facts。
3. 读取 M11D allocation 中权重最高的任务/客群/战场。
4. 读取 M09C/M10C/M11C score breakdown 中的 claim evidence。
5. 读取 M05C comment support。
6. 读取 M07 价格带和同池表现。
7. 分类卖点。

分类规则：

| 类型 | 判定 |
| --- | --- |
| `premium_driver` | 高价带或高 ASP，卖点支撑主/辅高价值维度，并有评论或参数验证。 |
| `sales_driver` | 支撑 M11D 高权重维度，有评论或市场验证。 |
| `basic_support` | 支撑购买但同池普遍具备，不能解释溢价。 |
| `brand_claim_only` | 厂家有声明，参数或评论支撑不足。 |
| `drag_factor` | 评论负向或参数不足，影响用户需求满足。 |

### 8.4 `battlefield-space`

步骤：

1. 解析 dimension code 或自然语言 battlefield name。
2. 调用 `semantic-dimension-space`。
3. 如有品牌、尺寸、价格带限制，在 M11D contributions 上过滤。
4. 输出空间摘要、Top SKU、品牌结构、尺寸价格结构。

说明：

- 默认使用 M11D `fact_complete_with_comment`。
- 输出的是估算解释销量。
- 一个 SKU 可出现在多个战场，但在战场维度内 allocation weight 闭合。

### 8.5 `battlefield-opportunity`

步骤：

1. `sku-fact-brief`
2. `opportunity-gaps`
3. 对目标机会战场调用 `semantic-dimension-space`
4. 找该战场 Top SKU 和直接竞品。
5. 形成行动建议。

输出：

- `current_position`
- `target_opportunities`
- `required_changes`
- `expected_battlefield_effect`
- `market_space_reference`
- `risk_and_limits`

### 8.6 `sku-business-brief`

步骤：

1. `resolve-sku`
2. `sku-fact-brief`
3. `same-size-price-candidates`
4. `semantic-dimension-space` 查询目标主战场/主客群/主任务。
5. 汇总业务结论。

输出：

- `one_sentence_summary`
- `core_position`
- `key_strengths`
- `key_weaknesses`
- `market_context`
- `competitor_context`
- `next_questions`

## 9. `ask` 路由设计

`ask` 分三层：

1. 固定 SOP 命中。
2. 原子能力组合。
3. 不支持边界回答。

路由规则：

| 用户意图 | 命令 |
| --- | --- |
| 竞品、和谁竞争 | `competitor-set` |
| 为什么 A 比 B 卖得好/差 | `why-sales-diff` |
| 溢价卖点、用户选择理由 | `premium-claim-drivers` |
| 战场空间、某战场有哪些 SKU | `battlefield-space` 或 `semantic-dimension-space` |
| 能不能进入更多战场 | `battlefield-opportunity` |
| 综合画像 | `sku-business-brief` |
| 单点事实 | 转交 `catforge_insight ask` |
| 数据准备/重跑 | 转交 `catforge_pipeline ask` |

开放问题路由：

1. 抽取对象：品牌、型号、尺寸、价格带、维度名。
2. 抽取问题类型：表现、对比、空间、机会、原因。
3. 从能力注册表选择原子能力。
4. 输出 `analysis_plan`。
5. 执行原子能力。
6. 生成结构化结果。

如果缺数据：

```json
{
  "status": "unsupported",
  "unsupported_reason_code": "missing_ad_inventory_data",
  "message_cn": "当前没有广告、流量、库存数据，不能直接测算投放带来的销量增长。",
  "alternative_analysis": ["可用战场空间和当前 SKU 份额做情景假设。"]
}
```

## 10. Skill 设计

Skill 路径：

```text
tools/openclaw/skills/xiaoao-home-appliance-market-analysis/SKILL.md
```

Skill 内容结构：

1. 角色：小奥家电市场分析专家的工具使用规则。
2. 工作目录：`/opt/catforge`。
3. 优先命令：
   - `catforge_analyst` 用于复合分析。
   - `catforge_insight` 用于事实查询。
   - `catforge_pipeline` 用于执行重跑。
4. 固定 SOP 路由表。
5. 开放问题原子能力组合规则。
6. 边界回答规则。
7. 回答格式。
8. 禁止事项。

Skill 必须要求：

- 每次业务结论前先调用 CLI。
- 竞品列表问题优先调用 `catforge_analyst competitor-set --format text`，直接使用稳定业务文本，不再让智能体二次解析 JSON。
- CLI 返回 `ambiguous` 时，必须要求用户确认 SKU。
- CLI 返回 `unsupported` 时，必须说明数据缺口。
- 不允许把 `estimated_sales_volume` 说成真实归因。
- 不允许把 `sales_volume_total` 当作销量胜负判断。
- 不允许把工具错误、命令失败、JSON 解析错误、shell 片段或 stdout/stderr 原文暴露给用户。
- 普通业务问题不得出现 CatForge、CLI、OpenClaw、Mxx、BF/TG/TASK 代码、批次号、字段名或程序路径。
- 竞品问题默认按业务优先级给三款重点竞品：最直接竞品、价格贴身竞品、分流/替代竞品；不说“CLI 返回顺序”或“SOP 候选顺序”。
- 第一句话必须直接回答业务问题，不用“数据完整”“下面是回答”等工具状态开场，不用 emoji 排名，不展示未翻译的英文价格带。
- 禁止为竞品列表问题写临时 Python、jq、grep、sed、awk 或 shell 管道解析 JSON。

## 11. Agent 设计

Agent 路径：

```text
tools/openclaw/agents/xiaoao-home-appliance-market-analyst/AGENTS.md
```

Agent prompt 必须包含：

```text
你是小奥家电市场分析专家。
你面向业务用户回答彩电、空调等家电市场问题。
用户不需要知道 M00/Mxx。
你必须先调用 CatForge CLI 获取事实或分析包，再组织业务答案。
最终答案必须是市场分析师语言，不输出工具运行记录或内部代码。
```

Agent 回答结构：

1. 结论。
2. 判断依据。
3. 分析过程。
4. 口径与限制。
5. 下一步可验证动作。

Agent 禁止：

- 直接输出数据库凭据。
- 未调用 CLI 直接编结论。
- 把 M11D 解释销量当真实购买因果。
- 把累计销量当输赢依据。
- 把服务履约当产品价值战场。
- 把工具错误、命令失败、JSON 解析错误或 shell 输出贴给用户。
- 用“根据 CatForge CLI/SOP/Mxx 模块”作为业务回答依据。
- 在聊天场景输出宽表格；优先使用结论段和编号列表。
- 用“数据完整”“已查询到”“下面是回答”等工具口吻开场，或输出 emoji 排名、英文价格带标签。
- 为竞品列表问题写临时脚本或管道解析 JSON；应直接使用稳定文本输出。

## 12. 数据访问设计

优先复用现有服务和 CLI 查询逻辑，避免重复 SQL。

推荐实现方式：

1. `AnalystRepository` 读取必要结果表。
2. 对已在 `catforge_insight` 中稳定实现的查询，可直接复用其函数，而不是重新写 SQL。
3. 对跨 SKU 的高频计算，放在 `AnalystService`。
4. 对格式化和路由，放在 CLI 层。

核心读取对象：

| 数据 | 来源 |
| --- | --- |
| SKU identity、价格、尺寸、周均销量 | M07 + M01 clean weekly |
| 参数事实 | M03B |
| 卖点事实 | M04C |
| 评论事实 | M05C |
| 用户任务 | M09C |
| 目标客群 | M10C |
| 价值战场 | M11C |
| 图谱和销量分配 | M11D |

## 13. 测试设计

### 13.1 单元测试

每个原子能力至少测试：

- 正常 SKU。
- SKU 不存在。
- SKU 模糊匹配。
- 上游结果缺失。
- 空结果。

每个 SOP 至少测试：

- 正常输出。
- 中间原子能力部分缺失。
- 不支持问题。
- 累计销量不参与判断。

### 13.2 集成测试

205 当前批次用海信 65 寸 SKU 验收：

- `65E7Q`
- `65E3Q`

固定问题：

- 竞品是谁。
- 为什么卖得好/差。
- 哪些卖点支撑选择。
- 哪些是溢价卖点。
- 战场空间。
- 能否进入更多战场。

开放问题：

- 品牌在某战场表现。
- 某尺寸价格带内哪个任务空间更大。
- 无广告数据时如何回答投放问题。

### 13.3 快照测试

对 `catforge_analyst` JSON 输出建立快照，固定字段：

- `status`
- `command`
- `sop_steps[].step_code`
- `atoms_used[].ability_code`
- `result` 顶层结构
- `limitations`

不固定会随数据变化的销量数值，只校验字段存在和口径。

## 14. 性能和运行约束

- `catforge_analyst` 默认只读。
- 不调用 LLM。
- 不跑全量重计算。
- 单次命令默认候选数不超过 50。
- 大结果通过 `--sku-limit`、`--candidate-limit` 控制。
- 查询 M11D 图谱优先读 summary/contribution，不读取完整 graph_json。

## 15. 部署和安装

开发完成后：

1. 推送 GitHub。
2. 205 `git pull`。
3. 如果 API 容器未挂载源码，热修 `docker cp` 或重建镜像。
4. 在 205 安装小奥 Skill。
5. 在 205 安装小奥 Agent 文档。
6. 用 OpenClaw 直接提问验收。

## 16. 开发顺序

建议小步开发：

1. `catforge_analyst` CLI 框架和 `resolve-sku`。
2. `sku-fact-brief`、`semantic-dimension-space`。
3. `same-size-price-candidates`、`semantic-overlap`、`sales-overlap`。
4. `param-claim-overlap`、`comment-support`、`opportunity-gaps`。
5. `competitor-set`、`sku-business-brief`。
6. `why-sales-diff`。
7. `premium-claim-drivers`。
8. `battlefield-space`、`battlefield-opportunity`。
9. `ask` 路由。
10. 小奥 Skill。
11. 小奥 Agent。

每完成一个阶段必须运行相关单元测试和至少一个 205 smoke test。

## 17. 待评审问题

1. `competitor-set` 是否需要限制最多输出 3 个直接竞品，还是保留直接/压力/替代各 3 个。
2. `premium-claim-drivers` 中“溢价”是否必须要求价格带为 `mid_high/high`，还是允许同价带内 ASP 高于中位数即算。
3. 开放问题的 `analysis_plan` 是否需要返回给用户，还是仅保留在 JSON 中供调试。
4. 小奥 Agent 是否默认隐藏模块名，还是在“依据”里展示 M03B/M04C/M11D 等来源。
