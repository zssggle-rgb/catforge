# CatForge Analyst 竞品问答 CLI 与小奥 Skill 详细设计

## 1. 设计目标

本文承接 [CatForge Analyst 竞品问答 CLI 与小奥 Skill 需求](../sop_requirements/CATFORGE_ANALYST_competitor_answer_requirements.md)，定义 `catforge_analyst` 竞品问答的工程实现方案。

设计目标：

1. 把竞品排序从“通用相似度”升级为“购买池 + 主辅语义重合 + 价值锚点替代 + 替代压力 + 市场验证”。
2. 由 CLI 生成最终聊天摘要，避免 OpenClaw 解析大 JSON 后改写答案。
3. 由 CLI 生成飞书详细报告，聊天中只放短结论和链接。
4. Skill 只做路由、边界处理和原样转发，不做竞品计算。
5. 所有测试不调用外部 LLM，不依赖真实飞书 API。

## 2. 总体架构

```text
用户问题
  -> 小奥 Skill
  -> catforge_analyst competitor-set
       -> SKUResolver
       -> CompetitorCandidateBuilder
       -> RoleWeightedOverlapScorer
       -> ValueAnchorMatcher
       -> ReplacementPressureClassifier
       -> MarketValidationService
       -> ClaimValueEvidenceAssembler
       -> CompetitorSelectionService
       -> CompetitorAnswerRenderer
       -> CompetitorReportRenderer
       -> FeishuReportPublisher
  -> short_answer + report_url
```

职责边界：

| 模块 | 职责 |
| --- | --- |
| Skill | 识别竞品意图，调用 CLI，发送 `short_answer`。 |
| CLI | 参数解析、调用服务、输出 text/json。 |
| CandidateBuilder | 生成购买池候选和扩展候选。 |
| OverlapScorer | 计算价值战场、用户任务、目标客群的主辅加权重合。 |
| ValueAnchorMatcher | 提炼目标 SKU 和候选 SKU 的可替代价值锚点。 |
| PressureClassifier | 判断竞品角色和替代压力。 |
| ClaimValueEvidenceAssembler | 读取目标和候选 SKU 的 M12C 卖点价值量化，形成报告可直接展示的卖点溢价指数、价格支撑、销量支撑和拖后腿/机会缺口。 |
| SelectionService | 汇总分数、排序、分桶、Top 3 选择。 |
| AnswerRenderer | 生成 600 字以内业务摘要。 |
| ReportRenderer | 生成飞书 Markdown 报告内容。 |
| FeishuReportPublisher | 创建飞书文档并返回链接；测试中用 mock。 |

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

当 `--format text --answer-style xiaoao` 时，stdout 只输出：

```text
{short_answer}
```

不得输出命令提示、debug 文本、JSON、stderr 内容或内部字段。

### 3.3 JSON 输出

JSON 中保留结构化分析，供调试、验收和后续飞书卡片使用。

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

## 6. 价值锚点匹配

`ValueAnchorMatcher` 负责把参数、卖点和评论转成业务可读的价值锚点。

### 6.1 电视品类首版锚点

| 锚点 | 证据来源 |
| --- | --- |
| 客厅尺寸升级 | 尺寸、尺寸档、评论空间/换新表达、卖点大屏表达。 |
| 高端画质 | MiniLED/OLED/QD、亮度、分区、HDR、色域、画质芯片、评论画质正负向。 |
| 影院沉浸 | 大屏、音响、杜比、HDR、评论电影/追剧/客厅沉浸。 |
| 游戏流畅 | 刷新率、HDMI2.1、VRR、低延迟、评论游戏/主机/运动流畅。 |
| 智能互联 | AI、语音、投屏、IoT、系统易用、评论投屏/语音/系统体验。 |
| 护眼长看 | 护眼、低蓝光、无频闪、儿童/家庭长时间观看评论。 |
| 家装融合 | 壁画、贴墙、超薄、全面屏、外观材质、评论新家/客厅空间。 |
| 预算价值 | 同尺寸价格位置、配置获得感、补贴、性价比评论。 |

