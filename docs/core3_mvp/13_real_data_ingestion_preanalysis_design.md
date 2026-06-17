# 13 真实样例数据接入、清洗与预分析详细设计

> 状态：第一版草案，已被 [真实数据版 Core3 MVP v2 设计包](real_data_v2/README.md) 取代。
>
> 保留本文用于追溯早期讨论。后续实现 205 真实样例表接入、清洗落表、语义抽取、资产候选、SKU 画像和增量任务时，以 `docs/core3_mvp/real_data_v2/` 为准。

## 1. 背景与目标

205 上已经有一批真实样例数据，当前落在 4 张独立表中：

- `week_sales_data`：周销、销售额、均价、渠道平台。
- `attribute_data`：型号参数和属性。
- `selling_points_data`：结构化卖点。
- `comment_data`：评论原文、评论分段、情感、一级/二级/三级维度。

现有 Core3 MVP 链路消费的是 `raw_sku_master`、`raw_market_fact`、`raw_sku_param`、`raw_sku_claim`、`raw_sku_comment`。这 4 张真实样例表不在现有标准导入链里，因此页面仍然基于旧 sample 数据。

本设计目标是在不推翻现有 Core3 pipeline 的前提下，增加一层真实样例数据接入、清洗和预分析能力，让 MVP 可以基于真实样例数据生成竞品报告。

竞品口径调整为：不区分内部品牌和外部品牌，凡是抢同一用户任务、同尺寸或相邻尺寸、同价位或形成价格/销量压力、价值战场重合的型号，均可作为竞品。海信型号也可以成为海信型号的竞品。

## 2. 设计原则

1. 原始表不改写：`week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data` 保持数据团队写入结果，不在业务链路中更新或删除。
2. 清洗结果可复算：清洗和预分析产物由输入表重新计算，支持幂等重跑。
3. 缺失就是未知：`-`、空串、空值、`未知` 等不代表 false，不参与负向判断。
4. 证据优先：每个参数、卖点、评论主题、战场和竞品结论都要能追溯到真实表行或聚合证据。
5. 不硬凑竞品：如果某个槽位没有达到证据门槛，可以展示“暂未命中”，但当前 35 个型号内仍要提供候选池排序供业务判断。
6. 现有链路复用：保留 `Core3InputBundle -> market_profile -> extraction -> semantic_profile -> competitor_engine -> report` 主链路，只在前面增加真实数据适配层。
7. 页面业务化：页面展示“销量、价格、参数、评论、战场、竞品理由”，不展示数据库字段名、UUID、内部 source_type。

## 3. 总体架构

### 3.1 当前链路

```text
raw_sku_master
raw_market_fact
raw_sku_param
raw_sku_claim
raw_sku_comment
  -> load_project_input
  -> market_profile
  -> extraction
  -> semantic_profile
  -> competitor_engine
  -> report_service
  -> Core3 页面
```

### 3.2 新链路

```text
week_sales_data
attribute_data
selling_points_data
comment_data
  -> real_data_access
  -> real_data_cleaning
  -> real_data_preanalysis
  -> RealCore3InputBundleAdapter
  -> market_profile / extraction / semantic_profile
  -> competitor_engine
  -> report_service
  -> 真实数据版 Core3 页面
```

### 3.3 模块划分

新增模块建议：

```text
apps/api-server/app/services/core3_mvp/
  real_data_access.py
  real_data_cleaning.py
  real_data_preanalysis.py
  real_data_adapter.py
  real_data_quality.py
```

职责：

- `real_data_access.py`：只负责读取真实表，返回 typed rows。
- `real_data_cleaning.py`：只负责字段清洗、去重、单位解析、无效评论过滤。
- `real_data_preanalysis.py`：生成 SKU 画像、评论画像、卖点画像、战场输入。
- `real_data_adapter.py`：把真实数据画像投影成现有 `Core3InputBundle` 或等价输入。
- `real_data_quality.py`：输出数据质量摘要，供页面展示和任务门槛判断。

