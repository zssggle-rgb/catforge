# M11 价值战场 v2：尺寸价格池与主辅战场优化设计

## 1. 文档定位

本文是对以下详细设计的补充和修订约束：

- `M08_4_M08_5_dimension_boundary_optimization_design.md`
- `M08_6_product_anchor_evidence_layer_design.md`
- `M11_battlefield_design.md`
- `M11_6_sku_business_profile_design.md`
- `M11_7_dimension_sales_reconciliation_design.md`
- `M12_candidate_recall_design.md`

本文解决 205 真实数据运行后暴露出的两个相反问题：

1. 旧逻辑过宽：84 个 SKU 几乎都进入所有价值战场，导致战场没有区分度。
2. 新收敛逻辑过窄：每个 SKU 只进入一个主战场，解决了全覆盖问题，但丢失了“主战场 + 辅战场”的真实业务结构。

本设计目标是把价值战场从“主题标签”升级为“市场池约束下的产品价值竞争场景”。

## 2. 核心结论

价值战场不能只由画质、游戏、护眼等产品主题决定，也不能只由价格带决定。正确口径是：

```text
价值战场 = 展示用价值主张 + 内部市场池约束 + 产品锚点 + 市场验证
```

其中：

- 展示名称不写具体尺寸，例如“大屏换新性价比战场”，不叫“75/85 寸换新战场”。
- 内部规则必须使用尺寸段、同尺寸价格位置、价格/英寸、同池销量和同池参数优势。
- 小尺寸和大尺寸即使价格接近，默认也不是同一个价值战场；只有相邻尺寸段且购买任务可替代时，才允许形成相邻战场或辅战场关系。
- 一个 SKU 应有 1 个主战场，允许 0-2 个辅战场；主辅战场销量权重加总必须等于该 SKU 总销量。
- 服务履约、物流安装、售后体验不是产品价值战场，只能作为服务语境、风险或报告侧证据。

## 3. 业务定义

### 3.1 价值战场回答什么

价值战场回答：

```text
这款 SKU 在哪个购买池里被比较，靠什么产品价值赢得购买。
```

它不是：

- 用户任务：用户要完成什么事。
- 目标客群：谁在买、谁在用。
- 卖点列表：产品宣传了什么。
- 价格带：卖多少钱。
- 尺寸段：多大屏。

它必须同时具备：

| 构成 | 说明 |
| --- | --- |
| 市场池 | SKU 被消费者实际比较的尺寸段、价格位置、渠道和同池样本 |
| 产品价值主张 | 画质、流畅、换新、性价比、易用、护眼等竞争理由 |
| 产品锚点 | 参数、卖点、评论感知和可比池参数优势 |
| 市场验证 | 同池销量、销额、价格分位、增长、渠道份额 |
| 业务解释 | 能说明为什么这是主战场或辅战场 |

### 3.2 主战场、辅战场、机会战场

| 层级 | 定义 | 是否进入销量分配 | 是否进入候选召回 |
| --- | --- | --- | --- |
| 主战场 | SKU 最核心的购买池和竞争理由 | 是 | 是，最高优先级 |
| 辅战场 | 证据成立但不是第一竞争理由 | 是 | 是，次优先级 |
| 机会战场 | 有局部证据或相邻市场机会，但不够支撑销量主归因 | 默认否，可展示 | 默认否，除非人工指定 |
| 弱战场 | 只有泛评论、弱参数或规则猜测 | 否 | 否 |
| 排除战场 | 服务履约、低价值评论、无产品锚点或市场池不匹配 | 否 | 否 |

每个有效 SKU 必须有一个主战场。若证据不足，只能生成 `primary_inferred` 主战场并标记低置信和复核，不能把销量平均摊到所有战场。

## 4. 市场池设计

### 4.1 尺寸段

尺寸段用于内部计算，不出现在战场展示名称中。

| 内部尺寸段 | 建议规则 | 业务含义 |
| --- | --- | --- |
| `compact_screen` | 32/40/43 寸 | 卧室、小空间、低预算、补充屏 |
| `mainstream_living` | 50/55/65 寸 | 主流客厅、入门换新、家庭基础屏 |
| `large_upgrade` | 75/85 寸 | 客厅大屏升级、家庭观影、游戏体育 |
| `ultra_large_flagship` | 98/100 寸及以上 | 超大屏、旗舰体验、别墅/大客厅 |

相邻尺寸段可以形成替代关系，但非相邻尺寸段不能因为价格接近就进入同一战场。

### 4.2 同尺寸价格位置

价格位置必须在同尺寸段或可比池内计算，不能用全市场绝对价格直接比较。

