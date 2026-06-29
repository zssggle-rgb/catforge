# M04C SKU 卖点事实画像与卖点位置覆盖详细设计

## 1. 文档定位

本文是 M04C 的工程详细设计，承接：

- `sop_requirements/M04C_claim_fact_profile_requirements.md`
- `sop_detailed_design/M01_cleaning_quality_design.md`
- `sop_detailed_design/M02_evidence_atom_design.md`
- `sop_detailed_design/M03B_sku_param_profile_design.md`
- `08_layered_analysis_path_guidance.md`

M04C 是 SKU 事实层的新模块族，用标准卖点 taxonomy 生成 SKU 卖点事实画像。它是确定性画像模块，不依赖既有 M04a/M04b 激活结果，不读取评论，不判断溢价。

M04C 不判断用户是否愿意付费，但必须为 M12C 提供可用的事实门槛：卖点是否由具体参数支撑、是否只是泛参数支撑、是否与其他标准卖点来自同一条原始卖点或同一组核心参数。没有这些门槛，后续会把“杜比/影音认证 + HDR”误判为独占支付价值，也会把“芯片/处理器性能”和“画质芯片/AI 画质引擎”重复计价。

## 2. 模块职责

### 2.1 必须回答的问题

1. 当前品类有哪些已发布标准卖点。
2. 某 SKU 的原始卖点文本命中了哪些标准卖点。
3. 这些标准卖点属于哪些维度和子类。
4. 这些卖点是否有 M03B 参数事实支撑。
5. 该 SKU 在每个卖点维度中处于什么位置。
6. 某个卖点位置覆盖哪些 SKU。

### 2.2 不回答的问题

M04C 不回答：

- 评论是否认可该卖点。
- 卖点是否正向或负向影响购买。
- 卖点是否溢价。
- SKU 的主用户任务、主目标客群、主价值战场。
- 核心竞品是谁。

这些问题由后续评论事实层、语义能力层、画像层和竞品分析层处理。

## 3. 总体流程

```text
M04C-A taxonomy 生成/发布
  1. 读取某品类全部结构化卖点
  2. 归纳标准卖点、维度、子类、位置规则
  3. 关联 M03B 标准参数，定义参数支撑规则、泛参数保护和同源同参策略
  4. 人工复核并发布 taxonomy version

M04C-B SKU 卖点画像生成
  1. 解析 batch 与 product_category
  2. 加载已发布 claim taxonomy
  3. 读取清洗后的 promo evidence
  4. 读取 M03B SKU 参数画像
  5. 匹配 SKU 卖点事实明细
  6. 计算参数支撑状态、参数支撑等级和用户支付价值输入门槛
  7. 计算同源同参分组和业务代表卖点
  8. 计算 claimed_position 与 supported_position
  9. 写入 SKU 卖点画像、维度位置和覆盖索引
```

## 4. Taxonomy 设计

### 4.1 文件或表结构

首版可以用代码内置 JSON/YAML asset，后续可迁移到数据库资产表。无论存储方式，taxonomy 发布结构必须一致。

```json
{
  "taxonomy_version": "tv_claim_taxonomy_manual_v0.1",
  "product_category": "TV",
  "category_label_cn": "彩电",
  "source_summary": {
    "source_table": "selling_points_data",
    "source_category": "彩电",
    "source_row_count": 4229,
    "source_model_count": 328,
    "source_brand_count": 18
  },
  "dimensions": [],
  "standard_claims": [],
  "dimension_position_rules": [],
  "service_separation_rules": []
}
```

### 4.2 `standard_claims`

每个标准卖点至少包含：

| 字段 | 说明 |
| --- | --- |
| `claim_code` | 稳定编码，例如 `TV_CLAIM_MINI_LED_BACKLIGHT` |
| `claim_name` | 中文名称 |
| `dimension_code` | 一级维度 |
| `subtype_code` | 二级子类 |
| `claim_kind` | `product_function`、`experience_scene`、`authority`、`content`、`service`、`price_value` |
| `source_text_patterns` | 用于匹配原始卖点文本的关键词/正则 |
| `source_header_patterns` | 用于匹配 `【标题】` 的表达 |
| `required_param_support` | 必要参数支撑规则 |
| `optional_param_support` | 辅助参数支撑规则 |
| `support_policy` | 参数支撑策略 |
| `param_support_level_policy` | 参数支撑等级策略，定义具体支撑、泛参数支撑、弱间接支撑等 |
| `generic_support_param_codes` | 只能提供泛化支撑的参数，例如用 HDR 支撑杜比认证 |
| `wtp_input_guard_policy` | 给 M12C 的输入门槛策略 |
| `same_source_param_group_policy` | 同一原始卖点或同一核心参数支撑多个标准卖点时的合并策略 |
| `canonical_claim_policy` | 同源同参时的业务代表卖点选择策略 |
| `downstream_usage_policy` | 下游可用性 |
| `review_notes` | 人工复核说明 |

示例：

```json
{
  "claim_code": "TV_CLAIM_MINI_LED_BACKLIGHT",
  "claim_name": "Mini LED 背光技术",
  "dimension_code": "picture_display",
  "subtype_code": "display_tech",
  "claim_kind": "product_function",
  "source_text_patterns": ["Mini LED", "MiniLED", "QD-Mini", "RGB-Mini", "ULED"],
  "required_param_support": [
    {
      "param_code": "display_technology_family",
      "operator": "in",
      "expected_values": ["miniled", "qd_miniled", "rgb_miniled"]
    }
  ],
  "support_policy": "required_any",
  "downstream_usage_policy": {
    "sku_fact_profile": true,
    "candidate_recall": true,
    "semantic_anchor": true,
    "premium_claim": "defer_to_comment_market_battlefield"
  }
}
```