不建议把所有逻辑塞进 `data_access.py`，避免把旧 sample 链路和真实数据链路混在一起。

## 4. 数据源与字段设计

### 4.1 `week_sales_data`

字段：

| 字段 | 含义 | 清洗处理 |
| --- | --- | --- |
| `model_code` | 型号编码 | 作为 SKU code |
| `category` | 类目 | `彩电` 映射到 `TV` |
| `brand` | 品牌 | 原样保留 |
| `model` | 型号名称 | 映射到 `model_name` |
| `date_value` | 周期，如 `26W23` | 解析为年周序，用于排序 |
| `channel` | 渠道，如 `线上` | 渠道大类 |
| `platform` | 平台，如 `专业电商` | 渠道细分 |
| `sales_volume` | 销量 | 非负校验 |
| `sales_amount` | 销售额 | 非负校验 |
| `avg_price` | 均价 | 与 `sales_amount / sales_volume` 交叉校验 |
| `write_time` | 写入时间 | 用于选择最新批次 |

业务产物：

- 23 周销量和销售额。
- 加权均价。
- 最新周均价。
- 价格趋势。
- 销量趋势。
- 渠道平台占比。
- 价格分位、销量分位、销售额分位。

### 4.2 `attribute_data`

字段：

| 字段 | 含义 | 清洗处理 |
| --- | --- | --- |
| `model_code` | 型号编码 | SKU code |
| `category` | 类目 | `彩电` -> `TV` |
| `brand` | 品牌 | 原样保留 |
| `model` | 型号名称 | 映射到 `model_name` |
| `attr_name` | 原始参数名 | 归一到标准参数 code |
| `attr_value` | 原始参数值 | 清洗、解析、单位归一 |
| `write_time` | 写入时间 | 选择最新批次 |

关键映射：

| `attr_name` | 标准参数 | 示例 |
| --- | --- | --- |
| `尺寸` | `screen_size_inch` | `85` |
| `尺寸段` | `screen_size_segment` | `>=70` |
| `分辨率` | `resolution_raw` | `3840×2160` |
| `清晰度2` | `resolution_class` | `4K` |
| `亮度` | `peak_brightness_nits` | `5200` |
| `屏幕刷新率` | `system_refresh_rate_hz` | `300HZ` |
| `分区背光` | `dimming_zone_count` | `3500` |
| `MINILED` | `mini_led` | `是` |
| `HDR` | `hdr_support` | `HDR` |
| `HDMI参数` | `hdmi_spec` | `HDMI2.1` |
| `HDMI数量` | `hdmi_port_count` | `4` |
| `RAM内存` | `ram_gb` | `4GB` |
| `ROM容量` | `rom_gb` | `64GB` |
| `AI大模型` | `ai_model_name` | `海信星海` |
| `远场语音` | `far_field_voice` | `远场语音` |
| `能效等级` | `energy_efficiency_level` | `一级` |
| `背光源细分` | `backlight_subtype` | `U-LED` |

不参与首版核心分析的参数仍保留在 `raw_attributes`，后续可映射。

### 4.3 `selling_points_data`

字段：

| 字段 | 含义 | 清洗处理 |
| --- | --- | --- |
| `model_code` | 型号编码 | SKU code |
| `variable` | 卖点序号 | 保留排序 |
| `selling_point` | 卖点文本 | 分句、关键词匹配 |
| `write_time` | 写入时间 | 选择最新批次 |

当前覆盖 5 个型号，不覆盖 `85E7Q`。因此设计上卖点分两类：

- 结构化卖点：来自 `selling_points_data`。
- 推导卖点：来自参数和评论，例如高亮、MiniLED、高刷、服务安装、智能语音。

页面必须展示卖点来源：

- `结构化卖点`
- `参数推导`
- `评论印证`
- `参数推导 + 评论印证`

### 4.4 `comment_data`

字段：