| 字段 | 说明 |
| --- | --- |
| `same_pool_price_percentile` | 同尺寸段、同渠道可比池内价格分位 |
| `same_pool_amount_percentile` | 同池销额分位 |
| `same_pool_volume_percentile` | 同池销量分位 |
| `price_per_inch_percentile` | 同尺寸段内价格/英寸分位 |
| `price_gap_to_pool_median` | 相对同池中位价差 |
| `config_value_index` | 同池参数强度 / 价格位置 |

价格位置枚举建议：

| 价格位置 | 同池价格分位 |
| --- | --- |
| `entry` | 0-20% |
| `value` | 20-40% |
| `mainstream` | 40-65% |
| `upper_mainstream` | 65-80% |
| `premium` | 80-95% |
| `flagship` | 95%+ |

### 4.3 市场池 key

M07/M08 应输出稳定市场池 key：

```text
market_pool_key =
  category_code
  + screen_size_class
  + channel_group
  + analysis_window
```

价格位置是 market pool 内的属性，不应写入 key。原因是同一战场需要比较同池不同价格层级的 SKU。

## 5. 价值战场 v2 预设

战场名称不写具体尺寸；尺寸和价格只写在定义和入场规则中。

| v2 code | 展示名称 | 适用市场池 | 产品锚点 | 价格/市场约束 |
| --- | --- | --- | --- | --- |
| `BF_ENTRY_ESSENTIAL_VALUE` | 入门刚需普及战场 | 小空间、主流客厅低价池 | 基础画质、基础智能、尺寸适配 | 同池价格 `entry/value`，销量验证优先 |
| `BF_MAINSTREAM_LIVING_UPGRADE` | 主流客厅换新战场 | 主流客厅、相邻大屏升级池 | 尺寸、画质、系统、家庭观影基础体验 | 同池价格 `mainstream/value`，销量或销额不低 |
| `BF_LARGE_SCREEN_VALUE_UPGRADE` | 大屏换新性价比战场 | 大屏升级池 | 大尺寸、价格/英寸、关键配置、国补/促销价值 | 同池价格/英寸低或配置价值指数高 |
| `BF_PREMIUM_PICTURE_UPGRADE` | 高端画质升级战场 | 主流客厅高价池、大屏高价池、超大屏池 | Mini LED/OLED/QLED、分区控光、亮度、色域、HDR、画质芯片 | 同池价格 `upper_mainstream/premium/flagship`，销额或高端参数验证 |
| `BF_PREMIUM_VALUE_DOWNTRADE` | 高端下探价值战场 | 大屏升级池、高端画质相邻池 | 高端画质锚点 + 低于同配置/同池高端价格 | 同池价格低于高端竞品，配置价值指数高 |
| `BF_GAMING_SPORTS_FLUENCY` | 游戏体育流畅战场 | 主流客厅、大屏升级池 | 高刷、HDMI2.1、VRR、ALLM、MEMC、低延迟、运动补偿 | 参数锚点必须成立，评论只做验证 |
| `BF_FAMILY_VIEWING_COMFORT` | 家庭观影舒适战场 | 主流客厅、大屏升级池 | 尺寸、画质、音效、系统稳定、多人观看体验 | 家庭观影任务或评论验证，不能只靠“大屏” |
| `BF_ULTRA_LARGE_FLAGSHIP_EXPERIENCE` | 超大屏旗舰体验战场 | 超大屏池、大屏高端相邻池 | 超大尺寸、旗舰画质、音画沉浸、空间适配 | 同池价格和销额高，旗舰属性明确 |
| `BF_SMART_EASE_EXPERIENCE` | 智能交互易用战场 | 小空间、主流客厅、长辈/家庭相关池 | 语音、遥控、系统、内存、开机广告、投屏 | 必须有交互/系统锚点，不能只因“长辈”成立 |
| `BF_EYE_CARE_COMFORT_VIEWING` | 护眼舒适观看战场 | 主流客厅、小空间、儿童/长期观看相关池 | 低蓝光、无频闪、护眼认证、环境光、儿童模式 | 必须有护眼参数或卖点锚点 |

### 5.1 从旧战场到 v2 的迁移

