# M09C 用户任务画像 SOP 需求

## 0. 定位

M09C 是新语义能力层的“用户任务画像”模块。它基于 M03B 参数事实、M04C 卖点事实、M05C 评论事实和尺寸价格事实，为每个 SKU 判断其主用户任务、次用户任务、评论观察任务、厂家主打任务、潜在能力任务和拖后腿任务，并生成用户任务覆盖统计。

M09C 不沿用旧 M09 的 10 个 seed 任务，也不读取旧 M08/M09/M10/M11 结果作为主链路输入。旧 M09 保留历史兼容和对照验证，新链路使用本文件定义的 TV 12 个用户任务预设。

用户任务回答：

```text
用户买这台 SKU，主观上想完成什么使用或购买目的；这个判断由评论、卖点、参数、尺寸价格和市场表现中的哪些证据支撑。
```

用户任务不是参数、卖点、评论主题或价格带的直接标签。评论代表用户真实目的和体验，是最高优先级；卖点代表厂家想打什么；参数代表产品能力能否支撑；尺寸价格代表该任务是否处在合理竞争池中；销量和销额只能做验证。销量/销额验证必须使用同尺寸 SKU 重叠在售周的周均表现，累计销量只可展示，不可参与任务判断。

负向评论不是排除任务。负向评论说明用户有这个任务需求，但产品没有做好，必须保留为 `drag_factor_task` 或未满足需求，不能简单删除。

## 1. 总体原则

### 1.1 证据优先级

M09C 的证据优先级为：

```text
评论中的真实用途/购买目的/体验表达
-> 标准卖点表达
-> 标准参数能力
-> M03B 五档尺寸和尺寸内价格带适配
-> 同尺寸重叠周周均销量/销额验证
```

说明：

1. 评论里直接出现用途、购买对象、使用场景、体验痛点或购买动机时，优先级最高。
2. 评论强支持 + 卖点/参数支持，可成为主用户任务，相关卖点才可能成为后续溢价点。
3. 评论强支持 + 卖点支持 + 参数弱/缺失，可成为主用户任务，但卖点有支撑风险。
4. 评论强支持 + 卖点/参数都弱，仍可成为主用户任务，但产品未满足，是短板或拖后腿。
5. 评论负向集中仍可形成用户任务，并标记负向任务痛点。
6. 卖点强 + 参数强 + 评论弱/无，只能是厂家主打任务或推断任务，不是主用户任务。
7. 参数强 + 卖点弱 + 评论弱/无，只能是潜在能力任务，不是主用户任务。
8. 卖点强 + 参数弱 + 评论弱/无，是宣传任务，需复核或降级。
9. 三类证据都弱时，任务不成立。
10. 允许 `primary_user_task_count = 0`，但必须说明是评论不足、证据分散、事实层缺失还是尺寸价格不适配。

### 1.2 与 M10C/M11C 的关系

M09C 输出是后续目标客群和价值战场的正式任务输入。

当前开发序列中，M10C/M11C 已经有首版代理规则，可在没有 M09C 输出时运行。M09C 落地后：

- M10C 应优先消费 M09C 的 `primary_user_task`、`secondary_user_task`、`drag_factor_task`，替代原来的 `task_proxy_support`。
- M11C 应优先消费 M09C 的用户任务画像，增强战场的 `task_group_fit_score`。
- M09C 不反向读取 M10C/M11C 结果，避免循环依赖。

## 2. 模块边界

### 2.1 必须解决

1. 加载已发布的 TV 用户任务 taxonomy。
2. 对每个 SKU 计算 SKU x 用户任务关系。
3. 区分主用户任务、次用户任务、评论观察任务、厂家主打任务、潜在能力任务、拖后腿任务和不支持。
4. 对每个任务输出评论、卖点、参数、尺寸价格和市场验证证据。
5. 负向评论不排除任务需求，而是识别为 `drag_factor_task` 或支撑风险。
6. 输出每个 SKU 的用户任务画像和每个用户任务覆盖哪些 SKU。
7. 提供 CLI 执行和查询能力，并能被 Claude Code skill 用自然语言驱动。

### 2.2 不解决