| 字段 | 含义 | 清洗处理 |
| --- | --- | --- |
| `platform` | 评论平台 | 京东/天猫 |
| `model_code` | 型号编码 | SKU code |
| `url_id` | 商品链接标识 | 证据引用 |
| `comment_id` | 评论 ID | 去重主键之一 |
| `comment_content` | 评论原文 | 过滤空评/默认评 |
| `comment_time` | 评论时间 | 用于新近程度 |
| `primary_dim` | 一级维度 | 直接用于业务维度 |
| `secondary_dim` | 二级维度 | 直接用于业务维度 |
| `third_dim` | 三级维度 | 直接用于细项 |
| `comments_segments` | 评论分段 | 优先作为主题证据 |
| `sentiment` | 情感 | 正面/中立/负面 |
| `write_time` | 写入时间 | 选择最新批次 |

评论清洗规则：

1. 按 `platform + model_code + comment_id + comment_content` 去重，避免同一评论因多维度标签拆成多行后重复统计声量。
2. 对维度统计保留拆分行，因为同一评论可同时命中安装、物流、画质等多个维度。
3. `此用户未填写评价内容`、`此用户没有填写评价`、空白评论，不进入战场和卖点推导。
4. 情感为空时不参与正负向占比，但可以作为原始声量记录。
5. 优先使用 `comments_segments`，为空时才从 `comment_content` 切句。

## 5. 批次选择与项目绑定

真实表缺少 `project_id`，因此需要明确绑定策略。

### 5.1 默认绑定

首版规则：

- `category='彩电'` 绑定到 `category_code='TV'` 的 Core3 MVP 项目。
- 如果只有一个 TV 项目，自动绑定。
- 如果有多个 TV 项目，使用项目配置指定。

建议新增配置：

```json
{
  "project_id": "d8d2245b-358b-4a64-95cc-9d7f2341bd26",
  "source_mode": "real_sample_v1",
  "category_mapping": {
    "彩电": "TV"
  },
  "target_model_default": "85E7Q"
}
```

### 5.2 批次选择

每张表按最新 `write_time` 选择当前批次：

- `week_sales_data` 最新批次。
- `attribute_data` 最新批次。
- `selling_points_data` 最新批次。
- `comment_data` 最新批次。

如果后续数据追加而不是整批覆盖，则需要支持两种模式：

- `latest_batch`：只使用最新 `write_time`。
- `all_current`：使用表中全部数据。

首版建议用 `all_current`，同时在数据质量摘要中展示每张表的 `min_write_time` 和 `max_write_time`。

## 6. 清洗与标准化详细设计

### 6.1 通用未知值规则

以下值统一视为 unknown：

```text
null
""
"-"
"--"
"未知"
"无"
"N/A"
"na"
"none"
"null"
```

unknown 不等于 false。例如 `量子点 = "-"` 只能表示未知/缺失，不表示“不支持量子点”。

### 6.2 周销清洗

输入主键：

```text
model_code + date_value + channel + platform
```

处理：

1. 去掉空 `model_code`。
2. 校验 `sales_volume >= 0`。
3. 校验 `sales_amount >= 0`。
4. 校验 `avg_price >= 0`。
5. 如果同主键多行，聚合：
   - `sales_volume=sum`
   - `sales_amount=sum`
   - `avg_price=sales_amount/sales_volume`
6. 周期排序：
   - `26W01` -> `2026-W01`
   - 当前样例只需按字符串后两位周序排序，后续可扩展自然年。

输出 `CleanMarketRow`：

```python
class CleanMarketRow:
    sku_code: str
    brand: str
    model_name: str
    category_code: str
    period: str
    period_order: int
    channel_group: str
    channel_name: str
    sales_volume: float
    sales_amount: float
    avg_price: float
    source_ref: dict
```

### 6.3 参数清洗

输入主键：

```text
model_code + attr_name
```

处理：

1. 过滤空 `model_code`、空 `attr_name`。
2. 统一全角半角。
3. `attr_value` unknown 则保留为缺失，不生成标准参数值。
4. 映射 `attr_name` 到 `param_code`。
5. 按 parser 解析值。
6. 无法解析但有业务意义的枚举值，保留原值。

