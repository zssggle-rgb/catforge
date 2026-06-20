# M03B SKU 参数事实画像与参数档位覆盖 SOP 需求

## 0. 定位

M03B 是新数据批次进入后高频执行的 SKU 参数事实画像模块。它消费 M03A 已发布的品类参数 taxonomy，把 M02 `param_raw` evidence 转成每个 SKU 的标准参数值、参数维度档位画像，以及不同参数档位覆盖的 SKU 清单。

M03B 解决的问题是：

```text
某个 SKU 有哪些可验证参数事实；
这些参数事实在本品类当前样本中处于什么档位；
每个档位覆盖哪些 SKU，可供后续竞品召回参考。
```

M03B 不生成卖点、用户任务、目标客群、价值战场或竞品结论。它只提供 SKU 参数事实和参数档位索引。

## 1. 与 M03A 的关系

| 模块 | 生命周期 | 职责 |
| --- | --- | --- |
| M03A | 低频，品类资产维护 | 从原始参数字段生成并发布品类参数 taxonomy、标准参数、字段映射、缺失规则、参数档位规则 |
| M03B | 高频，新批次运行 | 使用已发布 taxonomy 生成 SKU 参数事实画像、SKU 参数维度档位、档位覆盖 SKU 清单 |

如果没有已发布 taxonomy，M03B 必须阻断。M03B 不能在运行时自动新增标准参数、修改字段映射、修改档位规则，不能用其他品类 taxonomy 兜底。

## 2. 输入

| 输入 | 来源 | 必需 | 用途 |
| --- | --- | --- | --- |
| 已发布品类 taxonomy | M03A | 是 | 标准参数、原始字段映射、parser、缺失规则、档位规则 |
| 参数 evidence | M02 `core3_evidence_atom`，`evidence_type=param_raw` | 是 | SKU 参数事实来源 |
| 批次信息 | M00 `core3_source_batch` | 是 | batch 边界、增量重跑边界 |
| 人工复核决策 | M16 或参数复核 API | 否 | 解决参数冲突或规则例外 |

当前 205 彩电临时边界：

```text
project_id = d8d2245b-358b-4a64-95cc-9d7f2341bd26
batch_id = m00_20260619084551_857df63b
category_code = TV
sku_code like 'TV%'
```

当前批次存在 AC SKU 混入 `category_code=TV` 的历史问题。M03B-TV 在 M00/M02 品类边界彻底修复前，必须保留 `sku_code like 'TV%'` 防御性过滤。

## 3. 输出

M03B 必须输出三类结果。

### 3.1 SKU 参数事实画像

每个 SKU 一条参数事实画像，包含：

- 标准参数值。
- 原始字段来源。
- evidence id。
- parser 版本。
- taxonomy 版本。
- 缺失、false-by-absence、排除字段、冲突和异常说明。

典型输出字段：

```json
{
  "sku_code": "TV00027549",
  "category_code": "TV",
  "taxonomy_version": "tv_param_taxonomy_manual_v0.1",
  "param_fact_profile": {
    "screen_size_inch": 65,
    "resolution_label": "4K",
    "declared_refresh_rate_hz": 144,
    "declared_brightness_band": "200-300",
    "display_tech_class": "lcd_led",
    "local_dimming_zone_count": 0,
    "ram_gb": 2,
    "storage_gb": 32,
    "ai_model_name": "海信星海",
    "hdmi_version_mix": "HDMI2.1",
    "energy_efficiency_grade": "一级"
  }
}
```

### 3.2 SKU 参数维度档位画像

每个 SKU 必须同时生成参数维度档位：

- 尺寸档位。
- 显示技术档位。
- 分区控光档位。
- 画质综合档位。
- 性能档位。
- 智能档位。
- 接口档位。
- 外观安装档位。
- 能效档位。

示例：

```json
{
  "sku_code": "TV00027549",
  "dimension_tier_profile": {
    "size": "large_60_69",
    "display_tech": "lcd_led",
    "local_dimming": "z_none_0",
    "picture_overall": "picture_enhanced",
    "performance": "perf_basic",
    "smart": "smart_ai_voice",
    "ports": "ports_main_hdmi21",
    "appearance": "appearance_standard",
    "energy": "energy_grade_1"
  }
}
```

档位画像必须保留解释，说明该 SKU 为什么落入该档位。解释只基于参数事实，不得引入评论、卖点、市场表现或业务推断。

