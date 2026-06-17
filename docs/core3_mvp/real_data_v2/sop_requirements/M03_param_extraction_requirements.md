# M03 参数字段画像与标准参数抽取 SOP 需求

## 0. 单模块强化状态

本文件已按“单模块逐一强化”要求完成第一轮强化。下一步应处理 M04a 基础卖点激活。

## 1. 模块目标

M03 把 M02 的参数 evidence 和宣传文本中的可解析数值实体，转换成标准参数画像。它要解决四个问题：

1. 原始 `attribute_data.attr_name` 有 84 类字段，字段名不等于标准参数名，需要做字段画像和别名匹配。
2. `attr_value` 有大量 unknown、空值和 `-`，需要把 unknown 与 false 严格区分。
3. 部分参数可能来自宣传文本，例如 nits、Hz、HDMI2.1、分区数，需要作为派生参数候选，但不能覆盖参数表事实。
4. 下游 M04a、M07、M08、M09-M15 需要稳定的 `param_code + normalized_value + evidence_ids + confidence`。

M03 是“参数标准化与参数画像”模块，不做卖点激活、用户任务、目标客群、价值战场或竞品判断。

## 2. 设计依据

本模块依据：

- `cankao/CatForge_竞品生成SOP_详细指导_v1.md` 的 M03 要求。
- `cankao/catforge_sop_md/modules/M03_参数字段画像与标准参数抽取.md`。
- M02 已强化后的 evidence 类型与粒度。
- [00 真实样例数据基线](00_real_data_baseline.md)。
- 项目现有彩电 seed：`apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json`。

## 3. 上游输入

### 3.1 必须输入

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| `param_raw` evidence | M02 `core3_evidence_atom` | 原始参数字段和值的主输入 |
| `promo_sentence` evidence | M02 `core3_evidence_atom` | 宣传文本中的派生参数候选 |
| `quality_issue` evidence | M02 `core3_evidence_atom` | unknown、冲突、覆盖缺失等降权 |
| 标准参数 seed | `tv_core3_mvp_seed_v0_2.json` 或后续 `core3_std_param_seed` | 标准参数定义、别名、解析器、阈值、映射关系 |

### 3.2 不消费的输入

| 数据 | 处理 |
| --- | --- |
| 评论正文 | M03 不直接消费。评论中与参数相关的表达由 M05/M06 形成评论信号，不能在 M03 直接当标准参数 |
| 市场量价 | M03 不消费。价格、销量、渠道由 M07 处理 |
| M04a 卖点激活结果 | M03 不依赖 M04a，避免循环依赖 |

## 4. 本模块不做什么

- 不判断标准卖点是否激活。
- 不把参数强弱解释成用户任务或价值战场。
- 不判断某 SKU 是否是竞品。
- 不把 unknown、空值、`-` 当 false。
- 不把宣传派生参数当成比参数表更高优先级的事实。
- 不用 85E7Q 的样例字段写死全部逻辑。
- 不丢弃高覆盖但未映射的原始字段。

## 5. 预制与抽取边界

### 5.1 必须预制的内容

标准参数库必须预制，并且可版本化维护。首版来自 `tv_core3_mvp_seed_v0_2.json`。

每个标准参数至少包含：

| 字段 | 说明 |
| --- | --- |
| `param_code` | 稳定编码 |
| `param_name` | 中文名 |
| `definition` | 业务定义 |
| `param_group` | 参数组 |
| `data_type` | number/enum/boolean/list/string |
| `unit` | 标准单位 |
| `aliases` | 原始字段别名 |
| `keywords` | 文本抽取关键词 |
| `source_types` | 可接受来源 |
| `source_priority` | 来源优先级 |
| `value_parsers` | 值解析器 |
| `thresholds` | 分档阈值 |
| `enum_values` | 枚举值 |
| `mapped_claim_codes` | 可支撑的卖点 |
| `mapped_task_codes` | 可支撑的用户任务 |
| `mapped_battlefield_codes` | 可支撑的战场 |

