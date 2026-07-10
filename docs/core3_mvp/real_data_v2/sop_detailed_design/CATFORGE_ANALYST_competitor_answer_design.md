# CatForge Analyst 竞品问答 CLI 与小奥 Skill 详细设计

## 1. 设计目标

本文承接 [CatForge Analyst 竞品问答 CLI 与小奥 Skill 需求](../sop_requirements/CATFORGE_ANALYST_competitor_answer_requirements.md)，定义 `catforge_analyst` 竞品问答的工程实现方案。

设计目标：

1. 消费已发布 M12D `SKU成交理由画像`，不在竞品问答链路中生成 M12D。
2. 把竞品排序从“通用相似度”升级为“购买池 + 主辅语义重合 + 关键价值锚点可替代性 + 替代压力 + 市场验证”。
3. 由 CLI 生成最终聊天摘要，避免 OpenClaw 解析大 JSON 后改写答案。
4. 由 CLI 生成飞书卡片看板 payload，让飞书会话主回答直接展示 Top 3、重合结构和证据入口。
5. 由 CLI 生成飞书详细报告，报告作为看板的佐证层，而不是主回答展现内容。
6. Skill 只做路由、边界处理、卡片发送和降级转发，不做竞品计算或卡片拼装。
7. 所有测试不调用外部 LLM，不依赖真实飞书 API。

## 2. 总体架构

```text
用户问题
  -> 小奥 Skill
  -> catforge_analyst competitor-set
       -> SKUResolver
       -> PurchaseReasonProfileReader
       -> CompetitorCandidateBuilder
       -> RoleWeightedOverlapScorer
       -> ValueAnchorMatcher
       -> ReplacementPressureClassifier
       -> MarketValidationService
       -> ClaimValueEvidenceAssembler
       -> CompetitorSelectionService
       -> CompetitorAnswerRenderer
       -> CompetitorDashboardPayloadBuilder
       -> FeishuCardRenderer
       -> CompetitorReportRenderer
       -> FeishuReportPublisher
  -> short_answer + dashboard_payload + feishu_card_payload + report_url
```

职责边界：

| 模块 | 职责 |
| --- | --- |
| Skill | 识别竞品意图，调用 CLI；飞书入口传入 `message_id` 和 `--feishu-card-only`，把卡片发送状态原样作为可见回复。 |
| CLI | 参数解析、调用服务、输出 text/json；非卡片入口输出 `short_answer`，飞书入口优先输出卡片发送状态。 |
| PurchaseReasonProfileReader | 读取已发布 M12D `SKU成交理由画像`，为目标和候选 SKU 提供核心成交理由、关键价值锚点和证据强度；不生成 M12D。 |
| CandidateBuilder | 生成购买池候选和扩展候选。 |
| OverlapScorer | 计算价值战场、用户任务、目标客群的主辅加权重合。 |
| ValueAnchorMatcher | 消费目标和候选的 M12D 画像，计算 pair 级关键价值锚点可替代性和成交理由替代强度。 |
| PressureClassifier | 消费购买池、语义重合、关键价值锚点可替代性、价格/配置冲击和市场验证，判断竞品角色和替代压力。 |
| ClaimValueEvidenceAssembler | 读取目标和候选 SKU 的 M12C 卖点价值量化，形成报告可直接展示的业务卖点标签、可比产品价格/销量差异、本品可解释价差/销量差份额、竞品拦截、补强建议和拖后腿卖点。 |
| SelectionService | 汇总分数、排序、分桶、Top 3 选择。 |
| AnswerRenderer | 生成 600 字以内业务摘要。 |
| DashboardPayloadBuilder | 把 Top 3 结果裁剪成会话看板 payload，固定包含竞品角色、重合结构、价值锚点、市场验证和证据链接。 |
| FeishuCardRenderer | 把 `dashboard_payload` 渲染成飞书卡片 JSON 2.0 或卡片模板变量；不做竞品计算。 |
| ReportRenderer | 生成飞书 Markdown 报告内容。 |
| FeishuReportPublisher | 创建飞书文档并返回链接；测试中用 mock。 |

这不是新写一套竞品排序程序。M12D 是独立前置资产，用于把每个 SKU 的成交理由先结构化；`competitor-set` 只消费已发布 M12D，并负责候选选择、pair 评分、Top 3 排序、看板和报告输出。

## 3. CLI 接口设计

### 3.1 参数

增强现有 `competitor-set`：

```bash
python -m app.cli.catforge_analyst competitor-set \
  --query "海信 65E7Q" \
  --product-category tv \
  --batch-id latest \
  --limit 10 \
  --format json \
  --answer-style xiaoao \
  --with-report feishu-doc
```

