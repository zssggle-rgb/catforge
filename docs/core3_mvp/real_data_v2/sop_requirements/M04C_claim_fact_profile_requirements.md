# M04C SKU 卖点事实画像与卖点位置覆盖 SOP 需求

## 0. 定位

M04C 是新的 SKU 卖点事实画像模块族，独立于既有 M04a/M04b。它像 M03A/M03B 处理参数一样处理卖点：

```text
品类标准卖点 taxonomy
  -> SKU 卖点事实画像
  -> SKU 在各卖点维度中的位置
  -> 卖点位置覆盖 SKU 清单
```

M04C 解决的问题是：

1. 当前品类的真实结构化卖点能归纳出哪些标准卖点。
2. 每个 SKU 宣传了哪些具体卖点。
3. 每个卖点是否有参数事实支撑。
4. 每个 SKU 在画质、游戏、智能、音频、外观等卖点维度中处于什么位置。
5. 每个卖点位置覆盖哪些 SKU，供后续竞品召回、事实画像和业务解释使用。

M04C 不判断卖点是否溢价，不读取评论正负反馈，不判断用户任务、目标客群、价值战场或竞品结论。

M04C 必须为后续用户卖点支付价值分析提供更细的事实门槛：不仅要说明“卖点是否被参数支撑”，还要说明“参数支撑是否专属、是否可比较、是否只是泛参数”。例如 `杜比/影音认证` 不能只因为 `HDR=true` 就被认为具备可支撑用户支付价值的强参数事实；`HDR` 可以作为高端画质池的基础门槛，但不能证明杜比认证本身具有独占支付价值。

## 1. 模块拆分

| 子能力 | 生命周期 | 职责 |
| --- | --- | --- |
| M04C-A 标准卖点 taxonomy | 低频，品类资产维护 | 从当前品类真实卖点中归纳标准卖点、维度、子类、参数支撑规则、服务隔离规则 |
| M04C-B SKU 卖点事实画像 | 高频，新数据批次运行 | 使用已发布 taxonomy，把清洗后的卖点和 M03B 参数画像转成 SKU 卖点事实画像 |

如果品类没有已发布卖点 taxonomy，M04C-B 必须阻断。M04C-B 不能运行时自动借用其他品类 taxonomy，也不能自动新增标准卖点。

## 2. 与既有 M04a/M04b 的边界

M04C 是新增事实层能力，不消费、不复用、不依赖以下旧结果：

- `core3_extract_claim_hit`
- `core3_sku_claim_source_status`
- `core3_sku_claim_activation_base`
- `core3_sku_claim_comment_validation`
- `core3_sku_claim_activation`

既有 M04a/M04b 可以保留给历史链路，但新事实层以 M04C 输出为准。

| 模块 | 新定位 |
| --- | --- |
| M04a | 历史基础卖点激活，不作为新标准卖点依据 |
| M04b | 历史评论增强卖点激活，不作为新卖点事实画像依据 |
| M04C | 新的卖点 taxonomy、SKU 卖点事实、卖点维度位置和覆盖索引 |

## 3. 输入

### 3.1 M04C-A 输入

| 输入 | 来源 | 必需 | 用途 |
| --- | --- | --- | --- |
| 结构化卖点文本 | `selling_points_data` 或 M01/M02 清洗后的 `promo_raw` / `promo_sentence` | 是 | 归纳真实标准卖点 |
| SKU、品牌、型号、品类 | 原始表或清洗表 | 是 | 统计覆盖与样例 |
| M03A/M03B 参数 taxonomy 与参数画像 | 参数事实层 | 是 | 为标准卖点配置参数支撑规则 |
| 人工复核意见 | 人工评审 | 是 | 确认标准卖点命名、合并、拆分和服务隔离 |

M04C-A 可以使用 LLM 或人工分析辅助归纳 taxonomy，但发布后的 taxonomy 必须版本化、可审计、可复现。

### 3.2 M04C-B 输入