### 5.2 必须从真实数据抽取的内容

| 抽取内容 | 来源 | 输出 |
| --- | --- | --- |
| 原始字段覆盖率 | `param_raw` evidence | 字段画像 |
| unknown 率 | `param_raw` + `quality_issue` | 字段画像和质量标记 |
| 高频值 | `param_raw` evidence | 字段画像 |
| 字段到标准参数的映射 | seed 别名和真实字段 | `matched_param_code` |
| 标准参数值 | `param_raw` 和 `promo_sentence` | `core3_extract_param_value` |
| 未映射高覆盖字段 | 真实字段画像 | 参数别名候选 |
| 同 SKU 同参数冲突 | 多 evidence 对比 | 冲突复核 |

## 6. MVP 标准参数范围

首版标准参数不只覆盖 85E7Q 样例字段，应覆盖彩电竞品生成需要的核心参数域。

| 参数组 | 标准参数 |
| --- | --- |
| 显示基础 | `screen_size_inch`、`resolution_class`、`panel_type`、`display_technology`、`series_name`、`launch_period` |
| 画质 | `native_refresh_rate_hz`、`system_refresh_rate_hz`、`refresh_rate_hz`、`peak_brightness_nits`、`instant_peak_brightness_nits`、`sustained_brightness_nits`、`sustained_peak_brightness_nits`、`color_gamut_pct`、`color_gamut_standard`、`color_depth_bit`、`hdr_format_list`、`picture_processor`、`motion_compensation_flag` |
| 背光控光 | `mini_led_flag`、`oled_flag`、`qled_flag`、`backlight_type`、`dimming_zones`、`local_dimming_flag`、`halo_control_claim_flag` |
| 游戏连接 | `hdmi_2_1_ports`、`full_bandwidth_hdmi_flag`、`vrr_flag`、`allm_flag`、`input_lag_ms`、`game_mode_flag`、`freesync_flag` |
| 音频 | `speaker_power_w`、`speaker_channel`、`subwoofer_flag`、`dolby_atmos_flag`、`dts_flag` |
| 智能系统 | `ram_gb`、`storage_gb`、`chipset_name`、`os_name`、`voice_control_flag`、`far_field_voice_flag`、`startup_ads_risk_flag` |
| 护眼体验 | `eye_dimming_freq_hz`、`low_blue_light_flag`、`flicker_free_flag`、`ambient_light_sensor_flag`、`anti_glare_flag`、`elder_mode_flag`、`child_mode_flag` |

以上是首版预制参数范围；真实数据中高覆盖但未命中的字段必须进入候选，不允许因为 seed 没有就丢弃。

## 7. 字段画像需求

### 7.1 画像目标

字段画像回答：

- 这个原始字段覆盖多少 SKU。
- unknown 比例是多少。
- 高频值有哪些。
- 是否匹配到标准参数。
- 匹配置信度如何。
- 是否需要进入标准参数库复核。

### 7.2 匹配流程

字段名匹配顺序：

1. 精确别名匹配：`raw_attr_name_norm == alias_norm`。
2. 标准名匹配：`raw_attr_name_norm == param_name_norm`。
3. 包含别名匹配：字段名包含 seed alias。
4. 关键词匹配：字段名或高频值命中 seed keywords。
5. 值形态辅助：字段值形态符合某参数，例如 `85` 更可能是尺寸，`300HZ` 更可能是刷新率。
6. 未命中则进入 `unmapped` 或 `review_candidate`。

### 7.3 输出表：`core3_param_field_profile`

| 字段 | 说明 |
| --- | --- |
| `project_id` | 项目 |
| `category_code` | 品类，MVP 为 TV |
| `batch_id` | 批次 |
| `raw_param_name` | 原始字段名 |
| `clean_param_name` | 清洗字段名 |
| `occurrence_count` | 出现次数 |
| `sku_coverage_count` | 覆盖 SKU 数 |
| `sku_coverage_rate` | 覆盖率 |
| `unknown_count` | unknown 数量 |
| `unknown_rate` | unknown 比例 |
| `top_values_json` | 高频值 |
| `value_pattern_summary` | 值形态摘要 |
| `matched_param_code` | 命中的标准参数 |
| `match_type` | exact_alias/contains_alias/keyword/value_pattern/unmapped |
| `alias_confidence` | 字段别名置信度 |
| `candidate_status` | mapped/unmapped/review_candidate |
| `review_reason` | 复核原因 |
| `evidence_ids` | 支撑 evidence |
| `rule_version` | 规则版本 |