| 不做事项 | 原因 |
| --- | --- |
| 不生成目标客群 taxonomy | 目标客群由 M10C 或人工发布客群预设负责 |
| 不生成价值战场 taxonomy | 价值战场由 M11C 负责 |
| 不把品牌信任/复购当作用户任务 | 它是购买心理增强因素，不是使用任务 |
| 不把服务履约作为产品任务 | 服务、物流、安装、售后只能作为服务语境或风险 |
| 不直接判断核心竞品 | 竞品召回和评分由后续竞品分析层负责 |
| 不强制每个 SKU 都有主任务 | 评论不足或证据分散时可以没有高置信主任务 |
| 不调用运行时 LLM 动态创建任务 | M09C 基于已发布预设确定性执行 |
| 不读取原始四张表直接做业务判断 | 必须消费上游事实层产物 |

## 3. 输入

### 3.1 必须输入

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| 用户任务 taxonomy | 人工/LLM 辅助生成并发布的品类资产 | 任务定义、证据规则、状态封顶规则 |
| SKU 参数事实画像 | M03B | 尺寸五档、画质、刷新率、亮度、智能、护眼、外观、接口等产品能力 |
| SKU 卖点事实画像 | M04C | 标准卖点、参数支撑状态、卖点维度位置 |
| SKU 评论事实画像 | M05C | 用户用途、人群、购买动机、价格价值、品牌力、竞品、正负向体验 |
| SKU 量价事实 | M07 价格事实 + M01 清洗周度量价 | 尺寸内价格带、同尺寸重叠周周均销量/销额位置、价格/英寸、市场验证 |

M09C 必须统一使用 M03B 参数事实画像中的五档尺寸口径：

| 尺寸档 | 规则 |
| --- | --- |
| `small_32_45` | `screen_size_inch <= 45` |
| `medium_46_59` | `46 <= screen_size_inch <= 59` |
| `large_60_69` | `60 <= screen_size_inch <= 69` |
| `xlarge_70_85` | `70 <= screen_size_inch <= 85` |
| `giant_98_plus` | `screen_size_inch >= 98` |

价格带不是原始量价表字段。M09C 必须在五档尺寸内按加权均价分位派生 `low/mid_low/mid/mid_high/high`，不得使用旧 M07 的 `compact_screen/mainstream_living/large_upgrade/ultra_large_flagship` 作为主口径。

### 3.2 禁止输入

| 禁止输入 | 原因 |
| --- | --- |
| 原始 `comment_data` | 评论事实必须来自 M05C |
| 原始 `selling_points_data` | 卖点事实必须来自 M04C |
| 原始 `attribute_data` | 参数事实必须来自 M03B |
| 原始 `week_sales_data` | 市场事实必须来自 M07 或新市场事实模块 |
| 旧 M06 下游信号 | 旧 seed 与新任务/客群/战场口径不一致 |
| 旧 M09 任务结果 | 新 M09C 需要独立生成，不继承旧结果 |
| M10C/M11C 输出 | M09C 是它们的正式上游，不反向读取 |

## 4. TV 首版用户任务预设

M09C 必须沿用已确认的 12 个 TV 用户任务 code 和含义。

| task_code | 名称 | 业务定义 |
| --- | --- | --- |
| `TASK_MAINSTREAM_LIVING_VIEWING` | 主流客厅日常观影 | 家庭日常看电视、追剧、综艺，要求尺寸合适、画质够用、系统稳定 |
| `TASK_CINEMA_IMMERSION` | 影院沉浸观影 | 在客厅/大空间看电影、大片、剧集，追求大屏、HDR、音效、沉浸感 |
| `TASK_PREMIUM_PICTURE_EXPERIENCE` | 高端画质体验 | 重点追求亮度、控光、色彩、MiniLED/OLED/QD、画质芯片 |
| `TASK_LARGE_SCREEN_UPGRADE` | 大屏换新升级 | 从小屏/旧电视升级到 70/75/85/98 寸以上，核心是屏幕变大和换新价值 |
| `TASK_GAMING_CONSOLE_ENTERTAINMENT` | 主机游戏娱乐 | 连接游戏主机或高帧娱乐，关注高刷、HDMI2.1、VRR、低延迟 |
| `TASK_SPORTS_MOTION_WATCHING` | 体育赛事观看 | 看球赛、运动、赛车等高速画面，关注流畅、拖影、运动补偿 |
| `TASK_EYE_CARE_LONG_WATCHING` | 长时间护眼观看 | 儿童、家庭、长时间观看场景，关注护眼、低蓝光、无频闪、舒适度 |
| `TASK_SENIOR_EASY_OPERATION` | 长辈易用操作 | 给父母/老人使用，关注语音、遥控简单、系统清爽、少广告 |
| `TASK_BEDROOM_SECOND_SCREEN` | 卧室/副屏小空间 | 卧室、租房、第二台电视，小尺寸、低价、易用、够用 |
| `TASK_SMART_CASTING_IOT` | 投屏互联与智能控制 | 手机投屏、无线连接、AI 语音、家电联动、摄像头互动等智能场景 |
| `TASK_HOME_DECOR_SPACE_FIT` | 新家装修与空间融合 | 新家、客厅布置、贴墙、超薄、全面屏、外观和空间适配 |
| `TASK_VALUE_FOR_MONEY_PURCHASE` | 预算内高性价比购买 | 在预算内追求更大尺寸、更好配置、更高销量口碑或补贴价格 |