新增参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--answer-style` | `raw` | `raw` 保持当前结构；`xiaoao` 生成业务摘要与展示策略。 |
| `--with-report` | `none` | `none` 不生成报告；`markdown` 返回报告 markdown；`feishu-doc` 创建飞书文档。 |
| `--top-n` | `3` | 聊天摘要展示竞品数，默认 3。 |
| `--max-chat-chars` | `600` | 短摘要字符上限。 |
| `--report-title` | 自动生成 | 可覆盖飞书文档标题。 |

保留：

- `--format json`
- `--format text`
- `--query`
- `--sku-code`
- `--model-name`
- `--product-category`
- `--batch-id`
- `--limit`

### 3.2 text 输出

当 `--format text --answer-style xiaoao` 且没有飞书卡片发送结果时，stdout 只输出：

```text
{short_answer}
```

当同一次调用包含 `feishu_card_delivery` 时，stdout 优先输出卡片发送状态；`--feishu-card-only` 下缺少发送结果也必须输出“未发送飞书竞品看板卡片：缺少发送结果。”，不得退回短摘要掩盖问题。

不得输出命令提示、debug 文本、JSON、stderr 内容或内部字段。

### 3.3 JSON 输出

JSON 中保留结构化分析，供调试、验收和飞书卡片发送使用。

```json
{
  "status": "ok",
  "command": "competitor-set",
  "target": {
    "brand_name": "海信",
    "model_name": "65E7Q",
    "sku_code": "..."
  },
  "result": {
    "competitor_set": {
      "candidate_count": 10,
      "candidates": []
    },
    "competitor_answer": {
      "short_answer": "...",
      "report_url": "https://...",
      "report_status": "created",
      "dashboard_payload": {},
      "feishu_card_payload": {},
      "top_competitors": [],
      "candidate_buckets": {
        "primary_direct": [],
        "strong_direct": [],
        "price_adjacent": [],
        "downtrade_diversion": [],
        "uptrade_alternative": [],
        "scenario_alternative": [],
        "excluded": []
      },
      "display_policy": {
        "send_short_answer_as_is": true,
        "prefer_feishu_card": true,
        "card_delivery_stdout": true,
        "fallback_to_short_answer": false,
        "max_chat_chars": 600,
        "hide_internal_fields": true
      }
    }
  },
  "limitations": []
}
```

## 4. 候选池设计

### 4.1 购买池分层

`CompetitorCandidateBuilder` 先按购买池找候选。

| 层级 | 条件 | 角色倾向 |
| --- | --- | --- |
| P0 | 同精确尺寸 + 同价格带 | 首选直接 / 强直接 |
| P1 | 同精确尺寸 + 邻近价格带 | 直接 / 价格贴身 / 下探或上探 |
| P2 | 同 M03B 五档尺寸段 + 同价格带 | 场景替代 / 直接补充 |
| P3 | 同 M03B 五档尺寸段 + 邻近价格带 | 场景替代 / 下探 / 上探 |
| P4 | 战场强重合但尺寸或价格偏离 | 战略参考，不优先入 Top 3 |

购买池得分建议：

| 条件 | `purchase_pool_score` |
| --- | ---: |
| 同精确尺寸 + 同价格带 | 1.00 |
| 同精确尺寸 + 邻近价格带 | 0.85 |
| 同尺寸档 + 同价格带 | 0.70 |
| 同尺寸档 + 邻近价格带 | 0.55 |
| 战场强重合但购买池偏离 | 0.35 |

P0/P1 是 Top 3 的主要来源。P2/P3 只能在语义替代性很强时进入 Top 3。P4 默认进入报告候选或战略参考。

### 4.2 价格差分桶

相对目标 SKU 均价：

| 价差 | 业务解释 |
| --- | --- |
| `abs(diff) <= 8%` | 价格贴身，用户容易同屏比较。 |
| `8% < abs(diff) <= 15%` | 同预算层级，存在明显价格压力。 |
| `-30% <= diff < -15%` | 下探分流，吸走预算敏感用户。 |
| `15% < diff <= 35%` | 上探替代，吸走高预算用户。 |
| `abs(diff) > 35%` | 一般不作为直接竞品，除非语义场景极强。 |

价格差只定义购买池和替代压力，不单独决定排序。

## 5. 主辅加权重合算法

### 5.1 关系权重

把每个 SKU 的价值战场、用户任务、目标客群转为 `{code: role_weight}`。

| 状态 | 权重 |
| --- | ---: |
| `primary_*` | 1.00 |
| `secondary_*` | 0.75 |
| `comment_observed_*` / `user_observed_*` | 0.45 |
| `opportunity_*` / `latent_*` | 0.35 |
| `brand_claimed_*` | 0.25 |
| `unmet_*` / `drag_factor_*` | -0.30 |
| `excluded` / `not_supported` | 0 |

### 5.2 Weighted Jaccard

对目标 SKU 与候选 SKU 的同一维度计算加权 Jaccard：

```text
positive_weight(code) = max(role_weight(code), 0)
intersection = sum(min(target_weight[code], candidate_weight[code]))
union = sum(max(target_weight[code], candidate_weight[code]))
weighted_overlap = intersection / union
```

拖后腿和未满足单独计算风险：

```text
risk_overlap = count(common_negative_codes) / max(1, target_positive_code_count)
```

最终维度结果：

```json
{
  "weighted_overlap": 0.72,
  "primary_hit_count": 1,
  "secondary_hit_count": 2,
  "target_primary_hit_candidate_role": "secondary",
  "candidate_primary_hit_target_role": "secondary",
  "risk_overlap": 0.0,
  "matched_codes": []
}
```

### 5.3 维度权重

竞品排序中三类语义重合建议权重：

| 维度 | 权重 |
| --- | ---: |
| 价值战场加权重合 | 0.30 |
| 用户任务加权重合 | 0.20 |
| 目标客群加权重合 | 0.20 |

价值战场权重最高，因为它结合了尺寸价格、任务、客群、卖点和评论验证，是竞品比较的主语境。

## 6. 已发布 M12D 消费与价值锚点匹配

M12D 的生成、验证、全量发布见独立文档：

- [M12D SKU成交理由画像需求](../sop_requirements/M12D_sku_purchase_reason_profile_requirements.md)
- [M12D SKU成交理由画像详细设计](M12D_sku_purchase_reason_profile_design.md)

竞品分析智能体只读取已发布 M12D，不在 `competitor-set` 中生成或修正 M12D。

### 6.1 M12D 读取契约

`PurchaseReasonProfileReader` 按以下键读取画像：

```text
category_code + project_id + batch_id + m12d_profile_version + sku_code
```

读取结果必须包含：

| 字段 | 用途 |
| --- | --- |
| `status` | 判断画像是否可消费。 |
| `core_reasons_cn` | 报告展示目标和竞品成交理由。 |
| `core_payment_anchors` | 作为目标核心锚点覆盖计算的基准。 |
| `supporting_anchors` | 作为辅助锚点覆盖。 |
| `weak_expression_anchors` | 只能作为弱表达，不得推高可替代性。 |
| `risk_drag_anchors` | 作为风险和扣分信号。 |
| `anchors[]` | 读取每个锚点的中文名、角色、证据强度、置信度和解释。 |
| `profile_confidence` | 决定 pair 级评分置信度。 |

缺失处理：

- 目标 SKU M12D 缺失或未发布：竞品分析返回“成交理由画像待生成/置信度不足”，不输出强排序结论。
- 候选 SKU M12D 缺失：该候选锚点可替代性降置信度；如候选依赖锚点替代进入 Top 3，应退出 Top 3 或标为需复核。
- `weak_expression` 不得被下游改写为 `core_payment`。
- 下游只能做 pair 级覆盖、替代、候选更强和目标独有判断，不得修改 M12D 原始角色。

### 6.2 pair 级关键价值锚点可替代性

`ValueAnchorMatcher` 读取目标和候选的 M12D 画像，按 15 分计算 `anchor_substitutability_score`：

```text
anchor_substitutability_score =
  target_core_anchor_coverage      # 0-5
  + evidence_parity                # 0-4
  + candidate_relative_advantage   # 0-3
  + scenario_task_audience_fit     # 0-2
  + market_comment_validation      # 0-1
  - penalties
```

匹配类型：

| match_type | 含义 |
| --- | --- |
| `exact_substitute` | 候选在目标核心锚点上形成同类替代，证据强度接近。 |
| `adjacent_substitute` | 候选覆盖相邻锚点或同一战场内的不同解释方式。 |
| `candidate_stronger` | 候选在目标核心锚点或关键场景上更强。 |
| `target_only` | 目标具备，候选无法替代。 |
| `candidate_only` | 候选具备，但不直接替代目标核心成交理由。 |
| `weak_expression` | 只有宣传文本、价格价值表达或位置标签，不能作为强替代证据。 |
| `unsupported` | 数据不足或证据冲突。 |

每个候选输出：

```json
{
  "anchor_substitutability_score": 12,
  "anchor_substitutability_level": "strong",
  "shared_core_anchors": ["高端画质", "游戏流畅"],
  "target_only_anchors": ["预算内配置获得感"],
  "candidate_stronger_anchors": ["家装融合"],
  "weak_expression_anchors": ["预算内配置获得感"],
  "match_details": [
    {
      "target_anchor_cn": "高端画质",
      "candidate_anchor_cn": "高端画质",
      "match_type": "exact_substitute",
      "score": 5,
      "evidence_comparison_cn": "双方都有参数和卖点支撑，候选评论验证略强。"
    }
  ],
  "anchor_substitution_summary_cn": "候选覆盖目标的高端画质和游戏流畅核心成交理由，但目标的预算价值表达证据较弱，只作为弱表达处理。"
}
```

短摘要只使用业务表达，不列长参数清单。若目标没有高置信 `core_payment` 锚点，短摘要必须改写为“当前成交理由画像不足，排序置信度降低”，不得用默认词补写“技术型高端体验”或“场景型高端体验”。

## 7. 替代压力评分与分类

`ReplacementPressureClassifier` 生成 pair 级替代压力。它不生成单 SKU 画像，也不重新计算关键价值锚点；它消费购买池、价格差、主辅语义重合、M12D 锚点可替代性、候选优势和市场验证，回答“这个候选会怎样影响目标 SKU 成交”。

### 7.1 替代压力 10 分评分

```text
replacement_pressure_score =
  purchase_pool_pressure       # 0-2
  + purchase_reason_pressure   # 0-3
  + price_or_config_impact     # 0-2
  + scenario_mindshare_shift   # 0-1
  + market_diversion_validation # 0-1
  + confidence_adjustment       # -1 to +1, capped