| 输入 | 来源 | 必需 | 用途 |
| --- | --- | --- | --- |
| 已发布品类卖点 taxonomy | M04C-A | 是 | 标准卖点、维度、位置规则、参数支撑规则 |
| 清洗后的卖点 evidence | M01/M02，`promo_raw` / `promo_sentence` | 是 | SKU 卖点文本来源 |
| SKU 参数画像 | M03B | 否但强建议 | 判断卖点参数支撑 |
| 批次信息 | M00 | 是 | batch 边界、增量重跑范围 |
| 人工复核决策 | M16 或卖点复核 API | 否 | 解决规则例外、误归类、参数冲突 |

M04C-B 不读取评论。评论正负验证属于后续评论事实和价值判断。

## 4. 输出

M04C 必须输出四类结果。

### 4.1 品类标准卖点 taxonomy

每个品类一套 taxonomy，至少包含：

- 标准卖点。
- 卖点维度。
- 卖点子类。
- 原始卖点表达模式。
- 参数支撑规则。
- 维度位置规则。
- 服务履约隔离规则。
- 下游使用策略。

TV 首版 taxonomy 来源于 205 当前 TV 卖点数据：

| 指标 | 数量 |
| --- | ---: |
| TV 卖点行 | 4,229 |
| TV 型号 | 328 |
| TV 品牌 | 18 |
| 去重卖点文本 | 4,160 |
| 当前规则覆盖卖点行 | 4,206 |
| 当前未归类卖点行 | 23 |

### 4.2 SKU 卖点事实画像

每个 SKU 一条聚合画像，包含：

- SKU 身份。
- 结构化卖点覆盖情况。
- 标准卖点命中清单。
- 具体原始卖点文本。
- 每个卖点的参数支撑状态。
- 每个卖点的参数支撑等级：强专属支撑、泛参数支撑、弱间接支撑、无支撑、不适用。
- 每个卖点的关键参数是否可比较，例如数值型、档位型、布尔型、文本型号型、认证型。
- 同一原始卖点或同一核心参数支撑多个标准卖点时的同源同参分组。
- 每个维度的卖点位置。
- 服务履约、行业背书、内容权益等非产品主卖点隔离信息。
- 缺失、冲突、低置信和复核项。

### 4.3 SKU 卖点事实明细

每个 SKU 的每个标准卖点生成一条事实明细。

关键字段：

```text
sku_code
claim_code
claim_name
claim_dimension
claim_subtype
source_claim_texts
source_variables
promo_evidence_ids
param_support_status
supporting_param_codes
supporting_param_values
param_support_level
param_support_specificity
primary_supporting_param_codes
source_claim_group_id
same_source_param_group_id
wtp_input_guard
param_evidence_ids
fact_claim_flag
service_separate_flag
confidence
review_required
```

其中 `fact_claim_flag=true` 只表示“该卖点作为产品事实有参数支撑”。它不表示溢价成立，也不表示消费者认可。

`wtp_input_guard` 不是 M04C 对溢价的判断，只是给 M12C 的事实门槛信号。它只回答“该卖点是否具备进入用户支付价值分析的参数事实基础”：

| `wtp_input_guard` | 含义 | M12C 默认处理 |
| --- | --- | --- |
| `eligible_strong_param` | 卖点有专属、强相关、可比较的参数支撑 | 可进入用户支付价值候选 |
| `eligible_key_param_advantage` | 卖点文本不一定完整，但关键参数显著支撑该价值 | 可作为待激活或人无我有候选 |
| `blocked_generic_param` | 只由泛参数支撑，不能证明该卖点本身 | 不得进入用户支付价值；可把泛参数本身作为门槛判断 |
| `blocked_no_param` | 无参数支撑或参数未知 | 不得进入用户支付价值；仅保留宣传/待验证 |
| `not_product_wtp_scope` | 服务、内容权益、价格补贴、行业背书等非产品参数卖点 | 不进入产品用户支付价值 |

### 4.3.1 给 M12C 的可量化资格提示

M04C 不判断溢价，但必须把下游会误判的卖点类型提前打清楚。M12C 只能在这些事实提示基础上进一步判断用户支付价值，不能绕过 M04C 的参数支撑口径。

