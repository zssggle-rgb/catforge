# M12D-G04R1 TV 价值主题与购买理由候选提炼报告

生成时间 UTC：2026-07-08T07:54:50.113439+00:00

本报告由只读脚本从 205 当前 Core3 TV 结果提炼候选。它不是最终标准，最终标准需要业务/Codex 审阅后固化版本。

## 1. 数据覆盖

| 模块 | 证据域 | 表 | 行数 | SKU 数 |
| --- | --- | --- | ---: | ---: |
| M03B | param | `core3_sku_param_profile` | 461 | 377 |
| M04C | claim | `core3_sku_claim_fact` | 15268 | 328 |
| M04C | claim | `core3_sku_claim_fact_profile` | 621 | 328 |
| M05C | comment | `core3_comment_fact_atom` | 43750 | 348 |
| M05C | comment | `core3_sku_comment_fact_profile` | 348 | 348 |
| M07 | market | `core3_sku_market_profile` | 377 | 377 |
| M09C | semantic_reference | `core3_m09c_sku_user_task_profile` | 531 | 348 |
| M10C | semantic_reference | `core3_m10c_sku_target_group_profile` | 531 | 348 |
| M11C | semantic_reference | `core3_sku_value_battlefield_profile` | 1007 | 368 |
| M11D | semantic_market | `core3_semantic_market_dimension_summary` | 70 | 0 |
| M12C | claim_value | `core3_sku_claim_value_quantification` | 20663 | 259 |

## 2. 价值主题候选

| 候选代码 | 中文名 | 得分 | SKU 数 | 证据域 | 审阅标记 |
| --- | --- | ---: | ---: | --- | --- |
| `dynamic_stability_perception` | 动态画面稳定感 | 0.9300 | 377 | claim, claim_value, comment, param, semantic_reference | review_candidate |
| `picture_upgrade_perception` | 画质升级感 | 0.9300 | 377 | claim, claim_value, comment, param, semantic_reference | review_candidate |
| `living_room_immersion_perception` | 客厅沉浸感 | 0.9100 | 377 | claim, comment, market, param, semantic_reference | review_candidate |
| `budget_configuration_efficiency` | 预算配置效率 | 0.8800 | 377 | claim, claim_value, comment, market | review_candidate |
| `long_watch_comfort_perception` | 长看舒适感 | 0.7600 | 377 | claim, comment, param, semantic_reference | review_candidate |
| `operation_convenience_perception` | 操作便利感 | 0.7600 | 377 | claim, comment, param, semantic_reference | review_candidate |
| `space_aesthetic_fit` | 空间审美适配 | 0.7600 | 377 | claim, comment, param, semantic_reference | review_candidate |

## 3. 标准购买理由候选

| 候选代码 | 中文名 | 得分 | SKU 数 | 证据域 | 审阅标记 |
| --- | --- | ---: | ---: | --- | --- |
| `picture_upgrade_justifies_price` | 画质配置解释加价 | 1.0000 | 377 | claim, claim_value, comment, market, param, semantic_reference | review_candidate |
| `low_price_core_experience_intact` | 低价不明显牺牲核心体验 | 0.9500 | 377 | claim, claim_value, comment, market, param | review_candidate |
| `same_price_core_config_gain` | 同价位核心配置获得感 | 0.9500 | 377 | claim, claim_value, comment, market, param | review_candidate |
| `same_size_picture_step_up` | 同尺寸画质越级获得感 | 0.9500 | 377 | claim, claim_value, comment, market, param | review_candidate |
| `worth_paying_more_for_experience_upgrade` | 贵得值的体验升级 | 0.9500 | 377 | claim, claim_value, comment, market, param | review_candidate |
| `av_user_willing_to_pay_for_picture` | 影音用户愿为画质升级付费 | 0.9300 | 377 | claim, claim_value, comment, param, semantic_reference | review_candidate |
| `gaming_device_fit_reduces_risk` | 游戏设备适配降低踩坑风险 | 0.9300 | 377 | claim, claim_value, comment, param, semantic_reference | review_candidate |
| `sports_motion_stability` | 体育/运动画面流畅更稳 | 0.9300 | 377 | claim, claim_value, comment, param, semantic_reference | review_candidate |
| `big_screen_cinema_substitution` | 大屏影音替代影院感 | 0.9100 | 377 | claim, comment, market, param, semantic_reference | review_candidate |
| `living_room_upgrade_one_step` | 客厅换新一步到位 | 0.9100 | 377 | claim, comment, market, param, semantic_reference | review_candidate |
| `family_long_watch_comfort_assurance` | 家庭长时间观看更安心 | 0.7300 | 377 | claim, comment, param, semantic_reference | needs_price_or_payment_validation |
| `family_operation_less_friction` | 家庭多设备使用更省操作 | 0.7300 | 377 | claim, comment, param, semantic_reference | needs_price_or_payment_validation |
| `new_home_aesthetic_fit` | 新家客厅审美适配 | 0.7300 | 377 | claim, comment, param, semantic_reference | needs_price_or_payment_validation |