```

| 分项 | 来源 | 判断 |
| --- | --- | --- |
| `purchase_pool_pressure` | CandidateBuilder | 同尺寸同价带最高，尺寸或价格偏离则下降。 |
| `purchase_reason_pressure` | ValueAnchorMatcher | 直接使用关键价值锚点可替代性，目标核心锚点覆盖越高压力越强。 |
| `price_or_config_impact` | M03B/M07/M12C | 低价保核心锚点、同价更强配置、高价更强理由都会形成冲击。 |
| `scenario_mindshare_shift` | M09C/M10C/M11C/M05C | 候选是否把同类锚点转成更清晰的家庭、游戏、家装或长看场景。 |
| `market_diversion_validation` | MarketValidationService | 重叠在售周销量、销额和平台结构是否证明真实分流能力。 |
| `confidence_adjustment` | evidence completeness | 样本不足、仅厂家主张、服务信号过重或证据冲突时扣分。 |

### 7.2 压力类型选择

主压力类型只选一个，辅助压力类型最多两个。

| 压力类型 | 规则 |
| --- | --- |
| `value_substitution` 价值替代压力 | P0/P1 购买池，目标核心锚点可替代，战场/任务/客群综合高。 |
| `price_suppression` 价格压制压力 | 候选价格更低，且仍覆盖目标核心成交理由。 |
| `configuration_benchmark` 配置标杆压力 | 候选同价或相邻价位上参数/卖点更强，抬高用户配置预期。 |
| `scenario_mindshare` 场景心智压力 | 候选在目标关键场景中表达更清晰，例如客厅空间、游戏、家装融合、家庭长看。 |
| `brand_ecosystem` 品牌/生态压力 | 品牌心智、系统生态或渠道表达使其进入同一候选清单。 |
| `downtrade_diversion` 下探分流压力 | 用户降低预算后仍能满足部分核心需求。 |
| `uptrade_alternative` 上探替代压力 | 用户追加预算后获得更明确的高端理由。 |

### 7.3 竞品角色规则

| 角色 | 规则 |
| --- | --- |
| 首选直接竞品 | P0/P1 购买池，战场/任务/客群综合高，关键价值锚点可替代性强，替代压力高，市场验证有效。 |
| 强直接竞品 | P0/P1 购买池，语义和锚点强，但替代压力略低或角色偏配置标杆。 |
| 价格贴身竞品 | 价差极小，但语义或锚点重合明显弱于直接竞品。 |
| 下探分流竞品 | 价格明显更低，仍保留目标 SKU 部分核心锚点。 |
| 上探替代竞品 | 价格明显更高，品牌/配置/高端锚点能吸走高预算用户。 |
| 场景替代竞品 | 购买池偏离，但在目标核心场景中强替代。 |
| 排除候选 | 只满足局部相似，无法进入最终候选清单。 |

### 7.4 替代压力说明

每个 Top 3 候选必须输出：

```json
{
  "pressure_type": "value_substitution",
  "pressure_cn": "价值替代压力",
  "pressure_score": 8,
  "secondary_pressure_types": ["scenario_mindshare"],
  "business_reason_cn": "在同一 65 寸高价购买池中，承接目标 SKU 的高端画质、影院沉浸和家庭客厅体验支付理由。",
  "target_risk_cn": "如果目标 SKU 没有把技术优势转成用户可理解的场景价值，候选会削弱其溢价解释。",
  "score_breakdown": {
    "purchase_pool_pressure": 2,
    "purchase_reason_pressure": 3,
    "price_or_config_impact": 1,
    "scenario_mindshare_shift": 1,
    "market_diversion_validation": 1,
    "confidence_adjustment": 0
  }
}
```

## 8. 市场验证设计

`MarketValidationService` 使用重叠在售周数据。

输出字段：

```json
{
  "overlap_week_count": 24,
  "target_avg_weekly_sales": 251.0,
  "candidate_avg_weekly_sales": 216.6,
  "candidate_has_real_sales": true,
  "market_validation_level": "strong",
  "market_validation_cn": "候选在重叠在售周具备稳定成交，不是纸面相似 SKU。"
}
```

使用约束：

- 市场验证不直接决定首选竞品。
- 重叠周不足时降低置信度。
- 周均销量用于验证分流能力，累计销量仅可在报告附录展示。
- 如果候选销量极高但购买池或语义偏离，不得排入直接竞品。

## 9. 卖点价值证据设计

### 9.1 数据来源

竞品详细报告必须同时读取卖点事实画像、M12C 和 M12D：

- 卖点画像章节只展示 M04C/M05C/M09C-M11C 等事实与语义支撑：事实卖点、评论支持/反向、参数支撑、需复核表达和共同价值锚点。
- `sku-claim-value`：单 SKU 的 SKU×卖点价值角色、可比产品价格/销量/销额差异、本品可解释价差/销量差份额和置信度。
- `claim-contribution`：单 SKU 在价值战场、用户任务、目标客群等市场场景中的本品相对可比产品表现差异。
- `sku-purchase-reason-profile`：单 SKU 的核心成交理由、关键价值锚点、证据强度、弱表达和拖累标记。

`competitor-set` 在 `answer_style=xiaoao` 或 `with_report != none` 时，除 `sku-fact-brief` 外，还要为目标 SKU 和进入候选池的 SKU 拉取 M12C 与已发布 M12D 结果。M12C 查询失败或无数据不能阻断竞品集合生成，但报告必须展示“卖点价值量化待生成”。目标 SKU 的 M12D 缺失或未发布时，竞品问答必须降级或阻断，不得按需生成 M12D，也不得使用默认成交理由补写结论；候选 SKU 的 M12D 缺失时，该候选关键价值锚点可替代性降置信度或退出 Top 3。

### 9.2 卖点价值量化展示

报告不再生成“卖点溢价指数”这类单一分数。原因是单一分数容易让业务用户误解为“某个卖点绝对值多少钱”。报告改为展示两层量化：

1. 可比池卖点组差异：有卖点组与对照组在同尺寸、同价格带、同语义市场里的可观测价格/销量/销额差异。
2. 本品可解释价差/销量差份额：本品相对可比产品基准的价格、周均销量或周均销额差异，按卖点证据权重做解释性分摊。

### 9.3 报告输出结构

在“四个产品横向详细对比”中保留“卖点画像”事实行，并新增独立的“卖点价值量化”子目录：

| 行 | 内容 |
| --- | --- |
| Top5 核心卖点商业价值 | 展示每个 SKU 最重要的 5 个卖点及业务标签，例如 `MiniLED（强溢价卖点）；高刷（强销量卖点）`。 |
| 价格溢价卖点 | 展示可比产品价格差异、销量差异和本品可解释价差份额。 |
| 销量驱动卖点 | 展示可比产品销量差异、销额差异和本品可解释销量差份额。 |
| 组合型增值卖点 | 展示与主战场、主任务、主客群共同构成成交理由的卖点。 |
| 基础门槛卖点 | 展示可比产品普遍具备、缺失会拖累但不单独加价的卖点。 |
| 竞品拦截与补强建议 | 展示竞品具备、本品缺失、表达弱、用户感知不足或拖后腿的卖点。 |
| 卖点有效市场 | 展示卖点在哪些尺寸价格池、价值战场、用户任务和目标客群中有效。 |
| 本品相对可比产品表现差异 | 展示本品相对可比产品基准的价格、销量和销额差异如何被卖点解释。 |

在每个产品画像中，`卖点画像`之后新增独立的`卖点价值量化`表：

| 排名 | 卖点 | 业务类型 | 业务含义 | 卖点有效市场 | 可比产品价格差异 | 可比产品销量差异 | 可比产品销额差异 | 本品可解释价差份额 | 本品可解释销量差份额 | 证据支撑强度 | 业务解释 |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

业务类型含义、卖点解释、竞品拦截与补强建议、本品相对可比产品表现差异必须在表格和表后说明中同步出现，避免报告只剩“卖点 + 指数”。

如果没有 M12C：

- 卖点画像仍然展示事实卖点/评论支撑。
- 卖点价值量化章节写“卖点价值量化待生成”，不得伪造指数、价格支撑或销量支撑。
- 不显示伪造指数、价格支撑或销量支撑。

## 10. 综合排序设计

### 10.1 分数结构

建议保留内部综合分，但不在聊天回答中展示。

```text
competitor_business_score =
  purchase_pool_score * 0.20
  + battlefield_overlap * 0.25
  + user_task_overlap * 0.15
  + target_group_overlap * 0.15
  + anchor_substitutability_score * 0.15
  + replacement_pressure_score * 0.10