| 旧 code | 处理 |
| --- | --- |
| `BF_LARGE_SCREEN_VALUE` | 拆成 `BF_LARGE_SCREEN_VALUE_UPGRADE`，并按尺寸池过滤；小屏低价不再进入大屏战场 |
| `BF_PREMIUM_PICTURE` | 升级为 `BF_PREMIUM_PICTURE_UPGRADE`，必须看同池价格位置和高端参数 |
| `BF_GAMING_SPORTS` | 升级为 `BF_GAMING_SPORTS_FLUENCY`，必须有高刷/低延迟/运动补偿等参数 |
| `BF_FAMILY_VIEWING_UPGRADE` | 升级为 `BF_FAMILY_VIEWING_COMFORT`，不再只因家庭评论或大屏成立 |
| `BF_FAMILY_EYE_CARE` | 升级为 `BF_EYE_CARE_COMFORT_VIEWING` |
| `BF_SENIOR_EASE_OF_USE` | 不再作为人群战场，合并到 `BF_SMART_EASE_EXPERIENCE`，长辈是客群证据 |
| `BF_SMART_SYSTEM_EXPERIENCE` | 合并到 `BF_SMART_EASE_EXPERIENCE` |
| `BF_CINEMA_AUDIO_IMMERSION` | 当前数据不足时作为 `BF_FAMILY_VIEWING_COMFORT` 或 `BF_ULTRA_LARGE_FLAGSHIP_EXPERIENCE` 的音效锚点；未来音效证据充分可单独恢复 |
| `BF_DESIGN_HOME_FIT` | 当前作为空间适配/装修语境，不作为核心产品战场；未来外观参数和评论充足可独立恢复 |
| `BF_SERVICE_ASSURANCE` | 移出产品战场，改为 `service_context`，不参与 M11.6 产品战场销量分配 |

## 6. M08/M07/M03 需要补充的上游字段

### 6.1 M07 市场画像补充

| 字段 | 用途 |
| --- | --- |
| `screen_size_class` | 内部尺寸段 |
| `market_pool_key` | 同尺寸段、同渠道、同窗口比较池 |
| `same_pool_price_percentile` | 同池价格位置 |
| `same_pool_volume_percentile` | 同池销量位置 |
| `same_pool_amount_percentile` | 同池销额位置 |
| `price_per_inch` | 价格/英寸 |
| `price_per_inch_percentile` | 同池价格/英寸位置 |
| `adjacent_size_pool_keys_json` | 可替代相邻尺寸池 |

### 6.2 M03/M08 产品锚点补充

| 字段 | 用途 |
| --- | --- |
| `display_anchor_json` | 亮度、分区、背光、色域、HDR、画质芯片等 |
| `motion_anchor_json` | 刷新率、MEMC、VRR、HDMI2.1、低延迟 |
| `audio_anchor_json` | 扬声器功率、声道、杜比、DTS |
| `eye_care_anchor_json` | 低蓝光、无频闪、护眼认证、儿童模式 |
| `smart_anchor_json` | 语音、内存、存储、系统、投屏、广告风险 |
| `space_anchor_json` | 厚度、边框、挂装、底座、外观、艺术模式 |
| `config_value_index` | 同池配置强度 / 价格位置 |

M03 参数稳定化仍是前提。若原始字段名不标准，必须通过 M03 参数映射后再进入这些 anchor json。

## 7. M11 战场评分 v2

### 7.1 评分结构

M11 对每个 SKU 和每个 v2 战场计算：

```text
battlefield_score_v2 =
  market_pool_fit_score * 0.25
  + product_anchor_score * 0.30
  + value_theme_score * 0.15
  + task_group_fit_score * 0.10
  + comment_validation_score * 0.10
  + market_performance_score * 0.10
```

其中：

| 分项 | 说明 |
| --- | --- |
| `market_pool_fit_score` | 尺寸段、相邻尺寸可替代性、同池价格位置是否适合该战场 |
| `product_anchor_score` | 参数、卖点、配置价值指数是否支撑战场 |
| `value_theme_score` | 画质、游戏、换新、护眼、易用等价值主题匹配 |
| `task_group_fit_score` | M09 主/次任务和 M10 主/次客群是否支持该战场 |
| `comment_validation_score` | 去重后评论是否能验证用户感知 |
| `market_performance_score` | 同池销量、销额、增长、价格接受度 |

### 7.2 市场池适配规则

| 规则 | 处理 |
| --- | --- |
| 同尺寸段 | `market_pool_fit_score` 可高分 |
| 相邻尺寸段且任务可替代 | 最高 `0.65`，可作为辅战场或机会战场 |
| 非相邻尺寸段 | 最高 `0.30`，不得作为主战场 |
| 同价格但尺寸差距大 | 不自动同战场 |
| 小屏低价 | 不进入“大屏换新性价比战场”，优先进入“入门刚需普及战场” |
| 大屏高配低价 | 可进入“大屏换新性价比”或“高端下探价值” |

### 7.3 关系等级

