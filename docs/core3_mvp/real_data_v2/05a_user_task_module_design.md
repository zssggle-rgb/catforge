# 05a 用户任务独立模块详细设计

## 1. 模块定位

用户任务模块是独立模块，不是评论主题模块的附属，也不是价值战场模块里的一个字段。

它回答：

```text
这个 SKU 主要帮助哪些用户在什么场景下完成什么任务？
这些任务是否有参数、卖点、评论和市场共同支撑？
这些任务是否足够强，能支撑客群和价值战场判断？
```

用户任务不能直接从评论句贴标签，也不能只靠 seed 写死。它必须综合四类输入：

- 参数信号。
- 卖点信号。
- 评论任务线索。
- 市场信号。

## 2. 模块输入

### 2.1 预制资产输入

来自 approved seed 或已批准资产：

```text
category_asset_user_task
category_asset_mapping(param -> task)
category_asset_mapping(claim -> task)
category_asset_mapping(comment_topic -> task)
category_asset_mapping(task -> target_group)
category_asset_mapping(task -> battlefield)
```

用户任务定义必须包含：

```text
task_code
task_name
definition
positive_param_codes
positive_claim_codes
positive_comment_signal_rules
required_or_core_signals
negative_or_weak_signals
market_signal_rule
score_rule
mapped_target_group_codes
mapped_battlefield_codes
review_status
asset_version
```

### 2.2 参数输入

来自参数模块：

- `core3_extract_param_value`
- `core3_sku_semantic_profile.standard_params_json`

用户任务关心的参数不是全部参数，而是任务相关参数。

示例：

| 用户任务 | 需要的参数信号 |
| --- | --- |
| 大屏家庭观影 | 尺寸、分辨率、亮度、HDR、音响 |
| 游戏娱乐 | 刷新率、HDMI2.1、VRR、ALLM、输入延迟 |
| 体育观看 | 刷新率、运动补偿、亮度、抗反光 |
| 长辈易用 | 语音、系统流畅、遥控、长辈模式 |
| 护眼观看 | 低蓝光、无频闪、亮度调节、护眼认证 |
| 影音沉浸 | 大屏、音响功率、杜比、HDR |

### 2.3 卖点输入

来自卖点模块：

- `core3_sku_claim_activation`
- `core3_comment_claim_evidence`

卖点提供“产品是否具备完成任务的能力”。

示例：

| 用户任务 | 需要的卖点 |
| --- | --- |
| 游戏娱乐 | 高刷新率、HDMI2.1、低延迟、游戏模式 |
| 大屏家庭观影 | 大屏沉浸、高亮 HDR、音画增强 |
| 体育观看 | 运动流畅、高刷、MEMC、抗拖影 |
| 长辈易用 | 语音操控、简单系统、开机便捷 |
| 大屏性价比购买 | 大尺寸、价格优势、基础画质够用 |

### 2.4 评论输入

来自评论独立模块，不直接读原始评论：

- `core3_comment_task_signal`
- `core3_comment_topic_hit`
- `core3_comment_group_signal`
- `core3_comment_pain_risk_signal`
- `core3_comment_price_value_signal`
- `core3_sku_comment_profile`

用户任务模块从评论中消费的是“任务线索”，不是粗主题。

任务线索必须包含：

```text
scene
action
actor
object
desired_outcome
pain_constraint
polarity
specificity_score
evidence_id
```

### 2.5 市场输入

来自市场画像：

- `core3_sku_market_profile`
- 同尺寸/同价位可比池。
- 渠道占比。
- 销量/销额分位。
- 价格带。
- 价格趋势。
- 销量趋势。

市场信号说明“这个任务是否被市场验证”，不能只靠语义判断。

## 3. 模块输出

### 3.1 SKU 任务得分表：`core3_sku_task_score`

字段：

```text
score_id
batch_id
project_id
category_code
sku_code
task_code
task_name
score
relation_level          -- main/secondary/weak/insufficient
param_signal_score
claim_signal_score
comment_signal_score
market_signal_score
component_scores_json
comment_signal_summary_json
missing_signals_json
negative_signals_json
evidence_ids_json
rule_version
asset_version
confidence
created_at
updated_at
```

### 3.2 任务候选表：`core3_candidate_asset(asset_type=user_task)`

用于从数据中发现 seed 之外的新任务。

字段沿用候选资产通用结构，但 `candidate_payload_json` 必须包含：

```text
candidate_task_name
scene_phrases
action_phrases
actor_phrases
related_claim_codes
related_param_codes
related_comment_topic_codes
market_support_json
example_sku_codes
example_sentence_ids
suggested_target_groups
suggested_battlefields
```

候选任务不直接参与高置信竞品结果，除非复核通过或映射到已批准任务。

## 4. 用户任务生成分两条链路

### 4.1 已批准任务的 SKU 得分链路