```

换算到报告展示的 100 分时：

| 维度 | 分值 | 来源 |
| --- | ---: | --- |
| 购买池 | 20 | CandidateBuilder |
| 价值战场 | 25 | RoleWeightedOverlapScorer |
| 用户任务 | 15 | RoleWeightedOverlapScorer |
| 目标客群 | 15 | RoleWeightedOverlapScorer |
| 关键价值锚点可替代性 | 15 | ValueAnchorMatcher + M12D |
| 替代压力 | 10 | ReplacementPressureClassifier |

市场验证不进入主体分，作为置信度和同分排序因素：

```text
final_sort_key =
  competitor_business_score,
  market_validation_level,
  purchase_pool_priority,
  abs(price_gap)
```

### 10.2 Top 3 选择

Top 3 不能机械取最高分前三名，必须保证业务解释完整：

1. 先选择最高分的首选直接竞品。
2. 再选择强直接竞品或配置标杆型竞品。
3. 第三名优先选择具有明确战略压力的下探分流、上探替代或价格贴身竞品。

硬门槛：

- `anchor_substitutability_score < 7/15` 时，候选不能作为首选直接竞品，除非业务角色明确是价格贴身、下探分流或上探替代。
- 目标 SKU 没有高置信 `core_payment` 锚点时，Top 3 可以输出，但整体置信度必须降低，报告要说明“成交理由画像不足”。
- 替代压力分低于 5/10 时，不能输出“强替代”“最可能影响最终成交”等高确定性话术。
- 市场验证不足不直接清零候选，但会降低置信度；若同时购买池偏离和市场验证不足，不进入 Top 3。

若前三名都属于同一角色，允许保留三个直接竞品，但报告必须说明角色相似。

若没有足够候选，不硬凑三款。

## 11. 短摘要生成设计

`CompetitorAnswerRenderer` 从结构化结果生成短摘要。

### 11.1 模板

```text
{target_name} 的重点竞品建议看三款：{name1}、{name2} 和 {name3}。
{name1} 排第一，是因为它{purchase_pool_phrase}，并且在{core_overlap_phrase}上覆盖了{target_name}最核心的成交理由，对其{pressure_phrase}。
{name2} 更像{role2_phrase}，在{anchor2_phrase}上与{target_name}正面对比，会{risk2_phrase}。
{name3} 属于{role3_phrase}，{price_or_pool_phrase}，但仍能承接{anchor3_phrase}，会{risk3_phrase}。
详细分析报告见飞书链接：{report_url}
```

### 11.2 语言约束

渲染器必须做文本校验：

- 字符数大于 `max_chat_chars` 时自动压缩每个候选理由。
- 禁止输出：`M00`、`M03B`、`BF_`、`TG_`、`TASK_`、`catforge`、`CLI`、`JSON`、`score`、`stderr`。
- 禁止以“根据”“下面”“数据完整”“工具返回”开头。
- 避免“不是……而是……”句式。
- 不在末尾追问用户是否继续。

校验失败时回退到更短的保底模板：

```text
{target_name} 的重点竞品建议看三款：{name1}、{name2} 和 {name3}。{name1} 是首选直接竞品，主要压力来自同一购买池内对核心成交理由的替代；{name2} 是强直接竞品，主要压力来自同价段配置和体验预期；{name3} 是{role3}，主要压力来自{pressure3}。详细分析报告见飞书链接：{report_url}
```

## 12. 飞书卡片看板设计

### 12.1 看板生成原则

`CompetitorDashboardPayloadBuilder` 从 `top_competitors` 裁剪出飞书会话主回答所需的最小业务结构。它只消费已排序结果，不重新计算竞品。

看板必须遵守：

- 主回答是卡片看板，飞书文档是佐证入口。
- 第一屏必须看见目标 SKU、Top 3 竞品、角色和替代压力。
- 重合强度必须拆成“价值战场 / 用户任务 / 目标客群”三行，每行同时展示百分比、命中点和成交影响。
- 不展示内部字段、模块名、原始 code、批次号、表名或长 JSON。
- 每张卡片只展示 Top 3，不展示全量候选池；全量候选和未选原因留在报告。
- 卡片消息体必须控制在飞书卡片消息大小限制内，首版只使用摘要、三类重合行、关键价值锚点可替代性摘要、市场验证和按钮。

### 12.2 Dashboard payload

`dashboard_payload` 是产品无关的业务看板结构，可供飞书卡片、前端看板或链接预览复用。

```json
{
  "schema_version": "competitor_dashboard_v1",
  "title": "海信 65E7Q 重点竞品看板",
  "target": {
    "display_name_cn": "海信 65E7Q",
    "market_summary_cn": "65 寸高价带核心 SKU，均价 5,949 元，周均约 251 台"
  },
  "summary_cn": "建议重点关注 3 款竞品，分别代表价值替代、配置对标和价格下探分流。",
  "competitors": [
    {
      "rank": 1,
      "display_name_cn": "创维 65A7H PRO",
      "role_cn": "首选直接竞品",
      "pressure_cn": "价值替代压力",
      "score_cn": "87 分",
      "summary_cn": "同预算池内替代关系最完整，直接拦截目标 SKU 成交理由。",
      "overlap_rows": [
        {
          "dimension_key": "battlefield",
          "dimension_cn": "价值战场",
          "strength_cn": "66%",
          "matched_points_cn": ["高端画质", "智能互联", "游戏体育"],
          "impact_cn": "争夺同一类付费场景"
        },
        {
          "dimension_key": "user_task",
          "dimension_cn": "用户任务",
          "strength_cn": "65%",
          "matched_points_cn": ["高端画质体验", "日常观影", "护眼观看"],
          "impact_cn": "进入同一次购买任务比较"
        },
        {
          "dimension_key": "target_group",
          "dimension_cn": "目标客群",
          "strength_cn": "86%",
          "matched_points_cn": ["高端影音", "儿童家庭", "投屏互联"],
          "impact_cn": "核心人群高度重合"
        }
      ],
      "shared_anchors_cn": ["智能互联", "高端画质", "游戏流畅"],
      "anchor_substitutability_cn": "强：覆盖高端画质和游戏流畅核心成交理由，家装融合表达更清晰",
      "pressure_breakdown_cn": "主压力为价值替代，辅助压力为场景心智",
      "market_validation_cn": "周均约 217 台，具备真实分流能力",
      "evidence_links": [
        {"label_cn": "完整报告", "url": "https://..."},
        {"label_cn": "评分依据", "url": "https://...#section-score"},
        {"label_cn": "横向对比", "url": "https://...#section-compare"}
      ],
      "follow_up_actions": [
        {"action": "analyze_competitor", "label_cn": "继续分析这款"}
      ]
    }
  ],
  "report_url": "https://..."
}
```

字段生成规则：

| 字段 | 来源 | 规则 |
| --- | --- | --- |
| `score_cn` | `business_score` | 四舍五入为整数分；如果展示会误导，可隐藏。 |
| `overlap_rows[].strength_cn` | `weighted_overlap` | 转成百分比；缺失时显示“待验证”，不能写 0%。 |
| `overlap_rows[].matched_points_cn` | `matched_dimensions` | 只取中文业务名，最多 4 个。 |
| `overlap_rows[].impact_cn` | 固定模板 + 角色 | 价值战场写付费场景，用户任务写购买任务，目标客群写人群争夺。 |
| `shared_anchors_cn` | `anchor_substitutability.shared_core_anchors` | 最多 5 个，不列参数长清单。 |
| `anchor_substitutability_cn` | `anchor_substitutability` | 用“强/中/弱 + 覆盖哪些目标核心锚点 + 哪些只是弱表达”生成一句话。 |
| `pressure_breakdown_cn` | `replacement_pressure` | 展示主压力和最多一个辅助压力，避免卡片堆满分项。 |
| `market_validation_cn` | `market_validation` | 周均销量用整数台，说明真实分流能力。 |
| `evidence_links` | `report_url` + 锚点 | 首版至少提供完整报告；有章节锚点时再提供评分依据、横向对比。 |

### 12.3 Feishu card payload

`FeishuCardRenderer` 把 `dashboard_payload` 渲染为飞书卡片。首版优先 raw JSON 2.0：

```json
{
  "schema": "2.0",
  "config": {
    "update_multi": true,
    "width_mode": "fill",
    "summary": {"content": "海信 65E7Q 重点竞品看板"}
  },
  "header": {
    "title": {"tag": "plain_text", "content": "海信 65E7Q 重点竞品看板"},
    "subtitle": {"tag": "plain_text", "content": "Top 3 竞品、重合结构和证据入口"},
    "template": "blue"
  },
  "body": {
    "elements": []
  }
}
```

卡片正文推荐顺序：

1. `markdown`：一句话结论。
2. `column_set` 或连续 `markdown`：Top 3 竞品摘要。
3. 每个竞品下方展示三行重合结构：`价值战场`、`用户任务`、`目标客群`。
4. `markdown`：关键价值锚点可替代性、替代压力和市场验证。
5. `button`：查看完整报告、查看评分依据、横向对比、继续分析这款。

卡片限制：

- 不在卡片中展示全量横向对比表、候选池列表和长证据矩阵。
- 不使用图片上传作为首版依赖。
- 不要求卡片模板先发布；raw JSON 2.0 可离线测试。
- 后续样式稳定后，可以把 raw JSON 迁移为飞书卡片模板，`dashboard_payload` 保持不变。

### 12.4 发送与降级

飞书入口可以由小奥外层适配器或服务端消息发送器执行。推荐先实现为可选适配层：

```python
class FeishuCardSender(Protocol):
    def send(self, receive_id_type: str, receive_id: str, card_payload: dict[str, Any]) -> FeishuSendResult:
        ...