输出 `CleanParamRow`：

```python
class CleanParamRow:
    sku_code: str
    raw_param_name: str
    raw_param_value: str
    param_code: str | None
    normalized_value: str | float | bool | None
    unit: str | None
    confidence: float
    parse_status: Literal["parsed", "unknown_value", "unmapped_param", "parse_failed"]
    source_ref: dict
```

### 6.4 卖点清洗

处理：

1. 保留 `variable` 排序。
2. 对 `selling_point` 分句。
3. 匹配现有 claim seed。
4. 提取数值能力，例如高刷、MiniLED、抗反光、AI 画质芯片。
5. 对未映射但高频短语进入候选卖点。

输出 `CleanClaimSentence`：

```python
class CleanClaimSentence:
    sku_code: str
    variable: str
    sentence: str
    matched_claim_codes: list[str]
    extracted_param_hints: list[dict]
    source_ref: dict
```

### 6.5 评论清洗

需要同时生成两类结果：

1. 去重后的评论原声，用于有效评论数、代表性评论。
2. 评论维度明细，用于维度热度和战场推导。

输出 `CleanCommentReview`：

```python
class CleanCommentReview:
    sku_code: str
    platform: str
    comment_id: str
    comment_content: str
    comment_time: datetime | None
    sentiment: Literal["positive", "neutral", "negative", "unknown"]
    is_valid_text: bool
    source_ref: dict
```

输出 `CleanCommentTopicSignal`：

```python
class CleanCommentTopicSignal:
    sku_code: str
    comment_key: str
    primary_dim: str | None
    secondary_dim: str | None
    third_dim: str | None
    segment: str
    sentiment: str
    mapped_topic_code: str | None
    source_ref: dict
```

## 7. 预分析产物设计

预分析不直接给最终竞品结论，而是生成可复用画像。

### 7.1 数据质量摘要

输出 `RealDataQualitySummary`：

```json
{
  "source_mode": "real_sample_v1",
  "sku_count": 35,
  "brand_count": 1,
  "market": {
    "row_count": 1326,
    "sku_count": 35,
    "period_range": ["26W01", "26W23"],
    "duplicate_key_count": 0,
    "bad_numeric_count": 0
  },
  "attribute": {
    "row_count": 2843,
    "sku_count": 35,
    "attr_name_count": 84,
    "unknown_value_count": 961,
    "core_param_coverage": 1.0
  },
  "selling_point": {
    "row_count": 65,
    "sku_count": 5,
    "coverage_status": "partial"
  },
  "comment": {
    "row_count": 62426,
    "sku_count": 33,
    "dedup_comment_count": 34438,
    "empty_or_default_count": 15417,
    "valid_comment_count": 19021
  },
  "warnings": [
    "当前品牌只有海信，竞品为同品牌竞争型号。",
    "卖点仅覆盖 5 个型号，缺失型号使用参数和评论推导卖点。"
  ]
}
```

### 7.2 SKU 市场画像

输出 `RealSkuMarketProfile`：

```json
{
  "sku_code": "TV00029115",
  "brand": "海信",
  "model_name": "85E7Q",
  "size_inch": 85,
  "sales_volume_total": 20561,
  "sales_amount_total": 192848975.65,
  "price_wavg": 9380.31,
  "avg_price_mean": 9583.89,
  "latest_week": "26W23",
  "latest_price": 0,
  "channel_share": {
    "线上/专业电商": 0.75,
    "线上/平台电商": 0.25
  },
  "price_band": "9000-10000",
  "sales_rank": 4,
  "amount_rank": 4,
  "price_percentile": 0.8
}
```

说明：具体值以实现计算为准，设计中只定义字段。

### 7.3 SKU 参数画像

输出 `RealSkuParamProfile`：

