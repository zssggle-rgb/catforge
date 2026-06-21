# 电视评论事实维度草案 v0.1

生成时间：2026-06-21  
数据来源：205 `/opt/catforge`，`catforge_dev`，`project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`，`batch_id=m00_20260619084551_857df63b`。  
主语料：M02 `core3_evidence_atom`，`evidence_type='comment_sentence'`，`category_code='TV'`，`sku_code like 'TV%'`。

## 1. 当前数据口径

M02 评论主语料：

| 口径 | 行数 | 覆盖 SKU |
| --- | ---: | ---: |
| `comment_raw` | 7,986 | 183 |
| `comment_sentence` | 20,060 | 183 |
| `comment_dimension` | 7,986 | 183 |

同批次事实资产：

| 资产 | 行数 | 覆盖 SKU | 用途 |
| --- | ---: | ---: | --- |
| M03B `core3_sku_param_profile` | 293 | 293 | 每个 SKU 的标准参数事实画像 |
| M03B `core3_sku_param_dimension_tier` | 2,637 | 293 | 每个 SKU 在尺寸、画质、性能、智能、接口、外观、能效等维度的档位 |
| M04C `core3_sku_claim_fact_profile` | 293 | 293 | 每个 SKU 的标准卖点事实画像 |
| M04C `core3_sku_claim_fact` | 7,275 | 293 | 每个 SKU 的标准卖点命中、参数支撑状态和卖点维度 |

说明：

1. M02 评论覆盖 183 个 TV SKU，少于 M03B/M04C 的 293 个 TV SKU，这是评论源数据覆盖差异，不代表参数或卖点缺失。
2. 本草案只用 M02 作为产品评论事实主语料；M01 被过滤内容只作为抽样复核池，不进入主分析。
3. M04C 里的 `service_fulfillment` 卖点维度只作为过滤/审计边界，不进入产品评论事实画像。

## 2. 维度生成原则

评论事实维度分两层使用：

### 2.1 品类层：生成标准评论维度

品类层输入：

- M02 电视评论句子。
- M03B 电视标准参数 taxonomy。
- M04C 电视标准卖点 taxonomy。

标准参数和标准卖点在这里的作用是“锚点”，用于提醒评论维度不要漏掉品类重要能力，例如画质、刷新率、亮度、分区控光、语音、投屏、HDMI2.1、超薄、无缝贴墙、能效、性价比等。

品类层不能推出某个 SKU 被评论支持。它只回答：电视评论事实应该从哪些维度观察。

### 2.2 SKU 层：判断本 SKU 是否被评论支持

SKU 层输入：

- 这个 SKU 自己的 M02 评论句子。
- 这个 SKU 自己的 M03B 参数事实画像。
- 这个 SKU 自己的 M04C 卖点事实画像。

SKU 层只允许形成以下关系：

| 关系 | 判断口径 |
| --- | --- |
| 参数被评论支持 | SKU 有该参数事实，且本 SKU 评论出现一致体验证据 |
| 参数被评论反证 | SKU 有该参数事实，但本 SKU 评论出现相反体验证据 |
| 参数未被评论提及 | SKU 有该参数事实，但本 SKU 评论没有相关体验证据 |
| 评论提到但参数缺失 | 评论出现明确产品体验，但 SKU 参数画像没有对应参数，进入“参数可能缺漏/弱相关/待复核” |
| 卖点被评论支持 | SKU 有该标准卖点，且本 SKU 评论出现一致体验证据 |
| 卖点被评论反证 | SKU 有该标准卖点，但本 SKU 评论出现相反体验证据 |
| 卖点未被评论提及 | SKU 有该标准卖点，但本 SKU 评论没有相关体验证据 |
| 评论新增产品事实 | 评论出现有价值体验，但 SKU 卖点没有覆盖，作为后续卖点补充候选 |

必须避免把“品类标准参数/卖点存在”误判为“某个 SKU 已经被评论证明”。

## 3. 抽样覆盖观察

以下是基于 M02 `comment_sentence` 的关键词抽样覆盖。该统计用于判断维度是否有真实语料支撑，不是最终标签覆盖率；不同维度之间允许重叠。