## 8. 标准参数值抽取

### 8.1 抽取流程

1. 读取 `param_raw` evidence。
2. 基于字段画像确定 `param_code`。
3. 基于 `param_code` 的 `data_type` 和 `value_parsers` 解析值。
4. 生成 `normalized_value`、`unit`、`value_text` 和 `value_level`。
5. 使用 seed 阈值生成参数分档。
6. 合并同 SKU 同参数多来源值。
7. 识别冲突和 unknown。
8. 写入标准参数值表。

### 8.2 值解析规则

| 类型 | 示例 | 解析要求 |
| --- | --- | --- |
| 尺寸 | `85`、`85英寸` | 解析为 inch 数值 |
| 分辨率 | `4K`、`3840x2160` | 归一到 4K/8K/FHD/UNKNOWN |
| 刷新率 | `300HZ`、`144Hz` | 解析 Hz，并区分原生刷新率、系统/倍频刷新率 |
| 亮度 | `5200`、`5200nits` | 解析 nits；无单位时保留单位不确定标记 |
| 分区 | `3500`、`千级分区` | 解析 zones；口径不明时标记 uncertain_unit |
| HDMI | `HDMI2.1`、`4个HDMI` | 解析接口版本、数量或能力标记 |
| 内存 | `4GB` | 解析 GB |
| 存储 | `64GB` | 解析 GB |
| 布尔 | `是`、`支持`、`无`、`不支持` | 解析 true/false/unknown，缺失不是 false |
| 枚举 | `海信星海`、`Mini LED` | 保留标准枚举或字符串 |

### 8.3 刷新率特殊口径

`屏幕刷新率=300HZ` 这类字段必须支持口径复核：

- 如果 seed 或字段名明确是“系统/倍频刷新率”，进入 `system_refresh_rate_hz`。
- 如果字段名明确是“原生刷新率”，进入 `native_refresh_rate_hz`。
- 如果字段名只有“屏幕刷新率/刷新率”，且值高于常见原生口径，首版可进入 `system_refresh_rate_hz`，同时生成 `refresh_rate_scope_uncertain` 复核提示。
- 不允许把系统/倍频刷新率直接当成原生刷新率支撑游戏战场高置信结论。

### 8.4 宣传派生参数

M03 可以从 M02 `promo_sentence` evidence 中抽取派生参数候选，例如：

- `5200nits`
- `3500分区`
- `144Hz`
- `HDMI2.1`
- `4+64GB`

要求：

- 派生参数 `source_type=derived_from_claim`。
- 派生参数置信度低于参数表事实。
- 如果与参数表冲突，保留两边 evidence 并进入复核。
- 对 85E7Q 当前没有结构化卖点的情况，不应生成宣传派生参数。

## 9. 多来源合并与冲突

### 9.1 来源优先级

默认优先级：

```text
raw_param > claim_text > model_name
```

评论不进入 M03 标准参数值。评论可以在 M06 形成“体验感知信号”，再给 M04b/M09-M11 使用。

### 9.2 冲突类型

| 冲突类型 | 示例 | 处理 |
| --- | --- | --- |
| 同字段多值 | 同一 SKU 多条 `亮度` 值不同 | 保留多值，主值待定 |
| 参数表与宣传冲突 | 参数 144Hz，宣传 300Hz | 降置信，进入复核 |
| 单位不明确 | `亮度=5200` 无单位 | 保留数值，单位不确定 |
| 口径不明确 | `屏幕刷新率=300HZ` | 标记原生/系统口径不确定 |
| 布尔缺失 | `MINILED` 为空 | unknown，不是 false |