```json
{
  "sku_code": "TV00029115",
  "core_params": {
    "screen_size_inch": {"value": 85, "unit": "inch"},
    "resolution_class": {"value": "4K"},
    "peak_brightness_nits": {"value": 5200, "unit": "nits"},
    "system_refresh_rate_hz": {"value": 300, "unit": "Hz"},
    "dimming_zone_count": {"value": 3500},
    "mini_led": {"value": true},
    "hdmi_spec": {"value": "HDMI2.1"},
    "hdmi_port_count": {"value": 4},
    "ram_gb": {"value": 4, "unit": "GB"},
    "rom_gb": {"value": 64, "unit": "GB"}
  },
  "strong_points": [
    "5200 尼特高亮",
    "3500 分区背光",
    "300Hz 高刷",
    "HDMI2.1"
  ],
  "missing_params": []
}
```

### 7.4 SKU 卖点画像

输出 `RealSkuClaimProfile`：

```json
{
  "sku_code": "TV00029115",
  "structured_claims": [],
  "derived_claims": [
    {
      "claim_code": "CLAIM_HIGH_BRIGHTNESS_HDR",
      "claim_name": "高亮 HDR",
      "source": "param",
      "score": 0.95,
      "evidence": ["亮度 5200", "HDR"]
    },
    {
      "claim_code": "CLAIM_HIGH_REFRESH_GAMING",
      "claim_name": "游戏高刷",
      "source": "param+comment",
      "score": 0.92,
      "evidence": ["屏幕刷新率 300Hz", "HDMI2.1"]
    }
  ],
  "claim_source_status": "derived_without_structured_selling_points"
}
```

### 7.5 SKU 评论画像

输出 `RealSkuCommentProfile`：

```json
{
  "sku_code": "TV00029115",
  "raw_rows": 3621,
  "dedup_comments": 1648,
  "empty_or_default_rows": 492,
  "valid_signal_rows": 3129,
  "sentiment": {
    "positive": 2902,
    "neutral": 153,
    "negative": 61,
    "unknown": 505
  },
  "top_positive_dimensions": [
    {"dimension": "送装维保/安装服务", "count": 1000},
    {"dimension": "送装维保/物流配送", "count": 500},
    {"dimension": "产品质量/显示画质", "count": 300}
  ],
  "top_negative_dimensions": [
    {"dimension": "营销服务/产品价格", "count": 20},
    {"dimension": "送装维保/售后维保", "count": 15}
  ],
  "representative_comments": [
    {
      "sentiment": "positive",
      "dimension": "送装维保/安装服务",
      "text": "京东服务细致到位，送拆装取一体高效快速，师傅技术好，非常满意！"
    }
  ]
}
```

### 7.6 价值战场画像

首版战场仍复用 seed 中已有战场，但激活信号来自真实画像。

建议战场：

| 战场 | 主要数据来源 | 激活信号 |
| --- | --- | --- |
| 高亮画质战场 | 参数 + 评论 | 亮度、分区背光、MiniLED、显示画质评论 |
| 游戏高刷战场 | 参数 + 评论 | 刷新率、HDMI2.1、游戏/流畅评论 |
| 大屏客厅战场 | 参数 + 市场 | 尺寸、价格带、销量 |
| 服务安装战场 | 评论 | 安装服务、物流配送、客服服务 |
| 价格性价比战场 | 市场 + 评论 | 价格分位、销量强度、价格评论 |
| 智能交互战场 | 参数 + 评论 | AI 大模型、远场语音、系统/交互评论 |

输出 `RealSkuBattlefieldProfile`：

```json
{
  "sku_code": "TV00029115",
  "battlefields": [
    {
      "battlefield_code": "BF_PREMIUM_PICTURE",
      "battlefield_name": "高亮画质战场",
      "score": 0.94,
      "rank": 1,
      "evidence": ["亮度 5200", "分区背光 3500", "显示画质正向评论"]
    },
    {
      "battlefield_code": "BF_SERVICE_ASSURANCE",
      "battlefield_name": "服务安装战场",
      "score": 0.90,
      "rank": 2,
      "evidence": ["安装服务正向评论", "物流配送正向评论"]
    }
  ]
}
```

## 8. 竞品推导详细设计

### 8.1 候选池范围