### 4.3 参数支撑规则

`required_param_support` 支持以下规则类型：

| 规则 | 说明 |
| --- | --- |
| `param_present` | 参数存在即可支撑 |
| `param_value_in` | 参数值属于指定集合 |
| `param_numeric_gte` | 数值大于等于阈值 |
| `param_numeric_between` | 数值落在区间 |
| `dimension_tier_in` | M03B 参数维度档位属于指定集合 |
| `param_pattern_match` | 参数文本匹配关键词 |
| `not_param_applicable` | 该卖点不适用参数支撑 |

支撑策略：

| `support_policy` | 说明 |
| --- | --- |
| `required_all` | 必要参数全部满足才 supported |
| `required_any` | 任一必要参数满足即 supported |
| `weighted` | 按规则权重合成支撑分 |
| `not_applicable` | 行业背书、服务、内容等不做参数支撑 |

### 4.4 参数支撑等级和用户支付价值输入门槛

`param_support_status` 只说明参数规则是否满足，不能直接说明该卖点是否可进入 M12C 用户支付价值分析。M04C 必须额外输出 `param_support_level` 和 `wtp_input_guard`。

| `param_support_level` | 定义 | 示例 | M12C 处理 |
| --- | --- | --- | --- |
| `strong_specific_support` | 有专属、明确、可解释的参数支撑 | 画质芯片卖点由芯片型号、AI 画质能力支撑 | 可进入用户支付价值候选 |
| `strong_numeric_or_tier_support` | 有数值或档位参数支撑，并可在同池比较 | 高亮卖点由 5200nits 支撑 | 可进入用户支付价值候选 |
| `broad_generic_support` | 只有宽泛参数支撑，不能证明具体卖点 | 用 `HDR=true` 支撑“杜比/影音认证” | 不得作为该具体卖点进入用户支付价值；泛参数本身可进入门槛判断 |
| `weak_indirect_support` | 参数只间接关联，不能独立证明卖点 | 用系统参数间接支撑“系统顺滑” | 默认待验证 |
| `no_param_support` | 没有可用参数支撑 | 只有营销文案 | 厂家主张或待验证 |
| `not_param_applicable` | 内容权益、服务、销量背书等不适用产品参数 | 会员权益、送装服务 | 不进入产品用户支付价值 |

`wtp_input_guard` 只回答“该卖点是否具备进入 M12C 的事实基础”，不回答“是否溢价”。

| `wtp_input_guard` | 触发条件 | M12C 默认处理 |
| --- | --- | --- |
| `eligible_strong_param` | `strong_specific_support` 或 `strong_numeric_or_tier_support` | 可进入战场、门槛、参数竞争力和用户支付价值判断 |
| `eligible_key_param_advantage` | 卖点表达弱，但关键参数明显强 | 可作为待激活或人无我有候选 |
| `blocked_generic_param` | 只被泛参数支撑 | 具体卖点不得进入用户支付价值；泛参数本身按门槛处理 |
| `blocked_no_param` | 无参数支撑，且不属于参数不适用 | 厂家主张，不分配金额 |
| `not_product_wtp_scope` | 服务、物流、安装、售后、内容权益等 | 排除产品支付价值分析 |

泛参数保护示例：

| 标准卖点 | 当前可见支撑 | M04C 输出 | 业务含义 |
| --- | --- | --- | --- |
| 杜比/影音认证 | 只有 `hdr_support_flag=true` | `broad_generic_support` + `blocked_generic_param` | HDR 可以作为高端画质门槛；杜比认证本身不能被 HDR 证明 |
| HDR/高亮画质 | `hdr_support_flag=true`，亮度参数缺失 | `broad_generic_support` 或 `weak_indirect_support` | 基础 HDR 可入门槛，不能直接判高溢价 |
| HDR/高亮画质 | `brightness_nits=5200` | `strong_numeric_or_tier_support` + `eligible_strong_param` | 可进入 M12C 参数竞争力比较 |

### 4.5 同源同参合并策略

一条原始卖点文本可能命中多个标准卖点，同一组核心参数也可能支撑多个标准卖点。M04C 必须输出分组，避免 M12C 重复计算同一价值。

| 字段 | 含义 |
| --- | --- |
| `source_claim_group_id` | 同一条原始卖点文本命中的标准卖点分组 |
| `same_source_param_group_id` | 同一组核心参数支撑的标准卖点分组 |
| `canonical_claim_code` | 该组对外展示和用户支付价值计算优先使用的代表卖点 |
| `canonical_claim_name` | 代表卖点中文名 |

示例：海信 65E7Q 的“信芯 AI 画质芯片 H6 超频版”可能同时命中“芯片/处理器性能”和“画质芯片/AI 画质引擎”。M04C 可以保留两条标准卖点事实，但必须把它们标记到同一 `same_source_param_group_id`，并给出代表卖点。M12C 后续只能把它们作为一个业务价值理由分析，不能把同一个芯片参数拆成两个独立高溢价卖点。

## 5. 输出数据模型

### 5.1 `core3_sku_claim_fact_profile`

