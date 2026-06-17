# M06 评论下游信号抽取层 SOP 需求

## 0. 单模块强化状态

本文件已按“单模块逐一强化”要求完成第一轮强化。下一步应处理 M04b 评论验证增强。

## 1. 模块目标

M06 基于 M05 的评论基础证据，按不同下游模块的需要抽取专用评论信号。M06 不是“把评论一次性分析完并生成任务、客群、战场、卖点结论”，而是建立评论到下游模块之间的标准信号接口。

M06 要解决五个问题：

1. 同一句评论可能同时包含场景、动作、人群、结果、痛点和服务信息，需要拆成不同信号。
2. 卖点验证、用户任务、目标客群、价值战场、痛点风险、价格价值、服务保障的信号口径不同，不能混用。
3. 评论只能作为下游判断的支撑或削弱证据，不能单独高置信生成任务、客群、战场或竞品结论。
4. 服务、物流、安装评论必须与产品体验评论隔离，不能增强画质、游戏、护眼等产品卖点。
5. 每个评论信号都必须保留句级 evidence、去重口径、提及率、正负向和置信度。

## 2. 设计依据

本模块依据：

- `cankao/CatForge_竞品生成SOP_详细指导_v1.md` 的 M06 要求。
- `cankao/catforge_sop_md/modules/M06_评论下游信号抽取层.md`。
- M05 已强化后的评论单元、句级评论证据、弱主题提示和评论质量画像。
- M03 标准参数画像和 M04a 基础卖点激活的边界设计。
- [00 真实样例数据基线](00_real_data_baseline.md)。
- 项目现有彩电 seed：`standard_claims`、`user_tasks`、`target_groups`、`battlefields`、`comment_topics`。

## 3. 上游输入

### 3.1 必须输入

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| `core3_comment_unit` | M05 | 去重评论单元和重复口径 |
| `core3_comment_evidence_atom` | M05 | 句级评论证据 |
| `core3_comment_topic_hint` | M05 | 弱主题提示 |
| `core3_comment_quality_profile` | M05 | SKU 评论质量画像 |
| `comment_topics` seed | 彩电 seed | 弱主题到信号的辅助映射 |
| `standard_claims` seed | 彩电 seed | 卖点验证目标 |
| `user_tasks` seed | 彩电 seed | 用户任务信号目标 |
| `target_groups` seed | 彩电 seed | 客群信号目标 |
| `battlefields` seed | 彩电 seed | 战场信号目标 |

### 3.2 可选辅助输入

| 输入 | 用途 | 约束 |
| --- | --- | --- |
| M03 `core3_extract_param_value` | 辅助理解评论提到的规格或功能 | 不能用评论反推硬规格 |
| M04a `core3_sku_claim_activation_base` | 辅助判断评论是否验证已有基础卖点 | 不能让 M04a 依赖 M06，避免循环 |

### 3.3 明确不消费

| 数据 | 处理 |
| --- | --- |
| 原始 `comment_data` | 不直接读取，必须通过 M05 |
| 市场量价 | M06 不消费，价格事实由 M07/M13 处理 |
| M04b 结果 | M06 是 M04b 上游，不能依赖 M04b |

## 4. 本模块不做什么

- 不输出最终用户任务分，M09 负责。
- 不输出最终目标客群分，M10 负责。
- 不输出最终价值战场分，M11 负责。
- 不输出最终卖点激活，M04b 负责。
- 不做战场内卖点价值分层，M11.5 负责。
- 不做候选召回、竞品评分或核心竞品选择。
- 不用评论证明硬规格，例如亮度 5200 nits、3500 分区、HDMI2.1 接口数。
- 不把“安装快、师傅好、物流快”用于增强产品卖点。

## 5. 信号类型总览

M06 输出七类信号，每类信号独立抽取、独立聚合、独立给下游消费：