候选池默认使用当前真实数据内全部可分析 SKU：

```text
all_skus - target_sku
```

不按品牌排除。当前样例中都是海信，因此输出为海信内部竞争型号，但页面统一称为竞品。

### 8.2 硬过滤

硬过滤只排除明显不可比对象：

1. 类目不同。
2. 缺少市场画像且缺少参数画像。
3. 尺寸完全不可比且无价格/任务重合。例如 50 寸与 100 寸默认不可比，除非价格或战场强相关。

首版尺寸可比规则：

- 同尺寸：强可比。
- 相邻尺寸：75/85/100 互为上探或下探。
- 55/65/75 可作为中低尺寸段可比。
- 50 与 85 默认弱可比。

### 8.3 组件分

每个候选计算以下组件：

| 组件 | 含义 | 数据来源 |
| --- | --- | --- |
| `size_similarity` | 尺寸相似 | 参数 |
| `price_similarity` | 价格接近 | 市场 |
| `price_pressure` | 低价挤压 | 市场 |
| `sales_strength` | 销量/销额强势 | 市场 |
| `param_similarity` | 参数相似 | 参数 |
| `param_superiority` | 参数更强 | 参数 |
| `battlefield_similarity` | 战场重合 | 战场画像 |
| `comment_topic_similarity` | 评论关注点相似 | 评论画像 |
| `claim_similarity` | 卖点相似 | 卖点画像 |
| `channel_overlap` | 渠道重合 | 市场 |

### 8.4 三类竞品槽位

继续保留三类槽位，但解释口径调整。

#### 正面对打

适合条件：

- 尺寸相同或相邻。
- 价格接近。
- 主战场重合。
- 参数/评论关注点相似。

建议公式：

```text
direct_score =
  0.20 * size_similarity
  + 0.20 * price_similarity
  + 0.25 * battlefield_similarity
  + 0.15 * param_similarity
  + 0.10 * comment_topic_similarity
  + 0.10 * channel_overlap
```

#### 价格/销量挤压

适合条件：

- 价格更低或价格带下探。
- 销量/销售额更强。
- 尺寸或战场仍可比。

建议公式：

```text
pressure_score =
  0.25 * price_pressure
  + 0.25 * sales_strength
  + 0.15 * size_similarity
  + 0.15 * battlefield_similarity
  + 0.10 * comment_topic_similarity
  + 0.10 * channel_overlap
```

#### 高端标杆/上探

适合条件：

- 价格更高或定位更高。
- 参数显著更强。
- 同尺寸或上探尺寸。
- 战场相同或更高阶。

建议公式：

```text
benchmark_score =
  0.25 * param_superiority
  + 0.20 * price_premium_fit
  + 0.20 * battlefield_similarity
  + 0.15 * size_similarity
  + 0.10 * sales_strength
  + 0.10 * claim_similarity
```

### 8.5 结果去重与不硬凑

规则：

1. 同一个候选可以有多个高分槽位，但最终优先放到最高角色分槽位。
2. 三个槽位尽量不重复 SKU。
3. 分数低于门槛时显示“暂未命中”，但候选池排序仍可展示。
4. 当前 35 个型号样例中可以先输出 Top 3 竞争型号，再标注每个型号最强角色。

## 9. 与现有 Core3 链路衔接

### 9.1 适配为 `Core3InputBundle`

首版推荐用适配方式，不把真实数据物理写入 `raw_*`：

```python
def load_project_input(db, project_id):
    if use_real_sample_data(project_id):
        return load_real_project_input(db, project_id)
    return load_standard_project_input(db, project_id)
```

`load_real_project_input` 输出现有等价对象：

- `sku_master`：由四张表 union 出 SKU 列表。
- `market_facts`：由 `week_sales_data` 清洗投影。
- `params`：由 `attribute_data` 清洗投影。
- `claims`：由 `selling_points_data` 投影；缺失型号不补假 claim。
- `comments`：由 `comment_data` 清洗投影。
- `evidence_index`：真实表行引用。

### 9.2 Evidence 设计