```

发送规则：

1. `competitor-set --format text --answer-style xiaoao --with-report feishu-doc --feishu-reply-message-id <message_id> --feishu-card-only` 生成 `feishu_card_payload` 并尝试用 `msg_type=interactive` 回复飞书卡片。
2. `message_id` 来自 OpenClaw 飞书会话元数据；Skill 只负责传参，不解析或重组 `feishu_card_payload`。
3. CLI stdout 在飞书入口只输出卡片发送状态；发送成功显示“已发送飞书竞品看板卡片”，发送失败显示业务安全失败原因。Skill 必须把 stdout 作为可见文本回复发送给用户，不能输出 `NO_REPLY`、空回复或只发心跳。
4. 发送失败时不重跑竞品分析；失败状态必须可见，且只写业务化提示，不暴露 token、HTTP 响应体、卡片 JSON 或接口错误。
5. 非飞书入口继续使用 `--format text` 或 JSON 中的 `short_answer`。

JSON 2.0 卡片中的报告按钮必须直接作为 `body.elements` 中的 `button` 组件出现，使用 `behaviors: [{"type": "open_url", "default_url": "..."}]` 打开报告链接；不得使用 JSON 1.0 的 `tag: action` 包裹按钮。

链接预览不是主回答路径。只有当用户主动发送 CatForge 报告链接、且系统需要自动展开该链接时，再用 `dashboard_payload` 生成链接预览响应。

## 13. 飞书报告生成设计

### 13.1 报告渲染

`CompetitorReportRenderer` 生成 Markdown，交给发布器创建飞书文档。

目标报告章节：

1. `# {目标 SKU} 重点竞品分析报告`
2. `## 一、分析结论`
3. `## 二、分析过程`
4. `## 三、四个产品详情链接`
5. `## 四、四个产品横向详细对比`
6. `## 五、{目标 SKU} 产品画像`
7. `## 六/七/八、前三竞品产品画像`

`## 二、分析过程` 必须按维度组织，不按候选池组织：

```text
2.1 综合评分总览
2.2 购买池比较
2.3 价值战场比较
2.4 用户任务比较
2.5 目标客群比较
2.6 关键价值锚点可替代性比较
2.7 替代压力比较
2.8 市场验证比较
2.9 候选池与未选原因附录
```

每个维度章节使用同一模板：

```text
### 2.x {维度名}比较
判断口径：说明该维度如何评分、什么算强、什么只算弱证据。

| SKU | 角色 | 得分 | 本品/竞品表现 | 与本品的区别 | 业务判断 |
| --- | --- | ---: | --- | --- | --- |
| 目标 SKU | 本品 | - | ... | - | 本品在该维度的基准。 |
| 竞品 1 | 首选直接竞品 | ... | ... | ... | ... |
| 竞品 2 | 强直接竞品 | ... | ... | ... | ... |
| 竞品 3 | 下探分流竞品 | ... | ... | ... | ... |

业务结论：用 1-2 句话说明该维度为什么支持或削弱排序。
```

维度章节要求：

- 购买池比较必须展示尺寸、价格带、价差和是否进入同一次预算决策。
- 价值战场、用户任务、目标客群比较必须展示主/辅命中，而不是只展示重合数量。
- 关键价值锚点可替代性比较必须展示目标 `core_payment` 锚点、候选覆盖情况、弱表达锚点和证据强度。
- 替代压力比较必须展示主压力类型、辅助压力类型、10 分分项和目标成交影响。
- 市场验证比较必须说明真实分流能力和置信度，不把销量写成首选竞品的主因。
- 候选池与未选原因只作为附录或折叠区，不得放在 2.1 之前，也不得替代维度比较。

横向详细对比必须包含市场画像、价值战场画像、用户任务画像、目标客群画像、SKU成交理由画像、卖点画像、参数画像和卖点价值量化。卖点画像只展示事实和证据；SKU成交理由画像展示 M12D 的核心成交理由和关键价值锚点；卖点价值量化独立展示 M12C 的核心卖点商业价值、可比产品价格/销量差异、本品可解释价差/销量差份额、竞品拦截、补强建议和拖后腿卖点。

