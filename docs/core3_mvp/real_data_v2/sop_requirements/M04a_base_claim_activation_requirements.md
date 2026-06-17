# M04a 基础卖点激活 SOP 需求

## 0. 单模块强化状态

本文件已按“单模块逐一强化”要求完成第一轮强化。下一步应处理 M05 评论基础证据层。

## 1. 模块目标

M04a 基于“标准参数 + 结构化宣传卖点”计算 SKU 的标准卖点基础激活分，形成不含评论验证的卖点能力底座。

M04a 要解决四个问题：

1. 把原始宣传语、宣传句和技术实体映射到标准卖点。
2. 用 M03 标准参数判断宣传卖点是否有硬规格支撑。
3. 在没有结构化宣传卖点时，允许技术型卖点由参数形成低/中置信基础激活，但必须明确缺失宣传证据。
4. 为 M04b、M08、M09-M15 提供 `claim_code + base_activation_score + param_score + promo_score + evidence_ids + missing_signals`。

M04a 不消费评论，不判断用户感知，不做卖点价值分层。评论增强必须留给 M04b，战场内卖点价值分层必须留给 M11.5。

## 2. 设计依据

本模块依据：

- `cankao/CatForge_竞品生成SOP_详细指导_v1.md` 的 M04 拆分要求。
- `cankao/catforge_sop_md/modules/M04_宣传卖点切分、实体抽取与标准卖点激活.md`。
- M02 已强化后的 evidence 原子层。
- M03 已强化后的标准参数画像。
- [00 真实样例数据基线](00_real_data_baseline.md)。
- 项目现有彩电 seed：`apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` 中的 `standard_claims`。

## 3. 上游输入

### 3.1 必须输入

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| `promo_raw` evidence | M02 | 原始宣传卖点文本 |
| `promo_sentence` evidence | M02 | 宣传句级匹配和实体抽取 |
| `param_raw` evidence | M02 | 参数证据引用 |
| `core3_extract_param_value` | M03 | 标准参数值和置信度 |
| `core3_sku_param_profile` | M03 | SKU 级核心参数画像 |
| `quality_issue` evidence | M02 | 卖点覆盖缺失、参数 unknown、冲突等降权 |
| 标准卖点 seed | `standard_claims` | 标准卖点定义、关键词、映射参数、映射任务/战场 |

### 3.2 明确不消费

| 数据 | 处理 |
| --- | --- |
| 评论原文/评论句 | 不消费，M05/M06 负责 |
| 评论下游信号 | 不消费，M04b 负责 |
| 市场量价 | 不消费，M07/M11.5 负责 |
| 任务、客群、战场结果 | 不消费，M04a 是它们的上游 |

## 4. 本模块不做什么

- 不用评论证明卖点成立。
- 不判断卖点用户感知强弱。
- 不做战场内卖点价值分层。
- 不判断任务、客群、战场或竞品。
- 不把宣传强度等同于真实体验。
- 不因为 SKU 没有结构化卖点，就输出“无卖点”。
- 不伪造未覆盖 SKU 的宣传 evidence。
- 不把服务评论、安装评论提前混入卖点激活。

## 5. 预制与抽取边界

### 5.1 必须预制的内容

标准卖点库必须预制，并且可版本化。首版来自 `tv_core3_mvp_seed_v0_2.json` 的 `standard_claims`。

每个标准卖点至少包含：

| 字段 | 说明 |
| --- | --- |
| `claim_code` | 稳定卖点编码 |
| `claim_name` | 中文卖点名 |
| `definition` | 业务定义 |
| `claim_group` | picture/gaming/motion/eye_care/smart/audio/design/value/service |
| `aliases` | 宣传文本别名 |
| `keywords` | 关键词 |
| `source_types` | 可接受来源 |
| `required_param_codes` | 必需或强支撑参数 |
| `supporting_param_codes` | 辅助支撑参数 |
| `mapped_task_codes` | 可支撑任务 |
| `mapped_battlefield_codes` | 可支撑战场 |
| `activation_rule` | 激活规则和权重 |
| `review_rule` | 复核规则 |

### 5.2 必须从真实数据抽取的内容