| 信号类型 | 中文名 | 下游模块 | 主要问题 |
| --- | --- | --- | --- |
| `claim_validation` | 卖点体验验证信号 | M04b | 评论是否验证或削弱基础卖点体验 |
| `task_cue` | 用户任务线索 | M09 | 评论是否出现具体使用任务 |
| `target_group_cue` | 目标客群线索 | M10 | 评论是否出现人群、家庭结构或购买动机 |
| `battlefield_support` | 价值战场支撑/削弱信号 | M11 | 评论是否支持某个竞争语境 |
| `pain_point` | 痛点风险信号 | M08/M11/M13 | 评论是否暴露体验风险 |
| `price_perception` | 价格价值感信号 | M09/M13 | 评论是否表达贵、值、划算或价格压力 |
| `service_signal` | 服务保障信号 | M10/M11/M15 | 评论是否涉及安装、配送、客服、售后 |

M06 允许同一句评论产生多条信号，但必须保留不同 `signal_type` 和不同 `target_code_hint`。

## 6. 共同抽取流程

1. 读取 M05 的有效评论句，排除低价值强信号，仅允许低价值评论形成低置信弱提示。
2. 读取 M05 的弱主题、弱域、情感、代表短语和质量标签。
3. 对每条句子抽取实体：
   - 场景：客厅、卧室、白天、晚上、装修、看球、电影、游戏。
   - 动作：看球、追剧、打游戏、投屏、语音控制、安装、配送。
   - 对象：家人、父母、老人、孩子、PS5、Switch、球赛、电影。
   - 体验结果：清晰、流畅、震撼、方便、护眼、划算、卡顿、反光、复杂。
   - 约束条件：价格、空间、光线、操作复杂、广告、售后。
4. 按七类信号分别运行规则。
5. 计算句级信号分和置信度。
6. 按 SKU、信号类型、目标编码聚合 mention count、mention rate、positive rate、negative rate。
7. 输出句级信号候选、SKU 级评论信号画像和复核提示。

## 7. 七类信号独立设计

### 7.1 卖点体验验证信号 `claim_validation`

目标：给 M04b 验证、增强或削弱 M04a 的基础卖点激活。

输入：

- M05 评论句。
- M05 topic hint。
- M04a 基础卖点候选，可选。
- M03 参数，仅用于辅助区分评论是否对应某类功能。

抽取规则：

| 评论表达 | 可生成信号 | 禁止事项 |
| --- | --- | --- |
| 画面清晰、色彩好、亮度够 | 支持画质体验类卖点 | 不能证明具体 nits |
| 暗场细节好、黑位好 | 支持暗场/控光体验 | 不能证明具体分区数 |
| 看球不卡、运动画面顺 | 支持体育运动流畅体验 | 不能证明原生刷新率 |
| 打游戏流畅、接主机方便 | 支持游戏体验或接口体验 | 不能证明 HDMI2.1 端口数 |
| 语音方便、老人能用 | 支持智能语音/长辈友好体验 | 不能证明硬件配置 |
| 安装快、师傅好 | 只能进入服务信号 | 不进入产品卖点 |

输出 `target_code_hint` 应使用 `CLAIM_*`。

强信号要求：

- 评论句为产品体验域。
- 非低价值、非高度重复。
- 具体程度高。
- 正负向明确。
- 与 M04a 基础卖点或 seed 映射一致。

### 7.2 用户任务线索 `task_cue`

目标：给 M09 判断用户任务提供评论线索。M06 只输出线索，不输出任务分。

任务线索必须抽取“场景 + 动作/对象 + 结果/约束”中的至少两类信息，避免把单个词贴成任务。