### 9.3 输出表：`core3_param_value_conflict`

| 字段 | 说明 |
| --- | --- |
| `conflict_id` | 冲突 ID |
| `sku_code` | SKU |
| `param_code` | 标准参数 |
| `conflict_type` | 冲突类型 |
| `candidate_values_json` | 候选值 |
| `preferred_value` | 暂定主值 |
| `confidence` | 主值置信度 |
| `evidence_ids` | 冲突证据 |
| `review_status` | pending/approved/rejected |
| `review_reason` | 复核原因 |

## 10. 输出数据契约

### 10.1 `core3_extract_param_value`

| 字段 | 说明 |
| --- | --- |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `param_code` | 标准参数编码 |
| `param_name` | 中文参数名 |
| `param_group` | 参数组 |
| `data_type` | number/enum/boolean/list/string |
| `normalized_value` | 标准值 |
| `value_text` | 展示文本 |
| `unit` | 标准单位 |
| `value_level` | 分档 |
| `source_type` | raw_param/derived_from_claim/model_name |
| `match_type` | 字段匹配方式 |
| `parser_type` | 值解析器 |
| `confidence` | 参数值置信度 |
| `evidence_ids` | 参数 evidence |
| `quality_flags` | unknown/unit_uncertain/scope_uncertain/conflict |
| `conflict_flag` | 是否冲突 |
| `review_status` | auto/review_required/approved/rejected |
| `rule_version` | 规则版本 |

### 10.2 `core3_param_alias_candidate`

| 字段 | 说明 |
| --- | --- |
| `raw_param_name` | 原始字段名 |
| `sku_coverage_rate` | 覆盖率 |
| `unknown_rate` | unknown 率 |
| `top_values_json` | 高频值 |
| `suggested_param_code` | 建议标准参数 |
| `suggestion_reason` | 建议理由 |
| `confidence` | 建议置信度 |
| `review_status` | pending/accepted/rejected |

### 10.3 `core3_sku_param_profile`

SKU 级参数画像供 M08 直接消费。

| 字段 | 说明 |
| --- | --- |
| `sku_code` | SKU |
| `param_values_json` | 标准参数键值 |
| `core_picture_params_json` | 画质核心参数摘要 |
| `core_gaming_params_json` | 游戏连接核心参数摘要 |
| `core_system_params_json` | 智能系统参数摘要 |
| `param_completeness` | 参数完整度 |
| `unknown_param_count` | unknown 参数数 |
| `conflict_count` | 冲突数 |
| `evidence_ids` | 核心证据 |
| `quality_summary` | 质量摘要 |

## 11. 85E7Q 样例抽取要求

85E7Q 的 `model_code=TV00029115`。M03 至少应能从真实参数中抽取：

| 原始字段 | 原值 | 标准参数方向 | 注意事项 |
| --- | --- | --- | --- |
| `尺寸` | 85 | `screen_size_inch=85` | 支撑大屏、客厅观影、可比池 |
| `清晰度2` | 4K | `resolution_class=4K` | 原始字段别名需进入 seed 或候选 |
| `屏幕刷新率` | 300HZ | `system_refresh_rate_hz=300` 或待复核 | 不直接当原生刷新率 |
| `亮度` | 5200 | `peak_brightness_nits=5200` | 无单位时标记单位推断 |
| `分区背光` | 3500 | `dimming_zones=3500` | 字段别名需覆盖 |
| `MINILED` | 是 | `mini_led_flag=true` | “是”解析为 true |
| `HDMI参数` | HDMI2.1 | `hdmi_2_1_ports` 或 HDMI2.1 能力 | 若没有数量，不伪造端口数 |
| `HDMI数量` | 4 | HDMI 接口数量候选 | 与 HDMI2.1 版本合并需复核 |
| `RAM内存` | 4GB | `ram_gb=4` | 标准单位 GB |
| `ROM容量` | 64GB | `storage_gb=64` | 标准单位 GB |
| `AI大模型` | 海信星海 | 智能系统参数 | 保留字符串，不强行布尔 |

