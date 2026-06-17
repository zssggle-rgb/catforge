# M01 清洗规范化与质量诊断 SOP 需求

## 0. 单模块强化状态

本文件已按“单模块逐一强化”要求完成第一轮强化。下一步应处理 M02 Evidence 原子层。

## 1. 模块目标

M01 把 M00 登记的原始行转换为可被后续模块稳定消费的清洗事实表，并输出数据质量诊断。

M01 要解决四个问题：

1. 原始表字段不统一，先转换成统一的 SKU、市场、参数、卖点、评论清洗表。
2. 原始值存在空值、`unknown`、`-`、重复、拆行、默认评论等问题，先做质量标记。
3. 后续模块需要增量处理，M01 必须生成 clean hash 判断清洗结果是否变化。
4. 所有清洗结果必须保留 `batch_id`、`source_row_id` 和原始值，保证 evidence 可追溯。

M01 只做通用清洗和质量诊断，不生成标准参数、标准卖点、用户任务、目标客群、价值战场或竞品结论。

## 2. 设计依据

本模块依据：

- `cankao/CatForge_竞品生成SOP_详细指导_v1.md` 的 M01 要求。
- `cankao/catforge_sop_md/modules/M01_清洗规范化与质量诊断.md`。
- [00 真实样例数据基线](00_real_data_baseline.md)。
- M00 已强化后的批次、来源行、row hash、水位和受影响模块设计。
- 已确认的数据分层原则：原始表只读，清洗表单独保存，下游不直接读取原始表做业务判断。

## 3. 上游输入

M01 消费 M00 的输出：

| 上游产物 | 用途 |
| --- | --- |
| `core3_source_batch` | 确认批次、来源表、水位和批次状态 |
| `core3_source_row_registry` | 确认本次新增、变化、未变化、跳过的来源行 |
| `core3_source_impacted_sku` | 确认受影响 SKU 候选和建议触发模块 |
| 四张原始表 | 按 `source_row_id` 读取原始行内容 |

日常增量模式下，M01 只处理 M00 标记为 `insert`、`update`、`not_seen_in_current_scan` 或 `skipped` 的相关记录。全量重建模式下，可以按批次重跑所有 current rows。

## 4. 本模块不做什么

