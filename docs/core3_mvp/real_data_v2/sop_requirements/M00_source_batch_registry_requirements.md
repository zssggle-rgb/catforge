# M00 原始数据批次与行登记 SOP 需求

## 0. 单模块强化状态

本文件已按“单模块逐一强化”要求完成第一轮强化。下一步应处理 M01 清洗规范化与质量诊断。

## 1. 模块目标

M00 为每次真实数据接入建立稳定的数据边界，回答三个问题：

1. 本次扫描了哪些原始表、哪些时间范围、多少行数据。
2. 哪些原始行是新增、变化、未变化、疑似失效或跳过。
3. 哪些 SKU 受影响，后续应该触发哪些模块重算。

M00 只做“数据接入登记”和“增量边界判断”，不做清洗、不做语义抽取、不做竞品判断。它是 M01 清洗、M02 evidence、M16 增量编排的共同入口。

## 2. 设计依据

本模块依据：

- `cankao/CatForge_竞品生成SOP_详细指导_v1.md` 的 M00 要求。
- `cankao/catforge_sop_md/modules/M00_原始数据批次与行登记.md`。
- [00 真实样例数据基线](00_real_data_baseline.md)。
- 已确认的数据分层原则：原始表只读，清洗表、证据表、抽取表、画像表、结果表分层保存。

## 3. 上游输入

M00 读取 205 PostgreSQL `catforge_dev` 中的原始表或原始视图。当前 MVP 原始表为：

| 原始表 | 业务含义 | 当前样例规模 | 关键特点 |
| --- | --- | ---: | --- |
| `week_sales_data` | 周销量、销额、均价 | 1326 行 | 35 个型号，26W01-26W23，线上渠道，专业电商/平台电商 |
| `attribute_data` | SKU 参数属性 | 2843 行 | 35 个型号，84 类属性，unknown/空值/`-` 较多 |
| `selling_points_data` | 结构化宣传卖点 | 65 行 | 只覆盖 5 个型号，变量为卖点1..卖点13 |
| `comment_data` | 评论、评论分段、维度、情感 | 62426 行 | 33 个型号，存在维度拆行、重复正文、空维度和默认评价 |

M00 不要求四张表字段完全一致，只要求能从每张表提取来源主键、SKU 候选、写入时间和行内容。

## 4. 本模块不做什么

- 不清洗字段值。
- 不把 `model_code` 改名成标准 SKU。
- 不识别 unknown、false、空值的业务含义。
- 不做参数归一、卖点激活、评论去重或评论分类。
- 不生成业务 evidence。
- 不判断用户任务、客群、价值战场或竞品。
- 不修改原始表。

## 5. 原始字段映射要求

M00 只做来源登记，因此字段映射以“能稳定追溯”为目标。

| 表 | 来源主键 | SKU 候选 | 展示型号 | 时间字段 | 业务定位字段 |
| --- | --- | --- | --- | --- | --- |
| `week_sales_data` | `id` | `model_code` | `model` | `write_time` | `date_value`、`channel`、`platform` |
| `attribute_data` | `id` | `model_code` | `model` | `write_time` | `attr_name`、`attr_value` |
| `selling_points_data` | `id` | `model_code` | `model` | `write_time` | `variable`、`selling_point` |
| `comment_data` | `id` | `model_code` | `model` | `write_time` | `comment_id`、`comment_content`、`comments_segments`、`primary_dim`、`secondary_dim`、`third_dim`、`sentiment` |

`model_code` 在 M00 中只作为 `sku_code_candidate` 保存。是否成为最终标准 SKU，由 M01/M08 继续确认。

## 6. 行标识与 hash 规则

### 6.1 `source_row_id`

首版稳定规则：

```text
source_row_id = source_table + ':' + source_pk
```

示例：

```text
week_sales_data:123
attribute_data:456
selling_points_data:789
comment_data:10001
```

`source_row_id` 一旦生成，不因清洗规则变化而变化。

### 6.2 `source_pk`

当前四张原始表都有 `id`，因此 `source_pk=id`。如果后续上传方新增没有自增 `id` 的原始表，需要用业务主键生成 `source_pk`，但必须在 M00 输出中记录 `source_pk_strategy`。

### 6.3 `row_hash`

`row_hash` 用于判断同一来源行内容是否变化。计算原则：

