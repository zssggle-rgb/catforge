# M05 评论基础证据层 SOP 需求

## 0. 单模块强化状态

本文件已按“单模块逐一强化”要求完成第一轮强化。下一步应处理 M06 评论下游信号抽取层。

## 1. 模块目标

M05 把 M02 的评论 evidence 转换成可复用的评论基础证据层，解决四个问题：

1. 原始 `comment_data` 存在维度拆行、重复正文、默认评价和低价值文本，需要形成去重后的评论单元。
2. 下游要基于句子抽取卖点验证、任务、客群和战场信号，因此 M05 必须形成句级评论证据。
3. 原始维度和情感可以作为弱标签，但不能直接变成业务结论。
4. 服务、物流、安装、价格、产品体验必须先做基础域提示，避免服务评论被误用于产品卖点或价值战场。

M05 只输出“评论基础证据”和“弱主题提示”。M06 才负责把评论基础证据转换成下游专用信号，例如卖点验证、用户任务、目标客群、价值战场、痛点风险和价格价值感。

## 2. 设计依据

本模块依据：

- `cankao/CatForge_竞品生成SOP_详细指导_v1.md` 的 M05 要求。
- `cankao/catforge_sop_md/modules/M05_评论基础证据层.md`。
- M01 已强化后的评论清洗表。
- M02 已强化后的评论 evidence、维度 evidence、质量 evidence。
- [00 真实样例数据基线](00_real_data_baseline.md)。
- 项目现有彩电 seed：`apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` 中的 `comment_topics`。

## 3. 上游输入

M05 消费 M02 的评论类 evidence：

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| `comment_raw` evidence | M02 | 评论原文、评论 ID、正文 hash、低价值标记 |
| `comment_sentence` evidence | M02 | 评论句文本、句 hash、分句来源 |
| `comment_dimension` evidence | M02 | 原始评论维度路径弱标签 |
| `quality_issue` evidence | M02 | 默认评价、重复、空维度、低价值等质量问题 |
| `comment_topics` seed | 现有彩电 seed | 基础主题弱提示 |

M05 不直接读取原始 `comment_data`，只消费清洗层和 evidence 层产物。

## 4. 本模块不做什么

- 不直接生成用户任务。
- 不直接生成目标客群。
- 不直接生成价值战场。
- 不激活产品卖点。
- 不做评论验证增强，M04b 负责。
- 不判断竞品。
- 不把原始维度路径当成最终主题。
- 不把服务体验用于产品卖点高置信判断。
- 不把情感为空当成中立。

## 5. 预制与抽取边界

### 5.1 必须预制的内容

M05 可以使用基础评论主题 seed，但这些主题只是弱提示，不是业务结论。

首版主题来自 `tv_core3_mvp_seed_v0_2.json` 的 `comment_topics`：

| 主题编码 | 中文主题 | 主题组 |
| --- | --- | --- |
| `TOPIC_PICTURE_QUALITY` | 画质体验 | product_experience |
| `TOPIC_BRIGHTNESS_HDR` | 亮度/HDR | product_experience |
| `TOPIC_DARK_SCENE_CONTRAST` | 暗场/对比度 | product_experience |
| `TOPIC_SPORTS_WATCHING` | 体育观看 | product_experience |
| `TOPIC_GAMING_SMOOTHNESS` | 游戏流畅 | product_experience |
| `TOPIC_EYE_COMFORT` | 护眼舒适 | product_experience |
| `TOPIC_EASE_OF_USE` | 操作易用 | product_experience |
| `TOPIC_SENIOR_FRIENDLY` | 长辈友好 | product_experience |
| `TOPIC_CHILD_FAMILY` | 儿童家庭 | product_experience |
| `TOPIC_INTERFACE_CONNECTIVITY` | 接口连接 | product_experience |
| `TOPIC_AUDIO_QUALITY` | 音质体验 | product_experience |
| `TOPIC_SYSTEM_ADS_PERFORMANCE` | 系统广告/流畅 | product_risk |
| `TOPIC_SIZE_SPACE_FIT` | 尺寸与空间适配 | product_experience |
| `TOPIC_PRICE_VALUE` | 价格价值感 | market_perception |
| `TOPIC_INSTALLATION_SERVICE` | 安装服务 | service_experience |
| `TOPIC_DURABILITY_QUALITY` | 做工耐用 | product_risk |

### 5.2 必须从真实评论抽取的内容