### 6.2 锚点匹配结果

每个候选输出：

```json
{
  "value_anchor_overlap": 0.68,
  "shared_anchors": ["高端画质", "影院沉浸", "游戏流畅"],
  "target_stronger_anchors": ["高亮控光", "技术型游戏能力"],
  "candidate_stronger_anchors": ["家装融合", "客厅空间表达"],
  "anchor_substitution_summary_cn": "候选在目标的高端画质和客厅观影支付理由上形成替代。"
}
```

短摘要只使用业务表达，不列长参数清单。

## 7. 替代压力分类

`ReplacementPressureClassifier` 根据购买池、价格差、语义重合、价值锚点和市场验证生成竞品角色。

### 7.1 分类规则

| 角色 | 规则 |
| --- | --- |
| 首选直接竞品 | P0/P1 购买池，战场/任务/客群综合高，价值锚点可替代，市场验证有效。 |
| 强直接竞品 | P0/P1 购买池，语义和锚点强，但替代压力略低或角色偏配置标杆。 |
| 价格贴身竞品 | 价差极小，但语义或锚点重合明显弱于直接竞品。 |
| 下探分流竞品 | 价格明显更低，仍保留目标 SKU 部分核心锚点。 |
| 上探替代竞品 | 价格明显更高，品牌/配置/高端锚点能吸走高预算用户。 |
| 场景替代竞品 | 购买池偏离，但在目标核心场景中强替代。 |
| 排除候选 | 只满足局部相似，无法进入最终候选清单。 |

### 7.2 替代压力说明

每个 Top 3 候选必须输出：

```json
{
  "pressure_type": "value_substitution",
  "pressure_cn": "价值替代压力",
  "business_reason_cn": "在同一 65 寸高价购买池中，承接目标 SKU 的高端画质、影院沉浸和家庭客厅体验支付理由。",
  "target_risk_cn": "如果目标 SKU 没有把技术优势转成用户可理解的场景价值，候选会削弱其溢价解释。"
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

竞品详细报告的卖点画像必须优先读取 M12C：

- `sku-claim-value`：单 SKU 的 SKU×卖点价值角色、估算价格溢价、估算周均销量优势、估算周均销额优势、贡献占比和置信度。
- `claim-contribution`：单 SKU 在价值战场、用户任务、目标客群等上下文中的卖点贡献归因。

`competitor-set` 在 `answer_style=xiaoao` 或 `with_report != none` 时，除 `sku-fact-brief` 外，还要为目标 SKU 和进入候选池的 SKU 拉取 M12C 结果。M12C 查询失败或无数据不能阻断竞品集合生成，但报告必须展示“卖点价值量化待生成”。

### 9.2 卖点溢价指数

报告展示的“卖点溢价指数”是报告层展示分，不写入 M12C 结果表。计算目标是让业务用户快速看出同一 SKU 内哪个卖点更有价值。

建议口径：

```text
role_base =
  premium_driver_estimated: 70
  sales_driver_estimated: 60
  basic_threshold: 35
  user_validated_need: 45
  brand_claim_only: 25
  opportunity_gap: 30
  drag_factor: 15
  sample_insufficient: 10

claim_premium_index =
  role_base
  + normalized(price_premium_abs) * 15
  + normalized(weekly_sales_lift_abs) * 10
  + normalized(weekly_sales_amount_lift_abs) * 10
  + contribution_share_in_sku * 10
  + attribution_confidence * 5