### 3.3 参数档位覆盖 SKU 清单

每个参数维度的每个档位都要生成覆盖情况：

- `dimension_code`
- `tier_code`
- `tier_name`
- `sku_count`
- `sku_ratio`
- `sku_codes`
- 示例 SKU。
- 规则摘要。
- 当前批次是否有覆盖。

该清单供后续 M12/M13 竞品召回和评分使用。后续找竞品时可以优先按同尺寸档、同画质档、同显示技术档、同性能档、同智能档召回。

## 4. 不做事项

M03B 不做：

- 不调用 LLM。
- 不生成或修改品类 taxonomy。
- 不读取评论正文。
- 不读取卖点文本。
- 不读取销量、价格、平台等市场事实。
- 不生成卖点激活。
- 不生成用户任务、目标客群、价值战场。
- 不生成竞品候选或竞品评分。
- 不把服务履约、质量诊断、清洗质量信息当作产品能力证据。
- 不把缺失、空值、`-` 统一当作 false。

只有 M03A taxonomy 明确标记为 `false_by_absence` 的特性字段，M03B 才能按缺失判否。

## 5. 缺失和口径要求

| 情况 | 处理要求 |
| --- | --- |
| `missing_policy=unknown` | 缺失就是未知，不写 false |
| `missing_policy=false_by_absence` | 缺失按不具备该特性，写入画像并标记规则来源 |
| 原始值为空、`-`、unknown | 记为 unknown 或 parse warning |
| 原始值为占位 0 且 taxonomy 排除 | 不进入参数事实，只写审计说明 |
| 同一 SKU 同一参数多值冲突 | 选主值并生成冲突记录 |
| 刷新率、亮度等营销口径参数 | 字段名使用 `declared_*`，说明是原始标称参数，不等同实测指标 |

## 6. 彩电首版参数维度

TV 首版至少包含以下参数维度。

| 维度 | 主要参数 | 用途 |
| --- | --- | --- |
| 尺寸 | `screen_size_inch` | 可比池、价格带、竞品召回 |
| 显示技术 | `display_technology_family`、`backlight_source`、`mini_led_type`、`quantum_dot_flag` | 区分 LCD/LED、MiniLED、QD-MiniLED、RGB-MiniLED、LASER、OLED |
| 分区控光 | `local_dimming_zone_count` | 表达背光分区控制能力，支撑画质层级 |
| 画质综合 | 分辨率、刷新率、亮度、色域、HDR、显示技术、分区控光 | 后续画质相关卖点和竞品召回基础 |
| 性能 | CPU/GPU、RAM、ROM、芯片 | 智能系统性能基础 |
| 智能 | AI 大模型、人工智能、语音、远场语音、摄像头、全屋智控 | 智能交互能力基础 |
| 接口 | HDMI、USB | 外设扩展和游戏设备接入基础 |
| 外观安装 | 机身厚度、全面屏、超轻薄、无缝贴墙 | 家居融合和外观形态基础 |
| 能效 | 能效等级、待机功率 | 能效事实，不作为高端结论 |

## 7. 205 当前档位覆盖基线

以下是 2026-06-20 按 205 当前 TV `293` 个 SKU 验证的首版档位覆盖。该基线用于校验规则是否符合当前数据实际；未来新批次可以重新统计覆盖，但规则变更必须走 M03A taxonomy 版本更新。

### 7.1 尺寸

| 档位 | 规则 | SKU 数 |
| --- | --- | ---: |
| `small_32_45` | `<=45` 英寸 | 26 |
| `medium_46_59` | `46-59` 英寸 | 43 |
| `large_60_69` | `60-69` 英寸 | 38 |
| `xlarge_70_85` | `70-85` 英寸 | 135 |
| `xxlarge_86_97` | `86-97` 英寸 | 0 |
| `giant_98_plus` | `>=98` 英寸 | 51 |

### 7.2 显示技术

显示技术必须分层表达：

```text
显示技术大类：LCD / OLED / LASER
背光技术：LED / MiniLED
增强类型：QLED、QD-MiniLED、RGB-MiniLED
```

当前覆盖：

| 档位 | SKU 数 |
| --- | ---: |
| `lcd_led` | 100 |
| `miniled` | 108 |
| `qd_miniled` | 68 |
| `rgb_miniled` | 14 |
| `qled_lcd` | 2 |
| `laser` | 1 |
| `oled` | 0 |