| 抽取内容 | 来源 | 输出 |
| --- | --- | --- |
| 去重评论单元 | `comment_id`、正文 hash、分段 hash | `core3_comment_unit` |
| 句级评论证据 | `comment_sentence` evidence | `core3_comment_evidence_atom` |
| 低价值标记 | 文本规则、quality evidence | 低置信证据 |
| 原始维度弱标签 | `comment_dimension` evidence | 维度路径和弱域提示 |
| 情感弱标签 | 清洗情感 | positive/negative/neutral/unknown |
| 基础主题提示 | seed 关键词 + 原始维度 + 文本短语 | `core3_comment_topic_hint` |
| SKU 评论质量画像 | 去重数、重复率、低价值率、主题分布 | `core3_comment_quality_profile` |

## 6. 处理流程

### 6.1 评论去重单元

M05 先形成评论单元，而不是直接按原始行统计。

去重优先级：

1. 同一 `sku_code + comment_id` 形成一个评论单元。
2. `comment_id` 缺失时，用 `sku_code + comment_text_hash`。
3. 对同一正文、多维度拆行的记录，保留所有来源 evidence，但只作为一个评论单元。
4. 对同一评论中的多个 `comments_segments`，保留分段关系。

M05 不删除重复行，而是记录重复组和来源行数量。

### 6.2 低价值文本标记

低价值文本包括：

- “此用户没有填写评价”。
- “默认好评”。
- 空文本。
- 只有标点或表情。
- 文本过短且无实际评价信息。
- 明显模板化重复文本。

低价值文本可以保留 evidence，但不得形成强主题、强情感或强下游信号。

### 6.3 句级证据生成

句级证据来源：

- M01 系统分句。
- 原始 `comments_segments`。

规则：

- 优先使用系统分句作为统一句级证据。
- `comments_segments` 作为原始分段参考，不替代系统分句。
- 每个句子保留 `source_comment_evidence_id`、`source_sentence_evidence_id` 和原始评论单元。
- 空句、重复句、低价值句必须标记。

### 6.4 弱域提示

M05 可以给每条句子一个或多个弱域提示：

| 弱域 | 含义 |
| --- | --- |
| `product_experience` | 画质、音质、系统、尺寸、接口、护眼等产品体验 |
| `product_risk` | 卡顿、广告、画质差、做工差、故障等风险 |
| `market_perception` | 价格、划算、贵、优惠、性价比等价值感 |
| `service_experience` | 客服、售后、安装、送货、师傅等服务体验 |
| `logistics_installation` | 物流、配送、上门、挂装等送装流程 |
| `unknown` | 无法判断或低价值文本 |

弱域提示不是最终业务标签。M06 必须按不同下游目标重新抽取信号。

### 6.5 情感弱标签

情感规则：

- 原始正面、负面、中立可作为弱标签。
- 空情感必须是 `unknown`，不能当 neutral。
- 文本情感和原始情感冲突时，标记 `sentiment_conflict`。
- 低价值文本情感置信度必须降低。

### 6.6 基础主题提示

M05 可以基于 seed、关键词、原始维度路径、句子文本生成基础主题提示。

要求：

- 输出 `topic_hint`，不是最终 topic 结论。
- 多主题可以并存。
- 服务类主题不能用于产品卖点高置信判断。
- 主题提示必须有句子 evidence。
- 高频 unknown 主题进入复核。

## 7. 输出数据契约

### 7.1 `core3_comment_unit`

| 字段 | 说明 |
| --- | --- |
| `comment_unit_id` | 去重评论单元 ID |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `comment_id` | 原始评论 ID |
| `comment_text_hash` | 正文 hash |
| `source_row_count` | 来源行数 |
| `source_comment_evidence_ids` | 原始评论 evidence |
| `raw_dimension_paths` | 原始维度路径集合 |
| `sentiment_raw_set` | 原始情感集合 |
| `low_value_flag` | 是否低价值 |
| `duplicate_group_id` | 重复组 |
| `quality_flags` | 质量标记 |
| `confidence` | 评论单元可用性 |

### 7.2 `core3_comment_evidence_atom`

| 字段 | 说明 |
| --- | --- |
| `comment_evidence_id` | 评论基础证据 ID |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `comment_unit_id` | 去重评论单元 |
| `comment_id` | 原始评论 ID |
| `sentence_text` | 评论句 |
| `sentence_hash` | 句 hash |
| `sentence_seq` | 句序号 |
| `domain_hints` | 弱域提示 |
| `sentiment_hint` | positive/negative/neutral/unknown |
| `raw_dimension_paths` | 原始维度 |
| `low_value_flag` | 是否低价值 |
| `duplicate_group_id` | 重复组 |
| `specificity_score` | 具体程度 |
| `representative_phrase` | 代表短语 |
| `confidence` | 基础置信度 |
| `source_evidence_ids` | M02 evidence |
| `quality_flags` | 质量标签 |
| `rule_version` | 规则版本 |

### 7.3 `core3_comment_topic_hint`