每个 SKU 每个 taxonomy version 一条。

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `claim_profile_id` | text | 是 | 主键 |
| `project_id` | text | 是 | 项目 |
| `category_code` | text | 是 | 源 batch 品类 |
| `product_category` | text | 是 | 业务品类，TV/AC |
| `batch_id` | text | 是 | 批次 |
| `sku_code` | text | 是 | SKU |
| `model_name` | text | 否 | 型号 |
| `brand_name` | text | 否 | 品牌 |
| `taxonomy_version` | text | 是 | 卖点 taxonomy |
| `rule_version` | text | 是 | 画像规则版本 |
| `structured_claim_count` | integer | 是 | 结构化卖点行数 |
| `matched_claim_count` | integer | 是 | 命中标准卖点数 |
| `fact_claim_count` | integer | 是 | 有参数支撑的产品事实卖点数 |
| `param_supported_claim_count` | integer | 是 | `supported` 数 |
| `param_unknown_claim_count` | integer | 是 | `param_unknown` 数 |
| `service_separate_claim_count` | integer | 是 | 服务隔离卖点数 |
| `claimed_position_json` | jsonb | 是 | 只按卖点文本计算的位置 |
| `supported_position_json` | jsonb | 是 | 按参数支撑后确认或降级的位置 |
| `claim_summary_json` | jsonb | 是 | 卖点摘要 |
| `quality_summary_json` | jsonb | 是 | 缺失、冲突、复核 |
| `evidence_ids` | jsonb | 是 | promo evidence 汇总 |
| `param_evidence_ids` | jsonb | 是 | 参数 evidence 汇总 |
| `profile_hash` | text | 是 | 结果 hash |
| `is_current` | boolean | 是 | 当前版本 |
| `created_at` | timestamptz | 是 | 创建时间 |
| `updated_at` | timestamptz | 是 | 更新时间 |

唯一约束：

```text
project_id + category_code + product_category + batch_id + sku_code + taxonomy_version + rule_version + is_current
```

### 5.2 `core3_sku_claim_fact`