| 任务编码 | 典型评论线索 |
| --- | --- |
| `TASK_LIVING_ROOM_CINEMA` | 客厅、电影、追剧、音画震撼、全家观看 |
| `TASK_PREMIUM_PICTURE_AV` | 画质、清晰、色彩、亮度、暗场、影音 |
| `TASK_GAMING_ENTERTAINMENT` | 游戏、主机、PS5、Switch、低延迟、接口 |
| `TASK_SPORTS_WATCHING` | 看球、赛事、运动画面、不卡、拖影少 |
| `TASK_LARGE_SCREEN_REPLACEMENT` | 大屏、换新、尺寸满意、客厅升级 |
| `TASK_CHILD_EYE_CARE` | 孩子、儿童、护眼、长期看不累 |
| `TASK_SENIOR_EASY_USE` | 父母、老人、语音、操作简单 |
| `TASK_VALUE_PURCHASE` | 划算、性价比、优惠、价格值 |
| `TASK_NEW_HOME_DECORATION` | 新家、装修、挂墙、安装、家居适配 |
| `TASK_BEDROOM_SECOND_TV` | 卧室、副屏、第二台、小空间 |

评论任务线索不能单独使 M09 高置信成立；M09 必须再结合参数、卖点和市场。

### 7.3 目标客群线索 `target_group_cue`

目标：给 M10 判断目标客群提供人群和购买动机线索。

| 客群编码 | 评论线索 |
| --- | --- |
| `TG_FAMILY_UPGRADE` | 家人、全家、客厅、换新、大屏 |
| `TG_AV_QUALITY_SEEKER` | 画质党、影音、清晰、色彩、HDR |
| `TG_GAMER` | 游戏、主机、PS5、Switch、电竞 |
| `TG_SPORTS_FAN` | 看球、体育、赛事 |
| `TG_SENIOR_FAMILY` | 父母、老人、长辈、语音简单 |
| `TG_CHILD_FAMILY` | 孩子、儿童、护眼 |
| `TG_VALUE_BUYER` | 性价比、划算、预算、优惠 |
| `TG_NEW_HOME_DECORATOR` | 新家、装修、安装、家居搭配 |
| `TG_BEDROOM_SECOND_TV` | 卧室、副屏、第二台 |

客群信号必须保留 `cue_basis`：

- explicit_people：明确人群词。
- purchase_motivation：购买动机。
- scenario_inference：场景推断，置信度低于明确人群。

### 7.4 价值战场支撑/削弱信号 `battlefield_support`

目标：给 M11 判断战场提供评论体验支撑或削弱。

| 战场编码 | 支撑评论 | 削弱评论 |
| --- | --- | --- |
| `BF_PREMIUM_PICTURE` | 画质清晰、亮度好、色彩好、暗场好 | 画质差、刺眼、反光、暗场差 |
| `BF_FAMILY_VIEWING_UPGRADE` | 大屏满意、客厅看电影、音画震撼 | 尺寸不合适、音效差 |
| `BF_GAMING_SPORTS` | 看球不卡、游戏流畅、接口方便 | 拖影、卡顿、延迟 |
| `BF_LARGE_SCREEN_VALUE` | 屏幕大、价格值、换新划算 | 贵、不值、同价不如 |
| `BF_FAMILY_EYE_CARE` | 护眼、不累、孩子看舒服 | 刺眼、看久不舒服 |
| `BF_SENIOR_EASE_OF_USE` | 老人会用、语音方便、操作简单 | 操作复杂、广告多 |
| `BF_SMART_SYSTEM_EXPERIENCE` | 系统流畅、语音灵敏 | 卡顿、广告、系统复杂 |
| `BF_CINEMA_AUDIO_IMMERSION` | 音质好、低音强、沉浸 | 音效差、杂音 |
| `BF_DESIGN_HOME_FIT` | 外观好、挂墙合适、装修搭 | 不好看、尺寸不适配 |
| `BF_SERVICE_ASSURANCE` | 安装快、客服好、售后好 | 配送慢、安装差、售后差 |

服务类评论只能支撑 `BF_SERVICE_ASSURANCE` 或新家装修相关服务侧信号，不得支撑高端画质、游戏体育等产品战场。

### 7.5 痛点风险信号 `pain_point`

目标：给 M08、M11、M13 提供降权和风险信息。