| 字段 | 说明 |
| --- | --- |
| `topic_hint_id` | 主题提示 ID |
| `comment_evidence_id` | 评论基础证据 |
| `sku_code` | SKU |
| `topic_code` | 基础主题编码 |
| `topic_name` | 中文主题 |
| `topic_group` | product_experience/product_risk/market_perception/service_experience |
| `match_method` | keyword/dimension_path/phrase/seed_rule |
| `matched_terms` | 命中词 |
| `polarity_hint` | positive/negative/neutral/unknown |
| `confidence` | 弱主题置信度 |
| `is_weak_hint` | 必须为 true |

### 7.4 `core3_comment_quality_profile`

| 字段 | 说明 |
| --- | --- |
| `sku_code` | SKU |
| `raw_comment_row_count` | 原始评论行数 |
| `comment_unit_count` | 去重评论单元数 |
| `distinct_comment_text_count` | 去重正文数 |
| `sentence_count` | 评论句数 |
| `low_value_count` | 低价值数 |
| `duplicate_rate` | 重复率 |
| `empty_dimension_count` | 空维度数 |
| `sentiment_distribution_json` | 情感分布 |
| `domain_distribution_json` | 弱域分布 |
| `topic_distribution_json` | 弱主题分布 |
| `quality_summary` | 中文质量摘要 |

## 8. 真实数据约束

当前 205 样例数据对 M05 的硬约束：

- `comment_data` 有 62426 行，但只有 34438 个不同 `comment_id`、13514 个不同正文 hash、20916 个不同 `comments_segments`。
- M05 必须区分原始评论行数、去重评论单元数、去重正文数和句级证据数。
- 空维度约 15766 行，不能因为没有维度就丢弃评论。
- 服务安装类维度占比高，不能把安装、配送、客服好评用于增强画质、游戏、护眼等产品卖点。
- 情感为空的行必须是 unknown。
- 85E7Q 有 3621 行评论、1648 个去重评论 ID，必须能形成可用评论基础证据。
- 85E7Q 评论里服务安装、画质音质、价格价值、智能易用等内容要先拆成不同句级证据和弱域提示，不允许混成一个“好评”。

## 9. 与下游模块关系

### 给 M06 的承诺

- M06 使用 M05 的句级评论证据抽取下游专用信号。
- M05 提供低价值、重复、弱域、弱主题、情感和代表短语，M06 负责转成 claim/task/group/battlefield 等目标信号。

### 给 M04b 的边界

- M04b 不直接消费 M05 原始主题作为最终卖点验证，必须通过 M06 的 `claim_validation` 信号。

### 给 M08/M11/M13 的边界

- M05 的弱域和主题分布可作为质量参考。
- 战场、竞品评分、风险判断必须使用 M06 或更下游的聚合结果，不能直接拿 M05 弱主题当结论。

### 给 M15 的边界

- 报告可以引用 M05 的代表评论短句作为证据展示。
- 报告不能把 M05 主题提示写成最终业务结论。

## 10. 复核触发条件

以下情况进入复核或 warning：

- 高频 unknown 主题。
- 产品/服务边界不清。
- 服务类评论占比异常高，可能淹没产品体验。
- 低价值评论占比异常高。
- 重复正文比例异常高。
- 负面评论集中在目标 SKU。
- 某重点 SKU 评论过少或评论证据不可用。
- 原始维度与文本主题明显冲突。
- 情感为空或冲突比例异常。

## 11. 增量重算要求

| 输入变化 | M05 动作 | 下游影响 |
| --- | --- | --- |
| `comment_raw` evidence 新增/变化 | 重建对应评论单元 | M06、M04b、M08-M16 |
| `comment_sentence` evidence 新增/变化 | 重建句级证据和主题提示 | M06、M04b、M08-M16 |
| `comment_dimension` evidence 新增/变化 | 更新弱维度和域提示 | M06、M16 |
| `quality_issue` evidence 变化 | 更新低价值、重复、置信度 | M06、M16 |
| comment topic seed 变化 | 重算基础主题提示 | M05-M16 |

如果 `core3_comment_evidence_atom` 和 `core3_comment_topic_hint` hash 未变化，不触发下游重算。

## 12. 验收标准

| 验收项 | 标准 |
| --- | --- |
| 评论行数、去重评论数、去重正文数可区分 | 必须 |
| 评论基础证据可追溯到 M02 evidence | 必须 |
| 低价值评论可标记且不形成强信号 | 必须 |
| 原始维度作为弱标签保留 | 必须 |
| 情感空值为 unknown，不当 neutral | 必须 |
| 服务/安装/物流评论不误用于产品卖点 | 必须 |
| 基础主题只是弱提示 | 必须 |
| M05 不输出任务、客群、战场、竞品结论 | 必须 |
| 85E7Q 评论可形成可用句级证据 | 必须 |
| M06 可按下游目标消费 M05 输出 | 必须 |