真实表证据引用必须能回溯：

```json
{
  "source_mode": "real_sample_v1",
  "source_table": "attribute_data",
  "source_row_id": 123,
  "model_code": "TV00029115",
  "field": "亮度",
  "raw_value": "5200",
  "write_time": "2026-06-11 18:16:03"
}
```

聚合证据：

```json
{
  "source_table": "week_sales_data",
  "aggregation": "sum_sales_amount_by_sku",
  "model_code": "TV00029115",
  "period_range": ["26W01", "26W23"],
  "channel_platforms": ["线上/专业电商", "线上/平台电商"],
  "source_row_count": 46
}
```

页面不展示 source row id，但证据卡详情可以保留。

## 10. API 设计

### 10.1 数据质量

```http
GET /api/mvp/core3/projects/{project_id}/real-data/status
```

返回：

```json
{
  "source_mode": "real_sample_v1",
  "status": "ready_with_warnings",
  "sku_count": 35,
  "tables": [],
  "warnings": [],
  "recommended_actions": []
}
```

### 10.2 预分析总览

```http
GET /api/mvp/core3/projects/{project_id}/real-data/preanalysis
```

返回：

- SKU 排名。
- 数据覆盖。
- 价格带分布。
- 战场分布。
- 评论维度分布。

### 10.3 单 SKU 画像

```http
GET /api/mvp/core3/projects/{project_id}/real-data/sku/{sku_or_model}/profile
```

返回：

- 市场画像。
- 参数画像。
- 卖点画像。
- 评论画像。
- 战场画像。
- 可追溯证据摘要。

### 10.4 真实数据重算

现有 run API 增加参数：

```json
{
  "batch": true,
  "force_recompute": true,
  "source_mode": "real_sample_v1"
}
```

或新增：

```http
POST /api/mvp/core3/projects/{project_id}/real-data/run
```

首版建议扩展现有 run API，避免新增过多入口。

## 11. 页面设计

### 11.1 页面结构

第一屏：

- 标题：彩电竞品研判
- 数据底座：真实样例数据
- 数据更新时间：四张表最新写入时间
- 数据覆盖：35 个型号、周销/参数/评论/卖点覆盖情况
- 数据质量提醒：卖点只覆盖 5 个型号、当前品牌为海信

单品报告：

1. 目标型号画像。
2. 数据清洗摘要。
3. 价值战场推导。
4. 竞品候选池。
5. 三类竞品结论。
6. 每个竞品的证据解释。

### 11.2 目标型号画像卡

展示：

- 型号：海信 85E7Q。
- 价格带。
- 23 周销量/销售额。
- 核心参数：85 寸、4K、5200 尼特、3500 分区、300Hz、HDMI2.1。
- 评论概览：有效评论数、正负情绪、主要好评维度。

### 11.3 价值战场推导

不要只列战场，要展示推导链：

```text
参数证据：5200 尼特 + 3500 分区 + MiniLED
评论证据：显示画质正向反馈
市场证据：85 寸高价位且销售额靠前
=> 高亮画质战场
```

### 11.4 竞品解释

每个竞品卡包含：

- 为什么进入候选池。
- 哪些指标相似。
- 哪些指标形成压力。
- 共同价值战场。
- 价格/销量对比。
- 参数强弱对比。
- 评论关注点对比。

示例文案结构：

```text
85E5Q-PRO 被判定为 85E7Q 的正面对打竞品：
两者同为 85 英寸，处于相邻价格带，均以大屏高画质和客厅观影为核心战场。
85E5Q-PRO 销售额更高，对 85E7Q 形成明确市场分流。
```

## 12. 数据库与持久化设计

首版可以不新增物理画像表，使用运行时计算并写入现有 Core3 表：

- `core3_sku_market_profile`
- `core3_sku_feature_profile`
- `core3_competitor_candidate`
- `core3_competitor_result`
- `core3_evidence_card`

如果性能或复用需要，第二阶段再新增：

