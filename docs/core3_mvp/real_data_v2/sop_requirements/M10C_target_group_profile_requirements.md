# M10C 目标客群画像 SOP 需求

## 0. 定位

M10C 是新语义能力层的“目标客群画像”模块。它基于 M03B 参数事实、M04C 卖点事实、M05C 评论事实和量价事实，为每个 SKU 判断其主目标客群、次目标客群、用户观察客群、厂家主打客群、潜在客群和未满足客群需求，并生成目标客群覆盖统计。

M10C 不沿用旧 M10 的 9 个 `TG_*` seed，也不读取旧 M08/M09/M10 结果作为主链路输入。旧 M10 保留历史兼容和对照验证，新链路使用本文件定义的 TV 10 个目标客群预设。

目标客群回答：

```text
谁可能购买这个 SKU，为什么是这类人群购买，这个判断由用户评论、任务、尺寸价格、卖点和参数中的哪些证据支撑。
```

目标客群不是评论里出现一个人群词后的直接标签，也不是品牌信任/复购、服务履约或物流安装。品牌信任/复购只能作为购买心理增强因素；服务履约、物流安装、售后只能作为服务语境或风险，不作为产品客群。

## 1. 总体原则

### 1.1 证据优先级

M10C 的证据优先级为：

```text
评论人群/用途/购买动机
-> 已成立用户任务或任务代理规则
-> 五档尺寸和尺寸内价格带适配
-> 标准卖点表达
-> 标准参数能力
-> 市场销量/销额验证
```

说明：

1. 评论里直接出现人群、购买对象、使用场景或购买动机时，优先级最高。
2. 没有人群词但用户任务强，也可以推导客群，例如游戏任务强可以推导游戏体育娱乐用户。
3. 卖点只能说明厂家想服务谁，不能单独证明真实客群。
4. 参数只能说明产品适不适合这类客群，不能单独证明谁在买。
5. 负向评论仍可形成客群需求，但对应卖点或参数是短板。
6. 品牌信任/复购可以提高购买心理置信度，但不单独成为客群。
7. 服务履约不得生成产品客群，只能作为服务风险或语境写入解释。

### 1.2 与用户任务的关系

已确认的目标客群设计依赖用户任务，但本开发序列中 M10C 位于 M09C 用户任务模块之前。因此 M10C 首版必须能在没有 M09C 输出的情况下运行。

首版处理口径：

- 使用已确认的 12 个 TV 用户任务 code 作为 taxonomy 引用。
- 在 M10C 内部用评论、卖点、参数和尺寸价格规则计算 `task_proxy_support`，表示“该客群对应任务是否被事实层间接支撑”。
- 后续 M09C 落地后，M10C 可以读取 SKU 用户任务画像作为增强输入，并用真实 `primary_user_task`、`secondary_user_task` 替代或增强 `task_proxy_support`。
- 无论是否接入 M09C，评论优先、卖点不能单独证明客群、参数不能单独证明购买人群这三条原则不变。

## 2. 模块边界

### 2.1 必须解决

1. 加载已发布的 TV 目标客群 taxonomy。
2. 对每个 SKU 计算 SKU x 目标客群关系。
3. 区分主客群、次客群、评论观察客群、厂家主打客群、潜在客群、未满足客群需求和不支持。
4. 对每个目标客群输出评论、任务、尺寸价格、卖点、参数和市场验证证据。
5. 负向评论不排除客群需求，而是识别为 `unmet_group_need` 或支撑风险。
6. 输出每个 SKU 的目标客群画像和每个目标客群覆盖哪些 SKU。
7. 提供 CLI 执行和查询能力，并能被 Claude Code skill 用自然语言驱动。

### 2.2 不解决

