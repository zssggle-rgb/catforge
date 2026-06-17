# 04a 评论基础证据与下游独立抽取模块

## 1. 重新定义评论处理边界

评论不能在一次“产品体验/服务体验/物流安装/价格感知/未知”分类里被消费完。

这类分类只能是 `comment_domain_hint`，用于给后续模块参考，不能作为最终任务、客群、战场或卖点结论。

正确分层：

```text
评论原文
  -> 评论清洗与分句
  -> 评论基础证据原子
  -> 按用途独立抽取
      -> 参数弱提示
      -> 卖点体验验证
      -> 评论主题
      -> 用户任务线索
      -> 目标客群线索
      -> 价值战场支撑
      -> 痛点风险
      -> 价格价值感知
      -> 服务保障信号
  -> SKU 级评论画像
  -> 下游任务/客群/战场/竞品模块消费
```

原则：

1. 基础评论层只做事实切分和轻量标注，不生成业务结论。
2. 每个下游业务对象有独立抽取模块、独立输入、独立输出表、独立置信度。
3. 同一句评论可以同时服务多个模块，但 evidence_id 必须一致。
4. 评论不能单独证明硬规格，只能作为体验证据或弱提示。
5. 评论抽取结果要能被参数、卖点、市场数据交叉验证。

## 2. 评论基础证据层

### 2.1 输入

- `core3_clean_comment_fact`
- `core3_clean_comment_sentence`
- `core3_clean_comment_dimension_fact`

### 2.2 输出表

#### `core3_comment_evidence_atom`

每个评论句生成一个基础证据原子。

字段：

```text
atom_id
batch_id
project_id
category_code
sku_code
comment_id
sentence_id
sentence_text
sentence_hash
comment_domain_hint       -- product/service/logistics/price/unknown，仅参考
sentiment_hint            -- positive/negative/neutral/mixed，仅参考
intensity_score           -- 情绪强度或强调程度
negation_scope_json
raw_dimension_path_json
source_evidence_id
quality_flags_json
created_at
```

`comment_domain_hint` 只是基础提示：

- 它可以帮助卖点模块排除明显服务句。
- 它可以帮助服务保障模块召回服务句。
- 它不能直接生成“用户任务=游戏”“客群=老人”“战场=服务保障”。

### 2.3 基础实体表

#### `core3_comment_entity`

字段：

```text
entity_id
atom_id
sku_code
entity_type             -- scene / actor / action / object / outcome / pain / spec / price / service / channel
entity_text
entity_norm
start_pos
end_pos
confidence
extractor_version
created_at
```

实体类型说明：

| entity_type | 含义 | 示例 |
| --- | --- | --- |
| `scene` | 使用场景 | 客厅、卧室、白天、晚上、看球、打游戏 |
| `actor` | 使用人群 | 老人、孩子、父母、家人、玩家 |
| `action` | 用户动作 | 看电影、追剧、投屏、连游戏机、K 歌 |
| `object` | 观看或连接对象 | 球赛、PS5、Switch、电视剧、电影 |
| `outcome` | 期望结果 | 清晰、流畅、震撼、简单、护眼 |
| `pain` | 痛点 | 卡顿、反光、刺眼、广告多、操作复杂 |
| `spec` | 规格弱提示 | 大屏、高刷、亮、音响好 |
| `price` | 价格感知 | 划算、贵、优惠、性价比 |
| `service` | 服务安装 | 安装、送货、售后、挂装 |

### 2.4 基础短语表

#### `core3_comment_phrase`

字段：

```text
phrase_id
atom_id
sku_code
phrase_text
phrase_norm
phrase_type             -- task_phrase / group_phrase / claim_phrase / pain_phrase / price_phrase / service_phrase
confidence
created_at
```

基础短语只记录“评论里出现了什么”，不直接判断属于哪个任务或战场。

## 3. 下游独立抽取模块总览

| 模块 | 主要回答 | 输出表 | 是否可直接进入结论 |
| --- | --- | --- | --- |
| 参数弱提示抽取 | 用户评论是否提到规格体验 | `core3_comment_param_hint` | 否，只能弱提示 |
| 卖点体验验证 | 用户是否感知到某卖点 | `core3_comment_claim_evidence` | 可参与卖点分 |
| 评论主题抽取 | 评论集中在哪些体验主题 | `core3_comment_topic_hit` | 可参与主题画像 |
| 用户任务线索抽取 | 用户在什么场景下完成什么任务 | `core3_comment_task_signal` | 只能给任务模块输入 |
| 目标客群线索抽取 | 评论是否出现使用人群和购买动机 | `core3_comment_group_signal` | 只能给客群模块输入 |
| 价值战场支撑抽取 | 评论是否支撑某战场关键矛盾 | `core3_comment_battlefield_signal` | 只能给战场模块输入 |
| 痛点风险抽取 | 哪些体验可能削弱卖点或任务 | `core3_comment_pain_risk_signal` | 可做扣分/预警 |
| 价格价值感知抽取 | 用户是否认为值、贵、便宜 | `core3_comment_price_value_signal` | 可参与价格/性价比任务 |
| 服务保障信号抽取 | 安装、物流、售后是否影响购买体验 | `core3_comment_service_signal` | 可参与服务保障战场 |

