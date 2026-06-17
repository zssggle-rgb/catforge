# 03a 彩电预制知识资产目录

## 1. 预制知识的边界

预制知识不是 SKU 结论，也不是 evidence。它只定义 CatForge 要识别哪些彩电业务概念、这些概念有哪些别名/阈值/映射关系，以及从哪些数据源抽取证据。

SKU 是否具备某个参数、卖点、评论主题、用户任务、目标客群或价值战场，必须由真实 PostgreSQL 数据抽取和计算得到。

当前 `apps/api-server/app/rules/tv_seed_rules.json` 可作为 v0.1 起点，但 Core3 MVP 应新增或升级为：

```text
apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json
```

要求：

- 保留已有稳定 code 的兼容映射。
- 每个预制项必须有 code、中文名、定义、抽取来源、证据要求。
- 新发现的字段、短语、主题只能进入候选，不自动污染正式预制资产。

## 2. 标准参数目录

标准参数分 7 组。参数值要从 raw 参数、宣传文本、型号或评论弱信号中抽取，不能按 SKU 写死。

### 2.1 基础规格

| param_code | 中文名 | 类型 | 单位 | 主要来源 |
| --- | --- | --- | --- | --- |
| `screen_size_inch` | 屏幕尺寸 | number | inch | 参数、型号、宣传 |
| `resolution_class` | 分辨率档位 | enum | - | 参数、宣传 |
| `panel_type` | 面板类型 | enum | - | 参数、宣传 |
| `display_technology` | 显示技术 | enum | - | 参数、宣传 |
| `series_name` | 产品系列 | string | - | 主数据、型号 |
| `launch_period` | 上市周期 | string | - | 主数据、宣传 |

枚举值：

- `resolution_class`: `FHD`, `4K`, `8K`, `UNKNOWN`
- `panel_type`: `LCD`, `OLED`, `QLED`, `MiniLED_LCD`, `UNKNOWN`

### 2.2 显示画质

| param_code | 中文名 | 类型 | 单位 | 主要来源 |
| --- | --- | --- | --- | --- |
| `native_refresh_rate_hz` | 原生刷新率 | number | Hz | 参数、宣传 |
| `system_refresh_rate_hz` | 系统/倍频刷新率 | number | Hz | 参数、宣传 |
| `peak_brightness_nits` | 峰值亮度 | number | nits | 参数、宣传 |
| `sustained_brightness_nits` | 稳定亮度 | number | nits | 参数、宣传 |
| `color_gamut_pct` | 色域覆盖 | number | % | 参数、宣传 |
| `color_gamut_standard` | 色域标准 | enum | - | 参数、宣传 |
| `color_depth_bit` | 色深 | number | bit | 参数、宣传 |
| `hdr_format_list` | HDR 格式 | list | - | 参数、宣传 |
| `picture_processor` | 画质芯片/引擎 | string | - | 参数、宣传 |
| `motion_compensation_flag` | 运动补偿 | boolean | - | 参数、宣传 |

### 2.3 背光控光

| param_code | 中文名 | 类型 | 单位 | 主要来源 |
| --- | --- | --- | --- | --- |
| `mini_led_flag` | Mini LED 背光 | boolean | - | 参数、宣传 |
| `oled_flag` | OLED | boolean | - | 参数、宣传 |
| `qled_flag` | 量子点/QLED | boolean | - | 参数、宣传 |
| `backlight_type` | 背光类型 | enum | - | 参数、宣传 |
| `dimming_zones` | 控光分区数 | number | zones | 参数、宣传 |
| `local_dimming_flag` | 分区控光 | boolean | - | 参数、宣传 |
| `halo_control_claim_flag` | 光晕控制宣传 | boolean | - | 宣传、评论 |

### 2.4 游戏性能

| param_code | 中文名 | 类型 | 单位 | 主要来源 |
| --- | --- | --- | --- | --- |
| `hdmi_2_1_ports` | HDMI 2.1 接口数 | number | ports | 参数、宣传 |
| `full_bandwidth_hdmi_flag` | 满血 HDMI | boolean | - | 参数、宣传 |
| `vrr_flag` | VRR 可变刷新 | boolean | - | 参数、宣传 |
| `allm_flag` | ALLM 自动低延迟 | boolean | - | 参数、宣传 |
| `input_lag_ms` | 输入延迟 | number | ms | 参数、宣传 |
| `game_mode_flag` | 游戏模式 | boolean | - | 参数、宣传 |
| `freesync_flag` | FreeSync | boolean | - | 参数、宣传 |