风险类型：

| 风险编码 | 典型表达 |
| --- | --- |
| `RISK_PICTURE_NEGATIVE` | 画质差、模糊、偏色、反光 |
| `RISK_MOTION_LAG` | 拖影、卡顿、看球不顺 |
| `RISK_SYSTEM_ADS_LAG` | 广告多、系统卡、操作复杂 |
| `RISK_AUDIO_NEGATIVE` | 音质差、声音小、杂音 |
| `RISK_EYE_DISCOMFORT` | 刺眼、看久累 |
| `RISK_SERVICE_DELIVERY` | 配送慢、安装差、客服差 |
| `RISK_DURABILITY_QUALITY` | 做工差、故障、坏点 |
| `RISK_PRICE_OVERPAY` | 太贵、不值、降价背刺 |

痛点风险必须保留 severity：

- low：单句弱负向。
- medium：明确负向体验。
- high：多句集中或涉及核心功能。

### 7.6 价格价值感信号 `price_perception`

目标：给 M09 的性价比任务和 M13 的价格/价值拦截判断提供评论感知。

评论可表达价格感知，但不能代替真实价格数据。真实价格和价格带由 M07/M13 处理。

| 信号 | 典型表达 |
| --- | --- |
| `PRICE_VALUE_POSITIVE` | 性价比高、划算、买得值、优惠 |
| `PRICE_VALUE_NEGATIVE` | 太贵、不值、降价快 |
| `PRICE_PROMOTION_SENSITIVE` | 活动、优惠、补贴、赠品 |
| `PRICE_BIG_SCREEN_VALUE` | 大屏这个价很值 |

价格价值信号必须和市场价格分开保存。

### 7.7 服务保障信号 `service_signal`

目标：给 M10/M11/M15 提供服务敏感、安装保障、售后风险等证据。

服务信号类型：

| 信号 | 典型表达 |
| --- | --- |
| `SERVICE_INSTALL_POSITIVE` | 安装快、师傅专业、挂装好 |
| `SERVICE_DELIVERY_POSITIVE` | 送货快、物流好 |
| `SERVICE_SUPPORT_POSITIVE` | 客服好、售后响应 |
| `SERVICE_INSTALL_NEGATIVE` | 安装慢、不专业 |
| `SERVICE_DELIVERY_NEGATIVE` | 配送慢、破损 |
| `SERVICE_SUPPORT_NEGATIVE` | 售后差、客服差 |

服务信号可支撑服务保障战场和新家装修/服务敏感客群，不可增强产品技术卖点。

## 8. 输出数据契约

### 8.1 `core3_comment_signal_candidate`

句级信号候选表，保留每条评论句如何被映射成下游信号。

| 字段 | 说明 |
| --- | --- |
| `signal_candidate_id` | 句级信号候选 ID |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `comment_unit_id` | 去重评论单元 |
| `comment_evidence_id` | M05 句级证据 |
| `signal_type` | claim_validation/task_cue/target_group_cue/battlefield_support/pain_point/price_perception/service_signal |
| `target_code_hint` | CLAIM/TASK/TG/BF/RISK/PRICE/SERVICE 编码 |
| `polarity` | support/weaken/neutral |
| `signal_strength` | 句级强度 |
| `specificity_score` | 具体程度 |
| `sentiment_hint` | 情感弱标签 |
| `domain_hints` | M05 弱域 |
| `topic_hints` | M05 弱主题 |
| `matched_entities_json` | 场景/动作/人群/对象/结果/约束 |
| `cue_basis` | explicit/scenario/motivation/topic_hint |
| `confidence` | 句级信号置信度 |
| `quality_flags` | 低价值、重复、服务隔离等 |
| `evidence_ids` | 评论 evidence |
| `rule_version` | 规则版本 |

### 8.2 `core3_comment_downstream_signal`

SKU 聚合信号表，供下游模块消费。