| 不做事项 | 原因 |
| --- | --- |
| 不生成用户任务 taxonomy | 用户任务由 M09C 或人工发布任务预设负责 |
| 不生成价值战场 taxonomy | 价值战场由 M11C 负责 |
| 不把品牌信任/复购作为客群 | 它是购买心理增强因素，不是人群类型 |
| 不把服务履约作为产品客群 | 服务、物流、安装、售后只能作为服务语境或风险 |
| 不直接判断核心竞品 | 竞品召回和评分由后续竞品分析层负责 |
| 不强制每个 SKU 都有主客群 | 评论不足或证据分散时可以没有高置信主客群 |
| 不调用 LLM 运行时动态创建客群 | M10C 基于已发布预设确定性执行 |
| 不读取原始四张表直接做业务判断 | 必须消费上游事实层产物 |

## 3. 输入

### 3.1 必须输入

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| 目标客群 taxonomy | 人工/LLM 辅助生成并发布的品类资产 | 客群定义、来源任务、证据规则、状态封顶规则 |
| SKU 参数事实画像 | M03B | 尺寸五档、画质、刷新率、智能、护眼、外观、接口等产品能力 |
| SKU 卖点事实画像 | M04C | 标准卖点、参数支撑状态、卖点维度位置 |
| SKU 评论事实画像 | M05C | 用户人群、用途、购买动机、价格价值、品牌力、竞品、正负向体验 |
| SKU 量价事实 | M07 或新市场事实模块 | 尺寸内价格带、销量/销额位置、价格/英寸、市场验证 |

M10C 必须统一使用 M03B 参数事实画像中的五档尺寸口径：

| 尺寸档 | 规则 |
| --- | --- |
| `small_32_45` | `screen_size_inch <= 45` |
| `medium_46_59` | `46 <= screen_size_inch <= 59` |
| `large_60_69` | `60 <= screen_size_inch <= 69` |
| `xlarge_70_85` | `70 <= screen_size_inch <= 85` |
| `giant_98_plus` | `screen_size_inch >= 98` |

价格带不是原始量价表字段。M10C 必须在五档尺寸内按加权均价分位派生 `low/mid_low/mid/mid_high/high`，不得使用旧 M07 的 `compact_screen/mainstream_living/large_upgrade/ultra_large_flagship` 作为主口径。

### 3.2 可选增强输入

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| SKU 用户任务画像 | 后续 M09C | 用真实任务画像增强或替代 `task_proxy_support` |
| 价值战场画像 | M11C | 后续可用于报告解释或竞品分析，但不得反向决定客群 |

### 3.3 禁止输入

| 禁止输入 | 原因 |
| --- | --- |
| 原始 `comment_data` | 评论事实必须来自 M05C |
| 原始 `selling_points_data` | 卖点事实必须来自 M04C |
| 原始 `attribute_data` | 参数事实必须来自 M03B |
| 原始 `week_sales_data` | 市场事实必须来自 M07 或新市场事实模块 |
| 旧 M06 下游信号 | 旧 seed 与新任务/客群/战场口径不一致 |
| 旧 M10 客群结果 | 新 M10C 需要独立生成，不继承旧结果 |

## 4. TV 首版目标客群预设

M10C 必须沿用已确认的 10 个 TV 目标客群 code 和含义。