- 不修改 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data`。
- 不做标准参数归一，标准参数由 M03 负责。
- 不做标准卖点激活，基础卖点由 M04a 负责，评论增强由 M04b 负责。
- 不从评论中抽取用户任务、客群、战场或卖点信号，M05/M06 负责。
- 不把缺失、空值、`-`、`unknown` 当成 false。
- 不删除低价值评论、重复评论或卖点缺失 SKU，只做标记。
- 不生成业务 evidence，M02 负责。

## 5. 清洗总原则

| 原则 | 要求 |
| --- | --- |
| 保留原值 | 每条清洗事实都保留 raw 字段和 `source_row_id` |
| 规范字段 | 输出统一字段名、类型、状态和 hash |
| 缺失即未知 | unknown/空值/`-`/null 标记为 unknown，不当 false |
| 不丢数据 | 无法用于分析的行也要通过质量问题说明原因 |
| 弱标签保留 | 原始评论维度、情感、卖点标题只作为弱标签保留 |
| 可增量 | 每条清洗结果生成 `clean_hash`，用于判断是否触发下游 |
| 可复核 | 所有异常、冲突、覆盖不足都进入质量诊断 |

## 6. 清洗处理流程

1. 读取 M00 批次和行登记，确认本次输入范围。
2. 按 `source_table + source_pk` 回读原始行。
3. 生成跨表 SKU 主数据候选。
4. 分域清洗市场、参数、卖点、评论。
5. 对文本做最小规范化：去首尾空白、统一全半角标点、去不可见字符、保留中文业务原意。
6. 对数值做类型转换和解析失败标记。
7. 对评论和卖点做句级切分准备，但不做语义分类。
8. 识别重复、缺失、冲突、异常、覆盖不足。
9. 写入清洗事实表和质量问题表。
10. 计算 `clean_hash`，输出是否需要触发下游重算。

## 7. SKU 主数据清洗

### 7.1 目标

从四张原始表中形成统一的 SKU 候选清洗表，供后续所有模块使用。

### 7.2 输出表：`core3_clean_sku`

| 字段 | 说明 |
| --- | --- |
| `batch_id` | 批次 |
| `sku_code` | 由 `model_code` 清洗得到，首版等于原值 |
| `model_name` | `model` 清洗展示名 |
| `brand_name` | 品牌清洗值 |
| `category_code` | `彩电` 映射为 `TV` |
| `category_name` | 原始品类展示名 |
| `source_tables` | SKU 出现在哪些原始表 |
| `first_seen_source_row_id` | 首次来源行 |
| `field_conflicts_json` | 跨表品牌、型号、品类冲突 |
| `coverage_json` | 市场/参数/卖点/评论覆盖情况 |
| `quality_status` | ok/warn/error |
| `clean_hash` | 清洗结果 hash |

### 7.3 规则

- `model_code` 为空时，不能生成可信 `sku_code`，但要记录质量问题。
- 同一 `model_code` 在不同表的 `model`、`brand`、`category` 不一致时，不静默覆盖，写入 `field_conflicts_json`。
- 当前真实数据只有 `brand=海信`，M01 只登记事实，不做竞品内外部判断。
- 85E7Q 在市场、参数、评论有覆盖但卖点无覆盖，`coverage_json` 必须准确体现。

## 8. 市场量价清洗

### 8.1 来源

`week_sales_data`

### 8.2 输出表：`core3_clean_market_weekly`

| 字段 | 说明 |
| --- | --- |
| `batch_id` | 批次 |
| `source_row_id` | 来源行 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `brand_name` | 品牌 |
| `category_code` | 品类编码 |
| `period_raw` | 原始周期，如 `26W01` |
| `period_type` | week |
| `period_year_hint` | 年份提示，首版可来自周期前缀 |
| `period_week_index` | 周序号 |
| `channel_raw` | 原始渠道 |
| `channel_type` | 渠道大类，如线上 |
| `platform_raw` | 原始平台 |
| `platform_type` | 平台细分，如专业电商/平台电商 |
| `sales_volume` | 数值化销量 |
| `sales_amount` | 数值化销额 |
| `avg_price` | 数值化均价 |
| `price_check_status` | 均价校验结果 |
| `quality_status` | ok/warn/error |
| `quality_flags` | 质量标签 |
| `clean_hash` | 清洗结果 hash |

### 8.3 规则

- `category=彩电` 映射为 `category_code=TV`。
- `date_value=26W01..26W23` 保留原始周期，同时解析周序号；不要强行推断完整自然日期。
- `channel=线上` 保留为渠道大类，`platform=专业电商/平台电商` 保留为平台细分。
- `sales_volume`、`sales_amount`、`avg_price` 必须数值化，解析失败写质量问题。
- 校验 `avg_price` 与 `sales_amount / sales_volume` 是否一致；销量为 0 时不能除零，应标记不可校验。
- 负销量、负销额、负均价标记为 error。
- 极端价格只标记 outlier，不在 M01 删除。

## 9. 参数清洗

### 9.1 来源

`attribute_data`

### 9.2 输出表：`core3_clean_attribute`

| 字段 | 说明 |
| --- | --- |
| `batch_id` | 批次 |
| `source_row_id` | 来源行 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `brand_name` | 品牌 |
| `category_code` | 品类编码 |
| `raw_attr_name` | 原始属性名 |
| `clean_attr_name` | 文本规范化后的属性名 |
| `raw_attr_value` | 原始属性值 |
| `clean_attr_value` | 文本规范化后的属性值 |
| `value_presence` | present/unknown/empty |
| `value_number_candidate` | 可见数字候选 |
| `value_unit_candidate` | 可见单位候选 |
| `quality_status` | ok/warn/error |
| `quality_flags` | 质量标签 |
| `clean_hash` | 清洗结果 hash |

### 9.3 规则

- `attr_name` 只做文本规范化，不映射标准参数。标准参数编码由 M03 负责。
- `attr_value` 为 null、空字符串、`-`、`unknown`、`未知`、`暂无` 时，`value_presence=unknown`。
- unknown 不是 false。例如 `MINILED` 缺失不能解释为“不是 MiniLED”。
- 可以提取数字和单位候选，如 `300HZ` 拆出 `300` 和 `HZ`，但不做标准单位换算。
- 同一 SKU 同一属性名出现多个不同值时，记录冲突，交给 M03/M16 处理。
- 当前 `attribute_data` unknown/空值/`-` 约 961 行，M01 必须统计缺失比例。

## 10. 卖点清洗

### 10.1 来源

`selling_points_data`

### 10.2 输出表：`core3_clean_claim`

| 字段 | 说明 |
| --- | --- |
| `batch_id` | 批次 |
| `source_row_id` | 来源行 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `brand_name` | 品牌 |
| `category_code` | 品类编码 |
| `claim_seq_raw` | 原始变量位，如卖点1 |
| `claim_seq` | 数字序号 |
| `raw_claim_text` | 原始卖点文本 |
| `clean_claim_text` | 清洗后文本 |
| `title_hint` | 标题型结构候选 |
| `quality_status` | ok/warn/error |
| `quality_flags` | 质量标签 |
| `clean_hash` | 清洗结果 hash |

### 10.3 输出表：`core3_clean_claim_sentence`

| 字段 | 说明 |
| --- | --- |
| `batch_id` | 批次 |
| `source_row_id` | 来源行 |
| `sku_code` | SKU |
| `claim_seq` | 卖点序号 |
| `sentence_seq` | 句序号 |
| `sentence_text` | 切分后的句子 |
| `sentence_role_hint` | 标题/正文/数值描述等弱提示 |
| `quality_status` | ok/warn/error |

### 10.4 规则

- `variable=卖点1..卖点13` 保留顺序，解析失败时保留原值并标记。
- `selling_point` 去 HTML、去多余空白、保留业务文本。
- 按中文标点、换行、括号标题、冒号等切句。
- “核心定位、功能价值、情感价值、便捷体验、差异化定位、行业地位”等只作为 `title_hint` 或 `sentence_role_hint`，不能直接当最终卖点结论。
- 当前卖点只覆盖 5/35 个型号，未覆盖型号是“卖点数据缺失”，不是“没有卖点”。
- 85E7Q 没有结构化卖点行，M01 必须在 SKU 覆盖和质量诊断中体现。

## 11. 评论清洗

### 11.1 来源

`comment_data`

### 11.2 输出表：`core3_clean_comment`

| 字段 | 说明 |
| --- | --- |
| `batch_id` | 批次 |
| `source_row_id` | 来源行 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `brand_name` | 品牌 |
| `category_code` | 品类编码 |
| `platform_raw` | 原始平台 |
| `url_id` | 原始链接或商品页标识 |
| `comment_id` | 原始评论 ID |
| `comment_time_raw` | 原始评论时间 |
| `comment_time` | 规范化评论时间 |
| `raw_comment_text` | 原始评论正文 |
| `clean_comment_text` | 清洗正文 |
| `comment_text_hash` | 正文 hash |
| `segment_text_raw` | 原始分段 |
| `segment_text_hash` | 分段 hash |
| `sentiment_raw` | 原始情感 |
| `sentiment_clean` | 正面/中立/负面/unknown |
| `low_value_flag` | 是否低价值文本 |
| `duplicate_group_key` | 重复组键 |
| `quality_status` | ok/warn/error |
| `quality_flags` | 质量标签 |
| `clean_hash` | 清洗结果 hash |

### 11.3 输出表：`core3_clean_comment_sentence`

| 字段 | 说明 |
| --- | --- |
| `batch_id` | 批次 |
| `source_row_id` | 来源行 |
| `sku_code` | SKU |
| `comment_id` | 评论 ID |
| `sentence_seq` | 句序号 |
| `sentence_text` | 系统切分句 |
| `source_segment_text` | 原始 `comments_segments` |
| `is_from_existing_segment` | 是否来自原始分段 |
| `quality_status` | ok/warn/error |

### 11.4 输出表：`core3_clean_comment_dimension`

| 字段 | 说明 |
| --- | --- |
| `batch_id` | 批次 |
| `source_row_id` | 来源行 |
| `sku_code` | SKU |
| `comment_id` | 评论 ID |
| `primary_dim_raw` | 原始一级维度 |
| `secondary_dim_raw` | 原始二级维度 |
| `third_dim_raw` | 原始三级维度 |
| `dimension_path_raw` | 原始维度路径 |
| `dimension_available` | 是否有维度 |
| `dimension_quality_flag` | 空维度/弱标签/疑似拆行 |

### 11.5 规则

- 保留 `comment_content` 原文和清洗正文。
- “此用户没有填写评价”“默认好评”等标记为低价值，不删除。
- `comments_segments` 是已有分段参考，不替代系统分句。
- `primary_dim/secondary_dim/third_dim` 只作为弱标签另存，不直接生成任务、客群、战场或卖点。
- `sentiment` 为空时标记为 unknown，不能当中立。
- 同一 `comment_id` 多行、同一正文多行、同一分段多行，都应保留重复依据，供 M05 做评论 evidence 去重。
- 当前 `comment_data` 62426 行、34438 个不同 `comment_id`、13514 个正文 hash，M01 必须输出重复率和拆行提示。

## 12. 数据质量诊断

### 12.1 输出表：`core3_data_quality_issue`

| 字段 | 说明 |
| --- | --- |
| `issue_id` | 问题 ID |
| `batch_id` | 批次 |
| `source_row_id` | 来源行 |
| `sku_code` | SKU |
| `module_code` | M01 |
| `domain` | sku/market/attribute/claim/comment |
| `issue_type` | 问题类型 |
| `severity` | info/warn/error |
| `issue_detail` | 中文说明 |
| `suggested_downstream_action` | 给下游的处理建议 |
| `created_at` | 创建时间 |

### 12.2 质量问题类型

| 问题类型 | 触发场景 | 严重度建议 |
| --- | --- | --- |
| `missing_required_field` | 来源主键、SKU、核心事实字段缺失 | error/warn |
| `invalid_number` | 销量、销额、均价无法数值化 | error |
| `price_check_mismatch` | 均价与销额/销量偏差过大 | warn |
| `unknown_value` | 参数值为空、unknown、`-` | info/warn |
| `claim_coverage_missing` | SKU 没有结构化卖点 | warn |
| `low_value_comment` | 默认评价、空评价、无实际内容 | info |
| `duplicate_comment_text` | 评论正文重复 | info/warn |
| `comment_dimension_missing` | 评论维度为空 | info |
| `cross_table_conflict` | 同一 SKU 品牌、型号、品类冲突 | warn/error |
| `schema_changed` | M00 发现原始字段变化 | warn/error |

## 13. 增量重算要求

每条清洗事实生成 `clean_hash`。判断逻辑：

```text
same source_row_id + same clean_hash = clean_no_change
same source_row_id + different clean_hash = clean_changed
new source_row_id = clean_insert
not_seen_in_current_scan = clean_inactive_candidate
```

触发下游建议：

| 清洗变化 | 建议触发 |
| --- | --- |
| SKU 主数据变化 | M02-M16 |
| 市场清洗变化 | M02、M07、M08-M16 |
| 参数清洗变化 | M02、M03、M04a、M08-M16 |
| 卖点清洗变化 | M02、M04a、M04b、M08-M16 |
| 评论清洗变化 | M02、M05、M06、M04b、M08-M16 |
| 仅质量标签变化 | M02 置信度、M16 复核 |

M01 不直接调度下游，由 M16 根据 M01 输出决定。

## 14. 与下游模块关系

### 给 M02 的承诺

- M02 可以从清洗表生成 evidence。
- 每条清洗事实都有 `source_row_id`、原始值、清洗值和质量状态。
- 质量问题可影响 evidence 置信度。

### 给 M03 的承诺

- 参数表保留原始属性名、清洗属性名、原始值、清洗值、数字候选和单位候选。
- M01 不提供标准参数编码。

### 给 M04a/M04b 的承诺

- 卖点表保留原始宣传文本、清洗文本、切句结果和标题弱提示。
- 评论相关卖点验证只能使用 M05/M06 后续结果，M01 不直接提供语义验证。

### 给 M05/M06 的承诺

- 评论表保留原文、清洗正文、正文 hash、分段 hash、句级文本、弱维度标签和情感原值。
- M01 不把维度标签变成业务标签。

### 给 M07 的承诺

- 市场表提供数值化量价、周期原值、周序号、渠道和平台清洗值。
- 价格异常只做标记，不直接删除。

### 给 M16 的承诺

- M16 可以基于 clean hash、质量问题和覆盖诊断决定增量重算和复核。

## 15. 真实数据约束

当前 205 样例数据对 M01 的硬约束：

- `attribute_data` 共 2843 行，unknown/空值/`-` 约 961 行，缺失必须解释为 unknown。
- `selling_points_data` 只覆盖 5 个型号，M01 必须把未覆盖型号标记为卖点数据缺失。
- `85E7Q` 有 46 行周销、81 行属性、0 行卖点、3621 行评论，应被识别为“可分析但卖点结构化缺失”。
- `comment_data` 行数大于评论正文去重数，清洗必须保留去重依据，而不是直接去重丢行。
- 评论维度中空维度数量高，维度只能作为弱标签。
- 当前渠道只有线上，平台只有专业电商和平台电商，M01 不生成线下渠道。
- 所有数据当前品牌为海信，M01 不做竞品内外部判断。

## 16. 复核触发条件

M01 应向 M16 输出复核或 warning：

- 某 SKU 在市场、参数、卖点、评论覆盖明显缺失。
- 关键字段无法清洗，例如 SKU 为空、量价无法数值化。
- 同一 SKU 跨表品牌、型号、品类冲突。
- 参数 unknown 比例异常。
- 卖点覆盖型号数异常下降。
- 评论重复率异常升高。
- 评论低价值文本占比异常。
- 原始维度为空比例异常。
- clean hash 变化数量异常高。

## 17. 验收标准

| 验收项 | 标准 |
| --- | --- |
| 生成 SKU、市场、参数、卖点、评论清洗表 | 必须 |
| 每条清洗事实保留 `source_row_id` | 必须 |
| 原始值和清洗值同时保留 | 必须 |
| unknown 不被当成 false | 必须 |
| 卖点未覆盖不被判断为无卖点 | 必须 |
| 评论弱维度保留但不直接生成业务结论 | 必须 |
| 评论重复和拆行依据可供 M05 使用 | 必须 |
| 市场量价数值化并输出校验状态 | 必须 |
| 每条清洗事实有 `clean_hash` | 必须 |
| 数据质量问题可按 SKU、表、批次查询 | 必须 |
| M01 不生成业务 evidence 或竞品结论 | 必须 |