| 候选维度 | 命中句子 | 覆盖 SKU | 观察 |
| --- | ---: | ---: | --- |
| 画质/屏幕 | 8,864 | 182 | 评论主轴，覆盖清晰度、色彩、亮度、暗场、护眼、拖影、反光等 |
| 音质/影院 | 4,416 | 173 | 与观影场景高度重叠，既有音质评价，也有家庭影院感受 |
| 系统/交互 | 3,367 | 169 | 包含系统流畅、开机、广告、遥控、语音、投屏、联网等 |
| 游戏/运动 | 642 | 132 | 绝对量较少，但对高刷、HDMI2.1、低延迟和体育场景很关键 |
| 人群线索 | 884 | 141 | 老人、孩子、父母、家庭、自用/送礼等明显存在 |
| 用途线索 | 1,827 | 163 | 客厅、卧室、追剧、电影、看球、游戏、投屏等明显存在 |
| 尺寸/空间 | 3,554 | 174 | 尺寸、英寸、观看距离、挂墙、卧室/客厅适配均有支撑 |
| 价格/价值 | 2,552 | 170 | 性价比、价格、优惠、同价位、值得购买等高频 |
| 品牌力/竞品词 | 1,806 | 165 | 需拆成“本品牌信任/复购/推荐”和“竞品对比”；前者是品牌力事实，后者是竞品线索 |

负向候选约 2,404 句、覆盖 163 个 SKU，但关键词会误命中“不卡顿”“无广告”“不反光”等正向表达，后续必须做否定方向判断。

## 4. 标准参数锚点

M03B TV 标准参数已覆盖以下参数组，生成评论事实维度时应作为品类锚点：

| 参数组 | 关键标准参数 | 对评论维度的作用 |
| --- | --- | --- |
| 尺寸 | `screen_size_inch`、`screen_size_segment` | 支撑尺寸大小、客厅/卧室适配、观看距离、巨幕体验 |
| 画质 | `resolution_class`、`resolution_pixels`、`display_technology_family`、`mini_led_flag`、`mini_led_type`、`quantum_dot_flag`、`hdr_support_flag`、`declared_brightness_nit_or_band`、`color_gamut_ratio`、`high_color_gamut_flag`、`local_dimming_zone_count`、`declared_refresh_rate_hz`、`backlight_source`、`backlight_subtype` | 支撑清晰度、显示技术、亮度/HDR、色彩、控光、刷新率、护眼/防眩等评论事实 |
| 性能 | `processor_chip_model`、`processor_vendor`、`cpu_core_count`、`cpu_frequency_ghz`、`gpu_core_count`、`ram_gb`、`storage_gb` | 支撑系统流畅、应用打开速度、卡顿、芯片/存储卖点验证 |
| 智能 | `ai_model_name`、`ai_model_capability_flag`、`ai_capability_flag`、`voice_engine`、`voice_recognition_flag`、`far_field_voice_flag`、`whole_home_control_flag`、`smart_tv_flag`、`network_tv_flag`、`wifi_builtin_flag`、`camera_flag` | 支撑 AI、语音、投屏、联网、智能家居、摄像头互动等评论事实 |
| 接口 | `hdmi_version_mix`、`hdmi_2_1_port_count`、`hdmi_port_count`、`usb_version_mix`、`usb_3_0_flag`、`usb_port_count` | 支撑游戏主机、HDMI2.1、接口够用、连接能力 |
| 外观安装 | `slim_design_label`、`slim_design_flag`、`body_thickness_mm`、`full_screen_design_flag`、`flush_wall_mount_flag`、`product_color`、`portable_tv_flag` | 支撑超薄、窄边框、全面屏、壁画/无缝贴墙、颜值质感 |
| 内容/系统 | `content_license_provider`、`streaming_platform_bundle`、`vod_flag`、`os_family`、`os_distribution`、`os_version_detail` | 支撑内容资源、系统生态、应用体验 |
| 能效 | `energy_efficiency_grade`、`energy_efficiency_index`、`standby_power_w` | 支撑节能、一级能效、长期使用成本 |
| 身份 | `brand_name_standard`、`product_series`、`brand_type_internet_flag` | 支撑品牌/系列识别；结合评论中的信任、复购、推荐表达形成品牌力事实 |

## 5. 标准卖点锚点

M04C TV 标准卖点维度可作为评论事实维度的品类锚点：