- `core3_real_data_quality_snapshot`
- `core3_real_sku_preanalysis`
- `core3_real_comment_dimension_summary`

首版不建议新增太多表，避免迁移成本和双写一致性问题。

## 13. 测试设计

### 13.1 单元测试

新增测试：

- 周销清洗：重复聚合、价格校验、周序排序。
- 参数清洗：unknown 处理、亮度/刷新率/分区/内存解析。
- 评论清洗：空评过滤、评论去重、维度保留。
- 卖点清洗：分句、claim 匹配、缺失卖点不当作无卖点。
- SKU 画像：`85E7Q` 能生成市场/参数/评论画像。

### 13.2 集成测试

构造小型真实表 fixture：

- 目标 SKU：85E7Q。
- 候选 SKU：85E5Q-PRO、85E5Q、75E7Q、100E5Q。
- 覆盖周销、参数、评论、部分卖点。

验证：

- run API 能使用 `source_mode=real_sample_v1`。
- 生成 Core3 profiles。
- 候选池不按品牌排除。
- 同品牌型号能进入竞品结果。
- 证据卡包含真实表 source_ref。

### 13.3 页面测试

验证：

- 页面显示真实数据更新时间。
- 页面显示数据质量提醒。
- 页面不出现旧 TCL/小米样例结论。
- 85E7Q 页面显示真实参数和评论摘要。
- 竞品理由包含价格、销量、参数、评论证据。

## 14. 分阶段实施建议

### Phase 1：只读接入与质量摘要

实现：

- ORM/read model 或 SQL query 读取 4 张表。
- 数据质量 API。
- 页面展示数据底座。

验收：

- 页面能显示 35 个型号、4 张表覆盖、质量 warning。

### Phase 2：清洗与 SKU 画像

实现：

- 周销画像。
- 参数画像。
- 评论画像。
- 卖点画像。

验收：

- 85E7Q 有真实画像。
- 可展示参数、评论、量价证据。

### Phase 3：接入 Core3 pipeline

实现：

- `source_mode=real_sample_v1`。
- 真实数据适配到 Core3InputBundle。
- 重新跑 feature pipeline。

验收：

- 35 个型号生成 market profile 和 feature profile。

### Phase 4：真实竞品报告

实现：

- 候选池使用 35 个型号。
- 三槽位结果基于真实画像。
- 页面替换旧 sample 结论。

验收：

- 85E7Q 输出真实竞品。
- 每个竞品有业务解释和证据。

## 15. 风险与处理

| 风险 | 影响 | 处理 |
| --- | --- | --- |
| 当前只有海信品牌 | 不能证明外部品牌竞争 | 不按内外部区分，展示同品牌竞争型号 |
| 卖点只覆盖 5 个型号 | 85E7Q 没有结构化卖点 | 用参数和评论推导卖点，标注来源 |
| 评论重复维度拆行 | 评论声量被放大 | 原声去重，维度统计保留拆行 |
| 参数 unknown 多 | 错误当作不支持 | unknown 不参与负向判断 |
| 新数据继续追加 | 批次口径混乱 | 显示 write_time，支持 latest/all_current 模式 |
| 页面给领导看 | 技术词暴露 | 前端只展示业务语言 |

## 16. 待确认问题

1. 真实数据首版是否默认使用 `all_current`，而不是只取最新 `write_time`。
2. 目标型号是否仍默认 `85E7Q`。
3. 三槽位是否保留固定名称：正面对打、价格/销量挤压、高端标杆/上探。
4. 页面是否允许显示“数据质量提醒”。
5. 卖点缺失时，是否接受“由参数/评论推导卖点”的业务口径。
6. 是否需要把真实数据接入结果写回 `raw_*` 表，还是只通过 adapter 投影给 Core3 pipeline。

建议首版选择：

- 使用 `all_current`。
- 默认目标 `85E7Q`。
- 保留三槽位。
- 页面展示数据质量提醒，但用业务语言。
- 接受推导卖点，并明确标注证据来源。
- 不写回 `raw_*`，先用 adapter 投影，降低破坏风险。