```

实现中可采用无全局依赖的单 SKU 内归一化：同一 SKU 当前返回的 M12C 卖点中，价格、销量、销额分别按最大正值归一化到 0-1。最终分数限制在 0-100，并展示为整数。该分数仅用于报告内排序和阅读，不表达严格因果。

### 9.3 报告输出结构

在“四个产品横向详细对比 - 卖点画像”中新增行：

| 行 | 内容 |
| --- | --- |
| 卖点溢价指数 Top | 展示 Top 3 卖点及指数，例如 `MiniLED 87；高刷 76`。 |
| 可观测价格支撑 | 展示 Top 3 卖点对应估算价格支撑。 |
| 可观测销量支撑 | 展示 Top 3 卖点对应估算周均销量支撑。 |
| M12C 拖后腿/机会缺口 | 展示拖后腿卖点和机会缺口，区分风险与机会。 |

在每个产品的“卖点画像”中新增 M12C 表：

| 卖点类型 | 卖点 | 卖点溢价指数 | 可观测价格支撑 | 可观测周均销量支撑 | 上下文 | 置信度 | 判断 |
| --- | --- | ---: | --- | --- | --- | --- | --- |

如果没有 M12C：

- 保留原来的事实卖点/评论支撑表作为兜底。
- 表头或说明写“卖点价值量化待生成，以下为事实卖点与评论支撑兜底判断”。
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
  + value_anchor_overlap * 0.15
  + replacement_pressure_score * 0.10
```

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

## 12. 飞书报告生成设计

### 12.1 报告渲染

`CompetitorReportRenderer` 生成 Markdown，交给发布器创建飞书文档。

当前报告章节：

1. `# {目标 SKU} 重点竞品分析报告`
2. `## 一、分析结论`
3. `## 二、分析过程`
4. `## 三、四个产品详情链接`
5. `## 四、四个产品横向详细对比`
6. `## 五、{目标 SKU} 产品画像`
7. `## 六/七/八、前三竞品产品画像`

横向详细对比必须包含市场画像、价值战场画像、用户任务画像、目标客群画像、卖点画像和参数画像。卖点画像必须优先展示 M12C 卖点溢价指数、可观测价格支撑、可观测销量支撑和拖后腿/机会缺口；事实卖点与评论支撑只能作为 M12C 缺失时的兜底。

报告不得输出产品经理策略、导购话术、应对策略、实现过程、原始模块名、批次号或命令输出。

数字和缺失值渲染规则：

- 所有以“台”为单位的销量、周均销量、分配销量和空间销量使用整数展示，采用四舍五入，不输出小数台。
- 价值战场、用户任务、目标客群的 `market_space` 缺失时，显示“未纳入当前销量空间测算”。
- SKU 在某个语义维度没有销量分配时，显示“未分配销量，仅作机会或风险证据”。
- 禁止在业务报告里输出“图谱空间待生成”“暂无该分类市场空间数据”等技术性错误提示。

### 12.2 飞书发布器

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
    status: Literal["created", "disabled", "failed"]
    url: str | None
    message_cn: str | None
```

实现：

- `NoopReportPublisher`：本地和测试默认，不调用外部服务。
- `FeishuCliReportPublisher`：通过 `lark-cli docs +create --api-version v2 --as user --doc-format markdown` 创建文档。

配置：

| 配置 | 说明 |
| --- | --- |
| `CATFORGE_ANALYST_REPORT_PUBLISHER=none` | 不生成外部链接。 |
| `CATFORGE_ANALYST_REPORT_PUBLISHER=feishu_cli` | 使用飞书 CLI。 |
| `CATFORGE_FEISHU_AS=user` | 默认使用用户身份。 |

飞书发布失败时：

- `short_answer` 仍返回。
- `report_status = "failed"`。
- 聊天摘要末尾写“详细分析报告暂未生成”，不暴露失败命令。

## 13. Skill 设计

### 13.1 固定路由

`tools/openclaw/skills/xiaoao-home-appliance-market-analysis/SKILL.md` 的竞品问题路由改为：

```bash
docker compose -f docker-compose.cloud.yml exec -T api \
  python -m app.cli.catforge_analyst competitor-set \
  --query "<用户中的 SKU>" \
  --product-category tv \
  --batch-id latest \
  --limit 10 \
  --format json \
  --answer-style xiaoao \
  --with-report feishu-doc
```

### 13.2 Skill 消费规则

伪代码：

```text
result = run_cli(...)
if status == ok and result.competitor_answer.short_answer:
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
- 追加通用市场常识。
- 把工具错误粘贴给用户。