| 卖点维度 | 标准卖点 | 评论事实观察 |
| --- | --- | --- |
| `picture_quality` | MiniLED、QD-MiniLED、RGB-MiniLED、OLED、HDR/高亮、广色域/色彩还原、分区控光、画质芯片/AI 画质、护眼显示 | 评论应观察画质清晰、色彩、亮度、暗场、反光/刺眼、拖影、屏幕瑕疵、真实观影感受 |
| `motion_gaming` | 高刷新率、游戏/低延迟、HDMI2.1 | 评论应观察游戏主机、打游戏、看球、运动画面、延迟、拖影、流畅度 |
| `smart_interaction` | AI 大模型、语音控制、家电联动、投屏/无线连接、摄像头互动 | 评论应观察语音灵敏、投屏稳定、联网、遥控、智能功能是否好用 |
| `audio_cinema` | 杜比/影音认证、音响/声道、影院/观影场景 | 评论应观察音质、音量、环绕、低音、电影/追剧沉浸感 |
| `appearance_installation` | 超薄机身、全面屏/窄边框、无缝贴墙/壁画安装、金属/质感设计 | 评论应观察薄厚、上墙效果、边框、家装融合、外观质感 |
| `system_performance` | 芯片/处理器性能、运行内存/存储 | 评论应观察开机、系统流畅、应用切换、卡顿、广告 |
| `energy_value` | 能效/节能、价格/性价比表达 | 评论应观察节能、一级能效、同价位、补贴、物超所值、价格贵/便宜 |
| `service_fulfillment` | 服务履约/售后 | 不进入产品评论事实画像；只作为过滤/审计边界 |

## 6. 标准评论事实维度草案

### 6.1 画质与屏幕体验

定义：用户对电视显示效果的直接体验评价。

二级维度：

- 清晰度/分辨率：清晰、细腻、模糊、糊、4K、高清。
- 显示技术感知：MiniLED、OLED、量子点、背光、屏幕档次。
- 亮度/HDR/白天观看：亮度足、白天清晰、太暗、刺眼。
- 色彩/色准：色彩鲜艳、自然、真实、偏色。
- 暗场/对比度/控光：黑位、暗场细节、漏光、灰、控光。
- 运动流畅/拖影：看球、动作片、拖影、丝滑。
- 护眼/防眩/反光：不刺眼、低蓝光、不反光、白天反光。
- 屏幕质量风险：坏点、闪屏、黑屏、屏幕瑕疵。

标准参数锚点：`resolution_class`、`resolution_pixels`、`display_technology_family`、`mini_led_flag`、`mini_led_type`、`quantum_dot_flag`、`hdr_support_flag`、`declared_brightness_nit_or_band`、`color_gamut_ratio`、`high_color_gamut_flag`、`local_dimming_zone_count`、`declared_refresh_rate_hz`、`backlight_source`、`backlight_subtype`。

标准卖点锚点：`tv_claim_miniled_display`、`tv_claim_qd_miniled_display`、`tv_claim_rgb_miniled_display`、`tv_claim_oled_self_lit`、`tv_claim_hdr_high_brightness`、`tv_claim_wide_color_accuracy`、`tv_claim_local_dimming`、`tv_claim_picture_engine_ai`、`tv_claim_eye_care_display`、`tv_claim_high_refresh_rate`。

样本证据：

- `TV00027812`：黑色全黑、杜比片源、晚上灯光很亮。
- `TV00028424`：Mini LED 画质细腻、控光效果好、暗场细节到位、4K 120Hz 看球赛/玩游戏丝滑。
- `TV00027807`：看卫视电视画质低于预期，有时有拖影。

后续用途：支撑画质价值战场、观影/体育/游戏任务、溢价卖点验证、屏幕风险识别。

### 6.2 音质与影院体验

定义：用户对声音、音效、影音沉浸感和家庭影院场景的体验评价。

二级维度：

- 音质/音效：音质好、声音清晰、低音、环绕、音质差。
- 音量/声压：声音大、声音小、不用开很大声。
- 影音认证/片源体验：杜比、全景声、IMAX、HDR10 等感知。
- 家庭影院感：像电影院、追剧/看电影沉浸感。

标准参数锚点：`screen_size_inch`、`hdr_support_flag`、`declared_brightness_nit_or_band`；当前 M03B 对音响硬规格参数不足，评论可作为后续补充参数/卖点候选。

标准卖点锚点：`tv_claim_dolby_audio_video`、`tv_claim_speaker_sound`、`tv_claim_theater_scene`。

样本证据：

- `TV00027809`：画质清晰细腻、色彩自然、音质饱满立体。
- `TV00027652`：视听效果非常棒，就像在电影院一样。
- `TV00030293`：音响效果太差。