| target_group_code | 名称 | 来源任务 | 业务定义 |
| --- | --- | --- | --- |
| `TG_MAINSTREAM_FAMILY_VIEWER` | 主流家庭观影用户 | `TASK_MAINSTREAM_LIVING_VIEWING`、`TASK_CINEMA_IMMERSION` | 家庭日常看电视、追剧、综艺、电影，重视尺寸合适、画质够用、系统稳定 |
| `TG_LARGE_SCREEN_UPGRADER` | 大屏换新升级用户 | `TASK_LARGE_SCREEN_UPGRADE`、`TASK_CINEMA_IMMERSION` | 从小屏或旧电视升级到 70/75/85/98 寸以上，重视大屏换新价值 |
| `TG_PREMIUM_AV_ENTHUSIAST` | 高端影音体验用户 | `TASK_PREMIUM_PICTURE_EXPERIENCE`、`TASK_CINEMA_IMMERSION` | 对亮度、控光、色彩、MiniLED/OLED/QD、画质芯片和沉浸影音敏感 |
| `TG_GIANT_HOME_THEATER_BUYER` | 巨幕家庭影院用户 | `TASK_CINEMA_IMMERSION`、`TASK_HOME_DECOR_SPACE_FIT` | 大客厅、新家、巨幕影院场景，重视 98 寸以上、沉浸感和空间融合 |
| `TG_VALUE_MAXIMIZER` | 性价比理性用户 | `TASK_VALUE_FOR_MONEY_PURCHASE`、`TASK_LARGE_SCREEN_UPGRADE` | 预算内追求更大尺寸、更好配置、更高销量口碑或补贴价格 |
| `TG_GAMING_SPORTS_USER` | 游戏体育娱乐用户 | `TASK_GAMING_CONSOLE_ENTERTAINMENT`、`TASK_SPORTS_MOTION_WATCHING` | 连接游戏主机或观看高速赛事，重视高刷、HDMI2.1、低延迟、运动流畅 |
| `TG_CHILD_FAMILY_LONG_WATCH` | 儿童家庭长看用户 | `TASK_EYE_CARE_LONG_WATCHING`、`TASK_MAINSTREAM_LIVING_VIEWING` | 儿童、家庭、长时间观看场景，重视护眼、低蓝光、无频闪和舒适度 |
| `TG_SENIOR_PARENT_FRIENDLY` | 长辈友好使用用户 | `TASK_SENIOR_EASY_OPERATION`、`TASK_MAINSTREAM_LIVING_VIEWING` | 给父母/老人使用，重视语音、遥控简单、系统清爽、少广告 |
| `TG_BEDROOM_RENTAL_SECOND_SCREEN` | 卧室副屏/租房用户 | `TASK_BEDROOM_SECOND_SCREEN`、`TASK_VALUE_FOR_MONEY_PURCHASE` | 卧室、租房、第二台电视，小尺寸、低价、易用、够用 |
| `TG_SMART_CONNECTED_USER` | 投屏互联智能用户 | `TASK_SMART_CASTING_IOT`、`TASK_SENIOR_EASY_OPERATION` | 手机投屏、无线连接、AI 语音、家电联动、摄像头互动等智能场景 |

## 5. 每个客群的匹配规则

### 5.1 `TG_MAINSTREAM_FAMILY_VIEWER`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `audience_child_family`、`use_living_room_cinema`，或评论出现家里、家庭、全家、客厅、追剧、日常看、综艺、电影 |
| 用户任务 | `TASK_MAINSTREAM_LIVING_VIEWING` 强，`TASK_CINEMA_IMMERSION` 可增强 |
| 尺寸价格 | `medium_46_59`、`large_60_69`、`xlarge_70_85`；价格带 `low` 到 `mid_high` 均可，但 `mid/mid_high` 更偏均衡体验 |
| 卖点 | `tv_claim_theater_scene`、`tv_claim_hdr_high_brightness`、`tv_claim_speaker_sound`、`tv_claim_eye_care_display`、`tv_claim_voice_control` |
| 参数 | `screen_size_inch`、`resolution_class`、`hdr_support_flag`、`memory_capacity_gb`、`speaker_power_w`、`declared_refresh_rate_hz` |

### 5.2 `TG_LARGE_SCREEN_UPGRADER`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `use_living_room_cinema`、`replacement_source`、`appearance_size_fit`，或评论出现换新、旧电视、上一台、75 寸、85 寸、大屏、客厅震撼 |
| 用户任务 | `TASK_LARGE_SCREEN_UPGRADE` 强，`TASK_CINEMA_IMMERSION` 可增强 |
| 尺寸价格 | `xlarge_70_85` 为主，`giant_98_plus` 可进入巨幕升级，`large_60_69` 只能作为入门升级；价格带 `low/mid_low/mid` 偏换新性价比，`mid_high/high` 偏高端升级 |
| 卖点 | `tv_claim_theater_scene`、`tv_claim_value_price`、`tv_claim_full_screen_design` |
| 参数 | `screen_size_inch`、`resolution_class`、`price_per_inch`、`full_screen_design_flag` |