## 5. 每个任务的匹配规则

### 5.1 `TASK_MAINSTREAM_LIVING_VIEWING`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `use_living_room_cinema`、`audience_child_family`，或评论出现客厅、家庭、全家、日常看、追剧、综艺、电视剧、老人孩子一起看 |
| 卖点 | `tv_claim_theater_scene`、`tv_claim_hdr_high_brightness`、`tv_claim_speaker_sound`、`tv_claim_eye_care_display`、`tv_claim_voice_control` |
| 参数 | `screen_size_inch`、`resolution_class`、`hdr_support_flag`、`memory_capacity_gb`、`speaker_power_w`、`declared_refresh_rate_hz` |
| 尺寸价格 | `medium_46_59`、`large_60_69`、`xlarge_70_85`；价格带 `low` 到 `mid_high` 均可，`mid/mid_high` 更偏均衡体验 |
| 市场 | 同尺寸重叠在售周的周均销量或销额不弱可增强；缺市场不直接否定 |

### 5.2 `TASK_CINEMA_IMMERSION`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `use_living_room_cinema`、`audio_quality`、画质/音效正向，或评论出现电影、大片、影院、沉浸、震撼、大屏、客厅效果 |
| 卖点 | `tv_claim_theater_scene`、`tv_claim_hdr_high_brightness`、`tv_claim_dolby_audio_video`、`tv_claim_speaker_sound`、`tv_claim_local_dimming` |
| 参数 | `screen_size_inch`、`hdr_support_flag`、`declared_brightness_nit_or_band`、`speaker_power_w`、`local_dimming_zone_count`、`display_tech_class` |
| 尺寸价格 | `large_60_69`、`xlarge_70_85`、`giant_98_plus` 更匹配；`mid` 以上更可信 |
| 市场 | 大屏尺寸池重叠在售周的周均销量/销额位置可增强沉浸观影任务 |

### 5.3 `TASK_PREMIUM_PICTURE_EXPERIENCE`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `picture_clarity_resolution`、`picture_brightness_hdr`、`picture_color_accuracy`、`picture_local_dimming_black`，或评论出现画质、色彩、亮度、黑位、控光、MiniLED、OLED、电影效果 |
| 卖点 | `tv_claim_miniled_display`、`tv_claim_qd_miniled_display`、`tv_claim_rgb_miniled_display`、`tv_claim_oled_self_lit`、`tv_claim_hdr_high_brightness`、`tv_claim_wide_color_accuracy`、`tv_claim_local_dimming`、`tv_claim_picture_engine_ai` |
| 参数 | `display_tech_class`、`mini_led_flag`、`quantum_dot_flag`、`hdr_support_flag`、`declared_brightness_nit_or_band`、`local_dimming_zone_count`、`color_gamut_ratio`、`processor_chip_model` |
| 尺寸价格 | `large_60_69`、`xlarge_70_85` 为主；价格带 `mid_high/high` 最匹配，`mid` 只能作为高配下探或潜在任务 |
| 市场 | 高价带有重叠周周均销额验证可增强；销量低不直接否定高端画质任务 |