| 抽取内容 | 来源 | 输出 |
| --- | --- | --- |
| 宣传句片段 | `promo_sentence` evidence | `core3_extract_claim_hit` |
| 技术实体 | 宣传句和参数 | `extracted_entity_json` |
| 数值实体 | nits、Hz、分区、HDMI、GB 等 | 命中解释和参数校验 |
| 标准卖点候选 | seed 关键词/别名/参数映射 | `candidate_claim_code` |
| 参数支撑 | M03 标准参数 | `param_score` |
| 宣传支撑 | M02 宣传 evidence | `promo_score` |
| 缺失和冲突 | M02/M03 质量 evidence | `missing_signals`、`review_status` |

## 6. MVP 标准卖点范围

首版标准卖点应覆盖项目 seed 中已有的 20 类彩电卖点：

| 卖点编码 | 中文卖点 | 类型 |
| --- | --- | --- |
| `CLAIM_LARGE_SCREEN_IMMERSION` | 大屏沉浸观影 | 体验/场景型 |
| `CLAIM_MINI_LED_BACKLIGHT` | Mini LED 背光 | 技术型 |
| `CLAIM_OLED_SELF_LIT` | OLED 自发光 | 技术型 |
| `CLAIM_QLED_WIDE_COLOR` | 量子点广色域 | 技术型 |
| `CLAIM_HIGH_BRIGHTNESS_HDR` | 高亮 HDR | 技术型 |
| `CLAIM_FINE_LOCAL_DIMMING` | 精细分区控光 | 技术型 |
| `CLAIM_HIGH_REFRESH_RATE` | 高刷新率 | 技术型 |
| `CLAIM_GAMING_LOW_LATENCY` | 低延迟游戏 | 技术/体验型 |
| `CLAIM_HDMI_2_1_GAMING` | HDMI 2.1 游戏接口 | 技术型 |
| `CLAIM_SPORTS_MOTION_SMOOTH` | 体育运动流畅 | 体验型 |
| `CLAIM_EYE_CARE_COMFORT` | 护眼舒适 | 技术/体验型 |
| `CLAIM_ELDER_FRIENDLY_SMART` | 长辈友好智能 | 体验型 |
| `CLAIM_SMART_VOICE_EASE` | 智能语音易用 | 技术/体验型 |
| `CLAIM_NO_AD_OR_CLEAN_SYSTEM` | 清爽系统/少广告 | 体验型 |
| `CLAIM_IMMERSIVE_AUDIO` | 沉浸音效 | 技术/体验型 |
| `CLAIM_DOLBY_CINEMA_AUDIO` | 杜比影音 | 技术型 |
| `CLAIM_THIN_DESIGN` | 超薄美学设计 | 体验/设计型 |
| `CLAIM_ENERGY_SAVING` | 节能省电 | 价值型 |
| `CLAIM_VALUE_FOR_MONEY` | 高性价比 | 价值型 |
| `CLAIM_INSTALLATION_SERVICE_ASSURANCE` | 安装服务保障 | 服务型 |

M04a 可以为技术型卖点输出参数支撑；体验型、服务型、价值型需要宣传文本支撑，不能仅凭评论或市场事实在 M04a 激活。

## 7. 处理流程

### 7.1 SKU 卖点来源状态

先按 SKU 判断卖点来源状态：

| 状态 | 含义 |
| --- | --- |
| `has_structured_claim` | 有结构化宣传卖点 |
| `missing_structured_claim` | 没有结构化宣传卖点，但有参数或其它数据 |
| `claim_data_insufficient` | 宣传卖点为空、不可读或质量过低 |
| `claim_conflict` | 宣传与参数明显冲突 |

85E7Q 当前必须是 `missing_structured_claim`，不是“无卖点”。

### 7.2 宣传句解析

对 `promo_sentence` evidence 进行：

1. 保留 `claim_seq` 和 `sentence_seq`。
2. 识别标题结构：核心定位、功能价值、情感价值、便捷体验、差异化定位、行业地位等。
3. 抽取技术实体：Mini LED、OLED、QLED、HDR、高刷、VRR、ALLM、HDMI2.1、MEMC、护眼、低蓝光、杜比、语音、Wi-Fi 6、AI 等。
4. 抽取数值实体：Hz、nits、分区、GB、W、ms、百分比、接口数量等。
5. 生成标准卖点候选。

标题结构只能作为弱提示，不能直接变成业务结论。

### 7.3 参数支撑计算

基于 M03 标准参数判断卖点是否有硬规格支撑：