用于当前 MVP 报告。

```text
approved task definition
  -> 读取该任务需要的参数/卖点/评论/市场信号
  -> 计算四类 signal score
  -> 计算任务总分
  -> 输出 SKU 任务得分和证据
```

### 4.2 新任务候选发现链路

用于 CatForge 资产生产，不直接进入领导报告。

```text
评论任务短语 + 高频卖点组合 + 参数组合 + 高销量可比池
  -> 共现聚合
  -> 候选任务命名
  -> 生成候选任务资产
  -> 进入复核
```

两条链路不能混淆：

- 已批准任务用于稳定分析。
- 新任务候选用于扩展资产库。

## 5. 评论如何为用户任务提供输入

### 5.1 评论任务信号抽取

用户任务模块只消费 `core3_comment_task_signal`。

该表由评论模块独立生成，不能在用户任务模块里重新解析原始评论。

### 5.2 任务信号质量

一条评论任务信号的质量分：

```text
comment_task_signal_quality =
  specificity_score * 0.35
  + entity_completeness * 0.25
  + polarity_confidence * 0.20
  + dedup_weight * 0.10
  + source_quality * 0.10
```

其中：

- `specificity_score`：是否明确描述使用任务。
- `entity_completeness`：是否包含场景、动作、对象、人群、结果中的多个元素。
- `polarity_confidence`：情感和否定是否明确。
- `dedup_weight`：重复评论降权。
- `source_quality`：过滤默认好评和低价值短句。

### 5.3 SKU 级评论任务分

对每个 SKU 和任务：

```text
comment_signal_score =
  min(1, weighted_positive_task_mentions / task_comment_denominator)
  * specificity_adjustment
  * sentiment_adjustment
  * diversity_adjustment
  - negative_penalty
```

说明：

- `weighted_positive_task_mentions`：与该任务相关的正向任务信号。
- `task_comment_denominator`：有效评论句数或同类可比池归一化分母。
- `specificity_adjustment`：明确任务句权重高于泛泛好评。
- `sentiment_adjustment`：正向增强，负向削弱。
- `diversity_adjustment`：多个不同评论支持高于同一模板重复。
- `negative_penalty`：与任务相关的风险扣分。

### 5.4 示例：游戏娱乐任务

评论任务信号：

```text
打游戏很流畅
连 PS5 没有延迟
看球不卡
运动画面不拖影
```

对应信号：

```text
scene/action: 游戏、体育、看球
object: PS5、球赛
outcome: 流畅、不卡、低延迟
pain negative: 拖影、卡顿、延迟
```

评论任务分只说明用户感知，不替代参数：

```text
如果评论强但缺高刷/HDMI 参数：
  任务分可以中等，但任务置信度降低。

如果参数强但评论缺失：
  任务分可由参数和卖点支撑，但标记评论验证不足。
```

## 6. 四类信号计算

### 6.1 参数信号

```text
param_signal_score =
  weighted_avg(required_param_level_scores)
```

任务定义中要声明：

- 核心参数。
- 可选参数。
- 参数分档。
- 冲突处理。

示例：游戏娱乐任务

```text
native_refresh_rate_hz >= 120 -> 0.70
native_refresh_rate_hz >= 144 -> 0.85
hdmi_2_1_ports >= 1 -> 0.70
vrr_flag=true -> 0.80
input_lag_ms <= 10 -> 0.85
```

### 6.2 卖点信号

```text
claim_signal_score =
  weighted_avg(related_claim_activation_scores)
```

每个任务定义相关卖点权重。

示例：大屏家庭观影

```text
大屏沉浸 0.30
高亮 HDR 0.25
音画增强 0.20
清晰画质 0.15
智能投屏 0.10
```

### 6.3 评论信号

来自 `core3_comment_task_signal` 和相关风险信号。

```text
comment_signal_score =
  positive_task_signal_score
  + topic_validation_score * 0.20
  - pain_risk_penalty
```

评论主题只能辅助，不能替代任务信号。

### 6.4 市场信号

市场信号按任务定义不同：

| 用户任务 | 市场信号 |
| --- | --- |
| 游戏娱乐 | 线上渠道占比、高刷可比池销量、年轻化渠道表现 |
| 大屏家庭观影 | 大尺寸池销量、销售额、客厅升级价格带 |
| 大屏性价比 | 同尺寸低价分位、销量强度、价格下探 |
| 高端画质升级 | 高价位销售额、画质卖点溢价支撑 |
| 长辈易用 | 销量稳定、服务/安装反馈、低退货风险 |

首版没有更细渠道时，使用现有渠道和价格/销量分位。

## 7. 任务总分

默认：

```text
task_score =
  claim_signal_score * 0.35
  + param_signal_score * 0.25
  + comment_signal_score * 0.25
  + market_signal_score * 0.15
```