### 5.4 `TASK_LARGE_SCREEN_UPGRADE`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `replacement_source`、`appearance_size_fit`，或评论出现换新、旧电视、上一台、升级、75 寸、85 寸、98 寸、大屏、客厅震撼 |
| 卖点 | `tv_claim_theater_scene`、`tv_claim_value_price`、`tv_claim_full_screen_design` |
| 参数 | `screen_size_inch`、`resolution_class`、`full_screen_design_flag`、`price_per_inch` |
| 尺寸价格 | `xlarge_70_85` 为主，`giant_98_plus` 可进入巨幕升级；`large_60_69` 只能作为入门升级 |
| 市场 | 同尺寸池价格/英寸、重叠周周均销量分位、促销趋势是重要增强 |

### 5.5 `TASK_GAMING_CONSOLE_ENTERTAINMENT`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `use_gaming_sports`、`gaming_high_refresh_motion`，或评论出现游戏、主机、PS5、Xbox、Switch、高刷、低延迟、不卡、VRR |
| 卖点 | `tv_claim_high_refresh_rate`、`tv_claim_gaming_low_latency`、`tv_claim_hdmi21_connectivity` |
| 参数 | `declared_refresh_rate_hz >= 120`、`hdmi_2_1_port_count`、`hdmi_version_mix`、`memc_flag`、`memory_capacity_gb` |
| 尺寸价格 | `medium_46_59`、`large_60_69`、`xlarge_70_85`；价格带 `mid` 以上更匹配 |
| 市场 | 游戏任务主要靠评论、卖点、参数，市场只做同价位配置验证 |

### 5.6 `TASK_SPORTS_MOTION_WATCHING`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `use_gaming_sports`、`gaming_high_refresh_motion`，或评论出现看球、体育、赛事、运动、赛车、流畅、拖影、残影、运动补偿 |
| 卖点 | `tv_claim_high_refresh_rate`、`tv_claim_gaming_low_latency`、MEMC/运动补偿相关卖点 |
| 参数 | `declared_refresh_rate_hz`、`memc_flag`、`hdmi_2_1_port_count`、`processor_chip_model` |
| 尺寸价格 | `medium_46_59` 及以上更匹配；价格带 `mid` 以上更可信，小屏低价只能作为潜在任务 |
| 市场 | 体育任务市场验证弱于评论和参数，不能单独成立 |

### 5.7 `TASK_EYE_CARE_LONG_WATCHING`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `picture_eye_care_reflection`、`audience_child_family`，或评论出现孩子、小孩、儿童、长时间看、不刺眼、不累眼、护眼、舒适、反光 |
| 卖点 | `tv_claim_eye_care_display`、`tv_claim_hdr_high_brightness`、`tv_claim_wide_color_accuracy` |
| 参数 | `eye_care_flag`、低蓝光/无频闪/防眩相关参数、`declared_brightness_nit_or_band`、`declared_refresh_rate_hz`、`hdr_support_flag` |
| 尺寸价格 | `small_32_45`、`medium_46_59`、`large_60_69` 为主；`xlarge_70_85` 可作为家庭长看增强；`mid_low` 以上更可信 |
| 市场 | 护眼任务可由家庭销量和正向评论增强，销量不是必要条件 |

### 5.8 `TASK_SENIOR_EASY_OPERATION`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `audience_senior`、`interaction_voice_casting`、`system_smooth_ads`，或评论出现爸妈、父母、老人、长辈、语音好用、遥控简单、广告少、不卡 |
| 卖点 | `tv_claim_voice_control`、`tv_claim_casting_connectivity`、`tv_claim_ai_large_model` |
| 参数 | `voice_recognition_flag`、`far_field_voice_flag`、`smart_tv_flag`、`network_tv_flag`、`memory_capacity_gb` |
| 尺寸价格 | `small_32_45`、`medium_46_59`、`large_60_69` 为主；价格带 `low/mid_low/mid` 更常见 |
| 市场 | 价格温和、销量稳定可增强；高价型号需有代购父母或家庭升级评论支撑 |

### 5.9 `TASK_BEDROOM_SECOND_SCREEN`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `audience_rental_room`、`use_bedroom`，或评论出现卧室、租房、宿舍、小房间、第二台、副屏、床前、够用 |
| 卖点 | `tv_claim_value_price`、`tv_claim_full_screen_design`、`tv_claim_voice_control` |
| 参数 | `screen_size_inch <= 45`、`resolution_class`、`wifi_builtin_flag`、`smart_tv_flag`、`price_per_inch` |
| 尺寸价格 | `small_32_45` 最匹配，`medium_46_59` 可作为大卧室或租房客厅；价格带 `low/mid_low` 最匹配 |
| 市场 | 小屏低价池销量可增强；大尺寸高价不得成为该任务主任务 |