| relation_level | 条件 |
| --- | --- |
| `main` | 得分最高，`battlefield_score_v2 >= 0.55`，且 `market_pool_fit_score >= 0.50`、`product_anchor_score >= 0.30` |
| `secondary` | 得分接近主战场，`battlefield_score_v2 >= 0.45`，且与主战场分差不超过 0.18 |
| `opportunity` | 有局部证据，`battlefield_score_v2 >= 0.35`，但池适配或产品锚点不足 |
| `weak` | 有弱信号但不足以进入画像和销量分配 |
| `excluded` | 服务、泛化评论、池不匹配或无产品锚点 |

每个 SKU 最多：

- 1 个 `main`
- 2 个 `secondary`
- 3 个 `opportunity`

如果所有战场得分都低，仍选择最高者作为 `main_inferred`，但必须：

- `confidence_level='low'`
- `allocation_confidence <= 0.45`
- 生成 `battlefield_primary_inferred_review` 复核问题

## 8. M11.6 主辅战场销量分配 v2

### 8.1 准入集合

M11.6 战场销量分配只消费：

```text
relation_level in ('main', 'secondary')
and allocation_eligible = true
and service_context = false
```

`opportunity` 默认不参与销量分配，只进入报告候选或人工复核。

### 8.2 分配权重

对每个 SKU：

```text
raw_allocation_score =
  battlefield_score_v2
  * relation_factor
  * allocation_confidence
```

建议 relation_factor：

| relation_level | factor |
| --- | ---: |
| `main` | 1.00 |
| `secondary` | 0.70 |
| `opportunity` | 0.00 |
| `weak` | 0.00 |

归一化后应用主战场保护：

```text
primary_weight >= 0.50
secondary_weight_total <= 0.50
single_secondary_weight <= 0.35
sum(all battlefield weights per sku) = 1.0
```

如果只有主战场：

```text
primary_weight = 1.0
```

如果有 1-2 个辅战场：

```text
primary_weight = max(0.50, normalized_primary)
remaining_weight = 1 - primary_weight
secondary_weights = normalize(secondary_raw_scores) * remaining_weight
```

### 8.3 高端下探和降级进入战场

“高端降级进入性价比战场”应改成更准确的业务口径：`高端下探价值战场`。

成立条件：

1. 有高端产品锚点：画质、背光、亮度、刷新率、音画等至少一个强锚点成立。
2. 同池价格低于高端竞品或同配置均价。
3. 配置价值指数高于同池中位。
4. 销量或评论能验证“值、划算、配置高”。

它可以是：

- 主战场：销量主要由高配低价驱动。
- 辅战场：主战场是高端画质，但价格下探也有贡献。
- 机会战场：只有配置优势但市场验证不足。

## 9. M11.7 对账 v2

M11.7 不调整权重，只校验。

### 9.1 正确对账口径

以价值战场为例：

```text
sum(primary_sku_count across battlefields) = effective_sku_count
sum(sku_count across battlefields) >= effective_sku_count
sum(sku_count across battlefields) <= effective_sku_count * 3

for each sku:
  sum(battlefield allocation_weight) = 1
  sum(battlefield allocated_sales_volume) = sku.sales_volume_total
  sum(battlefield allocated_sales_amount) = sku.sales_amount_total

for all battlefields:
  sum(estimated_sales_volume) = total_sku_sales_volume
  sum(estimated_sales_amount) = total_sku_sales_amount
```

说明：

- `primary_sku_count` 是主战场 SKU 数，加总必须等于 SKU 总数。
- `sku_count` 是主战场 + 辅战场覆盖 SKU 数，加总可以大于 SKU 总数。
- 当前“每个 SKU 只进一个战场”能数学平账，但业务上过窄，应触发稀疏性提醒。
- 旧“每个 SKU 进全部战场”虽然也可能数学平账，但业务上过宽，应触发过宽阻断。

### 9.2 业务稀疏性检查

新增检查：

| check_type | 规则 | 级别 |
| --- | --- | --- |
| `battlefield_all_sku_all_battlefield` | 平均每 SKU 命中战场数 > 3 | blocking |
| `battlefield_too_narrow` | 平均每 SKU 命中战场数 = 1 且辅战场数占比 < 15% | warning |
| `battlefield_primary_missing` | 某 SKU 没有主战场 | blocking |
| `battlefield_primary_duplicate` | 某 SKU 超过 1 个主战场 | blocking |
| `battlefield_service_allocated` | 服务语境进入产品战场分配 | blocking |
| `battlefield_pool_mismatch` | 非相邻尺寸池却作为主/辅战场 | blocking |

## 10. 对 M12 候选召回的影响

M12 召回应使用主辅战场区别：

