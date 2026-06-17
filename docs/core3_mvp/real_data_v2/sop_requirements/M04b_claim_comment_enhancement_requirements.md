# M04b 评论验证增强 SOP 需求

## 0. 单模块强化状态

本文件已按“单模块逐一强化”要求完成第一轮强化。下一步应处理 M07 市场画像与可比池基线。

## 1. 模块目标

M04b 在 M04a 基础卖点激活之后，只使用 M06 的 `claim_validation` 评论信号，对卖点做体验验证、削弱、风险标记和最终置信度调整。

M04b 要解决五个问题：

1. 把“参数 + 宣传”的基础卖点能力，与“用户评论是否感知到该体验”分开保存。
2. 对体验型卖点，允许评论显著增强或削弱最终激活。
3. 对技术型卖点，评论只能验证体验表现，不能证明硬规格。
4. 对没有结构化卖点的 SKU，例如 85E7Q，允许评论增强参数型卖点的体验置信度，但必须保留 `param_only` 和 `missing_structured_claim` 风险。
5. 为 M08、M09、M11、M11.5、M13、M15 提供最终可引用的卖点激活结果和评论验证证据。

## 2. 设计依据

本模块依据：

- `cankao/CatForge_竞品生成SOP_详细指导_v1.md` 的 M04 拆分要求。
- M04a 已强化后的基础卖点激活设计。
- M06 已强化后的七类评论下游信号设计。
- [00 真实样例数据基线](00_real_data_baseline.md)。
- 项目现有彩电 seed：`standard_claims`。

## 3. 上游输入

### 3.1 必须输入

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| `core3_sku_claim_activation_base` | M04a | 基础卖点激活分、参数分、宣传分、缺失信号 |
| `core3_sku_claim_source_status` | M04a | 是否有结构化卖点、是否参数-only |
| `core3_comment_downstream_signal` | M06 | 只消费 `signal_type=claim_validation` |
| `core3_comment_signal_candidate` | M06 | 可选，用于解释代表评论句 |
| `core3_evidence_atom` | M02 | 参数、宣传、评论、质量 evidence 追溯 |
| `standard_claims` seed | 彩电 seed | 卖点类型、映射关系和增强权重 |

### 3.2 明确不消费

| 数据 | 处理 |
| --- | --- |
| 原始 `comment_data` | 不读取 |
| M05 基础主题 | 不直接作为最终卖点验证，必须通过 M06 `claim_validation` |
| 市场量价 | 不消费，卖点价值和价格支撑由 M11.5/M13 处理 |
| 用户任务/客群/战场结果 | 不消费，M04b 是它们的上游 |

## 4. 本模块不做什么

- 不重新解析原始评论。
- 不重新计算 M04a 的参数分和宣传分。
- 不用评论证明硬规格，例如 5200 nits、3500 分区、HDMI2.1 接口数、原生刷新率。
- 不把服务安装评论用于增强画质、游戏、护眼、音效等产品卖点。
- 不做战场内卖点价值分层，M11.5 负责。
- 不判断用户任务、目标客群、价值战场或竞品。
- 不把评论好评直接等同于卖点成立。

## 5. 输入边界

M04b 只接受 M06 的 `claim_validation`：

```text
M06 signal_type = claim_validation
target_code_hint = CLAIM_*
```

其他评论信号的处理边界：

| M06 信号 | M04b 是否消费 | 原因 |
| --- | --- | --- |
| `task_cue` | 不消费 | M09 使用 |
| `target_group_cue` | 不消费 | M10 使用 |
| `battlefield_support` | 不消费 | M11 使用 |
| `pain_point` | 只在已映射为 claim_validation 时消费 | 普通风险由 M08/M11/M13 使用 |
| `price_perception` | 不消费 | 价格价值由 M09/M13 结合市场判断 |
| `service_signal` | 只允许映射到 `CLAIM_INSTALLATION_SERVICE_ASSURANCE` | 不能增强产品技术卖点 |

## 6. 卖点类型与评论权重

M04b 需要按卖点类型处理评论权重。