后续用途：支撑家庭影院任务、影音型目标客群、影音增强卖点验证。

### 6.3 系统性能与交互体验

定义：用户对电视系统速度、操作、广告、遥控、语音、投屏、联网和应用体验的评价。

二级维度：

- 系统流畅/卡顿：流畅、不卡、卡顿、反应慢、应用切换。
- 开机与广告：开机快/慢、无广告、广告多。
- 遥控/操作：操作简单、遥控灵敏、界面习惯。
- 语音/AI：语音灵敏、声控、AI 智能。
- 投屏/连接：投屏稳定、WiFi、蓝牙、联网。
- 内容/应用：资源丰富、追剧看综艺、应用生态。

标准参数锚点：`processor_chip_model`、`processor_vendor`、`cpu_core_count`、`cpu_frequency_ghz`、`ram_gb`、`storage_gb`、`os_family`、`os_distribution`、`os_version_detail`、`ai_model_name`、`ai_model_capability_flag`、`ai_capability_flag`、`voice_engine`、`voice_recognition_flag`、`far_field_voice_flag`、`wifi_builtin_flag`、`smart_tv_flag`、`network_tv_flag`、`streaming_platform_bundle`。

标准卖点锚点：`tv_claim_chip_performance`、`tv_claim_memory_storage`、`tv_claim_ai_large_model`、`tv_claim_voice_control`、`tv_claim_casting_connectivity`、`tv_claim_smart_home_iot`。

样本证据：

- `TV00027699`：运行速度很流畅，开机没有广告。
- `TV00028831`：系统流畅不卡，语音灵敏好用。
- `TV00028121`：感觉开机有点慢。

后续用途：支撑老人易用、智能交互、系统性能战场，验证“流畅/AI/语音/投屏”等卖点。

### 6.4 游戏与运动流畅

定义：用户在游戏、主机连接、体育赛事、运动画面中的体验。

二级维度：

- 主机游戏：PS5、Xbox、主机、游戏模式。
- 高刷/低延迟：120Hz、144Hz、170Hz、240Hz、288Hz、低延迟、丝滑。
- HDMI2.1/接口：满血 HDMI2.1、4K120、接口够用。
- 体育/运动画面：看球、球赛、拖影、运动防抖。

标准参数锚点：`declared_refresh_rate_hz`、`hdmi_version_mix`、`hdmi_2_1_port_count`、`hdmi_port_count`、`usb_version_mix`、`usb_3_0_flag`。

标准卖点锚点：`tv_claim_high_refresh_rate`、`tv_claim_gaming_low_latency`、`tv_claim_hdmi21_connectivity`。

样本证据：

- `TV00027687`：有游戏模式，配合 PS5 可以上 4K 高刷。
- `TV00029301`：4 路满血 HDMI2.1 + 170Hz 高刷，接主机延迟很低。
- `TV00027807`：看卫视电视画质低于预期，有时有拖影。

后续用途：支撑游戏任务、体育任务、年轻/主机玩家客群、运动游戏价值战场。

### 6.5 外观、安装与空间适配

定义：用户对电视尺寸、外观、薄厚、挂墙、壁画效果、客厅/卧室适配的评价。

二级维度：

- 尺寸感知：大、小、刚好、压迫、巨幕。
- 空间适配：客厅、卧室、观看距离、小户型、出租房。
- 挂墙/上墙：挂墙方便、上墙效果、插座/走线、贴墙缝隙。
- 外观质感：超薄、窄边框、全面屏、金属感、壁画。

标准参数锚点：`screen_size_inch`、`screen_size_segment`、`slim_design_label`、`slim_design_flag`、`body_thickness_mm`、`full_screen_design_flag`、`flush_wall_mount_flag`、`product_color`。

标准卖点锚点：`tv_claim_slim_body`、`tv_claim_full_screen_design`、`tv_claim_flush_wall_mount`、`tv_claim_premium_material_design`、`tv_claim_theater_scene`。

样本证据：

- `TV00027801`：65 寸放在客厅大小刚好，性价比很高。
- `TV00029939`：85 寸壁纸电视上墙效果惊艳。
- `TV00029940`：电视背面不要留插座，否则贴墙有缝隙。

后续用途：支撑尺寸段画像、客厅/卧室任务、壁画/家装战场、竞品池尺寸匹配。

### 6.6 价格、价值与市场位置

定义：用户对价格、性价比、同价位、补贴、预算和值不值得买的判断。