产品详情链接章节在 Markdown 本地报告中可以使用内部锚点；发布为飞书文档时，必须在文档创建后读取 outline 和第三章列表项，把四个列表项回填为 `文档URL#产品画像标题block_id` 的飞书 block 直达链接。

市场画像必须展示“市场池口径”，即尺寸/匹数段 × 价格带。AC 必须消费 M07 的“匹数段 × 价格带”同池口径，3匹柜机和 3匹以上柜机统一展示为“3匹及以上柜机”，不得重新拆成 `floor_hp_3` 与 `floor_hp_3_plus` 两个可比池。所在池空间和池内排名/份额只代表 SKU 在各自市场池中的位置；当竞品市场池口径与本品不同时，报告必须标注“与本品不同池”，不得暗示这些池内排名和池内份额可直接横比。市场池 SKU 数小于 3 时属于小样本池，所在池空间只能作为背景，报告不得输出“第 1 名、占比 100%”作为竞争力判断，必须显示“样本不足，不做池内排名/份额判断”。

卖点画像中的“参数支撑状态”必须输出业务主题和证据项数，例如“能效/省电3项、智能控制/互联4项、耐用品质1项”。不得直接输出 `authority(2)`、`energy_efficiency(3)`、重复的同名标签或其他原始 key/count 表达。

报告不得输出产品经理策略、导购话术、应对策略、实现过程、原始模块名、批次号或命令输出。

数字和缺失值渲染规则：

- 所有以“台”为单位的销量、周均销量、分配销量和空间销量使用整数展示，采用四舍五入，不输出小数台。
- 价值战场、用户任务、目标客群的 `market_space` 缺失时，显示“本轮未计算该语义维度销量空间”。
- SKU 在主辅语义维度没有销量分配时，显示“本轮未分配该 SKU 在此维度的销量”。
- SKU 在机会、拖后腿、厂家主张、评论观察等补充关系中没有销量分配时，显示“本轮未做销量归因，仅作机会或观察证据”。
- 禁止在业务报告里输出“图谱空间待生成”“暂无该分类市场空间数据”等技术性错误提示。

### 13.2 飞书发布器

接口：

```python
class ReportPublisher(Protocol):
    def publish(self, title: str, markdown: str) -> ReportPublishResult:
        ...
```

结果：

```python
@dataclass
class ReportPublishResult:
    status: Literal["created", "created_profile_links_failed", "disabled", "failed"]
    url: str | None
    message_cn: str | None
```

实现：

- `NoopReportPublisher`：本地和测试默认，不调用外部服务。
- `FeishuCliReportPublisher`：通过 `lark-cli docs +create --api-version v2 --as <CATFORGE_FEISHU_AS> --doc-format markdown` 创建文档；205 默认使用 bot 身份。
- 创建成功后，发布器用 `docs +fetch --scope outline --detail with-ids` 和第三章 `section` 读取产品画像标题与列表项 block id，再用 `docs +update --command block_replace` 把第三章列表项替换为飞书 block 直达链接。回填失败不删除已创建文档，但返回 `created_profile_links_failed` 供调用方提示。

配置：

| 配置 | 说明 |
| --- | --- |
| `CATFORGE_ANALYST_REPORT_PUBLISHER=none` | 不生成外部链接。 |
| `CATFORGE_ANALYST_REPORT_PUBLISHER=feishu_cli` | 使用飞书 CLI。 |
| `CATFORGE_FEISHU_AS=bot` | 205 默认使用 bot 身份创建佐证文档。 |
| `CATFORGE_FEISHU_IM_AS=bot` | 可选；飞书卡片回复身份，缺省沿用 `CATFORGE_FEISHU_AS`。 |
| `CATFORGE_FEISHU_NODE_DIR=/home/deploy/.openclaw/tools/node` | host 上 lark-cli 所在 Node 工具目录，Compose 挂载到容器 `/opt/openclaw-node`。 |
| `CATFORGE_FEISHU_CONFIG_DIR=/home/deploy/.lark-cli` | host 上 lark-cli 配置目录，Compose 挂载到容器 `/root/.lark-cli`。 |
| `CATFORGE_FEISHU_DATA_DIR=/home/deploy/.local/share/lark-cli` | host 上 lark-cli keychain/密钥存储目录，Compose 挂载到容器 `/root/.local/share/lark-cli`。缺失时 bot 会报 `not_configured` 或无法解密 app secret。 |
| `CATFORGE_FEISHU_LINK_SHARE_ENTITY=anyone_readable` | 创建后将佐证文档设置为获得链接的人可阅读。 |

飞书发布失败时：

- `short_answer` 仍返回。
- `report_status = "failed"`。
- 聊天摘要末尾写“详细分析报告暂未生成”，不暴露失败命令。

## 14. Skill 设计

### 14.1 固定路由

`tools/openclaw/skills/xiaoao-home-appliance-market-analysis/SKILL.md` 的竞品问题路由改为：

```bash
docker compose -f docker-compose.cloud.yml exec -T api \
  python -m app.cli.catforge_analyst competitor-set \
  --query "<用户中的 SKU>" \
  --product-category tv \
  --batch-id latest \
  --limit 10 \
  --format text \
  --answer-style xiaoao \
  --with-report feishu-doc \
  --top-n 3 \
  --max-chat-chars 600 \
  --feishu-reply-message-id "<message_id>" \
  --feishu-card-idempotency-key "competitor-card-<message_id>" \
  --feishu-card-only
```

### 14.2 Skill 消费规则

伪代码：

```text
result = run_cli(...)
if status == ok and feishu_entrypoint:
    pass message_id to CLI with --feishu-card-only
    send CLI stdout card delivery status exactly
elif status == ok and result.competitor_answer.short_answer:
    send result.competitor_answer.short_answer exactly
elif status == ambiguous:
    ask user to choose candidate SKU
elif status == not_found:
    tell user current sample cannot find the SKU
else:
    tell user competitor analysis package is temporarily unavailable
```

Skill 不再做：

- 读取 `candidates` 后重新排序。
- 把英文字段翻译成新结论。
- 拼接飞书卡片组件。
- 追加通用市场常识。
- 把工具错误粘贴给用户。

### 14.3 追问处理

对于“第一款为什么选它”“分析第一名”等追问：

1. 从上一轮 `top_competitors[0]` 取候选 SKU。
2. 调用同一套竞品解释能力，或调用 `competitor-set --focus-candidate-sku-code <sku>`。
3. 如果上下文缺失，要求用户确认竞品名称。

后续可新增：

```bash
python -m app.cli.catforge_analyst competitor-explain \
  --sku-code <target> \
  --candidate-sku-code <candidate> \
  --answer-style xiaoao \
  --with-report feishu-doc
```

首版也可以由 `competitor-set` 在 JSON 中返回 `top_competitors[0].detail_answer`，供 Skill 直接使用。

## 15. 数据结构设计

### 15.1 Top competitor item