| 来源 | 召回权重 |
| --- | ---: |
| 同主战场 + 同市场池 | 最高 |
| 同主战场 + 相邻市场池 | 高 |
| 目标主战场 = 候选辅战场 | 中 |
| 目标辅战场 = 候选主战场 | 中 |
| 只有机会战场重合 | 低，只进扩展候选 |
| 战场不同但同市场池 | 可作为价格替代候选 |

候选召回不能只看 `battlefield_code`，还必须看：

- `market_pool_key`
- `screen_size_class`
- `same_pool_price_percentile`
- `price_per_inch_percentile`
- `battlefield_allocation_weight`

## 11. API 和前端展示

### 11.1 SKU 详情页

展示：

| 内容 | 说明 |
| --- | --- |
| 主战场 | 名称、权重、证据强度、市场池说明 |
| 辅战场 | 名称、权重、为什么成立 |
| 机会战场 | 不参与销量分配，但提示潜在竞争机会 |
| 不进入战场 | 关键排除原因，例如“只有服务评论”“尺寸池不匹配” |

页面用业务语言：

```text
该 SKU 的主战场是大屏换新性价比，主要因为它处在大屏升级池，价格/英寸低于同池中位，同时销量验证较强。
高端下探价值是辅战场，因为它具备部分高端画质锚点，但高端参数证据不如高端画质主战场 SKU 完整。
```

### 11.2 价值战场市场结构页

展示：

- 每个战场涉及多少 SKU。
- 主战场 SKU 数。
- 主 + 辅覆盖 SKU 数。
- 估算销量和销额占比。
- Top SKU 贡献。
- 尺寸段分布。
- 价格位置分布。
- 是否存在过宽/过窄提醒。

## 12. 开发任务拆分建议

后续开发不应一次改完全部链路，建议按以下顺序：

1. M07/M08 市场池字段补充：尺寸段、同池价格分位、价格/英寸、配置价值指数。
2. M08.6 产品锚点补充：把参数、卖点、评论和同池优势生成统一 anchor index。
3. M08.5 战场本体 v2：发布 v2 价值战场定义和迁移映射。
4. M11 战场评分 v2：加入市场池适配和 v2 relation_level。
5. M11.6 主辅战场分配 v2：允许 1 主 + 0-2 辅，并保证 SKU 内销量守恒。
6. M11.7 对账 v2：新增过宽、过窄、服务误入、市场池不匹配检查。
7. M12 候选召回 v2：候选召回同时使用战场和市场池。
8. FRONTEND 展示：展示主辅战场、权重、市场池解释和排除原因。

每完成一项，都需要在 205 或本地真实样例上运行并输出：

- 战场覆盖 SKU 数。
- 平均每 SKU 战场数。
- 主/辅战场比例。
- 战场销量守恒。
- SKU 销量守恒。
- 典型 SKU 解释是否符合业务直觉。

## 13. 验收标准

### 13.1 数据验收

| 项 | 标准 |
| --- | --- |
| 主战场 | 每个有效 SKU 正好 1 个主战场 |
| 辅战场 | 允许 0-2 个，不强制 |
| 平均战场数 | 大于 1 且不超过 3；若等于 1 需要 warning |
| 产品战场 | 不包含服务履约 |
| 市场池 | 主/辅战场必须有尺寸段和同池价格位置解释 |
| 销量守恒 | SKU 内战场权重和等于 1 |
| 全局守恒 | 所有战场估算销量等于全量 SKU 销量 |

### 13.2 业务验收

| 场景 | 预期 |
| --- | --- |
| 小屏低价 SKU | 不能因为价格低进入大屏换新性价比战场 |
| 大屏低价 SKU | 可进入大屏换新性价比战场 |
| 高端参数 + 中低价格 SKU | 可进入高端下探价值战场 |
| 高端参数 + 高价格 SKU | 可进入高端画质升级战场 |
| 游戏参数强 SKU | 可进入游戏体育流畅战场 |
| 只有安装服务评论 SKU | 不进入产品价值战场，只进入服务语境 |
| 只有泛化好评 SKU | 不支撑正式主/辅战场 |

### 13.3 当前 205 样例验收

以当前 84 个有效 SKU 为例，v2 运行后预期不是固定数量，但必须满足：

1. 不再出现 84 个 SKU 全部命中所有战场。
2. 不应长期停留在每个 SKU 只命中一个战场。
3. 大屏换新性价比战场不应混入明显小屏刚需 SKU。
4. 高端画质和高端下探价值应能区分：前者看高端能力和高价位，后者看高端能力与相对低价。
5. 战场销量、SKU 销量、战场内 SKU 贡献三者能交叉对齐。