| 字段 | 说明 |
| --- | --- |
| `signal_id` | 聚合信号 ID |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `signal_type` | 信号类型 |
| `target_code_hint` | 下游目标编码 |
| `polarity` | support/weaken/mixed/neutral |
| `mention_count` | 去重评论单元提及数 |
| `sentence_count` | 句级提及数 |
| `valid_comment_unit_count` | 有效评论单元分母 |
| `mention_rate` | 提及率 |
| `positive_count` | 正向数 |
| `negative_count` | 负向数 |
| `positive_rate` | 正向率 |
| `negative_rate` | 负向率 |
| `signal_score` | 聚合信号分 |
| `specificity_avg` | 平均具体程度 |
| `representative_phrases` | 代表短句 |
| `confidence` | 聚合置信度 |
| `evidence_ids` | 评论证据 |
| `quality_summary` | 质量摘要 |
| `review_status` | auto/review_required/approved/rejected |
| `rule_version` | 规则版本 |

### 8.3 `core3_sku_comment_signal_profile`

SKU 级评论信号画像，供 M08 汇总。

| 字段 | 说明 |
| --- | --- |
| `sku_code` | SKU |
| `comment_signal_summary_json` | 七类信号摘要 |
| `claim_validation_summary_json` | 卖点验证摘要 |
| `task_cue_summary_json` | 任务线索摘要 |
| `target_group_cue_summary_json` | 客群线索摘要 |
| `battlefield_support_summary_json` | 战场支撑摘要 |
| `pain_risk_summary_json` | 风险摘要 |
| `price_perception_summary_json` | 价格价值感摘要 |
| `service_signal_summary_json` | 服务信号摘要 |
| `comment_signal_confidence` | 评论信号整体置信度 |
| `quality_flags` | 重复、低价值、服务占比高等 |
| `evidence_ids` | 核心证据 |

## 9. 信号强度和置信度

### 9.1 句级信号强度

句级强度由以下因素决定：

```text
signal_strength =
  topic_match_score
  + entity_specificity_score
  + sentiment_strength
  - low_value_penalty
  - duplicate_penalty
  - domain_mismatch_penalty
```

### 9.2 聚合信号分

SKU 聚合信号分：

```text
signal_score =
  mention_rate * 0.35
  + positive_rate_or_negative_rate * 0.25
  + specificity_avg * 0.20
  + evidence_quality * 0.20
```

负向风险信号使用 negative_rate。

### 9.3 强信号最低条件

强信号至少满足：

- 去重评论单元提及，不只是重复句。
- 非低价值文本。
- 具体程度达到阈值。
- 情感或极性明确。
- 目标编码映射清楚。
- 服务/产品域没有冲突。

## 10. 85E7Q 样例要求

85E7Q 评论中应被拆成不同信号：

| 评论内容方向 | M06 信号 |
| --- | --- |
| 画面清晰、色彩好、细节好 | `claim_validation` 支持画质体验；`battlefield_support` 支持高端画质或家庭观影 |
| 看球清晰、运动画面顺 | `task_cue=TASK_SPORTS_WATCHING`；`battlefield_support=BF_GAMING_SPORTS`；可弱支持运动流畅体验 |
| 音质好、听觉棒 | `claim_validation` 支持沉浸音效；`battlefield_support=BF_CINEMA_AUDIO_IMMERSION` |
| 语音控制方便、运行流畅 | `task_cue=TASK_SENIOR_EASY_USE` 或智能系统任务线索；`battlefield_support=BF_SMART_SYSTEM_EXPERIENCE` |
| 性价比高、买得值 | `price_perception`；给 M09/M13 使用，不能代替真实价格 |
| 送装一体、安装快、师傅专业 | `service_signal`；可支持 `BF_SERVICE_ASSURANCE`，不能增强画质或游戏卖点 |

85E7Q 无结构化卖点，因此 M06 的 `claim_validation` 只能作为 M04b 的体验增强信号，不能直接补出硬规格宣传证据。