| 卖点类型 | M04C 事实口径 | 给 M12C 的处理提示 |
| --- | --- | --- |
| 产品能力型卖点 | 有专属参数、数值参数、档位参数或认证事实支撑 | 可进入 M12C 战场相关性、门槛和支付价值判断 |
| 基础门槛型能力 | 参数存在但同池大概率普遍具备，例如基础 HDR、基础 4K、基础 HDMI2.1 | 只能作为门槛候选；是否高溢价由 M12C 在战场和可比池里判断 |
| 场景/任务型表达 | 表达用户用途或场景，例如影院观影、客厅观影、游戏娱乐 | 只作为用户任务、目标客群和价值战场证据；不得作为产品卖点金额分配对象 |
| 认证/品牌表达型卖点 | 必须有认证字段、音频硬件、专属格式或明确事实支撑 | 只有泛参数时标 `blocked_generic_param`，例如杜比不能只由 HDR 支撑 |
| 宽泛组合型卖点 | 名称过宽，必须拆到关键参数判断，例如高端画质、性能强 | 输出卖点-参数映射，供 M12C 下钻到亮度、分区、芯片、刷新率等具体证据 |

典型 TV 口径：

| 标准表达 | M04C 应输出的事实提示 | 下游业务解释 |
| --- | --- | --- |
| HDR/高亮画质 | `hdr_support_flag` 只能说明基础 HDR；`declared_brightness_nit_or_band` 才能说明高亮档位 | HDR 普遍具备时是门槛，5200nits 等亮度档位优势才可能进入支付价值 |
| 护眼显示 | 只允许由低蓝光、无频闪、护眼认证、抗反光等护眼专属事实支撑 | 不能借用 HDR、亮度、刷新率来证明护眼价值 |
| 影院/观影场景 | 标记为场景/任务表达 | 进入用户任务和价值战场证据，不进入 M12C 正向金额分配 |
| 杜比/影音认证 | 需要杜比、DTS、IMAX、音频硬件或认证事实 | 只有 HDR 时属于泛参数支撑，不能证明杜比认证本身 |

### 4.4 卖点位置覆盖 SKU 清单

每个卖点维度的每个位置都要生成覆盖情况：

- `dimension_code`
- `position_code`
- `position_name`
- `sku_count`
- `sku_ratio`
- `sku_codes`
- 示例 SKU。
- 判断规则摘要。
- 参数支撑覆盖情况。
- 当前批次是否样本不足。

该清单供后续竞品召回使用。后续找竞品时可以优先按同画质卖点位置、同游戏卖点位置、同智能卖点位置、同外观形态位置等召回。

## 5. TV 首版标准卖点维度

### 5.1 一级维度

| 维度 | 说明 | 是否产品主链路 |
| --- | --- | --- |
| `positioning_scene` | 核心定位、人群、场景叙事 | 否，作为解释背景 |
| `scene_experience` | 大屏、巨幕、影院沉浸 | 是，需要尺寸/音画参数支撑 |
| `picture_display` | Mini LED、OLED、量子点、背光技术 | 是 |
| `picture_quality` | 高亮、HDR、分区控光、低反、画质芯片、清晰度 | 是 |
| `motion_gaming` | 高刷、MEMC、HDMI2.1、VRR、低延迟 | 是 |
| `eye_care` | 护眼、低蓝光、无频闪、视觉健康 | 是 |
| `audio_cinema` | 杜比、DTS、IMAX、音响硬件、环绕低音 | 是 |
| `smart_interaction` | AI 语音、系统、投屏、WiFi、摄像头 | 是 |
| `performance` | 芯片、处理器、内存、存储、运行性能 | 是 |
| `appearance` | 超薄、全面屏、金属、贴墙、家居美学 | 是 |
| `energy_value` | 能效、省电、价格、补贴、性价比 | 部分产品事实，价值判断延后 |
| `content_ecosystem` | 会员、片源、内容平台 | 非硬件产品能力，单独保留 |
| `authority` | 行业地位、认证、销量背书、专利 | 非产品主事实，单独保留 |
| `service_separate` | 安装、送装、售后、保修 | 否，服务履约隔离 |