| 卖点 | 典型参数支撑 |
| --- | --- |
| Mini LED 背光 | `mini_led_flag=true`、`backlight_type=MiniLED` |
| 高亮 HDR | `peak_brightness_nits`、`hdr_format_list` |
| 精细分区控光 | `dimming_zones`、`local_dimming_flag` |
| 高刷新率 | `native_refresh_rate_hz`、`system_refresh_rate_hz`、`refresh_rate_hz` |
| HDMI 2.1 游戏接口 | `hdmi_2_1_ports`、`full_bandwidth_hdmi_flag` |
| 低延迟游戏 | `input_lag_ms`、`vrr_flag`、`allm_flag`、`game_mode_flag` |
| 护眼舒适 | `eye_dimming_freq_hz`、`low_blue_light_flag`、`flicker_free_flag` |
| 智能语音易用 | `voice_control_flag`、`far_field_voice_flag` |
| 系统流畅 | `ram_gb`、`storage_gb`、`chipset_name` |
| 沉浸音效 | `speaker_power_w`、`speaker_channel`、`subwoofer_flag` |

参数支撑不是最终用户感知，只能作为基础能力。

### 7.4 宣传支撑计算

基于宣传 evidence 判断：

- 是否命中标准卖点关键词或别名。
- 是否有明确数值实体。
- 是否有标题结构支撑。
- 是否为抽象形容词。
- 是否与参数冲突。

抽象宣传词如“旗舰体验”“行业领先”“震撼升级”不能单独高置信激活。

### 7.5 基础激活分

M04a 不使用 comment_score。

技术型卖点建议：

```text
base_activation_score =
  param_score * 0.65
  + promo_score * 0.35
  - conflict_penalty
  - missing_signal_penalty
```

体验/设计/服务/价值型卖点建议：

```text
base_activation_score =
  param_score * 0.35
  + promo_score * 0.65
  - conflict_penalty
  - missing_signal_penalty
```

如果没有结构化宣传卖点：

- 技术型卖点可由强参数形成 `param_only_base_activation`。
- 体验型、服务型、价值型不应仅凭参数激活。
- `missing_signals` 必须包含 `missing_structured_claim`。
- 置信度必须低于“参数 + 宣传都命中”的情况。

## 8. 输出数据契约

### 8.1 `core3_extract_claim_hit`

| 字段 | 说明 |
| --- | --- |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `claim_code` | 标准卖点候选 |
| `claim_name` | 中文卖点名 |
| `source_sentence_key` | 宣传句键 |
| `claim_fragment` | 命中的宣传片段 |
| `matched_keywords` | 命中词 |
| `title_hint` | 标题结构弱提示 |
| `extracted_entity_json` | 技术和数值实体 |
| `match_method` | exact_alias/keyword/entity/param_support/manual |
| `promo_evidence_ids` | 宣传 evidence |
| `param_evidence_ids` | 参数 evidence |
| `match_confidence` | 命中置信度 |
| `quality_flags` | 抽象宣传/冲突/缺参数等 |

### 8.2 `core3_sku_claim_source_status`

| 字段 | 说明 |
| --- | --- |
| `sku_code` | SKU |
| `claim_source_status` | has_structured_claim/missing_structured_claim/claim_data_insufficient/claim_conflict |
| `structured_claim_count` | 结构化卖点条数 |
| `claim_sentence_count` | 宣传句数 |
| `param_only_claim_count` | 仅参数支撑的卖点数 |
| `quality_evidence_ids` | 质量 evidence |
| `status_note` | 中文说明 |

### 8.3 `core3_sku_claim_activation_base`

| 字段 | 说明 |
| --- | --- |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `claim_code` | 标准卖点 |
| `claim_name` | 中文卖点名 |
| `claim_group` | 卖点类型 |
| `param_score` | 参数支撑分 |
| `promo_score` | 宣传支撑分 |
| `base_activation_score` | 基础激活分 |
| `activation_level` | high/medium/low/unknown |
| `activation_basis` | param_and_promo/param_only/promo_only/insufficient |
| `missing_signals` | 缺失信号 |
| `conflict_flags` | 冲突标记 |
| `confidence` | 置信度 |
| `evidence_ids` | 参数和宣传证据 |
| `review_status` | auto/review_required/approved/rejected |
| `rule_version` | 规则版本 |

## 9. 置信度与降权规则

| 情况 | 处理 |
| --- | --- |
| 参数 + 宣传都强命中 | 高置信基础激活 |
| 技术型卖点只有参数强命中 | 中置信，标记 `param_only` |
| 只有宣传命中且无参数支撑 | 中低置信，技术型需复核 |
| 抽象宣传词无实体支撑 | 低置信 |
| 参数 unknown | 不当 false，标记缺失 |
| 参数与宣传冲突 | 降置信并进入复核 |
| 无结构化卖点 | 不生成 promo evidence，允许技术型参数基础激活并降级 |
| 服务/价值/体验型缺宣传 | 不强行激活 |