这些模块可以顺序执行，也可以并行执行，但不能混成一个“评论分析结果”。

## 4. 参数弱提示抽取模块

### 4.1 目标

从评论中提取用户对规格的体验描述，为参数模块提供弱提示。

评论不能单独证明：

- 真实刷新率。
- 真实亮度数值。
- HDMI 版本。
- 分区数。

但可以提示：

- 用户感知到大屏。
- 用户觉得画面亮。
- 用户觉得运动画面流畅。
- 用户觉得声音大或沉浸。

### 4.2 输入

- `core3_comment_evidence_atom`
- `core3_comment_entity`
- `core3_comment_phrase`
- 标准参数定义。

### 4.3 输出：`core3_comment_param_hint`

字段：

```text
hint_id
batch_id
sku_code
param_code
hint_type              -- perceived_large_screen / perceived_brightness / perceived_smoothness / perceived_audio_power
polarity               -- positive/negative/neutral
strength
atom_id
evidence_id
confidence
created_at
```

### 4.4 示例

```text
评论：“屏幕很大，看球很爽”
输出：
  screen_size_inch: perceived_large_screen, positive
  motion_smoothness: perceived_smoothness, positive
```

## 5. 卖点体验验证模块

### 5.1 目标

判断用户评论是否验证某个标准卖点的真实体验。

### 5.2 输入

- 标准卖点定义。
- `core3_sku_param_normalized`
- `core3_extract_claim_hit`
- 评论基础证据。
- 评论参数弱提示。

### 5.3 输出：`core3_comment_claim_evidence`

字段：

```text
evidence_id
batch_id
sku_code
claim_code
comment_evidence_type   -- validation / complaint / contradiction / weak_hint
polarity
strength
matched_entities_json
atom_id
source_evidence_id
confidence
created_at
```

### 5.4 规则

- “看球不卡”可以验证高刷/运动流畅体验。
- “画面刺眼”会削弱护眼相关卖点。
- “安装师傅专业”不能验证画质卖点。
- “很亮”只能作为亮度感知，不证明具体 nits。

## 6. 评论主题抽取模块

### 6.1 目标

从评论中形成稳定的体验主题库和 SKU 级主题画像。

### 6.2 输入

- 评论基础证据。
- 预制评论主题。
- 候选主题短语。
- 原始维度弱标签。

### 6.3 输出

- `core3_comment_topic_hit`
- `core3_sku_comment_topic_summary`
- `core3_candidate_asset(asset_type=comment_topic)`

### 6.4 设计要求

评论主题是“体验主题”，不是用户任务，也不是价值战场。

示例：

| 评论句 | 主题 |
| --- | --- |
| 看球不卡 | 运动流畅 |
| 老人也会用 | 操作易用 |
| 白天看也清楚 | 亮度表现 |
| 安装很快 | 安装服务 |
| 价格划算 | 价格价值感知 |

## 7. 用户任务线索抽取模块

### 7.1 目标

从评论中抽取“用户在什么场景下，为谁，用电视完成什么事情，以及希望得到什么结果”。

它不直接输出最终用户任务分，只输出任务线索，供用户任务模块消费。

### 7.2 需要从评论中提取的内容

| 抽取对象 | 说明 | 示例 |
| --- | --- | --- |
| 使用场景 | 在哪里、什么时候、什么内容 | 客厅、卧室、白天、晚上、球赛、电影 |
| 使用动作 | 用户用电视做什么 | 看球、追剧、打游戏、投屏、K 歌 |
| 使用对象 | 连接或观看对象 | PS5、Switch、手机、电影、体育比赛 |
| 目标结果 | 用户希望获得的价值 | 流畅、震撼、清晰、简单、护眼 |
| 使用人群 | 谁在使用 | 老人、孩子、父母、全家、玩家 |
| 痛点约束 | 任务中的阻碍 | 卡顿、反光、刺眼、操作复杂 |
| 评价极性 | 任务是否被满足 | 正向、负向、中性 |

### 7.3 输出：`core3_comment_task_signal`

字段：

```text
signal_id
batch_id
sku_code
task_signal_type        -- scene / action / actor / desired_outcome / pain_constraint
task_code_hint
scene_entities_json
action_entities_json
actor_entities_json
outcome_entities_json
pain_entities_json
polarity
specificity_score       -- 是否是明确任务句
strength
atom_id
source_evidence_id
confidence
created_at
```

### 7.4 任务线索判断

高质量任务线索需要至少满足两类元素：