二级维度：

- 性价比/物超所值：性价比高、划算、值得买。
- 价格负担：贵、便宜、预算、价格可以。
- 促销/补贴：优惠、活动、补贴、以旧换新。
- 同价位比较：同价位最优、配置对得起价格。

标准参数锚点：不直接由参数决定，但可结合 M07 市场画像中的价格带、销量位置、尺寸段位置。

标准卖点锚点：`tv_claim_value_price`、`tv_claim_energy_efficiency`。

样本证据：

- `TV00029034`：预算中等家庭用户，大屏、流畅、无广告，兼顾影音和游戏，同价位选择之一。
- `TV00030299`：农村用，这个价格比较便宜，画质也还可以。
- `TV00028424`：买了一个多月降了 800 多，不建议购买。

后续用途：支撑价格带价值战场、性价比客群、同价位竞品筛选、溢价卖点判断。

### 6.7 人群线索

定义：评论中明确出现的使用者、购买对象或家庭成员线索。这里先保留事实，不直接上升为目标客群。

二级维度：

- 老人/父母：老人、爸妈、父母、外婆、老人家。
- 孩子/儿童：孩子、小孩、宝宝、动画、护眼。
- 家庭/全家：全家人、家人、一家人、客厅主电视。
- 年轻/玩家：年轻、游戏、PS5、电竞。
- 送礼/自用/复购：送礼、自用、再次购买、给家里买。
- 租房/出租/农村：出租、租房、农村用、老家用。

标准参数锚点：无直接硬参数；可间接关联 `screen_size_inch`、护眼、系统交互、语音、无广告、价格带。

标准卖点锚点：按场景关联 `tv_claim_eye_care_display`、`tv_claim_voice_control`、`tv_claim_value_price`、`tv_claim_theater_scene`、`tv_claim_gaming_low_latency`。

样本证据：

- `TV00028087`：买给家里老人用，开机没有广告，可以设置快捷键。
- `TV00029104`：护眼模式孩子看动画也不担心伤眼。
- `TV00028108`：出租必备，老人宅家必备，也适合宝宝看动画片。

后续用途：作为目标客群生成的事实输入，不直接生成最终客群结论。

### 6.8 用途/用户任务线索

定义：评论中明确出现的使用任务或使用场景。这里先保留事实，不直接上升为用户任务。

二级维度：

- 客厅主电视：客厅、家用、大屏、家庭影院。
- 卧室副电视：卧室、房间、大小合适。
- 观影/追剧：电影、看剧、追剧、综艺、影院。
- 体育赛事：看球、球赛、春晚等强观看场景。
- 游戏/主机：打游戏、PS5、主机、游戏电视。
- 投屏/联网：投屏、手机投、网络电视。
- 商用/会议：会议、商用、展示。

标准参数锚点：`screen_size_inch`、`screen_size_segment`、`declared_refresh_rate_hz`、`hdmi_2_1_port_count`、`wifi_builtin_flag`、`network_tv_flag`。

标准卖点锚点：`tv_claim_theater_scene`、`tv_claim_high_refresh_rate`、`tv_claim_gaming_low_latency`、`tv_claim_hdmi21_connectivity`、`tv_claim_casting_connectivity`。

样本证据：

- `TV00030268`：投屏稳定，大屏观影、追剧、游戏体验都很出色。
- `TV00029123`：打游戏更舒服。
- `TV00028703`：可以直接投屏看电影。

后续用途：作为用户任务生成的事实输入，不直接生成最终任务结论。

### 6.9 品牌力、复购与竞品提及

定义：评论中出现品牌信任、品牌推荐、复购、型号提及、跨品牌对比或平台选择线索。这里的“本品牌信任/复购”不是噪声，也不是竞品误判项，而是品牌力在用户评论中的事实表现。

二级维度：

- 本品牌信任/复购：大品牌、老牌子、一直用、再次购买、家里第一台也是该品牌。
- 品牌推荐/口碑影响：朋友推荐、家人推荐、相信某品牌、值得信赖。
- 明确型号提及：评论里写出品牌 + 型号或系列。
- 跨品牌对比：比某品牌/某型号好或差，或者明确“对比/比较”。
- 替换来源：原来用某品牌，现在换本 SKU。
- 平台/渠道比较：同款平台、到货/价格平台差异。若只涉及物流服务，不进入产品事实。