每个 SKU 每个标准卖点一条。

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sku_claim_fact_id` | text | 是 | 主键 |
| `claim_profile_id` | text | 是 | SKU 画像 |
| `project_id` | text | 是 | 项目 |
| `category_code` | text | 是 | 源品类 |
| `product_category` | text | 是 | 业务品类 |
| `batch_id` | text | 是 | 批次 |
| `sku_code` | text | 是 | SKU |
| `claim_code` | text | 是 | 标准卖点 |
| `claim_name` | text | 是 | 中文名 |
| `dimension_code` | text | 是 | 维度 |
| `subtype_code` | text | 是 | 子类 |
| `claim_kind` | text | 是 | 类型 |
| `source_claim_texts` | jsonb | 是 | 原始卖点文本 |
| `source_variables` | jsonb | 是 | 卖点1..卖点13 |
| `promo_evidence_ids` | jsonb | 是 | 卖点 evidence |
| `match_method` | text | 是 | keyword/header/entity |
| `match_score` | numeric | 是 | 文本匹配分 |
| `param_support_status` | text | 是 | supported/partial/unknown/conflicted 等 |
| `param_support_score` | numeric | 是 | 参数支撑分 |
| `param_support_level` | text | 是 | strong_specific_support/broad_generic_support/no_param_support 等 |
| `param_support_specificity` | text | 是 | specific/numeric_tier/generic/indirect/none/not_applicable |
| `supporting_param_codes` | jsonb | 是 | 支撑参数 |
| `primary_supporting_param_codes` | jsonb | 是 | 对该卖点最关键的参数 |
| `generic_support_param_codes` | jsonb | 是 | 只能提供泛化支撑的参数 |
| `supporting_param_values` | jsonb | 是 | 参数值快照 |
| `missing_param_codes` | jsonb | 是 | 缺失参数 |
| `param_conflict_json` | jsonb | 是 | 冲突说明 |
| `param_evidence_ids` | jsonb | 是 | 参数 evidence |
| `source_claim_group_id` | text | 否 | 同一原始卖点文本命中的分组 |
| `same_source_param_group_id` | text | 否 | 同一核心参数支撑的分组 |
| `canonical_claim_code` | text | 否 | 同组业务代表卖点 |
| `canonical_claim_name` | text | 否 | 同组业务代表卖点中文名 |
| `wtp_input_guard` | text | 是 | eligible_strong_param/blocked_generic_param 等 |
| `fact_claim_flag` | boolean | 是 | 是否产品事实卖点 |
| `service_separate_flag` | boolean | 是 | 是否服务隔离 |
| `authority_flag` | boolean | 是 | 是否行业/认证背书 |
| `content_ecosystem_flag` | boolean | 是 | 是否内容权益 |
| `confidence` | numeric | 是 | 置信度 |
| `review_required` | boolean | 是 | 是否复核 |
| `review_reason_json` | jsonb | 是 | 复核原因 |
| `fact_hash` | text | 是 | 结果 hash |
| `is_current` | boolean | 是 | 当前版本 |

### 5.3 `core3_sku_claim_dimension_position`

每个 SKU 每个卖点维度一条。

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `claim_position_id` | text | 是 | 主键 |
| `claim_profile_id` | text | 是 | SKU 画像 |
| `project_id` | text | 是 | 项目 |
| `category_code` | text | 是 | 源品类 |
| `product_category` | text | 是 | 业务品类 |
| `batch_id` | text | 是 | 批次 |
| `sku_code` | text | 是 | SKU |
| `dimension_code` | text | 是 | 卖点维度 |
| `claimed_position_code` | text | 是 | 文本宣称位置 |
| `claimed_position_name` | text | 是 | 中文名 |
| `supported_position_code` | text | 是 | 参数支撑后位置 |
| `supported_position_name` | text | 是 | 中文名 |
| `position_rank` | integer | 否 | 位置等级，无顺序时为空 |
| `basis_claim_codes` | jsonb | 是 | 判断依据卖点 |
| `fact_claim_codes` | jsonb | 是 | 有参数支撑卖点 |
| `unsupported_claim_codes` | jsonb | 是 | 无参数支撑卖点 |
| `rule_snapshot_json` | jsonb | 是 | 位置规则快照 |
| `explanation` | text | 是 | 解释 |
| `evidence_ids` | jsonb | 是 | 卖点 evidence |
| `param_evidence_ids` | jsonb | 是 | 参数 evidence |
| `confidence` | numeric | 是 | 置信度 |
| `quality_flags` | jsonb | 是 | 质量标记 |
| `position_hash` | text | 是 | 结果 hash |
| `is_current` | boolean | 是 | 当前版本 |

`claimed_position` 和 `supported_position` 必须同时保留。

示例：

```json
{
  "dimension_code": "picture_quality",
  "claimed_position_code": "picture_miniled_composite_flagship",
  "supported_position_code": "picture_miniled_control_upgrade",
  "explanation": "卖点宣称 Mini LED 复合画质旗舰，但参数中只有 Mini LED 与部分控光支撑，亮度/HDR/色准参数缺失，因此支撑位置降级。"
}
```

### 5.4 `core3_claim_position_coverage`

每个维度位置一条覆盖索引。

| 字段 | 类型建议 | 必填 | 说明 |
| --- | --- | --- | --- |
| `claim_position_coverage_id` | text | 是 | 主键 |
| `project_id` | text | 是 | 项目 |
| `category_code` | text | 是 | 源品类 |
| `product_category` | text | 是 | 业务品类 |
| `batch_id` | text | 是 | 批次 |
| `taxonomy_version` | text | 是 | taxonomy |
| `rule_version` | text | 是 | 规则版本 |
| `dimension_code` | text | 是 | 维度 |
| `position_code` | text | 是 | 位置 |
| `position_name` | text | 是 | 中文名 |
| `position_rank` | integer | 否 | 排序 |
| `position_source` | text | 是 | `claimed` 或 `supported` |
| `rule_summary` | text | 是 | 规则说明 |
| `sku_count` | integer | 是 | 覆盖 SKU 数 |
| `sku_ratio` | numeric | 是 | 覆盖率 |
| `param_supported_sku_count` | integer | 是 | 参数支撑 SKU 数 |
| `sku_codes` | jsonb | 是 | SKU 列表 |
| `sample_sku_codes` | jsonb | 是 | 样例 |
| `coverage_status` | text | 是 | covered/empty/insufficient |
| `coverage_hash` | text | 是 | hash |
| `is_current` | boolean | 是 | 当前版本 |

## 6. 画像生成算法

### 6.1 批次解析

输入：

```text
project_id
category_code
product_category
batch_id/latest
sku_scope
force_rebuild
```

解析规则：

1. `batch_id=latest` 时优先找当前项目和源 `category_code` 最新 batch。
2. `product_category=tv` 使用 `sku_code like 'TV%'` 和原始 `category='彩电'` 防御过滤。
3. `product_category=ac` 使用 `sku_code like 'AC%'` 和原始 `category='空调'` 防御过滤。
4. 若源 batch 中包含混品类，输出 warning，但不阻断。

### 6.2 卖点 evidence 读取

优先读取 M02 当前 `promo_raw` / `promo_sentence` evidence：

```sql
project_id = :project_id
and category_code = :category_code
and batch_id = :batch_id
and evidence_type in ('promo_raw', 'promo_sentence')
and evidence_status = 'current'
and is_current = true
```

如果实现阶段 M02 对最新批次未生成完整 promo evidence，可以在 CLI 加 `--allow-raw-fallback` 调试模式读取 `selling_points_data`。正式 pipeline 不默认启用 raw fallback。

### 6.3 标准卖点匹配

每条卖点文本按以下顺序匹配：

1. `source_header_patterns`：解析 `【标题】`。
2. `source_text_patterns`：关键词/正则匹配正文。
3. `negative_patterns`：排除“媲美 OLED”误判为 OLED 自发光。
4. `claim_kind` 规则：服务、背书、内容、价格价值单独标记。

一条卖点文本可以命中多个标准卖点。每个命中记录保留：

- 原始文本。
- 标题。
- 命中模式。
- 关键词。
- evidence id。
- 匹配分。

### 6.4 参数支撑评分

对每个 SKU + 标准卖点读取 M03B `core3_sku_param_profile` 和 `core3_sku_param_dimension_tier`。

参数支撑分：

```text
required_support_score = required rules satisfied / required rules total
optional_support_score = optional weighted satisfied score
param_support_score = required_support_score * 0.75 + optional_support_score * 0.25
```

状态判断：

| 条件 | 状态 |
| --- | --- |
| `support_policy=not_applicable` | `not_param_applicable` |
| 无参数画像 | `param_unknown` |
| 必要参数全部满足 | `supported` |
| 部分必要参数满足且无冲突 | `partially_supported` |
| 关键参数缺失且无反证 | `param_unknown` |
| 参数明确反向 | `unsupported` |
| 同一参数多值冲突或卖点与参数冲突 | `conflicted` |

`fact_claim_flag=true` 条件：

```text
claim_kind in ('product_function', 'experience_scene')
and param_support_status in ('supported', 'partially_supported')
and service_separate_flag = false
```

### 6.4.1 参数支撑等级判定

参数支撑状态之后必须继续判定参数支撑等级：

```python
def classify_param_support_level(claim, support_status, matched_params):
    if claim.claim_kind in {"service", "content", "authority"} and claim.support_policy == "not_applicable":
        return "not_param_applicable"
    if support_status in {"unsupported", "param_unknown"} and not matched_params:
        return "no_param_support"
    if matched_params.only_generic_params(claim.generic_support_param_codes):
        return "broad_generic_support"
    if matched_params.has_numeric_or_tier_core_param():
        return "strong_numeric_or_tier_support"
    if matched_params.has_specific_core_param():
        return "strong_specific_support"
    if matched_params.has_indirect_param():
        return "weak_indirect_support"
    return "no_param_support"