- 使用原始表中除技术扫描时间外的业务字段。
- 字段名按固定顺序排序。
- null、空字符串、`-`、`unknown` 不在 M00 转义，只按原值参与 hash。
- 字符串只做最小序列化，不做业务清洗。
- 需要记录 `hash_version`，避免后续规则变化无法解释。

M00 的 hash 只判断“原始行是否变化”，不判断“业务含义是否变化”。

## 7. 批次类型

M00 支持两类批次：

| 批次类型 | 使用场景 | 处理要求 |
| --- | --- | --- |
| `full` | 首次接入、规则重建、人工指定全量扫描 | 扫描四张表全量行，建立完整 row registry |
| `incremental` | 日常新增数据接入 | 基于 `write_time`、`id`、row_hash 和历史登记判断新增/变化 |

每个批次必须记录输入水位，不能只记录运行时间。

## 8. 处理流程

1. 创建 `batch_id`，记录 `batch_type`、`source_system`、`ruleset_version`、运行人或运行任务。
2. 读取四张原始表的字段列表、总行数、`id` 范围、`write_time` 范围。
3. 按表扫描本次需要登记的行。
4. 为每行生成 `source_pk`、`source_row_id`、`row_hash`。
5. 与上一批 row registry 对比，标记 `operation_type`：
   - `insert`：历史不存在。
   - `update`：历史存在但 row_hash 变化。
   - `no_change`：历史存在且 row_hash 未变化。
   - `not_seen_in_current_scan`：全量扫描时历史存在但本次未出现。
   - `skipped`：行缺少来源主键或关键读取字段，无法登记。
6. 聚合受影响 SKU。
7. 计算受影响模块。
8. 输出批次摘要、行登记、受影响 SKU 清单、质量提示。
9. 将批次状态从 `running` 更新为 `registered`；失败则写入 `failed` 和错误原因。

## 9. 受影响 SKU 与模块判断

### 9.1 受影响 SKU

M00 的受影响 SKU 口径：

```text
impacted_sku_codes =
  changed_or_new week_sales_data.model_code
  union changed_or_new attribute_data.model_code
  union changed_or_new selling_points_data.model_code
  union changed_or_new comment_data.model_code
```

缺少 `model_code` 的行不能直接丢弃，应进入 `skipped` 或 `needs_review`，并保留表名、主键和原因。

### 9.2 受影响模块

| 原始表变化 | 直接影响 | 下游连带影响 |
| --- | --- | --- |
| `week_sales_data` | M01、M02、M07 | M08-M16 |
| `attribute_data` | M01、M02、M03 | M04a、M08-M16 |
| `selling_points_data` | M01、M02、M04a | M04b、M08-M16 |
| `comment_data` | M01、M02、M05、M06 | M04b、M08-M16 |

M00 只输出建议影响范围，实际调度由 M16 决定。

## 10. 输出数据契约

### 10.1 `core3_source_batch`

| 字段 | 说明 |
| --- | --- |
| `batch_id` | 本次数据批次 |
| `project_id` | 项目 |
| `category_code` | 品类，MVP 为 TV |
| `batch_type` | full/incremental |
| `source_system` | 数据来源，例如 205 PostgreSQL |
| `source_database` | 来源库标识，不保存敏感连接信息 |
| `source_tables` | 扫描表清单 |
| `ruleset_version` | 登记规则版本 |
| `hash_version` | hash 规则版本 |
| `input_watermark_json` | 每张表输入水位 |
| `row_counts_json` | 每张表扫描行数、登记行数、新增/变化/未变行数 |
| `write_time_range_json` | 每张表 `write_time` 范围 |
| `source_pk_range_json` | 每张表来源主键范围 |
| `impacted_sku_count` | 受影响 SKU 数 |
| `quality_summary_json` | 基础质量摘要 |
| `status` | running/registered/failed |
| `error_message` | 失败原因 |
| `created_at` | 创建时间 |
| `finished_at` | 完成时间 |

### 10.2 `core3_source_row_registry`