## 4. 候选详情

### 价值主题候选

#### 动态画面稳定感 `dynamic_stability_perception`

- 定义：游戏、体育、运动画面中流畅、低延迟、少拖影的体验获得感。
- 业务问题：这个主题是否代表动态画面体验，而不是简单复制游戏战场？
- 命中 SKU：377，证据域：claim, claim_value, comment, param, semantic_reference
- 证据域 SKU 数：{"claim": 258, "claim_value": 234, "comment": 324, "param": 377, "semantic_reference": 364}
- M12C role 分布：{"high_price_competitor_intercept": 319, "opportunity_gap": 149, "weak_user_perception_claim": 97, "drag_factor": 58, "sales_driver_estimated": 52, "price_up_opportunity": 51, "basic_threshold": 27, "brand_claim_only": 18, "premium_driver_estimated": 7}
- 主要命中词：{"claim": ["高刷", "游戏", "tv_claim_high_refresh", "刷新率"], "claim_value": ["tv_claim_high_refresh"], "comment": ["流畅", "smooth", "游戏", "gaming", "高刷", "sports", "体育", "motion"], "param": ["refresh", "hz", "hdmi", "刷新率"], "semantic_reference": ["gaming", "sports", "游戏", "体育", "fluency", "流畅"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 画质升级感 `picture_upgrade_perception`

- 定义：用户能感知到画面清晰度、亮度、控光、色彩或显示技术升级。
- 业务问题：这个主题是否代表用户可感知的画质升级价值，而不是单个画质参数？
- 命中 SKU：377，证据域：claim, claim_value, comment, param, semantic_reference
- 证据域 SKU 数：{"claim": 327, "claim_value": 251, "comment": 343, "param": 377, "semantic_reference": 365}
- M12C role 分布：{"sales_driver_estimated": 1115, "premium_driver_estimated": 212, "basic_threshold": 174, "high_price_competitor_intercept": 172, "drag_factor": 96, "weak_user_perception_claim": 52, "opportunity_gap": 43, "price_up_opportunity": 40}
- 主要命中词：{"claim": ["画质", "分区", "miniled", "控光", "tv_claim_miniled", "tv_claim_hdr"], "claim_value": ["sales_driver", "tv_claim_miniled", "premium_driver"], "comment": ["screen", "画质", "清晰", "picture", "clarity", "观影", "电影", "brightness", "亮度"], "param": ["mini_led", "hdr", "brightness", "dimming", "resolution", "picture", "color", "亮度", "分区", "色域", "miniled", "display"], "semantic_reference": ["premium_picture", "picture", "画质", "影音"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 客厅沉浸感 `living_room_immersion_perception`

- 定义：大屏、音效、杜比、观影距离与客厅空间共同形成的沉浸感。
- 业务问题：这个主题是否代表客厅场景下的沉浸体验，而不是只有尺寸参数？
- 命中 SKU：377，证据域：claim, comment, market, param, semantic_reference
- 证据域 SKU 数：{"claim": 326, "comment": 326, "market": 377, "param": 377, "semantic_reference": 368}
- 主要命中词：{"claim": ["影院", "沉浸", "音响", "杜比", "大屏"], "comment": ["cinema", "观影", "客厅", "living_room", "电影", "沉浸", "追剧"], "market": ["size_segment", "screen_size", "large", "ultra_large"], "param": ["screen_size", "inch", "尺寸", "large"], "semantic_reference": ["large_screen", "大屏", "客厅", "cinema", "观影"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 预算配置效率 `budget_configuration_efficiency`

- 定义：在给定预算和尺寸池里，用户获得核心配置、价格和销量承接的效率。
- 业务问题：这个主题是否代表预算内配置获得感，而不是厂家一句性价比？
- 弱表达边界：只有 value_price/price_value 或性价比口号时，只能作为弱表达候选。
- 命中 SKU：377，证据域：claim, claim_value, comment, market
- 证据域 SKU 数：{"claim": 115, "claim_value": 259, "comment": 324, "market": 377}
- M12C role 分布：{"high_price_competitor_intercept": 6464, "opportunity_gap": 4232, "brand_claim_only": 2288, "price_up_opportunity": 2198, "weak_user_perception_claim": 1940, "drag_factor": 1336, "sales_driver_estimated": 1115, "basic_threshold": 867, "premium_driver_estimated": 212, "value_bundle_claim": 6, "unique_payment_potential": 5}
- 主要命中词：{"claim": ["价格", "value_price", "tv_claim_value_price", "price_value", "性价比", "预算"], "claim_value": ["price", "价格", "value_bundle"], "comment": ["性价比", "划算", "这个价格", "预算"], "market": ["volume_percentile", "price_band", "low", "mid_low"]}
- 样本 SKU：TV00028200 创维 T60D, TV00028206 康佳 65E9G PRO-S, TV00023850 酷开 50P31, TV00025500 红米 L32RA-RA, TV00025501 红米 L43RA-RA, TV00025519 红米 L55RA-RA, TV00025784 红米 L75MA-RA, TV00026064 小米 L55MA-SPL
- 审阅标记：review_candidate

#### 长看舒适感 `long_watch_comfort_perception`

- 定义：护眼、低蓝光、无频闪、抗反光和家庭长时间观看形成的舒适安心。
- 业务问题：这个主题是否代表长时间观看舒适，而不是健康宣传语？
- 命中 SKU：377，证据域：claim, comment, param, semantic_reference
- 证据域 SKU 数：{"claim": 221, "comment": 302, "param": 377, "semantic_reference": 367}
- 主要命中词：{"claim": ["护眼", "低蓝光", "抗反光", "无频闪"], "comment": ["护眼", "老人", "eye", "child", "孩子", "久看"], "param": ["eye"], "semantic_reference": ["family", "家庭", "long_watch", "child"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 操作便利感 `operation_convenience_perception`

- 定义：AI、语音、投屏、IoT、系统易用带来的家庭使用便利。
- 业务问题：这个主题是否代表家庭使用便利，而不是泛化智能口号？
- 命中 SKU：377，证据域：claim, comment, param, semantic_reference
- 证据域 SKU 数：{"claim": 261, "comment": 294, "param": 377, "semantic_reference": 367}
- 主要命中词：{"claim": ["智能", "投屏", "语音", "tv_claim_voice_control", "互联"], "comment": ["语音", "投屏", "方便", "cast", "voice", "智能", "易用", "smart"], "param": ["ai", "voice", "语音", "智能", "wifi", "iot"], "semantic_reference": ["smart", "智能", "互联", "connected", "投屏", "iot"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 空间审美适配 `space_aesthetic_fit`

- 定义：外观、超薄、贴墙、全面屏、壁画和新家装修的空间适配价值。
- 业务问题：这个主题是否代表空间/审美适配，而不是单个外观卖点？
- 命中 SKU：377，证据域：claim, comment, param, semantic_reference
- 证据域 SKU 数：{"claim": 120, "comment": 341, "param": 377, "semantic_reference": 339}
- 主要命中词：{"claim": ["贴墙", "超薄", "壁画", "tv_claim_slim_body", "外观"], "comment": ["外观", "appearance", "好看", "家装", "新家"], "param": ["wall", "贴墙", "全面屏", "slim", "超薄", "art"], "semantic_reference": ["decor", "home_decor", "家装", "新家"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

### 购买理由候选

#### 画质配置解释加价 `picture_upgrade_justifies_price`

- 定义：在中高价或同尺寸对比中，SKU 用可验证画质配置和用户感知解释更高价格。
- 业务问题：这个 SKU 的画质配置是否足以解释它的价格？
- 成立逻辑：需要画质事实证据 + 用户感知或 M12C 支付价值 + 价格/市场位置。
- 弱表达边界：只有“高端画质”口号或单一 claim 时不能成立。
- 命中 SKU：377，证据域：claim, claim_value, comment, market, param, semantic_reference
- 证据域 SKU 数：{"claim": 327, "claim_value": 251, "comment": 343, "market": 377, "param": 377, "semantic_reference": 365}
- M12C role 分布：{"sales_driver_estimated": 1115, "premium_driver_estimated": 212, "basic_threshold": 174, "high_price_competitor_intercept": 172, "drag_factor": 96, "weak_user_perception_claim": 52, "opportunity_gap": 43, "price_up_opportunity": 40}
- 主要命中词：{"claim": ["画质", "分区", "miniled", "控光", "tv_claim_miniled", "tv_claim_hdr"], "claim_value": ["sales_driver", "tv_claim_miniled", "premium_driver"], "comment": ["screen", "画质", "清晰", "picture", "clarity", "观影", "电影", "brightness", "亮度"], "market": ["price_percentile", "price_band", "sales", "volume", "high", "mid_high"], "param": ["mini_led", "hdr", "brightness", "dimming", "resolution", "picture", "color", "亮度", "分区", "色域", "miniled", "display"], "semantic_reference": ["premium_picture", "picture", "画质", "影音"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 低价不明显牺牲核心体验 `low_price_core_experience_intact`

- 定义：在低/中低价格位置，SKU 用核心画质、尺寸、系统或评论满意度证明低价不是明显牺牲体验。
- 业务问题：这个 SKU 是否能解释低价下核心体验仍然够用？
- 成立逻辑：需要低/中低价格位置 + 至少一个核心体验证据；销量或评论正向可强化。
- 弱表达边界：只有低价、补贴或促销表达时，不进入产品购买理由。
- 命中 SKU：377，证据域：claim, claim_value, comment, market, param
- 证据域 SKU 数：{"claim": 313, "claim_value": 215, "comment": 346, "market": 377, "param": 377}
- M12C role 分布：{"sales_driver_estimated": 1115, "value_bundle_claim": 6}
- 主要命中词：{"claim": ["tv_claim_miniled", "tv_claim_high_refresh", "价格", "value_price", "price_value", "配置", "性价比"], "claim_value": ["sales_driver", "value_bundle"], "comment": ["清晰", "流畅", "性价比", "够用", "划算", "这个价格"], "market": ["price_band", "volume_percentile", "sales", "low", "mid_low"], "param": ["screen_size", "resolution", "refresh", "ai", "尺寸", "wifi"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 同价位核心配置获得感 `same_price_core_config_gain`

- 定义：在同尺寸/同价位池中，SKU 用更多核心配置或销量承接解释“选它更划算”。
- 业务问题：这个 SKU 是否在同价位中提供了更可解释的核心配置获得感？
- 成立逻辑：需要价格/市场证据 + 配置事实或评论价值感；厂家性价比表达只能弱支撑。
- 弱表达边界：只有 value_price/price_value 时封顶弱表达。
- 命中 SKU：377，证据域：claim, claim_value, comment, market, param
- 证据域 SKU 数：{"claim": 312, "claim_value": 259, "comment": 324, "market": 377, "param": 377}
- M12C role 分布：{"high_price_competitor_intercept": 6464, "opportunity_gap": 4232, "brand_claim_only": 2288, "price_up_opportunity": 2198, "weak_user_perception_claim": 1940, "drag_factor": 1336, "sales_driver_estimated": 1115, "basic_threshold": 867, "premium_driver_estimated": 212, "value_bundle_claim": 6, "unique_payment_potential": 5}
- 主要命中词：{"claim": ["tv_claim_miniled", "tv_claim_high_refresh", "价格", "value_price", "tv_claim_value_price", "price_value", "性价比", "预算"], "claim_value": ["price", "价格", "value_bundle"], "comment": ["性价比", "划算", "这个价格", "预算"], "market": ["volume_percentile", "price_band", "low", "mid_low"], "param": ["mini_led", "refresh", "hdmi", "screen_size", "ai", "尺寸"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 同尺寸画质越级获得感 `same_size_picture_step_up`

- 定义：在同尺寸池中，SKU 用显示技术、亮度、控光或画质芯片解释比普通同尺寸电视更值得选。
- 业务问题：这个 SKU 是否在同尺寸内提供了可感知的画质越级感？
- 成立逻辑：需要同尺寸/价格池参照 + 画质事实证据；评论或 M12C 可作为强化。
- 弱表达边界：只有 MiniLED/画质口号但没有同尺寸参照或体验证据时，只能弱支撑。
- 命中 SKU：377，证据域：claim, claim_value, comment, market, param
- 证据域 SKU 数：{"claim": 327, "claim_value": 251, "comment": 343, "market": 377, "param": 377}
- M12C role 分布：{"sales_driver_estimated": 1115, "premium_driver_estimated": 212, "basic_threshold": 174, "high_price_competitor_intercept": 172, "drag_factor": 96, "weak_user_perception_claim": 52, "opportunity_gap": 43, "price_up_opportunity": 40}
- 主要命中词：{"claim": ["画质", "分区", "miniled", "控光", "tv_claim_miniled", "tv_claim_hdr"], "claim_value": ["sales_driver", "tv_claim_miniled", "premium_driver"], "comment": ["screen", "画质", "清晰", "picture", "clarity", "观影", "电影", "brightness", "亮度"], "market": ["screen_size", "size_segment", "price_band_size", "price_percentile", "volume_percentile"], "param": ["mini_led", "hdr", "brightness", "dimming", "resolution", "picture", "color", "亮度", "分区", "色域", "screen_size", "inch"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 贵得值的体验升级 `worth_paying_more_for_experience_upgrade`

- 定义：在中高/高价格位置，SKU 让用户看到多花钱换来的画质、动态或沉浸升级，并由评论、M12C 或市场承接证明这笔加价值得。
- 业务问题：用户是否会觉得这个 SKU 虽然更贵，但多花的钱换来了明确体验升级？
- 成立逻辑：需要中高/高价格位置 + 至少一个可感知强体验证据 + 评论、M12C 或市场承接；若反馈反向则转为价格压力。
- 弱表达边界：只有高端口号、品牌溢价或参数堆叠，用户感知不到升级时，不能作为正向购买理由。
- 命中 SKU：377，证据域：claim, claim_value, comment, market, param
- 证据域 SKU 数：{"claim": 327, "claim_value": 259, "comment": 346, "market": 377, "param": 377}
- M12C role 分布：{"high_price_competitor_intercept": 6464, "opportunity_gap": 4232, "price_up_opportunity": 2198, "drag_factor": 1336, "sales_driver_estimated": 1115, "premium_driver_estimated": 212}
- 主要命中词：{"claim": ["画质", "高刷", "分区", "游戏", "miniled", "控光", "tv_claim_miniled", "tv_claim_high_refresh", "刷新率", "tv_claim_hdr"], "claim_value": ["high_price_competitor_intercept", "opportunity_gap", "price_up_opportunity", "drag_factor", "sales_driver", "premium_driver"], "comment": ["画质", "清晰", "流畅", "性价比", "价格", "观影", "高刷"], "market": ["price_percentile", "price_band", "volume_percentile", "high", "mid_high"], "param": ["mini_led", "hdr", "brightness", "dimming", "resolution", "picture", "color", "亮度", "分区", "色域", "refresh", "hz"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 影音用户愿为画质升级付费 `av_user_willing_to_pay_for_picture`

- 定义：面向影音/电影/追剧用户，SKU 用画质和沉浸体验证明其具备付费升级理由。
- 业务问题：影音用户是否有理由为这个 SKU 的画质/观影体验付费？
- 成立逻辑：需要画质事实 + 观影/影音任务或评论 + M12C 正向支付价值。
- 弱表达边界：只有影音/影院宣传语，缺少画质事实或 M12C 时不能强判。
- 命中 SKU：377，证据域：claim, claim_value, comment, param, semantic_reference
- 证据域 SKU 数：{"claim": 327, "claim_value": 251, "comment": 340, "param": 377, "semantic_reference": 366}
- M12C role 分布：{"sales_driver_estimated": 1115, "premium_driver_estimated": 212, "basic_threshold": 174, "high_price_competitor_intercept": 172, "drag_factor": 96, "weak_user_perception_claim": 52, "opportunity_gap": 43, "price_up_opportunity": 40}
- 主要命中词：{"claim": ["画质", "影院", "分区", "沉浸", "miniled", "控光", "音响", "tv_claim_miniled", "杜比", "tv_claim_hdr", "大屏"], "claim_value": ["sales_driver", "tv_claim_miniled", "premium_driver"], "comment": ["画质", "清晰", "观影", "电影", "影院", "亮度", "沉浸", "追剧"], "param": ["mini_led", "hdr", "brightness", "dimming", "resolution", "picture", "color", "亮度", "分区", "色域", "screen_size", "inch"], "semantic_reference": ["影院", "premium_picture", "cinema", "观影", "影音"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 游戏设备适配降低踩坑风险 `gaming_device_fit_reduces_risk`

- 定义：面向游戏/体育用户，SKU 用高刷、接口、VRR、低延迟等完整性降低体验不确定性。
- 业务问题：这个 SKU 是否能减少游戏/体育体验踩坑风险？
- 成立逻辑：需要高刷/接口/低延迟事实证据 + 游戏任务或评论感知。
- 弱表达边界：只有“游戏电视”表达时不能成立。
- 命中 SKU：377，证据域：claim, claim_value, comment, param, semantic_reference
- 证据域 SKU 数：{"claim": 258, "claim_value": 234, "comment": 324, "param": 377, "semantic_reference": 364}
- M12C role 分布：{"high_price_competitor_intercept": 319, "opportunity_gap": 149, "weak_user_perception_claim": 97, "drag_factor": 58, "sales_driver_estimated": 52, "price_up_opportunity": 51, "basic_threshold": 27, "brand_claim_only": 18, "premium_driver_estimated": 7}
- 主要命中词：{"claim": ["高刷", "游戏", "tv_claim_high_refresh", "刷新率"], "claim_value": ["tv_claim_high_refresh"], "comment": ["流畅", "smooth", "游戏", "gaming", "高刷", "sports", "体育", "motion"], "param": ["refresh", "hz", "hdmi", "刷新率"], "semantic_reference": ["gaming", "sports", "游戏", "体育", "fluency", "流畅"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 体育/运动画面流畅更稳 `sports_motion_stability`

- 定义：面向赛事和运动画面，SKU 用刷新率、运动补偿或高刷评论解释动态画面更稳。
- 业务问题：这个 SKU 是否能解释体育/运动画面看起来更稳？
- 成立逻辑：需要刷新率/MEMC/高刷事实 + 体育或运动评论/任务支撑。
- 弱表达边界：只有高刷口号，没有体育/运动场景证据时不能强判。
- 命中 SKU：377，证据域：claim, claim_value, comment, param, semantic_reference
- 证据域 SKU 数：{"claim": 242, "claim_value": 234, "comment": 324, "param": 377, "semantic_reference": 364}
- M12C role 分布：{"high_price_competitor_intercept": 319, "opportunity_gap": 149, "weak_user_perception_claim": 97, "drag_factor": 58, "sales_driver_estimated": 52, "price_up_opportunity": 51, "basic_threshold": 27, "brand_claim_only": 18, "premium_driver_estimated": 7}
- 主要命中词：{"claim": ["高刷", "tv_claim_high_refresh", "刷新率", "运动", "体育"], "claim_value": ["tv_claim_high_refresh"], "comment": ["流畅", "smooth", "高刷", "sports", "体育", "运动", "motion"], "param": ["refresh", "hz", "刷新率"], "semantic_reference": ["sports", "体育", "fluency", "流畅", "motion"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 大屏影音替代影院感 `big_screen_cinema_substitution`

- 定义：SKU 用大屏、画质、音效或杜比能力解释家庭观影的影院替代体验。
- 业务问题：这个 SKU 是否能解释用户用它获得大屏影音替代影院感？
- 成立逻辑：需要大屏/音画事实 + 观影评论或影院沉浸任务；市场同尺寸承接可强化。
- 弱表达边界：只有“影院级/沉浸感”宣传语，没有音画事实或评论时不能成立。
- 命中 SKU：377，证据域：claim, comment, market, param, semantic_reference
- 证据域 SKU 数：{"claim": 327, "comment": 277, "market": 377, "param": 377, "semantic_reference": 368}
- 主要命中词：{"claim": ["画质", "影院", "分区", "沉浸", "miniled", "控光", "音响", "tv_claim_miniled", "杜比", "tv_claim_hdr", "大屏"], "comment": ["观影", "客厅", "电影", "影院", "沉浸", "追剧", "大屏"], "market": ["size_segment", "screen_size", "large", "ultra_large"], "param": ["screen_size", "inch", "尺寸", "mini_led", "hdr", "brightness", "dimming", "resolution", "picture", "color", "亮度", "分区"], "semantic_reference": ["large_screen", "大屏", "影院", "cinema", "观影"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 客厅换新一步到位 `living_room_upgrade_one_step`

- 定义：面向客厅换新，SKU 用尺寸、观影沉浸和主流价格/销量承接解释一步升级。
- 业务问题：这个 SKU 是否能解释客厅换新时为什么一步升级到它？
- 成立逻辑：需要尺寸/观影事实 + 用户任务或评论感知 + 市场承接。
- 弱表达边界：只有屏幕尺寸数字，不足以成为购买理由。
- 命中 SKU：377，证据域：claim, comment, market, param, semantic_reference
- 证据域 SKU 数：{"claim": 326, "comment": 326, "market": 377, "param": 377, "semantic_reference": 368}
- 主要命中词：{"claim": ["影院", "沉浸", "音响", "杜比", "大屏"], "comment": ["cinema", "观影", "客厅", "living_room", "电影", "沉浸", "追剧"], "market": ["size_segment", "screen_size", "large", "ultra_large"], "param": ["screen_size", "inch", "尺寸", "large"], "semantic_reference": ["large_screen", "大屏", "客厅", "cinema", "观影"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：review_candidate

#### 家庭长时间观看更安心 `family_long_watch_comfort_assurance`

- 定义：老人、孩子或家庭长看场景下，SKU 用护眼事实和用户感知降低长期观看顾虑。
- 业务问题：这个 SKU 是否能解释家庭长时间观看更安心？
- 成立逻辑：需要护眼参数或认证 + 评论/任务支撑；泛健康口号不足。
- 弱表达边界：只有健康宣传或认证口号时不能强判。
- 命中 SKU：377，证据域：claim, comment, param, semantic_reference
- 证据域 SKU 数：{"claim": 221, "comment": 302, "param": 377, "semantic_reference": 367}
- 主要命中词：{"claim": ["护眼", "低蓝光", "抗反光", "无频闪"], "comment": ["护眼", "老人", "eye", "child", "孩子", "久看"], "param": ["eye"], "semantic_reference": ["family", "家庭", "long_watch", "child"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：needs_price_or_payment_validation

#### 家庭多设备使用更省操作 `family_operation_less_friction`

- 定义：家庭多人使用时，SKU 用投屏、语音、IoT 和系统易用降低操作成本。
- 业务问题：这个 SKU 是否能解释家庭日常使用更省操作？
- 成立逻辑：需要智能/互联事实证据 + 任务或评论易用感知。
- 弱表达边界：只有 AI 或智能口号时只能弱支撑。
- 命中 SKU：377，证据域：claim, comment, param, semantic_reference
- 证据域 SKU 数：{"claim": 261, "comment": 294, "param": 377, "semantic_reference": 367}
- 主要命中词：{"claim": ["智能", "投屏", "语音", "tv_claim_voice_control", "互联"], "comment": ["语音", "投屏", "方便", "cast", "voice", "智能", "易用", "smart"], "param": ["ai", "voice", "语音", "智能", "wifi", "iot"], "semantic_reference": ["smart", "智能", "互联", "connected", "投屏", "iot"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：needs_price_or_payment_validation

#### 新家客厅审美适配 `new_home_aesthetic_fit`

- 定义：新家装修或客厅审美场景下，SKU 用外观/安装适配解释为什么更适合。
- 业务问题：这个 SKU 是否能解释新家客厅为什么更适配？
- 成立逻辑：需要外观/安装事实 + 新家/家装任务或评论支撑。
- 弱表达边界：只有外观好看表达时不能直接成为核心购买理由。
- 命中 SKU：377，证据域：claim, comment, param, semantic_reference
- 证据域 SKU 数：{"claim": 120, "comment": 341, "param": 377, "semantic_reference": 339}
- 主要命中词：{"claim": ["贴墙", "超薄", "壁画", "tv_claim_slim_body", "外观"], "comment": ["外观", "appearance", "好看", "家装", "新家"], "param": ["wall", "贴墙", "全面屏", "slim", "超薄", "art"], "semantic_reference": ["decor", "home_decor", "家装", "新家"]}
- 样本 SKU：TV00009549 康佳 LED32E330CE, TV00023850 酷开 50P31, TV00027302 VIDDA 65V1Q-R, TV00027353 VIDDA 75V1Q-R, TV00027442 红米 L32RA-RAE, TV00027443 红米 L55RB-RAE, TV00027463 红米 L43RB-APE, TV00027475 红米 L55RB-APE
- 审阅标记：needs_price_or_payment_validation

## 5. 修正建议

- 标准模型：先固化 TV 标准价值主题，再在主题之上固化选择逻辑型标准购买理由；M12D 生产程序只消费标准，不自动生成标准。
- G04 taxonomy 修正：现有 G04 的高端画质/游戏流畅等应降级为价值主题候选或 theme_family；新增 purchase_reason_code 才能进入成交理由画像。
- 建议进入价值主题草案：dynamic_stability_perception, picture_upgrade_perception, living_room_immersion_perception, budget_configuration_efficiency, long_watch_comfort_perception, operation_convenience_perception, space_aesthetic_fit
- 需要复核的价值主题：无
- 建议进入购买理由草案：picture_upgrade_justifies_price, low_price_core_experience_intact, same_price_core_config_gain, same_size_picture_step_up, worth_paying_more_for_experience_upgrade, av_user_willing_to_pay_for_picture, gaming_device_fit_reduces_risk, sports_motion_stability, big_screen_cinema_substitution, living_room_upgrade_one_step
- 需要复核的购买理由：family_long_watch_comfort_assurance, family_operation_less_friction, new_home_aesthetic_fit

## 6. G05 前置结论

G05 不能继续消费 G04 中的名词型锚点作为购买理由。必须先把标准拆成 `value_theme_code` 与 `purchase_reason_code`，并让购买理由包含选择逻辑、证据门槛和弱表达边界。