### 5.3 `TG_PREMIUM_AV_ENTHUSIAST`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `picture_clarity_resolution`、`picture_brightness_hdr`、`picture_color_accuracy`、`picture_local_dimming_black`、`audio_quality`，或评论出现画质、色彩、亮度、黑位、控光、MiniLED、OLED、电影效果 |
| 用户任务 | `TASK_PREMIUM_PICTURE_EXPERIENCE` 强，`TASK_CINEMA_IMMERSION` 可增强 |
| 尺寸价格 | `large_60_69`、`xlarge_70_85` 为主；价格带 `mid_high/high` 最匹配，`mid` 只能作为高配下探或潜在客群 |
| 卖点 | `tv_claim_miniled_display`、`tv_claim_qd_miniled_display`、`tv_claim_rgb_miniled_display`、`tv_claim_oled_self_lit`、`tv_claim_hdr_high_brightness`、`tv_claim_wide_color_accuracy`、`tv_claim_local_dimming`、`tv_claim_picture_engine_ai` |
| 参数 | `display_tech_class`、`mini_led_flag`、`quantum_dot_flag`、`hdr_support_flag`、`declared_brightness_nit_or_band`、`local_dimming_zone_count`、`color_gamut_ratio`、`processor_chip_model` |

### 5.4 `TG_GIANT_HOME_THEATER_BUYER`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `use_living_room_cinema`、`appearance_size_fit`、`appearance_slim_wall`，或评论出现 98 寸、100 寸、巨幕、大客厅、新家、影院、上墙、装修 |
| 用户任务 | `TASK_CINEMA_IMMERSION` 和 `TASK_HOME_DECOR_SPACE_FIT` 同时较强时最佳 |
| 尺寸价格 | `giant_98_plus` 为硬门槛；价格带 `mid_high/high` 最匹配，低价格带需复核是否样本异常或高配下探 |
| 卖点 | `tv_claim_theater_scene`、`tv_claim_hdr_high_brightness`、`tv_claim_local_dimming`、`tv_claim_dolby_audio_video`、`tv_claim_flush_wall_mount` |
| 参数 | `screen_size_inch >= 98`、`display_tech_class`、`declared_brightness_nit_or_band`、`local_dimming_zone_count`、`speaker_power_w`、`flush_wall_mount_flag` |

### 5.5 `TG_VALUE_MAXIMIZER`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `value_price`、`brand_recommendation`，或评论出现性价比、划算、补贴、优惠、价格香、值得买、同价位更好 |
| 用户任务 | `TASK_VALUE_FOR_MONEY_PURCHASE` 强，`TASK_LARGE_SCREEN_UPGRADE` 可增强 |
| 尺寸价格 | 所有尺寸均可，但必须体现“尺寸内价格效率”；价格带 `low/mid_low/mid` 更匹配，`mid_high/high` 需要高端配置下探或销量口碑支撑 |
| 卖点 | `tv_claim_value_price`、`tv_claim_theater_scene`、`tv_claim_high_refresh_rate`、`tv_claim_hdr_high_brightness` 等同价位高配卖点 |
| 参数 | `screen_size_inch`、`resolution_class`、`declared_refresh_rate_hz`、`declared_brightness_nit_or_band`、`price_per_inch`、销量/销额分位 |

### 5.6 `TG_GAMING_SPORTS_USER`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `use_gaming_sports`、`gaming_high_refresh_motion`，或评论出现游戏、主机、PS5、Xbox、Switch、看球、体育、运动流畅、不卡、低延迟、拖影 |
| 用户任务 | `TASK_GAMING_CONSOLE_ENTERTAINMENT` 或 `TASK_SPORTS_MOTION_WATCHING` 强 |
| 尺寸价格 | `medium_46_59`、`large_60_69`、`xlarge_70_85`；价格带 `mid/mid_high/high` 更匹配，小屏或低价只能形成潜在客群 |
| 卖点 | `tv_claim_high_refresh_rate`、`tv_claim_gaming_low_latency`、`tv_claim_hdmi21_connectivity` |
| 参数 | `declared_refresh_rate_hz >= 120`、`hdmi_2_1_port_count`、`hdmi_version_mix`、`memc_flag`、`memory_capacity_gb` |