| 字段 | 说明 |
| --- | --- |
| `batch_id` | 批次 |
| `source_table` | 原始表 |
| `source_pk` | 原始主键 |
| `source_pk_strategy` | 主键策略 |
| `source_row_id` | 行级唯一 ID |
| `row_hash` | 行内容 hash |
| `hash_version` | hash 规则版本 |
| `sku_code_candidate` | `model_code` 原值 |
| `model_name_raw` | `model` 原值 |
| `brand_raw` | `brand` 原值 |
| `category_raw` | `category` 原值 |
| `write_time` | 原始写入时间 |
| `business_key_json` | 原始业务定位字段 |
| `operation_type` | insert/update/no_change/not_seen_in_current_scan/skipped |
| `affected_modules` | 建议受影响模块 |
| `quality_hint` | 基础可读性问题 |
| `created_at` | 登记时间 |

### 10.3 `core3_source_impacted_sku`

| 字段 | 说明 |
| --- | --- |
| `batch_id` | 批次 |
| `sku_code_candidate` | 受影响 SKU 候选 |
| `model_name_raw` | 型号原值 |
| `source_tables` | 触发变化的原始表 |
| `operation_summary_json` | 新增/变化/跳过数量 |
| `affected_modules` | 建议触发模块 |
| `impact_reason` | 中文影响原因 |

## 11. 基础质量规则

M00 只做接入级质量提示，不做业务清洗。

| 质量提示 | 判断口径 | 处理 |
| --- | --- | --- |
| `missing_source_pk` | 来源主键为空 | 标记 skipped |
| `missing_sku_code_candidate` | `model_code` 为空 | 登记但进入复核 |
| `missing_write_time` | `write_time` 为空 | 登记并提示水位不可用 |
| `duplicate_source_pk_in_scan` | 同一表同一主键重复 | 登记冲突，进入复核 |
| `hash_collision_suspected` | 不同行业务键 hash 异常一致 | 进入复核 |
| `source_schema_changed` | 字段列表较上一批变化 | 批次 warning，通知 M16 |

M00 不把 unknown、空字符串、`-` 转成 false，也不删除默认评论或重复评论。

## 12. 与下游模块关系

### 给 M01 的承诺

- M01 可以按 `batch_id` 读取新增和变化行。
- M01 可以通过 `source_row_id` 回到原始表行。
- M01 可以知道哪些行被 skipped 以及原因。

### 给 M02 的承诺

- M02 使用 `source_row_id` 生成 evidence。
- M00 不生成业务 evidence，但提供 source reference。

### 给 M16 的承诺

- M16 可以按 `batch_id`、`sku_code_candidate`、`affected_modules` 编排增量任务。
- M16 可以基于 `status` 和 `quality_summary_json` 决定是否进入复核。

## 13. 真实数据约束

当前 205 样例数据带来的 M00 约束：

- 原始字段不是统一命名，不能假设已有 `sku_code`。
- 当前只有海信品牌，M00 不做品牌内外判断。
- `selling_points_data` 只覆盖 5 个型号，未覆盖卖点的型号仍必须进入批次登记。
- `comment_data` 行数大且存在拆行，M00 不能在登记阶段去重。
- 评论存在空维度和默认评价，M00 只能登记质量提示，不能过滤。
- `week_sales_data` 的周期是 `date_value`，不是标准日期，M00 只保存原值。
- 渠道当前只有线上，平台有专业电商/平台电商，M00 只登记原值。

## 14. 复核触发条件

以下情况 M00 应向 M16 输出复核或 warning：

- 原始表字段结构发生变化。
- 某张表行数较上一批异常下降。
- 某张表 `write_time` 倒退或为空比例异常。
- 新增行大量缺少 `model_code`。
- 同一表出现重复 `id`。
- row_hash 变化数量异常高。
- `comment_data` 新增行很多但 distinct `comment_id` 很少，提示可能重复导入。

## 15. 验收标准

| 验收项 | 标准 |
| --- | --- |
| 四张原始表可登记 | 必须 |
| 原始表不被修改 | 必须 |
| 每条可读原始行都有 `source_row_id` | 100% |
| `source_row_id` 跨批次稳定 | 必须 |
| `row_hash` 能识别同源行变化 | 必须 |
| full/incremental 批次可区分 | 必须 |
| 每批次有输入水位 | 必须 |
| 能输出受影响 SKU 清单 | 必须 |
| 能输出建议受影响模块 | 必须 |
| skipped 行有原因 | 必须 |
| M00 不生成业务结论 | 必须 |
| M01/M02/M16 可消费输出 | 必须 |