### 13.3 追问处理

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

## 14. 数据结构设计

### 14.1 Top competitor item

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
  "value_anchor": {
    "score": 0.68,
    "shared_anchors": ["高端画质", "影院沉浸", "家庭客厅体验"],
    "candidate_stronger_anchors": ["家装融合"]
  },
  "replacement_pressure": {
    "type": "value_substitution",
    "type_cn": "价值替代压力",
    "reason_cn": "对目标 SKU 的主支付理由形成替代。"
  },
  "market_validation": {
    "level": "strong",
    "overlap_week_count": 24,
    "avg_weekly_sales_volume": 216.6
  },
  "business_summary_cn": "..."
}
```

### 14.2 Claim value payload

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

### 14.3 Report payload

```json
{
  "title": "海信 65E7Q 重点竞品分析报告",
  "markdown": "...",
  "url": "https://...",
  "status": "created"
}
```

## 15. 测试设计

### 15.1 单元测试

新增测试文件建议：

```text
apps/api-server/tests/core3_real_data/test_catforge_analyst_competitor_answer.py
apps/api-server/tests/core3_real_data/test_competitor_role_weighted_overlap.py
apps/api-server/tests/core3_real_data/test_competitor_report_renderer.py
```

测试项：

| 测试 | 断言 |
| --- | --- |
| 主辅加权重合 | 主主命中高于主辅，主辅高于辅辅。 |
| 负向状态 | 拖后腿和未满足不计入正向重合。 |
| 价格最近但语义弱 | 不能排在语义强的直接竞品前。 |
| 销量相近 | 不得单独让候选成为首选竞品。 |
| Top 3 选择 | 能同时覆盖直接、强直接、下探/价格贴身等角色。 |
| 短摘要长度 | 不超过 600 中文字符。 |
| 短摘要安全 | 不包含内部模块、字段、命令、JSON。 |
| text/json 一致 | `--format text` 等于 JSON `short_answer`。 |
| 飞书失败 | 仍返回短摘要，`report_status=failed`。 |
| 模糊 SKU | Pro/非 Pro 同时命中时返回 `ambiguous`。 |
| M12C 报告接入 | 竞品报告卖点画像展示卖点溢价指数、价格支撑、销量支撑和置信度。 |
| M12C 缺失兜底 | 报告写“卖点价值量化待生成”，不伪造指数。 |

### 15.2 集成测试

使用固定 fixture 或测试数据库样本：

- 目标：海信 65E7Q。
- 预期 Top 3 至少包括创维 65A7H PRO、TCL 65Q9L PRO。
- 小米 L65MC-SP 因价格贴身但语义重合较弱，不应排为首选。
- 创维 65A6F ULTRA 可作为下探分流或战略压力候选。

不要求在单元测试中调用真实飞书。

## 16. 部署与兼容

### 16.1 兼容策略

- 默认 `--answer-style raw` 保持现有输出兼容。
- 小奥 Skill 使用 `--answer-style xiaoao`。
- `--with-report none` 时不依赖飞书环境。
- 205 上若未配置飞书 CLI，仍可回答短摘要。

### 16.2 205 部署后验收

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
- 飞书链接可打开；如果当前 batch 找不到该 SKU，必须返回业务化边界提示。
- 飞书报告的“四个产品横向详细对比 - 卖点画像”和各产品“卖点画像”中出现 M12C 卖点溢价指数；若 latest 批次 M12C 未准备好，报告必须显示“卖点价值量化待生成”。

## 17. 后续扩展

首版聚焦“竞品有哪些”和“为什么第一款是首选竞品”。后续可以扩展：

1. `competitor-explain`：专门解释某个候选为什么入选或未入选。
2. `competitor-report --target feishu-base`：把详细矩阵写入飞书多维表格。
3. 飞书卡片二次选择：当 SKU 模糊匹配时让用户点选。
4. 不同品类的价值锚点配置：空调、洗衣机等按品类独立维护。
5. 报告页面图表化：购买池散点、战场重合雷达、候选分桶矩阵。