| 卖点类型 | 示例 | 评论作用 | 建议权重 |
| --- | --- | --- | --- |
| 硬规格技术型 | Mini LED、OLED、HDMI2.1、亮度、分区、高刷 | 只验证体验，不证明规格 | 低 |
| 技术体验混合型 | 高刷新率、护眼、音效、智能语音 | 可验证实际体验 | 中 |
| 体验/场景型 | 大屏沉浸、体育运动流畅、长辈友好 | 评论可显著增强或削弱 | 高 |
| 服务型 | 安装服务保障 | 评论可作为核心证据 | 高 |
| 价值型 | 高性价比、节能省电 | 评论只能代表感知，仍需市场/参数补证 | 中低 |

评论权重不能覆盖 M04a 的基础证据缺口。例如没有 HDMI2.1 参数时，评论“打游戏挺好”不能生成高置信 HDMI2.1 卖点。

## 7. 处理流程

### 7.1 读取基础卖点

以 M04a 输出为主表：

- `claim_code`
- `claim_group`
- `param_score`
- `promo_score`
- `base_activation_score`
- `activation_basis`
- `missing_signals`
- `confidence`
- `evidence_ids`

如果某个 `claim_validation` 评论信号没有对应 M04a 基础卖点，M04b 可以生成 `comment_only_claim_hint` 进入复核，但不得直接生成高置信最终激活。

### 7.2 聚合评论验证

按 `sku_code + claim_code` 聚合 M06 的 `claim_validation` 信号：

- 提及数。
- 提及率。
- 正向率。
- 负向率。
- 平均具体程度。
- 代表评论短句。
- 评论 evidence。
- 服务/产品域一致性。

低价值评论、重复评论、服务错配评论必须降权。

### 7.3 判断评论作用

评论对卖点有三种作用：

| 作用 | 条件 | 处理 |
| --- | --- | --- |
| 增强 | 正向提及率、具体程度、证据质量达标 | 提升体验置信度 |
| 削弱 | 负向提及集中，且对应同一体验 | 降低最终分，标记风险 |
| 不足 | 评论太少、低价值、弱主题、目标不匹配 | 不改变或轻微降置信 |

### 7.4 技术规格保护

硬规格技术型卖点必须保护：

- 评论可以验证“画质好”“看球顺”“接口使用方便”。
- 评论不能证明“5200 nits”“3500 分区”“HDMI2.1 接口数量”“原生刷新率”。
- 如果 M04a 是 `param_only`，评论增强只能提升体验侧置信度，不能补齐宣传证据。
- 如果 M04a 是 `promo_only` 且参数缺失，评论增强后仍需复核。

### 7.5 服务信号隔离

服务安装评论只能增强：

```text
CLAIM_INSTALLATION_SERVICE_ASSURANCE
```

不得增强：

- 高端画质。
- 游戏连接。
- 护眼。
- 音效。
- 智能系统。
- 大屏沉浸。

如果 M06 的服务评论被映射到产品卖点，M04b 必须进入复核。

## 8. 评分规则

### 8.1 评论验证分

```text
comment_validation_score =
  mention_rate_score * 0.30
  + positive_rate_score * 0.25
  + specificity_score * 0.20
  + evidence_quality_score * 0.15
  + domain_match_score * 0.10
```

负向评论生成 `comment_risk_score`：

```text
comment_risk_score =
  negative_rate_score * 0.40
  + risk_specificity_score * 0.30
  + evidence_quality_score * 0.20
  + repeated_issue_score * 0.10
```

### 8.2 最终激活分

硬规格技术型：

```text
final_activation_score =
  base_activation_score * 0.85
  + comment_validation_score * 0.15
  - comment_risk_score * 0.20
  - conflict_penalty
```

技术体验混合型：

```text
final_activation_score =
  base_activation_score * 0.70
  + comment_validation_score * 0.30
  - comment_risk_score * 0.25
  - conflict_penalty
```

体验/场景型：

```text
final_activation_score =
  base_activation_score * 0.55
  + comment_validation_score * 0.45
  - comment_risk_score * 0.30
  - conflict_penalty
```

服务型：