### 7.3 分区控光

`local_dimming` 来源于 `分区背光`。它表达背光能被分成多少个独立控制区域，属于画质参数，不单独决定画质高低。

| 档位 | 规则 | SKU 数 |
| --- | --- | ---: |
| `z_none_0` | `0` | 149 |
| `z_entry_1_499` | `1-499` | 38 |
| `z_mid_500_999` | `500-999` | 24 |
| `z_high_1000_1999` | `1000-1999` | 28 |
| `z_premium_2000_3999` | `2000-3999` | 36 |
| `z_flagship_4000_plus` | `>=4000` | 18 |

### 7.4 画质综合

| 档位 | SKU 数 | 说明 |
| --- | ---: | --- |
| `picture_basic` | 33 | HD/FHD、60Hz 或明显低规格 |
| `picture_mainstream` | 21 | 4K 但亮度、刷新率、控光无明显增强 |
| `picture_enhanced` | 90 | 有高刷、HDR、高色域或亮度增强，但未达到高端控光组合 |
| `picture_premium` | 110 | MiniLED/QD/RGB MiniLED，且亮度或分区有明显支撑 |
| `picture_flagship` | 39 | QD/RGB MiniLED + 高亮度 + 高分区控光组合成立 |

刷新率和亮度只作为画质综合输入，不单独决定画质总档位。字段解释使用 `declared_refresh_rate_hz`、`declared_brightness_nit_or_band`，避免误写成实测指标。

### 7.5 其他维度

| 维度 | 档位 | SKU 数 |
| --- | --- | ---: |
| 性能 | `perf_low` | 30 |
| 性能 | `perf_basic` | 51 |
| 性能 | `perf_mainstream` | 36 |
| 性能 | `perf_main_plus` | 113 |
| 性能 | `perf_high` | 56 |
| 性能 | `perf_unknown` | 7 |
| 智能 | `smart_basic` | 13 |
| 智能 | `smart_voice_ai_basic` | 110 |
| 智能 | `smart_ai_voice` | 144 |
| 智能 | `smart_interaction_iot` | 26 |
| 接口 | `ports_weak` | 30 |
| 接口 | `ports_basic` | 30 |
| 接口 | `ports_main_hdmi21` | 39 |
| 接口 | `ports_main_plus` | 85 |
| 接口 | `ports_rich` | 109 |
| 外观安装 | `appearance_standard` | 77 |
| 外观安装 | `appearance_thick` | 71 |
| 外观安装 | `appearance_wall_flush` | 35 |
| 外观安装 | `appearance_slim` | 33 |
| 外观安装 | `appearance_heavy` | 22 |
| 外观安装 | `appearance_ultra_slim` | 19 |
| 外观安装 | `appearance_slim_fullscreen` | 17 |
| 外观安装 | `appearance_unknown` | 19 |
| 能效 | `energy_grade_1` | 261 |
| 能效 | `energy_grade_2` | 30 |
| 能效 | `energy_grade_3_4` | 2 |

## 8. 下游使用要求

M03B 给下游提供的是参数事实和参数档位索引：

- M04a 可以用参数事实判断基础卖点支撑。
- M07/M12 可以用尺寸档、显示技术档、画质档、性能档、智能档辅助可比池和候选召回。
- M08 可以把参数画像与卖点、评论、市场画像合成 SKU 综合画像。
- M09-M11 可以引用参数事实，但不能直接把参数档位等同为用户任务、目标客群或价值战场结论。

## 9. 验收标准

M03B 首版验收必须满足：

1. 只处理目标品类 SKU，当前 TV 运行必须过滤掉 `AC%`。
2. 每个 TV SKU 生成一条 SKU 参数事实画像。
3. 每个 TV SKU 生成一组参数维度档位。
4. 每个参数档位生成覆盖 SKU 清单。
5. 205 当前 TV 数据的档位分布与本需求基线一致，允许只因数据批次变化产生差异。
6. 缺失规则符合 taxonomy：unknown 不判 false，特性标记字段才允许 false-by-absence。
7. 输出包含 evidence id、taxonomy version、parser version、rule version、confidence、quality flags。
8. 不读取评论、卖点、销量价格，不生成业务结论。
9. 所有测试不调用外部 LLM。