```json
{
  "rank": 1,
  "role": "primary_direct",
  "role_cn": "首选直接竞品",
  "brand_name": "创维",
  "model_name": "65A7H PRO",
  "sku_code": "...",
  "purchase_pool": {
    "pool_level": "P0",
    "price_gap_pct": -0.053,
    "pool_reason_cn": "同 65 寸高价购买池"
  },
  "weighted_overlap": {
    "battlefield": 0.72,
    "user_task": 0.51,
    "target_group": 0.63
  },
  "candidate_purchase_reason_profile": {
    "core_reasons_cn": ["高端画质和家庭客厅体验支撑同价段选择"],
    "core_anchors": ["高端画质", "家装融合"],
    "weak_expression_anchors": []
  },
  "anchor_substitutability": {
    "score": 12,
    "level": "strong",
    "shared_core_anchors": ["高端画质", "游戏流畅"],
    "target_only_anchors": ["预算内配置获得感"],
    "candidate_stronger_anchors": ["家装融合"],
    "weak_expression_anchors": ["预算内配置获得感"],
    "summary_cn": "覆盖目标主要成交理由，家装融合表达更清晰。"
  },
  "replacement_pressure": {
    "type": "value_substitution",
    "type_cn": "价值替代压力",
    "score": 8,
    "secondary_types": ["scenario_mindshare"],
    "reason_cn": "对目标 SKU 的主支付理由形成替代。",
    "score_breakdown": {
      "purchase_pool_pressure": 2,
      "purchase_reason_pressure": 3,
      "price_or_config_impact": 1,
      "scenario_mindshare_shift": 1,
      "market_diversion_validation": 1,
      "confidence_adjustment": 0
    }
  },
  "market_validation": {
    "level": "strong",
    "overlap_week_count": 24,
    "avg_weekly_sales_volume": 216.6
  },
  "business_summary_cn": "..."
}
```

### 15.2 Purchase reason profile payload

```json
{
  "purchase_reason_profile": {
    "schema_version": "sku_purchase_reason_profile_v1",
    "status": "ready",
    "sku_code": "TV00029112",
    "core_reasons_cn": [
      "高端画质和游戏流畅共同支撑高价段升级购买"
    ],
    "anchors": [
      {
        "anchor_code": "premium_picture",
        "anchor_cn": "高端画质",
        "role": "core_payment",
        "evidence_strength": "strong",
        "confidence": 0.82,
        "evidence_domains": ["param_fact", "fact_claim", "claim_value", "battlefield", "market"],
        "reason_cn": "MiniLED、亮度、分区控光和画质战场共同支撑高端画质升级。"
      }
    ],
    "risk_flags": [],
    "profile_confidence": 0.76
  }
}
```

### 15.3 Claim value payload

```json
{
  "claim_value_summary": {
    "status": "ready",
    "top_premium_claims": [
      {
        "claim_code": "tv_claim_miniled",
        "claim_name": "MiniLED",
        "claim_value_role": "premium_driver_estimated",
        "claim_premium_index": 87,
        "price_premium_abs": 280.0,
        "weekly_sales_lift_abs": 15.0,
        "weekly_sales_amount_lift_abs": 75000.0,
        "context_name": "高端画质升级战场",
        "confidence": 0.82
      }
    ],
    "drag_claims": [],
    "opportunity_claims": []
  }
}
```

### 15.4 Dashboard and card payload

```json
{
  "dashboard_payload": {
    "schema_version": "competitor_dashboard_v1",
    "title": "海信 65E7Q 重点竞品看板",
    "competitors": []
  },
  "feishu_card_payload": {
    "schema": "2.0",
    "config": {"summary": {"content": "海信 65E7Q 重点竞品看板"}},
    "header": {},
    "body": {"elements": []}
  }
}
```

`dashboard_payload` 是业务语义层，`feishu_card_payload` 是展示层。测试和后续前端复用应优先断言 `dashboard_payload`，避免把业务规则锁死在飞书卡片组件结构里。

### 15.5 Report payload

```json
{
  "title": "海信 65E7Q 重点竞品分析报告",
  "markdown": "...",
  "url": "https://...",
  "status": "created"
}
```

## 16. 测试设计

### 16.1 单元测试

新增测试文件建议：

```text
apps/api-server/tests/core3_real_data/test_catforge_analyst_competitor_answer.py
apps/api-server/tests/core3_real_data/test_sku_purchase_reason_profile.py
apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py
apps/api-server/tests/core3_real_data/test_replacement_pressure_score.py
apps/api-server/tests/core3_real_data/test_competitor_role_weighted_overlap.py
apps/api-server/tests/core3_real_data/test_competitor_dashboard_payload.py
apps/api-server/tests/core3_real_data/test_feishu_card_renderer.py
apps/api-server/tests/core3_real_data/test_competitor_report_renderer.py
```

测试项：

| 测试 | 断言 |
| --- | --- |
| M12D 消费契约 | 能读取已发布 M12D 中的 `core_payment`、`supporting`、`weak_expression`、`risk_drag`、证据强度和置信度。 |
| 弱表达封顶 | 只有 `value_price`、`price_value`、厂家主张或位置标签时，不得生成强核心成交理由。 |
| M12D 缺失兜底 | 目标画像缺失时降级或阻断；候选画像缺失时锚点可替代性降置信度；不在竞品问答中补跑画像。 |
| 关键价值锚点可替代性 | 目标核心锚点覆盖高于辅助锚点覆盖；候选只覆盖辅助锚点不能成为首选直接竞品。 |
| 替代压力评分 | 分项消费购买池、成交理由替代强度、价格/配置冲击、场景心智、市场验证和置信修正。 |
| 替代压力类型 | 主压力类型只选一个，辅助压力最多两个。 |
| 主辅加权重合 | 主主命中高于主辅，主辅高于辅辅。 |
| 负向状态 | 拖后腿和未满足不计入正向重合。 |
| 价格最近但语义弱 | 不能排在语义强的直接竞品前。 |
| 销量相近 | 不得单独让候选成为首选竞品。 |
| Top 3 选择 | 能同时覆盖直接、强直接、下探/价格贴身等角色。 |
| 短摘要长度 | 不超过 600 中文字符。 |
| 短摘要安全 | 不包含内部模块、字段、命令、JSON。 |
| text/json 一致 | 非卡片入口 `--format text` 等于 JSON `short_answer`；带 `feishu_card_delivery` 时 text 优先输出卡片发送状态。 |
| Dashboard payload | 只包含 Top 3，每个竞品都有价值战场、用户任务、目标客群三行重合结构，并有关键价值锚点可替代性摘要。 |
| Dashboard 业务语言 | 不包含 `BF_`、`TASK_`、`TG_`、表名或批次号。 |
| Feishu card payload | 可 JSON 序列化，包含 header/body/config，消息体大小符合飞书卡片限制。 |
| 卡片结构 | JSON 2.0 正文只使用 `body.elements` 组件；报告入口按钮使用 `button.behaviors.open_url`，不使用 `tag: action`。 |
| 卡片降级 | 发送失败时结构化结果仍返回 `short_answer` 和 `report_url`，但飞书入口 stdout 输出业务安全失败原因，不产生空回复。 |
| 飞书失败 | 仍返回短摘要，`report_status=failed`。 |
| 模糊 SKU | Pro/非 Pro 同时命中时返回 `ambiguous`。 |
| M12C 报告接入 | 竞品报告新增独立“卖点价值量化”章节，展示业务卖点标签、可比产品差异、本品可解释价差/销量差份额和置信度。 |
| M12C 缺失兜底 | 报告写“卖点价值量化待生成”，不伪造量化指标。 |
| 维度化报告结构 | `## 二、分析过程` 下按综合评分、购买池、价值战场、用户任务、目标客群、关键价值锚点、替代压力、市场验证和候选池附录排序。 |
| 维度章节模板 | 每个维度章节都有判断口径、本品 + Top 3 表格、差异解释和业务结论。 |
| 候选池降级 | 候选池与未选原因只出现在附录/折叠区，不作为主分析目录。 |

### 16.2 集成测试

使用固定 fixture 或测试数据库样本：