```

`wtp_input_guard` 映射：

| 参数支撑等级 | 默认 `wtp_input_guard` |
| --- | --- |
| `strong_specific_support` | `eligible_strong_param` |
| `strong_numeric_or_tier_support` | `eligible_strong_param` |
| `broad_generic_support` | `blocked_generic_param` |
| `weak_indirect_support` | `blocked_no_param`，可按 taxonomy 配置放宽为待激活 |
| `no_param_support` | `blocked_no_param` |
| `not_param_applicable` | `not_product_wtp_scope` |

注意：`fact_claim_flag=true` 和 `wtp_input_guard=eligible_strong_param` 不是同一个概念。一个卖点可以是事实卖点，但如果只有泛参数支撑，M12C 仍不得把该具体卖点作为高溢价或人无我有候选。

### 6.4.2 泛参数保护规则

泛参数保护用于处理“参数能证明基础能力，但不能证明具体认证或高阶能力”的场景。

规则：

1. 如果标准卖点只由 `generic_support_param_codes` 支撑，则 `param_support_level=broad_generic_support`。
2. 具体标准卖点的 `wtp_input_guard=blocked_generic_param`。
3. 泛参数本身可以作为 M12C 门槛判断输入，例如基础 HDR、基础高刷、基础 HDMI2.1。
4. 具体认证、芯片、专利、生态或高阶能力不能被泛参数替代证明。

示例：

| 卖点 | 可见参数 | 结果 |
| --- | --- | --- |
| 杜比/影音认证 | 只有 HDR | 杜比为 `blocked_generic_param`；HDR 可作为高端画质基础门槛 |
| HDMI2.1 连接 | 只有是否具备 HDMI2.1 | 可作为游戏战场门槛；没有接口数量/带宽/VRR/ALLM 时不得稳定高溢价 |
| 高刷新率 | 只有 120Hz/144Hz | 在游戏池多为门槛；若 300Hz 等档位领先，参数档位可继续进入 M12C |

### 6.4.3 场景表达和专属参数保护

M04C taxonomy 必须区分“产品能力卖点”和“用户场景表达”。场景表达可以帮助 M09C/M10C/M11C 判断用户任务、目标客群和价值战场，但不能被 M12C 当作可分配金额的产品卖点。

| 标准卖点/表达 | M04C taxonomy 配置 | M12C 使用方式 |
| --- | --- | --- |
| 影院/观影场景 | `claim_scope=scene_context`，`wtp_input_guard=not_product_wtp_scope` 或 `blocked_no_param` | 只进入任务/战场解释，不进入高溢价、份额转化或金额分配 |
| 客厅观影、家庭观影 | `claim_scope=scene_context` | 只作为用户任务/目标客群证据 |
| 护眼显示 | `claim_scope=product_capability`，专属参数只允许低蓝光、无频闪、护眼认证、抗反光等 | 不得用 HDR、亮度、刷新率支撑护眼支付价值 |
| HDR/高亮画质 | 拆成基础 HDR 和高亮档位两类支撑 | 基础 HDR 走门槛；亮度数值进入 M12C 参数档位比较 |
| 杜比/影音认证 | 专属认证或音频硬件为强支撑；HDR 为泛支撑 | 只有 HDR 时不得进入用户支付价值候选 |

实现要求：

1. `supporting_param_codes` 可以保留所有可解释参数，但 `primary_supporting_param_codes` 必须只放专属或核心参数。
2. `generic_support_param_codes` 必须显式列出只能提供泛化证明的参数，例如用 `hdr_support_flag` 支撑杜比认证。
3. 对护眼、杜比、芯片、认证、生态类卖点，M04C-B 生成事实时必须优先检查专属参数；如果只有泛参数，`wtp_input_guard` 必须降级。
4. 对场景表达，M04C 可以保留卖点事实和原文证据，但必须向 M12C 暴露“不可正向金额量化”的范围信号。

### 6.4.4 同源同参分组

M04C-B 在生成 `core3_sku_claim_fact` 时必须同时做两类分组：

```text
source_claim_group_id:
  同一 sku_code + 同一原始卖点 evidence_id 命中的标准卖点

same_source_param_group_id:
  同一 sku_code + 同一核心参数集合支撑的标准卖点