### 2.5 音频

| param_code | 中文名 | 类型 | 单位 | 主要来源 |
| --- | --- | --- | --- | --- |
| `speaker_power_w` | 音响功率 | number | W | 参数、宣传 |
| `speaker_channel` | 声道配置 | string | - | 参数、宣传 |
| `subwoofer_flag` | 独立低音炮 | boolean | - | 参数、宣传 |
| `dolby_atmos_flag` | 杜比全景声 | boolean | - | 参数、宣传 |
| `dts_flag` | DTS 支持 | boolean | - | 参数、宣传 |

### 2.6 智能系统

| param_code | 中文名 | 类型 | 单位 | 主要来源 |
| --- | --- | --- | --- | --- |
| `ram_gb` | 运行内存 | number | GB | 参数、宣传 |
| `storage_gb` | 存储容量 | number | GB | 参数、宣传 |
| `chipset_name` | 芯片/处理器 | string | - | 参数、宣传 |
| `os_name` | 操作系统 | string | - | 参数、宣传 |
| `voice_control_flag` | 语音控制 | boolean | - | 参数、宣传、评论 |
| `far_field_voice_flag` | 远场语音 | boolean | - | 参数、宣传 |
| `startup_ads_risk_flag` | 开机广告风险 | boolean | - | 评论 |

### 2.7 护眼与体验

| param_code | 中文名 | 类型 | 单位 | 主要来源 |
| --- | --- | --- | --- | --- |
| `eye_dimming_freq_hz` | 护眼调光频率 | number | Hz | 参数、宣传 |
| `low_blue_light_flag` | 低蓝光 | boolean | - | 参数、宣传 |
| `flicker_free_flag` | 无频闪 | boolean | - | 参数、宣传 |
| `ambient_light_sensor_flag` | 环境光感 | boolean | - | 参数、宣传 |
| `anti_glare_flag` | 防眩光 | boolean | - | 参数、宣传、评论 |
| `elder_mode_flag` | 长辈模式 | boolean | - | 参数、宣传、评论 |
| `child_mode_flag` | 儿童模式 | boolean | - | 参数、宣传 |

## 3. 标准卖点目录

| claim_code | 中文名 | 主要支撑参数 | 主要文本证据 | 映射任务 |
| --- | --- | --- | --- | --- |
| `CLAIM_LARGE_SCREEN_IMMERSION` | 大屏沉浸观影 | `screen_size_inch>=75` | 大屏、巨幕、沉浸 | 客厅影院、大屏换新 |
| `CLAIM_MINI_LED_BACKLIGHT` | Mini LED 背光 | `mini_led_flag=true` | Mini LED、U+Mini | 高端画质 |
| `CLAIM_OLED_SELF_LIT` | OLED 自发光 | `oled_flag=true` | OLED、自发光、纯黑 | 高端画质 |
| `CLAIM_QLED_WIDE_COLOR` | 量子点广色域 | `qled_flag`, `color_gamut_pct` | 量子点、广色域 | 高端画质 |
| `CLAIM_HIGH_BRIGHTNESS_HDR` | 高亮 HDR | `peak_brightness_nits>=1000` | 高亮、HDR、XDR、nits | 高端画质 |
| `CLAIM_FINE_LOCAL_DIMMING` | 精细分区控光 | `dimming_zones>=100` | 分区控光、光晕控制 | 高端画质 |
| `CLAIM_HIGH_REFRESH_RATE` | 高刷新率 | `native_refresh_rate_hz>=120` | 高刷、120Hz、144Hz | 游戏、体育 |
| `CLAIM_GAMING_LOW_LATENCY` | 低延迟游戏 | `input_lag_ms`, `ALLM`, `VRR` | 低延迟、VRR、ALLM | 游戏 |
| `CLAIM_HDMI_2_1_GAMING` | HDMI 2.1 游戏接口 | `hdmi_2_1_ports>=1` | HDMI 2.1、满血接口 | 游戏 |
| `CLAIM_SPORTS_MOTION_SMOOTH` | 体育运动流畅 | 刷新率、运动补偿 | 看球、运动补偿、不卡 | 体育 |
| `CLAIM_EYE_CARE_COMFORT` | 护眼舒适 | 高频调光、低蓝光、无频闪 | 护眼、低蓝光、无频闪 | 家庭护眼 |
| `CLAIM_ELDER_FRIENDLY_SMART` | 长辈友好智能 | 语音、长辈模式 | 老人、爸妈、语音 | 长辈易用 |
| `CLAIM_SMART_VOICE_EASE` | 智能语音易用 | 语音、RAM、系统 | AI、语音、系统流畅 | 智能易用 |
| `CLAIM_NO_AD_OR_CLEAN_SYSTEM` | 清爽系统/少广告 | 评论风险反向 | 无广告、开机快、系统清爽 | 长辈易用 |
| `CLAIM_IMMERSIVE_AUDIO` | 沉浸音效 | 音响功率、杜比 | 音响、环绕、低音 | 客厅影院 |
| `CLAIM_DOLBY_CINEMA_AUDIO` | 杜比影音 | Dolby Vision/Atmos | 杜比、影院 | 客厅影院 |
| `CLAIM_THIN_DESIGN` | 超薄美学设计 | 厚度、边框 | 超薄、全面屏、金属 | 新家装修 |
| `CLAIM_ENERGY_SAVING` | 节能省电 | 能效、功耗 | 一级能效、省电 | 价值型 |
| `CLAIM_VALUE_FOR_MONEY` | 高性价比 | 价格分位、销量 | 性价比、划算、同价更强 | 大屏换新 |
| `CLAIM_INSTALLATION_SERVICE_ASSURANCE` | 安装服务保障 | 评论服务 | 安装、送货、师傅 | 服务体验 |