## 11. 真实数据约束

当前 205 样例数据对 M06 的硬约束：

- 评论原始行 62426，但去重正文明显更少，提及率必须用 M05 的去重评论单元作为主要分母。
- 空维度约 15766 行，不能依赖原始维度做强判断。
- 服务安装类评论占比较高，必须隔离为服务信号。
- 情感为空不能当中立，应保留 unknown 并降低置信度。
- 低价值评论和默认评价不能形成强信号。
- 当前只有海信品牌，M06 不做品牌内外竞品判断。

## 12. 与下游模块关系

### 给 M04b 的承诺

- M04b 只消费 `signal_type=claim_validation`。
- `claim_validation` 只能验证体验，不证明硬规格。
- 服务信号不能进入 M04b 的产品卖点增强。

### 给 M08 的承诺

- M08 消费 `core3_sku_comment_signal_profile` 汇总 SKU 评论信号。
- M08 必须看到风险、低质量、服务占比等质量标签。

### 给 M09 的承诺

- M09 消费 `task_cue`、`price_perception` 和必要痛点信号。
- 评论任务线索不能单独决定用户任务，M09 必须结合参数、卖点和市场。

### 给 M10 的承诺

- M10 消费 `target_group_cue` 和服务敏感信号。
- 客群线索不能单独生成高置信客群结论。

### 给 M11 的承诺

- M11 消费 `battlefield_support` 和痛点风险。
- 战场仍需结合任务、客群、卖点和市场。

### 给 M11.5/M13 的承诺

- M11.5 可以使用评论正负向提及计算 CPI。
- M13 可以使用评论信号作为组件评分的一部分，但不能绕过 M06 直接读评论。

### 给 M15 的承诺

- M15 可以展示代表评论短句。
- M15 必须用业务语言说明评论只是支撑证据，不能把弱信号包装成强结论。

## 13. 复核触发条件

以下情况进入复核：

- 高频评论无法映射到任何信号。
- 服务信号占比过高，可能影响产品判断。
- 某 SKU 负向风险集中。
- 同一评论句同时命中多个关键目标且置信度接近。
- 低价值评论被规则误判为强信号。
- 评论信号与 M03 参数或 M04a 基础卖点明显冲突。
- 重点 SKU 评论信号太少，无法支撑 M04b/M09/M11。
- 价格价值感评论强，但市场价格证据未支撑，提示 M13 复核。

## 14. 增量重算要求

| 输入变化 | M06 动作 | 下游影响 |
| --- | --- | --- |
| M05 句级证据变化 | 重算对应评论句信号 | M04b、M08-M16 |
| M05 主题提示变化 | 重算对应信号映射 | M04b、M08-M16 |
| M05 评论质量画像变化 | 更新提及率和置信度 | M08-M16 |
| seed 中 claim/task/group/battlefield 映射变化 | 重算对应信号类型 | M06-M16 |
| M03 参数变化 | 只更新辅助校验和冲突标记 | M04b、M08、M16 |
| M04a 基础卖点变化 | 只更新 claim_validation 目标关联 | M04b、M08、M16 |

如果 `core3_comment_downstream_signal` hash 未变化，不触发下游重算。

## 15. 验收标准

| 验收项 | 标准 |
| --- | --- |
| 七类评论信号独立输出 | 必须 |
| M06 不生成最终任务、客群、战场或竞品结论 | 必须 |
| 每条句级信号有 comment evidence | 必须 |
| 聚合信号有 mention count、mention rate、positive/negative rate | 必须 |
| 低价值评论不形成强信号 | 必须 |
| 服务信号不进入产品卖点增强 | 必须 |
| 评论不能证明硬规格 | 必须 |
| 85E7Q 评论可拆成画质、看球、音效、价格、智能、服务不同信号 | 必须 |
| 下游只能按对应 signal_type 消费 | 必须 |
| 信号冲突和样本不足可复核 | 必须 |