```

代表卖点选择顺序：

1. taxonomy 中显式配置 `canonical_claim_policy`。
2. 优先选择更贴近用户价值表达的卖点，例如“画质芯片/AI 画质引擎”优先于泛化“芯片/处理器性能”。
3. 如果一个卖点同时服务多个战场，保留多条战场映射，但用户支付价值计算仍以同组代表卖点为主。

输出要求：

| 场景 | M04C 输出 | M12C 预期使用 |
| --- | --- | --- |
| 同一原始卖点命中多个标准卖点 | 多条 fact，带同一 `source_claim_group_id` | 作为一个业务证据组解释 |
| 同一参数支撑多个标准卖点 | 多条 fact，带同一 `same_source_param_group_id` | 合并为一个用户价值理由，不重复计价 |
| 卖点名称不同但参数证据不同 | 不合并 | 分别进入 M12C 判断 |

### 6.5 维度位置计算

每个维度计算两套位置：

| 位置 | 来源 |
| --- | --- |
| `claimed_position` | 只看卖点文本命中的标准卖点 |
| `supported_position` | 只看有参数支撑的标准卖点；必要时降级 |

位置规则示例：

```json
{
  "dimension_code": "picture_quality",
  "position_code": "picture_miniled_composite_flagship",
  "basis_claim_codes": [
    "TV_CLAIM_MINI_LED_BACKLIGHT",
    "TV_CLAIM_LOCAL_DIMMING_CONTRAST",
    "TV_CLAIM_HIGH_BRIGHTNESS_HDR",
    "TV_CLAIM_PICTURE_ENGINE_AI"
  ],
  "rule_expression": "mini_led and at_least_3_of(local_dimming, high_brightness_hdr, picture_engine, wide_color, color_accuracy)",
  "fallback_position": "picture_miniled_control_upgrade"
}
```

如果 `claimed_position` 强而 `supported_position` 弱，画像必须输出差异：

```text
卖点宣称位置较高，但参数支撑不足，后续报告只能按 supported_position 使用。
```

## 7. TV taxonomy 首版配置草案

### 7.1 标准卖点清单

| code | 维度 | 名称 | 参数支撑 |
| --- | --- | --- | --- |
| `TV_CLAIM_LARGE_SCREEN_IMMERSION` | `scene_experience` | 大屏/巨幕/影院沉浸 | 尺寸、音画参数辅助 |
| `TV_CLAIM_MINI_LED_BACKLIGHT` | `picture_display` | Mini LED 背光技术 | 显示技术/背光参数 |
| `TV_CLAIM_QUANTUM_DOT_WIDE_COLOR` | `picture_quality` | 量子点/广色域 | 色域、量子点参数 |
| `TV_CLAIM_COLOR_ACCURACY_CALIBRATION` | `picture_quality` | 色准/逐台校准 | 色准、校准、色域参数 |
| `TV_CLAIM_HIGH_BRIGHTNESS_HDR` | `picture_quality` | 高亮 HDR/XDR | 亮度、HDR 参数 |
| `TV_CLAIM_LOCAL_DIMMING_CONTRAST` | `picture_quality` | 分区控光/对比度 | 分区背光、控光参数 |
| `TV_CLAIM_ANTI_REFLECTION_WIDE_ANGLE` | `picture_quality` | 低反/防眩/广视角 | 屏幕材质、反射率、视角参数 |
| `TV_CLAIM_PICTURE_ENGINE_AI` | `picture_quality` | 画质芯片/AI 画质引擎 | 画质芯片、处理器、AI 画质参数 |
| `TV_CLAIM_4K_CLARITY` | `picture_quality` | 4K/高清/蓝光清晰度 | 分辨率 |
| `TV_CLAIM_HIGH_REFRESH_MOTION` | `motion_gaming` | 高刷/MEMC/运动流畅 | 刷新率、MEMC |
| `TV_CLAIM_GAMING_CONNECTIVITY` | `motion_gaming` | HDMI2.1/VRR/低延迟游戏 | HDMI、VRR、ALLM |
| `TV_CLAIM_EYE_CARE_COMFORT` | `eye_care` | 护眼/低蓝光/无频闪 | 护眼、低蓝光、频闪、认证 |
| `TV_CLAIM_DOLBY_IMAX_CERTIFIED` | `audio_cinema` | 杜比/DTS/IMAX 认证 | 音视频认证参数 |
| `TV_CLAIM_AUDIO_HARDWARE_SOUND` | `audio_cinema` | 音响硬件/声道/低音/环绕 | 声道、功率、扬声器 |
| `TV_CLAIM_AI_VOICE_SMART` | `smart_interaction` | AI 语音/大模型交互 | AI、语音、远场语音 |
| `TV_CLAIM_OS_NO_AD_SMOOTH` | `smart_interaction` | 无广告/系统流畅/秒开 | 系统类参数辅助；多数为宣传事实 |
| `TV_CLAIM_CASTING_IOT_CONNECTIVITY` | `smart_interaction` | 投屏/互联/WiFi/接口 | 投屏、WiFi、HDMI、USB |
| `TV_CLAIM_PERFORMANCE_MEMORY_CHIP` | `performance` | 芯片/内存/存储/运行性能 | CPU、RAM、ROM |
| `TV_CLAIM_CAMERA_VIDEO_CALL` | `smart_interaction` | 摄像头/视频通话/体感 | 摄像头参数 |
| `TV_CLAIM_THIN_FULLSCREEN_DESIGN` | `appearance` | 超薄/全面屏/金属美学 | 厚度、全面屏、外观参数 |
| `TV_CLAIM_WALL_MOUNT_FLUSH` | `appearance` | 贴墙/壁挂/平嵌 | 无缝贴墙、安装形态 |
| `TV_CLAIM_ENERGY_SAVING` | `energy_value` | 能效/省电/低碳 | 能效等级、功耗 |
| `TV_CLAIM_PRICE_VALUE` | `energy_value` | 性价比/补贴/价格价值 | 不作为参数事实，市场判断后置 |
| `TV_CLAIM_CONTENT_ECOSYSTEM` | `content_ecosystem` | 内容生态/会员/高码率片源 | 不作为硬件参数事实 |
| `TV_CLAIM_AUTHORITY_CERTIFICATION` | `authority` | 行业地位/认证/销量背书 | 不作为产品参数事实 |
| `TV_CLAIM_SERVICE_FULFILLMENT` | `service_separate` | 安装/送装/售后服务 | 服务隔离 |

### 7.2 TV 维度位置规则

#### 画质

| `position_code` | 规则摘要 |
| --- | --- |
| `picture_miniled_composite_flagship` | Mini LED 且至少命中分区控光、高亮 HDR、画质引擎、广色域/色准中的 3 类 |
| `picture_miniled_control_upgrade` | Mini LED 或控光成立，但复合旗舰条件不足 |
| `picture_quantum_color_upgrade` | 量子点/广色域/色准为主，Mini LED 旗舰条件不足 |
| `picture_anti_reflection_wide_angle` | 低反、防眩、类纸屏、广视角为主 |
| `picture_basic_4k_clear` | 主要是 4K、高清、清晰度 |
| `picture_claim_weak_or_unspecified` | 无明显画质标准卖点 |

#### 游戏运动

| `position_code` | 规则摘要 |
| --- | --- |
| `gaming_console_interface` | HDMI2.1、VRR、ALLM、主机游戏接口成立 |
| `gaming_advanced_high_refresh` | 240Hz 及以上、288/300/360/1000Hz 等高阶高刷 |
| `gaming_high_refresh_experience` | 120/144Hz 高刷并关联游戏体验 |
| `sports_motion_smooth` | MEMC、运动补偿、体育观赛为主 |
| `gaming_basic_high_refresh` | 有高刷但缺少游戏/接口锚点 |
| `gaming_weak_or_unspecified` | 游戏运动卖点弱或未明确 |

#### 智能交互

| `position_code` | 规则摘要 |
| --- | --- |
| `smart_full_scene_iot` | AI 语音 + 系统 + 投屏/互联多项成立 |
| `smart_ai_voice_smooth_os` | AI 语音和系统流畅成立 |
| `smart_no_ads_smooth_os` | 无广告、秒开、系统流畅为主 |
| `smart_senior_friendly_voice` | 长辈、儿童、极简、免遥控与语音相关 |
| `smart_casting_connectivity` | 投屏、NFC、跨屏、接口连接为主 |
| `smart_camera_gesture` | 摄像头、视频通话、体感 |
| `smart_weak_or_unspecified` | 智能卖点弱或未明确 |

#### 音频

| `position_code` | 规则摘要 |
| --- | --- |
| `audio_cinema_certified_hardware` | 杜比/DTS/IMAX 等认证 + 音响硬件 |
| `audio_bass_surround_soundbar` | 低音、环绕、回音壁、品牌音响 |
| `audio_speaker_channel_power` | 扬声器、声道、功率 |
| `audio_dolby_dts_certified` | 只有认证类音频卖点 |
| `audio_weak_or_unspecified` | 音频卖点弱或未明确 |

#### 外观

| `position_code` | 规则摘要 |
| --- | --- |
| `appearance_flush_wall_mount` | 贴墙、壁挂、平嵌、无缝安装 |
| `appearance_thin_metal_design` | 超薄、金属、一体成型 |
| `appearance_home_aesthetic` | 家居美学、艺术壁纸、质感 |
| `appearance_fullscreen_narrow_bezel` | 全面屏、窄边、高屏占比 |
| `appearance_weak_or_unspecified` | 外观卖点弱或未明确 |

## 8. Repository 与服务设计

### 8.1 主要组件

| 组件 | 职责 |
| --- | --- |
| `ClaimTaxonomyLoader` | 按 `product_category` 加载已发布 taxonomy |
| `ClaimEvidenceReader` | 读取 M02 promo evidence |
| `SkuParamProfileReader` | 读取 M03B SKU 参数画像和维度档位 |
| `ClaimTextMatcher` | 标准卖点文本匹配 |
| `ClaimParamSupportEvaluator` | 参数支撑评分和状态判断 |
| `ClaimPositionClassifier` | 计算 claimed/supported position |
| `SkuClaimFactProfileBuilder` | 聚合 SKU 卖点画像 |
| `ClaimFactProfileRepository` | 写入 profile/fact/position/coverage |
| `M04CClaimFactProfileRunner` | 编排批量运行 |

### 8.2 幂等写入

所有输出必须使用业务键和 hash 幂等写入：

```text
business_key + taxonomy_version + rule_version
```

同业务键 hash 一致则复用；hash 不一致且未 `force_rebuild` 时阻断并返回冲突；`force_rebuild` 时标记旧记录 `is_current=false` 后写新记录。

### 8.3 分批处理

虽然当前 TV 卖点只有 4,229 行，但实现必须按 SKU 分批：

| 参数 | 默认 |
| --- | ---: |
| `sku_chunk_size` | 200 |
| `max_claim_texts_per_sku` | 50 |
| `max_evidence_ids_per_fact` | 50 |

避免后续评论级或大规模卖点数据进入时把 205 内存打满。

## 9. CLI 设计

### 9.1 `catforge_pipeline`

新增写入命令：

```bash
python -m app.cli.catforge_pipeline run-claim-profile \
  --product-category tv \
  --batch-id latest \
  --force-rebuild \
  --format json