### 5.2 TV 卖点位置首版

#### 画质位置

| 位置 | 当前覆盖型号 | 说明 |
| --- | ---: | --- |
| `picture_miniled_composite_flagship` | 189 | Mini LED + 分区/亮度/HDR/画质引擎/色彩等多重画质卖点 |
| `picture_basic_4k_clear` | 71 | 主要讲 4K、高清、蓝光、清晰度 |
| `picture_quantum_color_upgrade` | 43 | 量子点、广色域、色准、色彩还原 |
| `picture_miniled_control_upgrade` | 15 | 有 Mini LED 或控光，但复合画质卖点不完整 |
| `picture_anti_reflection_wide_angle` | 9 | 低反、防眩、类纸屏、广视角 |
| `picture_claim_weak_or_unspecified` | 1 | 画质卖点锚点不足 |

#### 游戏运动位置

| 位置 | 当前覆盖型号 |
| --- | ---: |
| `gaming_weak_or_unspecified` | 88 |
| `gaming_advanced_high_refresh` | 83 |
| `gaming_high_refresh_experience` | 82 |
| `gaming_console_interface` | 52 |
| `sports_motion_smooth` | 16 |
| `gaming_basic_high_refresh` | 7 |

#### 智能交互位置

| 位置 | 当前覆盖型号 |
| --- | ---: |
| `smart_full_scene_iot` | 138 |
| `smart_ai_voice_smooth_os` | 50 |
| `smart_no_ads_smooth_os` | 48 |
| `smart_camera_gesture` | 36 |
| `smart_senior_friendly_voice` | 34 |
| `smart_weak_or_unspecified` | 15 |
| `smart_casting_connectivity` | 7 |

#### 音频位置

| 位置 | 当前覆盖型号 |
| --- | ---: |
| `audio_bass_surround_soundbar` | 129 |
| `audio_cinema_certified_hardware` | 116 |
| `audio_weak_or_unspecified` | 49 |
| `audio_speaker_channel_power` | 19 |
| `audio_dolby_dts_certified` | 15 |

#### 外观形态位置

| 位置 | 当前覆盖型号 |
| --- | ---: |
| `appearance_flush_wall_mount` | 123 |
| `appearance_weak_or_unspecified` | 113 |
| `appearance_home_aesthetic` | 41 |
| `appearance_thin_metal_design` | 27 |
| `appearance_fullscreen_narrow_bezel` | 24 |

## 6. 参数支撑口径

M04C-B 对每个标准卖点输出 `param_support_status`：

| 状态 | 含义 | 是否事实卖点 |
| --- | --- | --- |
| `supported` | 卖点所需核心参数存在且匹配 | 是 |
| `partially_supported` | 部分关键参数存在，仍有重要参数未知 | 是，但置信度较低 |
| `unsupported` | 卖点出现，但关键参数明确不支撑 | 否，需要复核 |
| `conflicted` | 卖点文本与参数事实冲突 | 否，需要复核 |
| `param_unknown` | 参数画像缺失或关键参数未知 | 否，只能记为宣传卖点 |
| `not_param_applicable` | 行业背书、内容权益、服务履约等不适用参数支撑 | 否，不作为产品事实卖点 |

示例：

| 卖点 | 参数支撑要求 |
| --- | --- |
| Mini LED | `display_technology_family`、`backlight_source`、`mini_led_type` 中至少有 Mini LED 支撑 |
| 分区控光 | `local_dimming_zone_count` 或分区相关参数支撑 |
| 高亮 HDR | HDR 标记、亮度标称、XDR/HDR 参数任一支撑，亮度口径必须标记为 declared |
| 高刷 | `declared_refresh_rate_hz` 支撑，且写明标称刷新率 |
| HDMI2.1 游戏 | HDMI 版本或接口参数支撑 |
| AI 语音 | AI/语音/远场语音参数支撑 |
| 摄像头 | 摄像头参数支撑；缺失不自动判否，除非 taxonomy 明确 false-by-absence |
| 无广告系统 | 参数表通常无硬件支撑，首版按 `param_unknown` 或系统类辅助支撑处理 |
| 安装送装 | `not_param_applicable`，服务履约隔离 |