```text
final_activation_score =
  base_activation_score * 0.40
  + comment_validation_score * 0.60
  - comment_risk_score * 0.35
```

价值型：

```text
final_activation_score =
  base_activation_score * 0.70
  + comment_validation_score * 0.30
  - comment_risk_score * 0.20
```

价值型最终商业价值仍需 M07/M11.5/M13 结合市场价格和销量验证。

### 8.3 激活等级

| 等级 | 条件 |
| --- | --- |
| high | 基础证据强，评论验证不冲突，证据完整 |
| medium | 基础证据成立但存在缺口，或评论验证中等 |
| low | 只有单侧证据、评论弱、低置信 |
| unknown | evidence 不足或冲突严重 |
| review_required | 影响下游核心判断但存在证据冲突 |

## 9. 输出数据契约

### 9.1 `core3_sku_claim_comment_validation`

评论验证聚合表，独立保存评论对卖点的体验支撑。

| 字段 | 说明 |
| --- | --- |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `claim_code` | 标准卖点 |
| `claim_name` | 中文卖点 |
| `claim_group` | 卖点类型 |
| `mention_count` | 去重评论单元提及数 |
| `mention_rate` | 提及率 |
| `positive_rate` | 正向率 |
| `negative_rate` | 负向率 |
| `specificity_avg` | 平均具体程度 |
| `comment_validation_score` | 评论验证分 |
| `comment_risk_score` | 评论风险分 |
| `representative_phrases` | 代表评论短句 |
| `comment_signal_ids` | M06 信号 ID |
| `comment_evidence_ids` | 评论 evidence |
| `quality_flags` | 低价值、重复、服务错配等 |
| `confidence` | 评论验证置信度 |

### 9.2 `core3_sku_claim_activation`

最终卖点激活表，供 M08 之后模块消费。

| 字段 | 说明 |
| --- | --- |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `claim_code` | 标准卖点 |
| `claim_name` | 中文卖点 |
| `claim_group` | 卖点类型 |
| `param_score` | M04a 参数分 |
| `promo_score` | M04a 宣传分 |
| `base_activation_score` | M04a 基础分 |
| `comment_validation_score` | 评论验证分 |
| `comment_risk_score` | 评论风险分 |
| `final_activation_score` | 最终激活分 |
| `activation_level` | high/medium/low/unknown/review_required |
| `activation_basis` | param_and_promo/param_only/promo_only/comment_enhanced/comment_only_hint |
| `perception_status` | validated/weak_perception/contradicted/insufficient_comment/not_applicable |
| `missing_signals` | 缺失项 |
| `conflict_flags` | 冲突标记 |
| `confidence` | 最终置信度 |
| `evidence_ids` | 参数、宣传、评论证据 |
| `review_status` | auto/review_required/approved/rejected |
| `rule_version` | 规则版本 |

### 9.3 `core3_claim_comment_review_issue`

| 字段 | 说明 |
| --- | --- |
| `issue_id` | 问题 ID |
| `sku_code` | SKU |
| `claim_code` | 标准卖点 |
| `issue_type` | comment_only/spec_claimed_by_comment/service_mismatch/comment_contradiction/weak_perception |
| `severity` | info/warn/error |
| `business_note` | 中文说明 |
| `evidence_ids` | 相关证据 |
| `suggested_action` | 建议复核动作 |

## 10. 85E7Q 样例要求

85E7Q 当前无结构化卖点，但参数强、评论多。M04b 必须这样处理：

| 情况 | 处理 |
| --- | --- |
| M04a 基于参数输出 Mini LED、高亮、分区、高刷、HDMI 等技术型 `param_only` 候选 | M04b 可以用评论增强体验置信度，但保留 `param_only` 和 `missing_structured_claim` |
| 评论“画面清晰、色彩好、细节好” | 可增强画质体验相关卖点，不证明 5200 nits |
| 评论“看球不卡、运动画面顺” | 可增强体育运动流畅体验，不证明原生刷新率 |
| 评论“语音控制方便、运行流畅” | 可增强智能语音/系统体验，不证明芯片或内存规格 |
| 评论“安装快、师傅专业” | 只进入安装服务保障，不增强画质或游戏卖点 |
| 评论“性价比高、买得值” | 只作为价值感评论，最终价格竞争仍需 M07/M13 验证 |