```

自然语言路由：

| 用户说法 | 路由 |
| --- | --- |
| 生成彩电 SKU 卖点画像 | `run-claim-profile --product-category tv` |
| 重跑电视卖点事实画像 | `run-claim-profile --product-category tv --force-rebuild` |
| 生成空调卖点画像 | `run-claim-profile --product-category ac` |
| 数据准备好可以分析 | 后续可串联 M00+M01+M02+M03B+M04C |

输出：

```json
{
  "status": "ok",
  "product_category": "TV",
  "batch_id": "m00_...",
  "taxonomy_version": "tv_claim_taxonomy_manual_v0.1",
  "rule_version": "m04c_claim_fact_profile_v0.1",
  "sku_profile_count": 328,
  "claim_fact_count": 0,
  "dimension_position_count": 0,
  "position_coverage_count": 0,
  "warnings": []
}
```

### 9.2 `catforge_insight`

新增只读命令：

```bash
python -m app.cli.catforge_insight claim-taxonomy --product-category tv --format json
python -m app.cli.catforge_insight sku-claim-profile --query 75E8Q --format json
python -m app.cli.catforge_insight claim-position-coverage --product-category tv --dimension-code picture_quality --position-code picture_miniled_composite_flagship --sku-limit 100 --format json
```

自然语言查询：

| 用户说法 | 输出 |
| --- | --- |
| 查某 SKU 的卖点画像 | SKU 卖点画像 |
| 某 SKU 哪些卖点有参数支撑 | 过滤 `param_support_status in supported/partially_supported` |
| 某 SKU 哪些卖点只有宣传没有参数支撑 | 过滤 `param_unknown/unsupported/conflicted` |
| 查彩电标准卖点 | taxonomy |
| 查 MiniLED 复合画质旗舰覆盖 SKU | coverage |

## 10. Claude Code Skill 设计

可以扩展现有 `catforge-pipeline` 和 `catforge-insight` skill，也可以新增：

```text
tools/claude/skills/catforge-claim-profile/SKILL.md
```

Skill 规则：

1. 用户说“生成/重跑/更新卖点画像”时使用 `catforge_pipeline run-claim-profile`。
2. 用户说“查某 SKU 卖点画像/标准卖点/覆盖 SKU”时使用 `catforge_insight`。
3. 不向用户暴露 M04C 编号，除非用户主动问技术实现。
4. 回答必须区分：
   - 结构化卖点存在。
   - 参数支撑成立。
   - 评论验证尚未判断。
   - 溢价卖点尚未判断。
5. 遇到服务履约卖点时说明“服务隔离，不作为产品主卖点”。

## 11. API 设计

后续可加 API，但 CLI/skill 是首要交付。

建议端点：

```text
POST /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/claim-fact-profiles/run
GET  /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/claim-fact-profile
GET  /api/mvp/core3/v2/projects/{project_id}/claim-taxonomies/{product_category}
GET  /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/claim-position-coverage
```

## 12. 测试设计

### 12.1 单元测试

| 测试 | 目的 |
| --- | --- |
| taxonomy loader validates unique claim codes | taxonomy 合法性 |
| matcher handles multiple claims per text | 一条卖点可多标签 |
| matcher does not treat 媲美 OLED as OLED fact | 防误判 |
| service claim is separated | 服务隔离 |
| param support supported | 参数支撑成立 |
| param support unknown | 参数缺失不判否 |
| param conflict requires review | 参数冲突复核 |
| param support level broad generic | 只有泛参数支撑时输出 `broad_generic_support` |
| wtp input guard blocks generic claim | 泛参数支撑的具体卖点输出 `blocked_generic_param` |
| dolby cannot be supported only by hdr | 杜比/影音认证不能只凭 HDR 成为用户支付价值可用卖点 |
| same source param group merges chip claims | 芯片/画质芯片同源同参时输出同一分组和代表卖点 |
| claimed position can differ from supported position | 宣称位置和支撑位置分离 |
| coverage aggregates SKU lists | 覆盖索引正确 |

### 12.2 CLI 测试

| 测试 | 目的 |
| --- | --- |
| `run-claim-profile --product-category tv` | 写入 TV 画像 |
| `run-claim-profile --product-category ac` without taxonomy | 阻断并提示 taxonomy 未发布 |
| `ask "生成彩电卖点画像"` | 自然语言路由 |
| `sku-claim-profile --query` | 查询 SKU |
| `claim-position-coverage --query` | 查询覆盖 |

### 12.3 205 验收

TV 当前基线：

| 项 | 期望 |
| --- | --- |
| 结构化 TV 卖点型号 | 328 |
| TV 卖点行 | 4,229 |
| taxonomy 覆盖率 | >= 95% |
| 服务隔离 | 安装、送装、售后不进入产品主事实 |
| 参数支撑 | 有 M03B 参数画像则输出支撑状态；缺 M03B 不阻断 |
| CLI 查询 | 支持 SKU、taxonomy、position coverage |

## 13. 迁移顺序建议

1. 写入 TV claim taxonomy asset。
2. 新增 M04C 表迁移和 ORM。
3. 实现 taxonomy loader、matcher、param support evaluator、position classifier。
4. 实现 M04C runner。
5. 扩展 `catforge_pipeline` 写入 CLI。
6. 扩展 `catforge_insight` 查询 CLI。
7. 更新 Claude Code skill。
8. 本地单元测试。
9. 推送 GitHub。
10. 205 hotfix 同步并全量跑 TV 卖点画像。

## 14. 风险与约束

| 风险 | 处理 |
| --- | --- |
| 卖点文本是营销写法 | 只作为 claimed claim，必须用参数支撑转 fact claim |
| “媲美 OLED”等比较词误判 | taxonomy 配置 negative patterns |
| M03B 参数画像少于卖点 SKU | 画像照常生成，参数支撑标记 unknown |
| 服务履约混入产品卖点 | `service_separate_flag` 隔离 |
| 多品类 taxonomy 混用 | 按 product_category 加载，缺失即阻断 |
| 旧 M04a/M04b 结果干扰 | M04C 不读取旧表 |
| 后续大数据量 | 按 SKU 分批处理、限制 evidence 展示长度 |