## 10. 85E7Q 样例要求

85E7Q 当前有强参数、无结构化卖点。M04a 对 85E7Q 必须：

- 输出 `claim_source_status=missing_structured_claim`。
- 可以基于参数输出技术型基础卖点候选，例如 Mini LED 背光、高亮 HDR、精细分区控光、高刷新率、HDMI2.1 游戏接口、系统配置等。
- 对上述候选标记 `activation_basis=param_only`。
- `missing_signals` 包含 `missing_structured_claim` 和缺少宣传 evidence。
- 不生成任何伪造的 `promo_evidence_ids`。
- 不激活安装服务保障、性价比、体育运动流畅、长辈友好等需要宣传/评论/市场补证的卖点。

## 11. 真实数据约束

当前 205 样例数据对 M04a 的硬约束：

- `selling_points_data` 只覆盖 5 个型号，每个覆盖型号 13 条卖点。
- 85E7Q 没有结构化卖点，必须走参数基础激活降级路径。
- 卖点文本含有“核心定位、功能价值、情感价值、便捷体验、差异化定位、行业地位”等标题结构，只能作为弱提示。
- M04a 不得使用 `comment_data` 中的安装、配送、画质、价格等评论。
- 卖点覆盖不足是数据缺口，不是 SKU 能力缺失。

## 12. 与下游模块关系

### 给 M04b 的承诺

- M04b 从 `core3_sku_claim_activation_base` 开始，只做评论验证增强。
- M04a 输出不包含评论分。

### 给 M08 的承诺

- M08 可使用基础卖点激活作为 SKU 画像的一部分。
- M08 必须看到 `activation_basis` 和 `missing_signals`。

### 给 M09-M11 的承诺

- 用户任务、目标客群、价值战场可以使用基础卖点作为语义支撑。
- 仅参数基础激活不能等同于用户任务成立。

### 给 M11.5 的承诺

- M11.5 做战场内卖点价值分层，M04a 不做价值层级。

### 给 M12-M15 的承诺

- 竞品解释中的卖点证据必须区分参数支撑、宣传支撑和评论验证。
- M15 面向领导展示时不能把 `param_only` 说成“宣传卖点明确”。

### 给 M16 的承诺

- M16 可基于结构化卖点缺失、参数宣传冲突、低置信基础激活进入复核。

## 13. 复核触发条件

以下情况进入复核：

- 新营销词高频出现但未匹配标准卖点。
- 一个宣传句命中多个标准卖点且分数接近。
- 技术型卖点只有宣传没有参数支撑。
- 参数和宣传冲突。
- 核心 SKU 结构化卖点缺失，例如 85E7Q。
- `param_only` 卖点会影响核心竞品判断。
- 体验型/服务型/价值型卖点只有弱宣传或无宣传。

## 14. 增量重算要求

| 输入变化 | M04a 动作 | 下游影响 |
| --- | --- | --- |
| `promo_raw` 或 `promo_sentence` evidence 变化 | 重算对应 SKU 宣传命中和基础激活 | M04b、M08-M16 |
| M03 标准参数变化 | 重算对应 SKU 参数支撑和基础激活 | M04b、M08-M16 |
| 标准卖点 seed 变化 | 重算所有受影响卖点映射 | M04a-M16 |
| quality evidence 变化 | 更新缺失、冲突、置信度 | M04b、M08、M16 |
| 评论变化 | 不触发 M04a，只触发 M06/M04b |

如果 `core3_sku_claim_activation_base` hash 未变化，不触发下游重算。

## 15. 验收标准

| 验收项 | 标准 |
| --- | --- |
| M04a 不消费评论 | 必须 |
| 标准卖点 seed 可版本化 | 必须 |
| 覆盖 20 类 MVP 标准卖点 | 必须 |
| 有卖点型号可生成宣传命中 | 必须 |
| 技术型卖点可参数支撑 | 必须 |
| 85E7Q 输出卖点来源缺失状态 | 必须 |
| 85E7Q 不生成伪造宣传 evidence | 必须 |
| 体验/服务/价值型不由参数强行激活 | 必须 |
| 每个激活卖点有 evidence_ids | 必须 |
| 参数和宣传冲突可复核 | 必须 |
| M04a 输出可被 M04b/M08 消费 | 必须 |