- 目标：海信 65E7Q。
- 预期 Top 3 至少包括创维 65A7H PRO、TCL 65Q9L PRO。
- 小米 L65MC-SP 因价格贴身但语义重合较弱，不应排为首选。
- 创维 65A6F ULTRA 可作为下探分流或战略压力候选。

不要求在单元测试中调用真实飞书。

## 17. 部署与兼容

### 17.1 兼容策略

- 默认 `--answer-style raw` 保持现有输出兼容。
- 小奥 Skill 使用 `--answer-style xiaoao`。
- `--with-report none` 时不依赖飞书环境。
- `dashboard_payload` 和 `feishu_card_payload` 只在 `--format json` 中消费；`--format text` 继续只输出短摘要。
- M12D `SKU成交理由画像` 必须由 M12D 独立模块预先生成、验证并发布；`competitor-set` 只能读取已发布画像，不能按需生成或缓存新画像。
- 飞书佐证文档标题下必须同步插入 Markdown 版“重点竞品看板”，字段与 `dashboard_payload` 同源，先展示 Top 3、重合强度、关键价值锚点可替代性、替代压力，以及价值战场、用户任务、目标客群三行重合证据；详细分析章节仍作为佐证放在看板之后。
- 205 上若未配置飞书 CLI，仍可回答短摘要。

### 17.2 205 部署后验收

验收命令：

```bash
docker compose -f docker-compose.cloud.yml exec -T api \
  python -m app.cli.catforge_analyst competitor-set \
  --query "海信 65E7Q" \
  --product-category tv \
  --batch-id latest \
  --limit 10 \
  --format text \
  --answer-style xiaoao \
  --with-report feishu-doc
```

验收要点：

- 输出是中文业务摘要。
- 不超过 600 字。
- 只输出 Top 3 和飞书链接。
- 不出现内部 code 和命令。
- JSON 输出包含 `dashboard_payload` 和 `feishu_card_payload`；飞书入口能发送卡片，且无论卡片发送成功或失败都能看到短摘要。
- JSON 输出包含目标 SKU 的 `target_purchase_reason_profile`，每个 Top 3 竞品包含 `candidate_purchase_reason_profile`、`anchor_substitutability` 和 `replacement_pressure.score_breakdown`。
- 飞书链接可打开；如果当前 batch 找不到该 SKU，必须返回业务化边界提示。
- 飞书报告 `## 二、分析过程` 下必须按维度展示 2.1-2.9，且每个维度章节有判断口径、本品 + Top 3 表格和业务结论。
- 价格价值表达或厂家主张只能显示为弱表达，不得作为海信或竞品的强核心成交理由。
- 飞书报告的“四个产品横向详细对比”和各产品画像中必须同时出现“卖点画像”和“卖点价值量化”；若 latest 批次 M12C 未准备好，卖点价值量化章节必须显示“卖点价值量化待生成”。

## 18. 后续扩展

首版聚焦“竞品有哪些”和“为什么第一款是首选竞品”。后续可以扩展：

1. `competitor-explain`：专门解释某个候选为什么入选或未入选。
2. `competitor-report --target feishu-base`：把详细矩阵写入飞书多维表格。
3. 飞书卡片二次选择：当 SKU 模糊匹配时让用户点选。
4. 不同品类的价值锚点配置：空调、洗衣机等按品类独立维护。
5. 链接预览：当用户发送 CatForge 报告链接时，复用 `dashboard_payload` 返回链接预览卡片。
6. 报告页面图表化：购买池散点、战场重合雷达、候选分桶矩阵。

## 19. Goal 实现任务拆分

后续实现必须拆成两条链，避免把 M12D 资产生产和竞品智能体消费混在一个不可验收的大改里。

### 前置链路：M12D 专项工程

M12D 的分析、需求、详细设计、实现、小批量验证、全量生成和发布，按独立文档推进：

- [M12D SKU成交理由画像需求](../sop_requirements/M12D_sku_purchase_reason_profile_requirements.md)
- [M12D SKU成交理由画像详细设计](M12D_sku_purchase_reason_profile_design.md)

竞品分析智能体的实现只能在 M12D 有可消费版本后开始。若只做联调，可使用固定 fixture 模拟已发布 M12D，但不能在竞品智能体里实现 M12D 生成逻辑。

### Goal 1：M12D 读取与缺失处理

交付内容：

- 新增 `PurchaseReasonProfileReader`，按 `category_code + project_id + batch_id + m12d_profile_version + sku_code` 读取已发布 M12D。
- 在 `competitor-set` 输出 `target_purchase_reason_profile` 和 `candidate_purchase_reason_profile`。
- 目标 M12D 缺失时降级或阻断；候选 M12D 缺失时降低候选锚点可替代性或退出 Top 3。

完成标准：

- `competitor-set` 不生成 M12D，不修改 M12D 锚点角色。
- 缺失 M12D 时不使用默认“技术型/场景型高端体验”补结论。

### Goal 2：关键价值锚点可替代性

交付内容：

- 改造 `ValueAnchorMatcher`，从已发布 M12D 读取目标和候选画像。
- 输出 `anchor_substitutability`：15 分、等级、共享核心锚点、目标独有、候选更强、弱表达和逐锚点匹配明细。
- 把 `anchor_substitutability_score` 接入竞品综合分和 Top 3 硬门槛。

完成标准：

- 候选只覆盖目标辅助锚点时，不能成为首选直接竞品。
- 锚点可替代性不足时，短摘要和报告不能写“完整替代目标成交理由”。

### Goal 3：替代压力评分

交付内容：

- 改造 `ReplacementPressureClassifier`，输出 10 分分项、主压力类型、辅助压力类型和目标成交影响。
- 替代压力消费购买池、成交理由替代强度、价格/配置冲击、场景心智、市场验证和证据置信修正。
- 更新竞品角色规则和硬门槛。

完成标准：

- 替代压力低于 5/10 时，报告不输出高确定性替代话术。
- 一个候选只有一个主压力类型，辅助压力最多两个。

### Goal 4：竞品报告结构改造

交付内容：

- 改造 `CompetitorReportRenderer`，把 `## 二、分析过程` 改为 2.1-2.9 维度目录。
- 每个维度章节生成判断口径、本品 + Top 3 横向表、差异解释和业务结论。
- 候选池与未选原因移动到附录或折叠区。
- 在横向详细对比和产品画像中加入 `SKU成交理由画像`。

完成标准：

- 飞书文档不再出现“关键价值锚点、替代压力和市场验证依据”合并章节。
- 业务用户能按任一维度横向比较本品和前三竞品。

### Goal 5：竞品看板、CLI 和小奥 Skill 接入

交付内容：

- `competitor-set --answer-style xiaoao` 输出 `target_purchase_reason_profile`、`candidate_purchase_reason_profile`、`anchor_substitutability` 和新的 `replacement_pressure`。
- `dashboard_payload` 和飞书卡片展示关键价值锚点可替代性摘要与替代压力摘要。
- 小奥 Skill 保持只路由和转发，不解析或改写新字段。

完成标准：

- 飞书入口仍能发送卡片；非飞书入口短摘要不超过 600 字。
- 回答和卡片不出现内部 code、Mxx、字段名或 JSON。

### Goal 6：端到端验证与 205 部署

交付内容：

- 补齐单测、集成测试和报告结构测试。
- 用海信 65E7Q 验证 Top 3、锚点可替代性、替代压力、飞书报告和小奥入口。
- 在 205 上部署并生成可打开的飞书报告。

完成标准：

- 关键测试通过。
- 65E7Q 报告中的成交理由、锚点可替代性和替代压力都有可审计依据。
- 小奥入口回答与飞书报告的排序、角色和维度解释一致。