```text
场景/动作 + 目标结果
动作 + 使用对象
使用人群 + 动作
痛点 + 目标结果
```

低质量线索示例：

```text
不错
满意
很好
```

这些只能作为情感证据，不能作为任务线索。

### 7.5 示例

```text
评论：“给爸妈买的，语音操作很方便”
输出：
  actor=爸妈
  action=语音操作
  outcome=方便
  task_code_hint=TASK_SENIOR_EASY_USE
  polarity=positive
```

```text
评论：“连 PS5 打游戏很流畅”
输出：
  object=PS5
  action=打游戏
  outcome=流畅
  task_code_hint=TASK_GAMING_ENTERTAINMENT
  polarity=positive
```

## 8. 目标客群线索抽取模块

### 8.1 目标

从评论中抽取人群、购买动机和使用关系，供目标客群模块消费。

### 8.2 输出：`core3_comment_group_signal`

字段：

```text
signal_id
batch_id
sku_code
group_code_hint
actor_entities_json
purchase_motivation_json
usage_context_json
price_sensitivity
polarity
atom_id
source_evidence_id
confidence
created_at
```

### 8.3 可抽取人群

首版应覆盖：

- 家庭观影升级用户。
- 游戏体育用户。
- 长辈易用用户。
- 亲子家庭用户。
- 大屏性价比用户。
- 影音沉浸用户。
- 智能便捷用户。
- 服务敏感用户。

评论只提供客群线索，最终客群还要结合任务、价格带、渠道和市场表现。

## 9. 价值战场支撑抽取模块

### 9.1 目标

从评论中抽取“竞争矛盾是否被用户感知”，供价值战场模块消费。

### 9.2 输出：`core3_comment_battlefield_signal`

字段：

```text
signal_id
batch_id
sku_code
battlefield_code_hint
support_type            -- support / weaken / contradiction / opportunity
related_task_signal_ids_json
related_claim_evidence_ids_json
polarity
strength
atom_id
source_evidence_id
confidence
created_at
```

### 9.3 示例

```text
高端画质战场：
  评论支撑：白天看也清楚、画面通透、颜色好
  评论削弱：反光、漏光、刺眼

游戏体育战场：
  评论支撑：看球不卡、打游戏流畅、延迟低
  评论削弱：拖影、卡顿、连主机麻烦
```

## 10. 痛点风险抽取模块

### 10.1 目标

识别会削弱任务、卖点或战场的风险。

### 10.2 输出：`core3_comment_pain_risk_signal`

字段：

```text
risk_id
batch_id
sku_code
risk_type               -- picture_risk / motion_risk / system_risk / eye_care_risk / service_risk / price_risk
risk_text
severity
frequency
atom_id
source_evidence_id
confidence
created_at
```

## 11. 价格价值感知模块

### 11.1 目标

抽取用户对价格、优惠、性价比和心理预期的表达。

### 11.2 输出：`core3_comment_price_value_signal`

字段：

```text
signal_id
batch_id
sku_code
price_signal_type       -- value_for_money / expensive / discount / worth_premium / price_sensitive
polarity
strength
atom_id
source_evidence_id
confidence
created_at
```

用途：

- 支持大屏性价比任务。
- 支持价格/销量挤压竞品解释。
- 辅助判断高端标杆是否具备溢价接受度。

## 12. 服务保障信号模块

### 12.1 目标

服务、物流、安装不是产品卖点，但会影响服务保障战场和购买转化。

### 12.2 输出：`core3_comment_service_signal`

字段：

```text
signal_id
batch_id
sku_code
service_signal_type     -- installation / delivery / after_sales / wall_mount / professional_service
polarity
severity_or_strength
atom_id
source_evidence_id
confidence
created_at
```

## 13. SKU 级评论画像汇总

每个独立模块输出后，再统一汇总为：

```text
core3_sku_comment_profile
```

字段：

```text
profile_id
batch_id
sku_code
topic_summary_json
task_signal_summary_json
group_signal_summary_json
battlefield_comment_summary_json
claim_comment_summary_json
pain_risk_summary_json
price_value_summary_json
service_summary_json
sample_sentence_ids_json
missing_signals_json
confidence
created_at
```

注意：这个汇总只是给下游消费和页面展示，不替代各独立模块的明细表。

## 14. 实施验收

1. “产品体验/服务体验/物流安装/价格感知/未知”只作为 `comment_domain_hint`，不能直接生成最终业务结论。
2. 用户任务线索有独立输出表，不能混在评论主题里。
3. 客群线索有独立输出表，不能只从任务名称反推。
4. 战场评论支撑有独立输出表，必须区分支撑、削弱、冲突和机会。
5. 同一句评论可以支持多个模块，但每个模块输出自己的置信度和用途。
6. 修改评论抽取规则后，可以只重跑评论模块和受影响下游，不必重跑参数清洗。