85E7Q 没有结构化卖点，因此 M03 不能从宣传文本补出 85E7Q 的派生参数。

## 12. 真实数据约束

当前 205 样例数据对 M03 的硬约束：

- `attribute_data` 有 84 类属性，M03 必须输出全字段画像。
- unknown/空值/`-` 约 961 行，unknown 必须独立标记。
- 高覆盖但未映射字段，例如 `CPU主频`、`GPU核数`、`HDR`、`IC型号`、`全面屏`、`UI界面`、`HEVC参数`、`主芯片供应商` 等，必须进入候选或质量摘要。
- 卖点只覆盖 5 个型号，派生参数覆盖天然不足，不应影响未覆盖 SKU 的参数表事实。
- 当前只有海信品牌，M03 不做竞品内外部判断。

## 13. 与下游模块关系

### 给 M04a 的承诺

- M04a 使用标准参数判断基础卖点支撑，例如 Mini LED、高亮度、分区控光、高刷、HDMI2.1。
- 每个参数都有 evidence 和置信度。
- unknown 不能被 M04a 当成卖点不成立。

### 给 M07 的承诺

- M07 使用 `screen_size_inch`、价格无关参数和必要技术参数构建可比池。
- M03 不计算价格带或销量。

### 给 M08 的承诺

- M08 可以直接消费 `core3_sku_param_profile`。
- M08 必须看到参数完整度、unknown 数和冲突数。

### 给 M09-M11.5 的承诺

- 用户任务、客群、战场和卖点分层可以引用参数支撑，但必须保留 evidence。
- 参数只说明能力事实，不直接等于任务或战场结论。

### 给 M12-M15 的承诺

- 竞品候选、组件评分和报告中的参数证据来自 M03 输出。
- 报告展示时应把参数转成中文业务表达，不展示内部 `param_code`。

### 给 M16 的承诺

- M16 可基于字段画像、参数冲突、候选别名和参数完整度触发复核。

## 14. 复核触发条件

以下情况必须进入复核队列：

- 高覆盖原始字段未匹配标准参数。
- 别名匹配置信度低但影响核心战场。
- 同一 SKU 同一标准参数出现多值冲突。
- 参数表和宣传派生参数冲突。
- 关键参数值 unknown，但 SKU 是目标 SKU 或候选核心 SKU。
- 口径不明，例如 `屏幕刷新率=300HZ`。
- 单位不明，例如 `亮度=5200` 无单位。
- 派生参数来自宣传文本但缺少参数表支撑。

## 15. 增量重算要求

M03 响应以下输入变化：

| 输入变化 | M03 动作 | 建议下游影响 |
| --- | --- | --- |
| `param_raw` evidence 新增/变化 | 重算对应 SKU 参数 | M04a、M08-M16 |
| `promo_sentence` evidence 新增/变化 | 重算派生参数候选 | M04a、M08-M16 |
| 标准参数 seed 变化 | 重算字段画像和参数值 | M03-M16 |
| quality evidence 变化 | 更新置信度和复核状态 | M04a、M08、M16 |

如果同一 SKU 的 `core3_sku_param_profile` hash 未变化，不触发下游重算。

## 16. 验收标准

| 验收项 | 标准 |
| --- | --- |
| 生成全字段参数画像 | 必须 |
| 预制标准参数库可版本化 | 必须 |
| 85E7Q 核心参数可抽取 | 必须 |
| 重点参数识别率 | 目标不低于 95%，未识别进入候选 |
| 参数 evidence 保留 | 100% |
| unknown 不误判 false | 必须 |
| 系统/原生刷新率口径可区分或复核 | 必须 |
| HDMI 版本和数量不混淆 | 必须 |
| 卖点派生参数低于参数表优先级 | 必须 |
| 未映射高覆盖字段进入候选 | 必须 |
| 冲突进入复核 | 必须 |
| 下游能按 SKU 消费标准参数画像 | 必须 |