### 5.10 `TASK_SMART_CASTING_IOT`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `use_casting_online`、`interaction_voice_casting`、`system_smooth_ads`，或评论出现投屏、手机连接、无线、联网、语音、AI、智能家居、家电联动、摄像头 |
| 卖点 | `tv_claim_casting_connectivity`、`tv_claim_voice_control`、`tv_claim_ai_large_model`、`tv_claim_smart_home_iot`、`tv_claim_camera_interaction` |
| 参数 | `wifi_builtin_flag`、`network_tv_flag`、`smart_tv_flag`、`voice_recognition_flag`、`far_field_voice_flag`、`ai_capability_flag`、`ai_model_capability_flag`、`smart_home_iot_flag`、`camera_flag`、`memory_capacity_gb` |
| 尺寸价格 | `medium_46_59` 及以上更匹配；价格带 `mid/mid_high/high` 更可信，小屏智能只能作为小屏易用侧面 |
| 市场 | 智能任务市场验证弱于评论和参数，不能单独成立 |

### 5.11 `TASK_HOME_DECOR_SPACE_FIT`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `appearance_size_fit`、`appearance_slim_wall`，或评论出现新家、装修、客厅布置、上墙、贴墙、超薄、全面屏、外观好看、空间协调 |
| 卖点 | `tv_claim_full_screen_design`、`tv_claim_flush_wall_mount`、`tv_claim_theater_scene` |
| 参数 | `screen_size_inch`、`full_screen_design_flag`、`flush_wall_mount_flag`、机身厚度/边框/外观相关参数 |
| 尺寸价格 | `large_60_69`、`xlarge_70_85`、`giant_98_plus` 更匹配；小屏只可作为卧室/小空间装修侧面 |
| 市场 | 新家装修不能由安装好评单独成立；纯物流安装和售后评价必须隔离 |

### 5.12 `TASK_VALUE_FOR_MONEY_PURCHASE`

| 证据域 | 匹配规则 |
| --- | --- |
| 评论 | `value_price`、`brand_recommendation`，或评论出现性价比、划算、补贴、优惠、价格香、值得买、同价位、预算、便宜、销量好 |
| 卖点 | `tv_claim_value_price`，以及同价位高配的画质、高刷、智能、大屏卖点 |
| 参数 | `screen_size_inch`、`resolution_class`、`declared_refresh_rate_hz`、`declared_brightness_nit_or_band`、`price_per_inch`、重叠周周均销量/销额分位 |
| 尺寸价格 | 所有尺寸均可，但必须体现尺寸内价格效率；`low/mid_low/mid` 更匹配，`mid_high/high` 需要高端配置下探或销量口碑支撑 |
| 市场 | 尺寸内价格分位、重叠周周均销量分位、价格/英寸是核心验证 |

## 6. 关系状态

M09C 输出关系状态必须包括：

| relation_status | 含义 |
| --- | --- |
| `primary_user_task` | 评论/卖点/参数/尺寸价格多域一致，是 SKU 最主要的用户任务 |
| `secondary_user_task` | 任务成立但不是第一目的，或部分证据域较弱 |
| `comment_observed_task` | 用户评论直接出现任务需求，但卖点/参数/价格支撑不足 |
| `brand_claimed_task` | 厂家卖点和参数暗示该任务，但用户评论弱或无 |
| `latent_capability_task` | 参数能力适合该任务，但评论和卖点都弱 |
| `drag_factor_task` | 用户需求明确且负向体验集中，说明该任务下产品没做好 |
| `not_supported` | 证据不足、尺寸价格明显不匹配或服务履约隔离 |

每个 SKU：

- 最多 1 个 `primary_user_task`。
- 最多 2 个 `secondary_user_task`。
- 可以有多个 `comment_observed_task`、`brand_claimed_task`、`latent_capability_task` 和 `drag_factor_task`。
- 可以没有主用户任务，但必须写明原因。

## 7. 评分口径

### 7.1 分项得分