## 4. 评论主题目录

| topic_code | 中文名 | 类型 | 映射 |
| --- | --- | --- | --- |
| `TOPIC_PICTURE_QUALITY` | 画质体验 | 产品 | 高端画质、客厅影院 |
| `TOPIC_BRIGHTNESS_HDR` | 亮度/HDR | 产品 | 高亮 HDR |
| `TOPIC_DARK_SCENE_CONTRAST` | 暗场/对比度 | 产品 | 分区控光/OLED |
| `TOPIC_SPORTS_WATCHING` | 体育观看 | 产品 | 体育任务 |
| `TOPIC_GAMING_SMOOTHNESS` | 游戏流畅 | 产品 | 游戏任务 |
| `TOPIC_EYE_COMFORT` | 护眼舒适 | 产品 | 家庭护眼 |
| `TOPIC_EASE_OF_USE` | 操作易用 | 产品 | 智能易用 |
| `TOPIC_SENIOR_FRIENDLY` | 长辈友好 | 产品 | 长辈易用 |
| `TOPIC_CHILD_FAMILY` | 儿童家庭 | 产品 | 儿童护眼 |
| `TOPIC_INTERFACE_CONNECTIVITY` | 接口连接 | 产品 | 游戏/连接 |
| `TOPIC_AUDIO_QUALITY` | 音质体验 | 产品 | 客厅影院 |
| `TOPIC_SYSTEM_ADS_PERFORMANCE` | 系统广告/流畅 | 产品风险 | 智能风险 |
| `TOPIC_SIZE_SPACE_FIT` | 尺寸与空间适配 | 产品 | 大屏换新 |
| `TOPIC_PRICE_VALUE` | 价格价值感 | 市场感知 | 价值型 |
| `TOPIC_INSTALLATION_SERVICE` | 安装服务 | 服务 | 服务风险 |
| `TOPIC_DURABILITY_QUALITY` | 做工耐用 | 产品风险 | 复核风险 |

## 5. 用户任务目录