标准参数锚点：`brand_name_standard`、`product_series`、`brand_type_internet_flag` 用于识别品牌和系列。评论中出现信任、复购、推荐、长期使用等表达时，形成品牌力事实；出现明确比较对象时，形成竞品线索。

标准卖点锚点：无固定卖点锚点；品牌力事实可支撑后续品牌力画像，跨品牌比较中提到的具体能力应同时落到画质、价格、系统、游戏等产品维度。

样本证据：

- `TV00027812`：原来用索尼，这个比投影强很多。
- `TV00030130`：同价格下比某品牌电视好很多。
- `TV00028907`：朋友推荐这个牌子，别的没看，就喜欢创维。

后续用途：支撑品牌力画像、品牌忠诚/复购分析、口碑推荐分析、竞品库候选、替换来源分析、同价位对比证据。必须区分本品牌信任/复购/推荐和真正竞品对比，但两者都属于评论事实。

### 6.10 质量稳定性与产品风险

定义：评论中对产品故障、稳定性、耐用性、屏幕/系统风险的反馈。

二级维度：

- 屏幕风险：闪屏、黑屏、坏点、漏光、反光严重。
- 系统风险：卡顿、死机、开机慢、广告多。
- 音画风险：音质差、画质低于预期、拖影。
- 耐用/故障：坏了、故障、退货、希望耐用。

标准参数锚点：不直接由参数证明；可关联屏幕、系统、性能参数做反证或风险说明。

标准卖点锚点：与对应卖点反证相关，例如画质、系统流畅、音响、护眼、游戏等。

样本证据：

- `TV00028424`：广告太多，买后降价明显，不建议购买。
- `TV00028087`：屏幕色调有一点暗。
- `TV00027807`：画质低于预期，有时有拖影。

后续用途：支撑卖点反证、产品风险提示、复核队列。

### 6.11 服务履约隔离维度

定义：物流、安装、客服、售后、保修、送货速度、师傅态度等服务履约内容。

处理原则：

1. 不进入产品评论事实画像。
2. 不用于支持参数、卖点、用户任务、目标客群或价值战场。
3. 可保留在清洗质量审计或独立服务履约分析里。
4. 若一句话同时包含服务和产品事实，应拆句后只保留产品事实句。

## 7. 后续程序化输出建议

标准维度确认后，应新增“评论事实画像”能力，但不应逐条评论发起 LLM 请求。

建议流程：

1. 以 M02 `comment_sentence` 为最小单元。
2. 先用规则快速识别人群、用途、尺寸、价格、品牌、标准参数/卖点关键词。
3. 对复杂句、冲突句、多维句进行 LLM 批处理，每批 30-80 句，输出结构化 JSON。
4. 对每个句子可输出多个评论事实原子。
5. 再按 SKU 聚合，形成 SKU 评论事实画像。

建议句级结构：

```text
sku_code
sentence_evidence_id
comment_dimension_code
comment_subdimension_code
polarity
evidence_strength
audience_signal
use_case_signal
size_space_signal
price_value_signal
brand_affinity_signal
brand_power_signal
competitor_comparison_signal
linked_sku_param_codes
linked_sku_claim_codes
support_relation
confidence
evidence_text
```

建议 SKU 级聚合：

```text
sku_code
comment_fact_profile
supported_param_codes
contradicted_param_codes
unmentioned_param_codes
comment_only_param_candidates
supported_claim_codes
contradicted_claim_codes
unmentioned_claim_codes
comment_only_claim_candidates
audience_signals
use_case_signals
size_space_signals
price_value_signals
brand_affinity_signals
brand_power_signals
competitor_comparison_signals
positive_evidence_examples
negative_evidence_examples
review_required_items
```

## 8. 需要复核的边界

1. 品牌词命中不能直接等于竞品提及；同品牌复购、品牌信任、品牌推荐应单列为品牌力评论事实。
2. 负向关键词不能直接等于负面评论；“不卡顿”“无广告”“不反光”是正向，需要否定方向识别。
3. M04C 的服务履约卖点必须隔离，不进入产品评论事实。
4. 音响硬参数当前不足，评论里的音质证据可能需要反向推动参数表补充。
5. M02 当前有全局去重逻辑，适合维度归纳；后续如果要计算 SKU 级提及率，需要确认是否改为 SKU 内去重或保留重复计数。
6. 评论维度是事实层输入，不直接生成目标客群、用户任务、价值战场；这些应由后续语义能力层基于事实再生成。