### 6.1 参数支撑等级

`param_support_status` 只能说明有无支撑，不能直接说明能否进入用户支付价值分析。M04C-B 必须进一步输出 `param_support_level`：

| 等级 | 定义 | 示例 | 是否可进入 M12C 用户支付价值分析 |
| --- | --- | --- | --- |
| `strong_specific_support` | 卖点由专属、强相关、可比较的参数支撑 | 5200nits 支撑高亮；1920 分区支撑控光；MT9655 支撑芯片 | 是 |
| `strong_numeric_or_tier_support` | 卖点背后有数值或档位参数，能与同池竞品比较 | 亮度、分区数、刷新率、色域、接口数量 | 是 |
| `broad_generic_support` | 只由宽泛参数支撑，参数不能证明具体卖点 | 用 `HDR=true` 支撑“杜比认证” | 否 |
| `weak_indirect_support` | 参数间接相关，但不能独立证明该卖点 | 用 AI 大模型支撑所有智能体验 | 默认否，可进待激活 |
| `no_param_support` | 没有参数、参数未知或参数冲突 | 只有宣传文本 | 否 |
| `not_param_applicable` | 行业背书、内容权益、服务履约等不适用参数 | 销量背书、送装售后 | 否 |

泛参数保护规则：

```text
如果某个标准卖点只被泛参数支撑，
则该标准卖点不能作为 M12C 的高溢价、人无我有或份额转化候选。
M12C 可以把该泛参数本身放入门槛判断，
但不能把泛参数解释成具体认证、芯片、专利或高阶能力。
```

示例：

| 标准卖点 | 当前参数支撑 | M04C 判断 | 下游解释 |
| --- | --- | --- | --- |
| 杜比/影音认证 | 只有 `hdr_support_flag=true` | `broad_generic_support` | HDR 可作为基础门槛；杜比认证本身待验证 |
| 芯片/处理器性能 | `processor_chip_model=MT9655` | `strong_specific_support` | 可进入芯片性能用户支付价值候选 |
| 画质芯片/AI 画质引擎 | 同样由 `processor_chip_model=MT9655` 与 AI 参数支撑 | `strong_specific_support`，但与芯片卖点同源同参 | 下游必须合并为一个价值理由，不能重复计价 |

### 6.2 同源同参分组

同一条原始卖点文本可能命中多个标准卖点，同一组核心参数也可能支撑多个标准卖点。M04C-B 必须输出分组，避免 M12C 重复放大同一价值。

分组规则：

| 分组 | 触发条件 | 输出字段 |
| --- | --- | --- |
| 同源卖点组 | 多个标准卖点来自同一条原始卖点文本或同一个 `promo_evidence_id` | `source_claim_group_id` |
| 同参支撑组 | 多个标准卖点的核心支撑参数高度重合 | `same_source_param_group_id` |
| 价值理由代表卖点 | 同组中最适合业务展示的主卖点 | `canonical_claim_code`、`canonical_claim_name` |

例如海信 65E7Q 的“信芯 AI 画质芯片 H6 超频版”同时命中：

- `芯片/处理器性能`
- `画质芯片/AI 画质引擎`
- 可能还支撑 `分区控光` 的控光精度表达

M04C 可以保留多条标准卖点事实，但必须标记它们属于同一 `same_source_param_group_id`。M12C 在用户支付价值展示中应合并为“信芯 AI 画质芯片 H6 带来的画质处理与系统性能优势”，不能把它们当作多个独立用户支付价值卖点重复计价。

## 7. 缺失和冲突口径

| 情况 | 处理 |
| --- | --- |
| SKU 没有结构化卖点 | 标记 `structured_claim_missing`，不能写“没有卖点” |
| SKU 有卖点但无 M03B 参数画像 | 生成卖点画像，参数支撑统一为 `param_unknown` |
| 卖点提到某参数，但参数缺失 | `param_unknown`，不当作不支持 |
| 卖点提到某参数，参数明确相反 | `conflicted`，进入复核 |
| 卖点属于服务履约 | `service_separate_flag=true`，不进入产品主分析 |
| 卖点属于行业背书 | 保留为 `authority`，不作为产品能力参数事实 |
| 卖点属于价格补贴 | 保留为 `energy_value/price_value`，是否溢价留给后续市场/战场判断 |