| task_code | 中文名 | 核心信号 |
| --- | --- | --- |
| `TASK_LIVING_ROOM_CINEMA` | 客厅影院观影 | 大屏、HDR、音效、家庭观影评论 |
| `TASK_PREMIUM_PICTURE_AV` | 高端画质影音 | Mini LED/OLED、高亮、控光、画质评论 |
| `TASK_GAMING_ENTERTAINMENT` | 游戏娱乐 | 高刷、HDMI 2.1、低延迟、游戏评论 |
| `TASK_SPORTS_WATCHING` | 体育赛事观看 | 高刷、运动补偿、看球评论 |
| `TASK_LARGE_SCREEN_REPLACEMENT` | 大屏换新 | 75/85+、价格/英寸、销量、换新评论 |
| `TASK_CHILD_EYE_CARE` | 儿童护眼 | 护眼参数、儿童评论、家庭价格带 |
| `TASK_SENIOR_EASY_USE` | 长辈易用 | 语音、简洁系统、长辈评论、低风险 |
| `TASK_VALUE_PURCHASE` | 性价比购买 | 低价格分位、高销量、性价比评论 |
| `TASK_NEW_HOME_DECORATION` | 新家装修搭配 | 外观、超薄、大屏、安装服务 |
| `TASK_BEDROOM_SECOND_TV` | 卧室/副屏 | 中小尺寸、低价、易用、音量/护眼 |

## 6. 目标客群目录

| target_group_code | 中文名 | 来源任务 |
| --- | --- | --- |
| `TG_FAMILY_UPGRADE` | 家庭换新用户 | 客厅影院、大屏换新 |
| `TG_AV_QUALITY_SEEKER` | 画质影音用户 | 高端画质影音 |
| `TG_GAMER` | 游戏用户 | 游戏娱乐 |
| `TG_SPORTS_FAN` | 体育观看用户 | 体育赛事观看 |
| `TG_SENIOR_FAMILY` | 长辈家庭用户 | 长辈易用 |
| `TG_CHILD_FAMILY` | 儿童家庭用户 | 儿童护眼 |
| `TG_VALUE_BUYER` | 性价比用户 | 性价比购买 |
| `TG_NEW_HOME_DECORATOR` | 新家装修用户 | 新家装修搭配 |
| `TG_BEDROOM_SECOND_TV` | 卧室副屏用户 | 卧室/副屏 |

## 7. 价值战场目录

| battlefield_code | 中文名 | 竞争核心 | 必要信号 |
| --- | --- | --- | --- |
| `BF_PREMIUM_PICTURE` | 高端画质战场 | 画质技术与价格支撑 | Mini LED/OLED/高亮/控光 |
| `BF_FAMILY_VIEWING_UPGRADE` | 家庭观影升级战场 | 客厅大屏影音体验 | 大屏、HDR、音效 |
| `BF_GAMING_SPORTS` | 游戏体育战场 | 高刷、低延迟、接口 | 高刷/HDMI/运动评论 |
| `BF_LARGE_SCREEN_VALUE` | 大屏性价比战场 | 大尺寸与价格效率 | 尺寸、价格/英寸、销量 |
| `BF_FAMILY_EYE_CARE` | 家庭护眼战场 | 儿童/家庭长期观看 | 护眼参数/评论 |
| `BF_SENIOR_EASE_OF_USE` | 长辈易用战场 | 操作简单、系统清晰 | 语音、长辈评论 |
| `BF_SMART_SYSTEM_EXPERIENCE` | 智能系统体验战场 | 流畅、语音、少广告 | RAM、语音、系统评论 |
| `BF_CINEMA_AUDIO_IMMERSION` | 影院音效战场 | 音响、杜比、沉浸 | 音频参数/音质评论 |
| `BF_DESIGN_HOME_FIT` | 家居美学战场 | 外观、超薄、装修适配 | 设计卖点/安装评论 |
| `BF_SERVICE_ASSURANCE` | 服务保障战场 | 安装、售后、送货 | 服务评论 |

## 8. 预制与抽取责任边界

| 对象 | 预制什么 | 从数据抽取什么 |
| --- | --- | --- |
| 标准参数 | code、别名、解析器、单位、阈值 | raw 字段映射、数值、置信度、新别名 |
| 标准卖点 | 定义、支撑参数、关键词、映射 | SKU 是否激活、激活分、证据、新候选卖点 |
| 评论主题 | 主题名、关键词、产品/服务类型 | 句子命中、情感、样例句、新主题候选 |
| 用户任务 | 任务定义、权重、映射客群/战场 | SKU 任务得分、原因、证据 |
| 目标客群 | 客群定义、来源任务 | SKU 客群得分、市场位置 |
| 价值战场 | 战场定义、必要信号、市场权重 | SKU 战场得分、关系级别、候选池上下文 |