### 5.7 `TG_CHILD_FAMILY_LONG_WATCH`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `audience_child_family`、`picture_eye_care_reflection`，或评论出现孩子、小孩、儿童、长时间看、不刺眼、不累眼、护眼、舒服 |
| 用户任务 | `TASK_EYE_CARE_LONG_WATCHING` 强，`TASK_MAINSTREAM_LIVING_VIEWING` 可增强 |
| 尺寸价格 | `small_32_45`、`medium_46_59`、`large_60_69` 为主，`xlarge_70_85` 可作为家庭长看增强；价格带 `mid_low` 以上更可信 |
| 卖点 | `tv_claim_eye_care_display`、`tv_claim_hdr_high_brightness`、`tv_claim_wide_color_accuracy` |
| 参数 | `eye_care_flag`、`declared_brightness_nit_or_band`、`declared_refresh_rate_hz`、`hdr_support_flag`、防眩/低蓝光/无频闪相关参数 |

### 5.8 `TG_SENIOR_PARENT_FRIENDLY`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `audience_senior`、`interaction_voice_casting`、`system_smooth_ads`，或评论出现爸妈、父母、老人、长辈、遥控简单、语音好用、广告少、不卡 |
| 用户任务 | `TASK_SENIOR_EASY_OPERATION` 强，`TASK_MAINSTREAM_LIVING_VIEWING` 可增强 |
| 尺寸价格 | `small_32_45`、`medium_46_59`、`large_60_69` 为主；价格带 `low/mid_low/mid` 更常见，过高价格需有家庭代购或高端客厅证据 |
| 卖点 | `tv_claim_voice_control`、`tv_claim_casting_connectivity`、`tv_claim_ai_large_model` |
| 参数 | `voice_recognition_flag`、`far_field_voice_flag`、`smart_tv_flag`、`network_tv_flag`、`memory_capacity_gb`、系统/广告相关评论风险 |

### 5.9 `TG_BEDROOM_RENTAL_SECOND_SCREEN`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `audience_rental_room`、`use_bedroom`，或评论出现卧室、租房、宿舍、小房间、第二台、副屏、床前、够用 |
| 用户任务 | `TASK_BEDROOM_SECOND_SCREEN` 强，`TASK_VALUE_FOR_MONEY_PURCHASE` 可增强 |
| 尺寸价格 | `small_32_45` 最匹配，`medium_46_59` 可作为大卧室或租房客厅；价格带 `low/mid_low` 最匹配 |
| 卖点 | `tv_claim_value_price`、`tv_claim_full_screen_design`、`tv_claim_voice_control` |
| 参数 | `screen_size_inch <= 45`、`resolution_class`、`wifi_builtin_flag`、`smart_tv_flag`、`price_per_inch` |

### 5.10 `TG_SMART_CONNECTED_USER`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `use_casting_online`、`interaction_voice_casting`、`system_smooth_ads`，或评论出现投屏、手机连接、无线、联网、语音、AI、智能家居、家电联动、摄像头 |
| 用户任务 | `TASK_SMART_CASTING_IOT` 强，`TASK_SENIOR_EASY_OPERATION` 可增强 |
| 尺寸价格 | `medium_46_59` 及以上更匹配；价格带 `mid/mid_high/high` 更可信，小屏智能只能形成小屏智能易用侧面 |
| 卖点 | `tv_claim_casting_connectivity`、`tv_claim_voice_control`、`tv_claim_ai_large_model`、`tv_claim_smart_home_iot`、`tv_claim_camera_interaction` |
| 参数 | `wifi_builtin_flag`、`network_tv_flag`、`smart_tv_flag`、`voice_recognition_flag`、`far_field_voice_flag`、`ai_capability_flag`、`ai_model_capability_flag`、`smart_home_iot_flag`、`camera_flag`、`memory_capacity_gb` |

## 6. 关系状态

M10C 输出关系状态必须包括：