M04b 不能为 85E7Q 生成伪造宣传 evidence，也不能把评论强行补成结构化卖点。

## 11. 真实数据约束

当前 205 样例数据对 M04b 的硬约束：

- `selling_points_data` 只覆盖 5 个型号，M04b 必须支持大量 SKU 缺结构化卖点。
- 85E7Q 有 3621 行评论、1648 个去重评论 ID，但无卖点行，必须走“参数基础 + 评论体验验证 + 缺宣传降级”的路径。
- 评论表服务安装类占比较高，服务评论必须隔离。
- 评论行有重复和低价值文本，M04b 只能使用 M06 聚合后的有效 `claim_validation` 信号。
- 情感 unknown 或低价值评论不能形成强增强。

## 12. 与下游模块关系

### 给 M08 的承诺

- M08 消费 `core3_sku_claim_activation` 作为 SKU 综合画像的一部分。
- M08 可以区分参数支撑、宣传支撑、评论验证和证据缺口。

### 给 M09/M10 的承诺

- 用户任务和客群可以使用最终卖点激活，但不能忽略 `activation_basis`。
- `comment_only_hint` 和 `param_only` 不能单独支撑高置信任务或客群。

### 给 M11/M11.5 的承诺

- M11 可以使用最终卖点激活判断战场语义支撑。
- M11.5 必须使用最终卖点激活、市场和评论感知做战场内卖点价值分层。
- M04b 不输出“基础门槛/竞争绩效/溢价倾向/弱感知”的价值层级。

### 给 M12-M14 的承诺

- 竞品召回和评分可以使用最终卖点激活，但必须看到评论验证和证据风险。
- 评论验证不能替代参数和市场证据。

### 给 M15 的承诺

- 报告可以展示“用户评论验证了某体验”，但不能写成“评论证明了某硬规格”。
- 对 85E7Q 这类缺结构化卖点的 SKU，报告必须说明宣传卖点数据缺口。

## 13. 复核触发条件

以下情况进入复核：

- 评论单独命中某卖点，但 M04a 没有基础卖点候选。
- 技术规格被评论信号单独支撑。
- 服务评论被映射到产品卖点。
- M04a 基础激活强，但评论负向集中，出现 `contradicted`。
- 宣传强但评论很弱，出现 `weak_perception`。
- `param_only` 卖点会影响核心竞品选择。
- 重点 SKU 结构化卖点缺失但评论增强强。
- 评论验证与参数或宣传明显冲突。

## 14. 增量重算要求

| 输入变化 | M04b 动作 | 下游影响 |
| --- | --- | --- |
| M04a 基础卖点变化 | 重算对应 SKU/claim 最终激活 | M08-M16 |
| M06 `claim_validation` 变化 | 重算评论验证和最终激活 | M08-M16 |
| M06 非 `claim_validation` 变化 | 不触发 M04b | 由对应下游处理 |
| 标准卖点 seed 变化 | 重算受影响 claim | M04b-M16 |
| quality evidence 变化 | 更新置信度和复核状态 | M08、M16 |

如果 `core3_sku_claim_activation` hash 未变化，不触发下游重算。

## 15. 验收标准

| 验收项 | 标准 |
| --- | --- |
| M04b 只消费 M04a 和 M06 `claim_validation` | 必须 |
| 不重新读取原始评论 | 必须 |
| 评论不证明硬规格 | 必须 |
| 服务评论不增强产品卖点 | 必须 |
| 技术型、体验型、服务型、价值型权重不同 | 必须 |
| 输出评论验证聚合表 | 必须 |
| 输出最终卖点激活表 | 必须 |
| 输出评论冲突/弱感知复核问题 | 必须 |
| 85E7Q 保留 `missing_structured_claim` 和 `param_only` 风险 | 必须 |
| 每个最终卖点有 evidence_ids 和置信度 | 必须 |
| M04b 不做卖点价值分层或竞品判断 | 必须 |