| 分项 | 含义 |
| --- | --- |
| `comment_task_need_score` | 评论中任务需求、用途、购买目的和正负向体验强度 |
| `claim_task_alignment_score` | 标准卖点是否表达该任务价值，且是否有参数支撑 |
| `param_capability_score` | 产品参数是否具备完成该任务的能力 |
| `size_price_fit_score` | M03B 五档尺寸和尺寸内价格带是否适合该任务 |
| `market_validation_score` | 重叠周周均销量/销额、价格/英寸和价格分位是否验证该任务 |
| `negative_drag_score` | 负向评论、反证参数或反证卖点形成的拖后腿程度 |

### 7.2 综合分

首版建议确定性评分：

```text
user_task_score =
  comment_task_need_score * 0.35
  + claim_task_alignment_score * 0.20
  + param_capability_score * 0.20
  + size_price_fit_score * 0.10
  + market_validation_score * 0.07
  - negative_drag_score * 0.05
```

说明：

- 评论权重最高，因为用户任务是主观使用/购买目的。
- 卖点和参数共同判断厂家表达与产品能力是否一致。
- 尺寸价格是适配和封顶条件，不是单独任务来源。
- 市场验证增强可信度，但不能直接生成用户任务。
- 负向评论不删除任务，而是影响状态和价值作用。

### 7.3 状态封顶

| 证据组合 | 最高状态 |
| --- | --- |
| 评论强 + 卖点/参数至少一类强 + 尺寸价格不冲突 | `primary_user_task` |
| 评论强 + 卖点/参数弱 | `comment_observed_task` 或 `drag_factor_task` |
| 评论负向集中 + 需求明确 | `drag_factor_task` |
| 卖点强 + 参数强 + 评论弱 | `brand_claimed_task` |
| 参数强 + 卖点弱 + 评论弱 | `latent_capability_task` |
| 卖点强 + 参数弱 + 评论弱 | `brand_claimed_task`，需复核 |
| 尺寸价格明显不匹配 | 不得成为 `primary_user_task` |
| 纯服务履约命中 | `not_supported`，写入服务语境或风险 |

## 8. 输出

### 8.1 SKU 用户任务画像

每个 SKU 输出：

| 字段 | 含义 |
| --- | --- |
| `primary_user_task_code` | 主用户任务，可空 |
| `secondary_user_task_codes` | 次用户任务，最多 2 个 |
| `comment_observed_task_codes` | 评论观察任务 |
| `brand_claimed_task_codes` | 厂家主打任务 |
| `latent_capability_task_codes` | 潜在能力任务 |
| `drag_factor_task_codes` | 用户需求存在但体验负向或支撑不足的任务 |
| `size_tier` | M03B 五档尺寸口径 |
| `price_band_in_size_tier` | M09C 在尺寸档内计算的价格带 |
| `user_voice_summary` | 评论对任务的正负向摘要 |
| `claim_param_summary` | 卖点和参数支撑摘要 |
| `market_summary` | 尺寸价格和重叠周周均销量验证摘要 |
| `no_primary_reason` | 没有主用户任务时的原因 |
| `review_required` | 是否需要人工复核 |

### 8.2 SKU x 用户任务分数

每个 SKU x 任务输出：

| 字段 | 含义 |
| --- | --- |
| `relation_status` | 关系状态 |
| `user_task_score` | 综合分 |
| `comment_task_need_score` | 评论任务需求分 |
| `claim_task_alignment_score` | 卖点任务表达分 |
| `param_capability_score` | 参数能力分 |
| `size_price_fit_score` | 尺寸价格适配分 |
| `market_validation_score` | 市场验证分 |
| `negative_drag_score` | 负向拖后腿分 |
| `sentiment_polarity` | `positive`、`negative`、`mixed`、`neutral`、`unknown` |
| `confidence` | 置信度 |
| `evidence_ids` | 可追溯证据 |
| `status_reason_cn` | 中文解释 |

### 8.3 用户任务覆盖统计

批次级输出：

| 输出 | 用途 |
| --- | --- |
| 任务覆盖 SKU | 每个任务覆盖哪些 SKU，并区分主/次/观察/厂家主打/潜在/拖后腿 |
| 尺寸分布 | 每个任务下 SKU 的五档尺寸分布 |
| 价格分布 | 每个任务下 SKU 的尺寸内价格带分布 |
| 卖点分布 | 每个任务下主要支撑和拖后腿卖点 |
| 参数分布 | 每个任务下主要参数能力和缺口 |
| 评论维度分布 | 每个任务下主要正负向评论事实维度 |
| 代表 SKU | 每个任务的高置信代表 SKU 和待复核 SKU |