| relation_status | 含义 |
| --- | --- |
| `primary_target_group` | 评论/任务/尺寸价格/卖点/参数多域一致，是 SKU 最主要服务的人群 |
| `secondary_target_group` | 证据成立但不是第一购买人群，或部分域较弱 |
| `comment_observed_group` | 用户评论直接出现人群或购买动机，但卖点/参数/价格支撑不足 |
| `brand_claimed_group` | 厂家卖点和参数暗示服务该客群，但用户评论弱或无 |
| `latent_group` | 尺寸价格和参数能力适合该客群，但评论和卖点都弱 |
| `unmet_group_need` | 用户评论体现该客群需求，且负向体验集中或产品支撑不足 |
| `not_supported` | 证据不足、尺寸价格明显不匹配或服务履约隔离 |

每个 SKU：

- 最多 1 个 `primary_target_group`。
- 最多 3 个 `secondary_target_group`。
- 可以有多个 `comment_observed_group`、`brand_claimed_group`、`latent_group` 和 `unmet_group_need`。
- 可以没有主客群，但必须写明原因。

## 7. 评分口径

建议首版综合分：

```text
target_group_score =
  comment_audience_motivation_score * 0.30
  + task_support_score * 0.20
  + size_price_fit_score * 0.15
  + claim_alignment_score * 0.12
  + param_capability_score * 0.10
  + market_validation_score * 0.08
  + brand_trust_boost * 0.05
```

说明：

- `comment_audience_motivation_score` 权重最高，因为客群是“谁在买/为谁买”的判断。
- `task_support_score` 首版可由 M10C 内部任务代理规则计算，M09C 落地后使用真实任务画像增强。
- `brand_trust_boost` 只增强置信度，不得单独生成客群。
- 服务履约信号不得加分到产品客群，只能进入风险或服务语境。
- 负向评论如果明确指向某客群需求，应形成 `unmet_group_need`，而不是直接 `not_supported`。

## 8. 输出

### 8.1 SKU 目标客群画像

每个 SKU 输出：

| 字段 | 含义 |
| --- | --- |
| `primary_target_group_code` | 主目标客群，可空 |
| `secondary_target_group_codes` | 次目标客群，最多 3 个 |
| `comment_observed_group_codes` | 评论观察客群 |
| `brand_claimed_group_codes` | 厂家主打客群 |
| `latent_group_codes` | 潜在客群 |
| `unmet_group_need_codes` | 未满足客群需求 |
| `size_tier` | M03B 五档尺寸口径 |
| `price_band_in_size_tier` | M10C 在尺寸档内计算的价格带 |
| `group_summary` | 客群摘要 |
| `no_primary_reason` | 没有主客群时的原因 |
| `review_required` | 是否需要人工复核 |

### 8.2 SKU x 目标客群分数

每个 SKU x 客群输出：

| 字段 | 含义 |
| --- | --- |
| `relation_status` | 七类关系状态 |
| `target_group_score` | 综合分 |
| `comment_audience_motivation_score` | 评论人群/用途/购买动机分 |
| `task_support_score` | 用户任务支撑分 |
| `size_price_fit_score` | 五档尺寸和尺寸内价格适配分 |
| `claim_alignment_score` | 卖点表达分 |
| `param_capability_score` | 参数能力分 |
| `market_validation_score` | 销量、销额、价格位置验证分 |
| `brand_trust_boost` | 品牌信任/复购增强 |
| `sentiment_polarity` | `positive`、`negative`、`mixed`、`neutral`、`unknown` |
| `status_reason_cn` | 中文原因 |
| `evidence_ids` | 可追溯证据 |
| `confidence` | 置信度 |

### 8.3 目标客群覆盖统计

批次级输出：

| 输出 | 用途 |
| --- | --- |
| 客群覆盖 SKU 数 | 看每个客群覆盖多少 SKU |
| 主客群 SKU | 看每个客群作为主客群覆盖哪些 SKU |
| 次客群 SKU | 看每个客群作为次客群覆盖哪些 SKU |
| 评论观察 SKU | 看用户评论明显出现但支撑不足的 SKU |
| 厂家主打 SKU | 看厂家表达但用户验证不足的 SKU |
| 潜在客群 SKU | 看能力适配但缺少评论/卖点的 SKU |
| 未满足需求 SKU | 看负向评论或支撑不足形成的客群痛点 |