## 8. 多品类要求

M04C 必须以 `product_category` 加载 taxonomy：

| 品类 | taxonomy | 状态 |
| --- | --- | --- |
| TV / 彩电 | `tv_claim_taxonomy_manual_v0.1` | 首版设计对象 |
| AC / 空调 | `ac_claim_taxonomy_manual_v0.1` | 待从空调卖点表按同流程生成 |

不同品类不得共享标准卖点。空调不能复用电视的 Mini LED、高刷、HDMI2.1 等 taxonomy。

在 205 当前混批次数据修复前，运行边界必须同时支持：

```text
source category_code = TV
product_category = tv/ac
sku_code_prefix = TV/AC
raw category = 彩电/空调
```

## 9. CLI 与 Skill 要求

### 9.1 写入 CLI

`catforge_pipeline` 增加：

```bash
python -m app.cli.catforge_pipeline run-claim-profile --product-category tv --batch-id latest --force-rebuild --format json
python -m app.cli.catforge_pipeline run-claim-profile --product-category ac --batch-id latest --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "生成彩电 SKU 卖点画像" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "重新生成空调卖点事实画像" --force-rebuild --format json
```

### 9.2 查询 CLI

`catforge_insight` 增加：

```bash
python -m app.cli.catforge_insight claim-taxonomy --product-category tv --format json
python -m app.cli.catforge_insight sku-claim-profile --query 75E8Q --format json
python -m app.cli.catforge_insight claim-position-coverage --product-category tv --dimension-code picture_quality --position-code picture_miniled_composite_flagship --sku-limit 100 --format json
python -m app.cli.catforge_insight ask "查 75E8Q 的卖点画像" --format json
python -m app.cli.catforge_insight ask "查 MiniLED 复合画质旗舰型覆盖哪些 SKU" --sku-limit 100 --format json
```

### 9.3 Claude Code Skill

必须更新或新增 Claude Code skill，使自然语言可以触发：

- 生成某品类 SKU 卖点画像。
- 查询某 SKU 卖点画像。
- 查询某品类标准卖点。
- 查询某卖点维度位置覆盖 SKU。
- 查询某 SKU 哪些卖点有参数支撑、哪些只有宣传文本、哪些需要复核。

## 10. 验收标准

TV 首版验收：

1. 标准卖点 taxonomy 覆盖当前 TV 卖点行不低于 95%；当前草案覆盖 4,206/4,229。
2. 能为 328 个有结构化卖点的 TV 型号生成 SKU 卖点画像。
3. 对有 M03B 参数画像的 SKU 输出参数支撑状态；没有 M03B 参数画像的 SKU 不阻断画像生成，但标记 `param_unknown`。
4. 生成画质、游戏运动、智能、音频、外观等维度位置。
5. 生成各位置覆盖 SKU 清单。
6. 服务履约类卖点被隔离，不进入产品主事实。
7. 查询 CLI 能按 SKU、标准卖点、维度位置返回结果。
8. 所有输出保留 `project_id`、`category_code`、`product_category`、`batch_id`、`taxonomy_version`、`rule_version`、`evidence_ids`、`profile_hash`。

## 11. 后续关系

M04C 输出进入：

| 下游 | 使用方式 |
| --- | --- |
| SKU 事实画像 | 汇总 SKU 的卖点事实、参数支撑和质量缺口 |
| 评论事实层 | 判断事实卖点是否被评论正向或负向验证 |
| 品类语义能力层 | 作为用户任务、目标客群、价值战场定义的产品锚点 |
| 竞品召回 | 按同卖点位置收敛候选池 |
| 溢价卖点判断 | 后续结合评论、主任务、主客群、主战场和市场表现判断 |

M04C 自身不输出溢价卖点。