## 9. CLI 与 Skill 要求

### 9.1 Pipeline CLI

实现时必须提供执行 CLI：

```bash
python -m app.cli.catforge_pipeline run-user-task --product-category tv --batch-id latest --force-rebuild --format json
```

必须支持：

| 参数 | 说明 |
| --- | --- |
| `--product-category` | 品类，首版 `tv` |
| `--batch-id` | 批次，默认支持 `latest` |
| `--sku-code` | 只跑单 SKU |
| `--user-task-code` | 只跑指定任务，可重复 |
| `--force-rebuild` | 清理并重算当前范围 |
| `--format` | `json`、`text` |

当前实现每次生成画像后同步重建本批次用户任务覆盖统计，保证跨 SKU 维度统计完整。

自然语言入口必须识别：

- “生成彩电用户任务画像”
- “重新分析某个 SKU 的用户任务”
- “新数据来了，把用户任务准备好”
- “哪些 SKU 是大屏换新任务”

### 9.2 Insight CLI

实现时必须提供查询 CLI：

```bash
python -m app.cli.catforge_insight user-task-taxonomy --product-category tv --format json
```

```bash
python -m app.cli.catforge_insight sku-user-task --sku-code TV00000000 --format json
```

```bash
python -m app.cli.catforge_insight user-task-skus --user-task-code TASK_LARGE_SCREEN_UPGRADE --sku-limit 100 --format json
```

必须支持自然语言查询：

- “查某 SKU 的用户任务”
- “彩电有哪些标准用户任务”
- “大屏换新任务有哪些 SKU”
- “哪些 SKU 在游戏任务上拖后腿”
- “查某任务的参数、卖点、评论证据”

### 9.3 Claude Code Skill

实现 CLI 后必须同步更新：

| Skill | 要求 |
| --- | --- |
| `tools/claude/skills/catforge-pipeline/SKILL.md` | 加入用户任务生成、单 SKU 重跑和覆盖重算的自然语言触发、稳定命令、执行后摘要规则 |
| `tools/claude/skills/catforge-insight/SKILL.md` | 加入任务 taxonomy、SKU 用户任务、任务覆盖 SKU 的查询触发和稳定命令 |

在 CLI 未实现前，不得把未实现命令写入已安装 skill，避免 Claude Code 误执行。

## 10. 验收标准

1. TV 用户任务 taxonomy 覆盖 12 个预设任务。
2. 每个任务都有评论规则、卖点规则、参数规则、尺寸价格规则和市场验证规则。
3. 每个 SKU 能输出 0-1 个主用户任务、0-2 个次用户任务和若干观察/厂家主打/潜在/拖后腿任务。
4. 评论负向集中时，不得简单排除；必须输出 `drag_factor_task` 或未满足任务需求。
5. 卖点强但评论弱时，不得直接判主任务；应输出 `brand_claimed_task` 或潜在任务。
6. 参数强但无评论/卖点时，不得直接判主任务；应输出 `latent_capability_task`。
7. 参数支撑不足的卖点不得作为后续溢价任务证据。
8. 服务履约、物流安装、售后体验不得进入产品用户任务。
9. 覆盖统计能查询每个任务包含哪些 SKU，并区分主/次/观察/厂家主打/潜在/拖后腿状态。
10. CLI 支持全量、单 SKU、单任务和覆盖重建。
11. Skill 能把自然语言请求映射到 CLI 执行或查询。

## 11. 性能与安全

M09C 不需要运行时 LLM，默认确定性执行。

执行策略：

- 当前 TV 首版可一次读取目标 SKU 集合并生成 SKU x 12 个任务分数。
- 可用 `sku_code` 限定单 SKU 或小范围重跑。
- 覆盖统计默认在 SKU 分析完成后重建一次；可用 `coverage_mode=skip` 只写 SKU 画像和分数。
- 后续多品类或大规模 SKU 扩展时，再补充 chunk 执行和覆盖单独重建能力。
- 不得一次加载全量评论原文；只能读取 M05C 聚合画像和必要 evidence 摘要。
- 测试不得调用外部 LLM。
- 输出必须带 `project_id`、`category_code`、`batch_id`、`taxonomy_version`、`rule_version`、`evidence_ids`、`confidence` 和 `review_status`。