## 9. CLI 与 Skill 要求

### 9.1 Pipeline CLI

后续实现时必须提供执行 CLI：

```bash
python -m app.cli.catforge_pipeline run-target-group --product-category tv --batch-id latest --force-rebuild --format json
```

必须支持：

| 参数 | 说明 |
| --- | --- |
| `--product-category` | 品类，首版 `tv` |
| `--batch-id` | 批次，默认支持 `latest` |
| `--sku-code` | 只跑单 SKU，可重复 |
| `--target-group-code` | 只跑指定客群，可重复 |
| `--force-rebuild` | 同业务键 hash 变化时替换旧结果 |
| `--format` | `json`、`text` |

自然语言入口必须识别：

- “生成彩电目标客群画像”
- “重新分析某个 SKU 的目标客群”
- “重新生成这个 SKU 的目标客户画像”
- “新数据来了，把目标客群准备好”

### 9.2 Insight CLI

后续实现时必须提供查询 CLI：

```bash
python -m app.cli.catforge_insight target-group-taxonomy --product-category tv --format json
python -m app.cli.catforge_insight sku-target-group --query 100A4F --include-scores --format json
python -m app.cli.catforge_insight target-group-skus --target-group-code TG_VALUE_MAXIMIZER --sku-limit 100 --format json
```

自然语言查询必须支持：

- “查某个 SKU 的目标客群”
- “这个 SKU 的目标客户是谁”
- “查彩电目标客群预设”
- “性价比理性用户有哪些 SKU”
- “哪些 SKU 是未满足长辈友好需求”

### 9.3 Claude Code Skill

skill 需要说明：

- 执行类问题使用 `catforge-pipeline run-target-group`。
- 查询类问题使用 `catforge-insight sku-target-group`、`target-group-taxonomy`、`target-group-skus`。
- 用户不需要知道 M10C 或内部 code。
- 回复时使用“目标客群画像”“目标客户”“覆盖 SKU”等业务语言。
- 如果 CLI 返回 `not_found`，提示先确认目标客群画像是否已经生成。

## 10. 验收标准

1. TV 目标客群 taxonomy 覆盖 10 个已确认客群。
2. 每个客群都有评论、用户任务、尺寸价格、卖点和参数匹配规则。
3. 每个 SKU 能输出 0-1 个主客群、0-3 个次客群和若干观察/厂家主打/潜在/未满足客群。
4. 品牌信任/复购不得单独生成客群，只能作为购买心理增强。
5. 服务履约、物流安装、售后体验不得进入产品客群。
6. 负向评论能形成 `unmet_group_need`，不得简单排除客群。
7. 卖点强但评论弱时，不得直接判主客群；应输出 `brand_claimed_group` 或 `latent_group`。
8. 参数强但评论/卖点弱时，不得直接证明真实购买人群；应输出 `latent_group`。
9. 目标客群覆盖统计能查询每个客群包含哪些 SKU，并区分主/次/观察/厂家主打/潜在/未满足。
10. CLI 和 skill 能用自然语言执行和查询。

## 11. 性能与安全

M10C 不需要运行时 LLM，默认确定性执行。

执行策略：

- 当前 TV 首版可一次读取目标 SKU 集合并生成 SKU x 10 个客群分数；可用 `sku_code` 限定单 SKU 或小范围重跑。
- 每次执行只读取目标 SKU 的参数、卖点、评论和市场事实；不直接扫描原始评论。
- 后续多品类或大规模 SKU 扩展时，再补充 chunk 执行和覆盖统计单独重建能力。
- 测试不得调用外部 LLM。
- 输出必须带 `project_id`、`category_code`、`batch_id`、`taxonomy_version`、`rule_version`、`evidence_ids`、`confidence` 和 `review_status`。