可以按任务调整：

- 技术强任务提高参数权重。
- 体验强任务提高评论权重。
- 价格购买任务提高市场和价格感知权重。

unknown 重归一：

```text
known_weight_sum = sum(weights where signal known)
task_score = known_weighted_score / known_weight_sum
confidence = base_confidence * known_weight_sum / total_weight
```

## 8. 任务关系级别

```text
主要任务: score >= 0.75 且 confidence >= 0.70
次要任务: 0.55 <= score < 0.75
弱相关: 0.35 <= score < 0.55
证据不足: score < 0.35 或 confidence < 0.40
```

如果参数、卖点、评论、市场只有单一来源支撑，不能输出高置信主要任务。

## 9. 首版用户任务目录

首版 seed 应完整预制以下任务，数据负责激活和校准：

| task_code | 业务名称 | 核心判断 |
| --- | --- | --- |
| `TASK_LARGE_SCREEN_FAMILY_VIEWING` | 大屏家庭观影 | 大尺寸、画质、音效、家庭/客厅评论 |
| `TASK_PREMIUM_PICTURE_UPGRADE` | 高端画质升级 | 高亮、分区、Mini LED/OLED、画质评论、价格支撑 |
| `TASK_GAMING_ENTERTAINMENT` | 游戏娱乐 | 高刷、HDMI2.1、低延迟、游戏评论 |
| `TASK_SPORTS_WATCHING` | 体育观看 | 运动流畅、看球不卡、刷新率、亮度 |
| `TASK_CINEMA_AUDIO_IMMERSION` | 影院沉浸 | HDR、音响、杜比、大屏、观影评论 |
| `TASK_EYE_CARE_FAMILY_VIEWING` | 家庭护眼观看 | 护眼参数、舒适评论、负面低 |
| `TASK_SENIOR_EASY_USE` | 长辈易用 | 语音、简单操作、长辈评论、服务支持 |
| `TASK_SMART_SYSTEM_DAILY_USE` | 智能系统日用 | 系统流畅、投屏、语音、应用生态 |
| `TASK_LARGE_SCREEN_VALUE_PURCHASE` | 大屏性价比购买 | 同尺寸低价、销量强、价格好评 |
| `TASK_DESIGN_HOME_FIT` | 家居融入 | 外观、薄机身、挂装、客厅适配 |
| `TASK_SERVICE_ASSURED_PURCHASE` | 省心安装购买 | 安装、送货、售后、服务评论 |

这些任务不是最终写死到 SKU 上，而是作为 approved task ontology。

## 10. 用户任务候选生成

### 10.1 候选来源

候选任务从以下共现中发现：

- 高频评论任务短语。
- 高频卖点组合。
- 参数组合。
- 高销量 SKU 的共同特征。
- 特定价格带或渠道的集中购买动机。

### 10.2 候选生成条件

进入候选任务：

- 覆盖 SKU 数达到阈值。
- 任务短语有明确场景或动作。
- 至少有一种非评论证据支撑。
- 与现有任务边界不同。
- 有代表 SKU 和样例句。

### 10.3 候选不自动生效

候选任务只进入：

- 候选资产表。
- 复核队列。
- 内部诊断页面。

不进入高层报告的主结论，除非复核批准。

## 11. 给页面的业务呈现

页面不展示公式，展示推导链：

```text
系统判断 85E7Q 的主要任务是“大屏家庭观影”。

参数依据：85 英寸大屏、画质和音效配置满足家庭观影。
卖点依据：高亮画质和大屏沉浸卖点被激活。
评论依据：用户反馈集中在画质清晰、屏幕大、观看体验好。
市场依据：同尺寸价格带内销量和销售额具备支撑。

游戏娱乐为次要任务：参数具备一定高刷基础，但游戏评论和接口证据不足，暂不作为主任务。
```

## 12. 模块实现建议

服务拆分：

```text
task_module/
  task_asset_loader.py
  task_signal_collector.py
  comment_task_signal_reader.py
  task_score_engine.py
  task_candidate_miner.py
  task_evidence_builder.py
```

核心函数：

```text
load_task_assets(project_id, asset_version)
collect_task_inputs(batch_id, sku_codes)
score_sku_tasks(task_assets, sku_inputs)
mine_task_candidates(batch_id)
write_task_scores(batch_id, scores)
```

## 13. 验收

1. 用户任务模块有独立输入、输出和表结构。
2. 评论只通过 `core3_comment_task_signal` 进入用户任务模块。
3. 评论主题不能直接等同用户任务。
4. 参数、卖点、评论、市场四类信号都能显示缺失和置信度。
5. 修改一条“连 PS5 打游戏很流畅”评论，应只影响对应 SKU 的评论任务信号、游戏娱乐任务分、相关战场和竞品分。
6. 新任务候选不会自动进入高置信报告。

