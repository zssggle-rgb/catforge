# M00 原始数据登记当前实现说明

本文档记录 `hotfix/data-preprocess-20260618` 分支中 M00 的当前实现。M00 不是清洗模块，也不产出业务事实；它负责把原始表变化登记成可追踪、可增量重算的 source batch。

## 1. 模块定位

M00 的职责：

- 扫描 4 张原始表。
- 生成 source batch。
- 为每一行原始数据建立稳定行标识、字段存在性快照和行 hash。
- 判断原始行是新增、更新、未变化、跳过，或上一批次有但本次未见。
- 聚合受影响 SKU，告诉后续哪些 SKU 需要重算。
- 记录 schema、水位、质量提示和影响模块摘要。

M00 不做：

- 不清洗字段值。
- 不判断评论是否有效。
- 不生成 `core3_clean_*` 清洗事实。
- 不生成 evidence。
- 不生成用户画像、目标客群、价值战场和竞品结论。

## 2. 输入边界

M00 当前读取 4 张原始表：

```text
week_sales_data
attribute_data
selling_points_data
comment_data
```

每张表默认用 `id` 作为来源主键，用 `model_code` 作为 SKU 候选值，用 `model`、`brand`、`category`、`write_time` 作为通用字段。

业务键字段：

| 原始表 | 业务键字段 |
| --- | --- |
| `week_sales_data` | `date_value`, `channel`, `platform` |
| `attribute_data` | `attr_name`, `attr_value` |
| `selling_points_data` | `variable`, `selling_point` |
| `comment_data` | `comment_id`, `comment_content`, `comments_segments`, `primary_dim`, `secondary_dim`, `third_dim`, `sentiment` |

行 hash 字段覆盖 SKU、品类、品牌、型号、业务字段和 `write_time`。hash 版本为：

```text
m00_row_hash_v1
```

## 3. 输出边界

M00 写入：

```text
core3_source_batch
core3_source_row_registry
core3_source_impacted_sku
```

`core3_source_batch` 记录批次状态、水位、schema 快照、行数统计、质量汇总和影响模块汇总。

`core3_source_row_registry` 记录每一行原始数据的：

- `source_table`
- `source_pk`
- `source_row_id`
- `row_hash`
- `business_key_json`
- `source_field_presence_json`
- `operation_type`
- `change_reason`
- `affected_modules`
- `quality_hint`
- `review_required`

`core3_source_impacted_sku` 聚合本批次受影响 SKU：

- 哪些原始表变化。
- 哪些模块需要重算。
- 每张表新增/更新/缺失的行数。
- 是否需要人工复核。

## 4. 变化判断规则

M00 当前使用如下操作类型：

| 操作类型 | 含义 |
| --- | --- |
| `insert` | 历史成功批次未登记过该来源行，本批新增 |
| `update` | 与上一成功批次同来源行 hash 不一致 |
| `no_change` | 与上一成功批次同来源行 hash 一致 |
| `not_seen_in_current_scan` | 上一成功批次存在，本次全量扫描未见 |
| `skipped` | 缺少来源主键或无法稳定登记 |

缺少 `id` 的原始行不会进入业务事实，只会形成质量提示：

```text
missing_source_pk
```

缺少 SKU 候选值会形成：

```text
missing_sku_code_candidate
```

缺少 `write_time` 会形成：

```text
missing_write_time
```

## 5. 批次模式

M00 支持 `full` 和 `incremental`。

`incremental` 默认使用上一成功批次水位：

- 新 `id` 范围：`id > previous_max_id`
- 已有 `id` 的更新：`id <= previous_max_id` 且 `write_time > previous_max_write_time`

如果请求增量但没有上一成功批次，自动退化为全量扫描，并在批次水位中记录：

```text
fallback_reason = no_previous_success_batch
```

## 6. 大数据保护

M00 当前按原始行 chunk 扫描，默认：

```text
M00_DEFAULT_ROW_CHUNK_SIZE = 5000
```

每个 chunk 写入后会 `flush` 并 `commit`，避免一次性把上百万原始行对象长期留在进程内存中。

在 205 上大批量执行时，仍应避免并发跑多个重处理任务。CLI 的 `prepare-new-data` 默认先跑 M00，再把目标 SKU 分批交给 M01/M02。

## 7. 质量口径

M00 的质量信息是“来源登记质量”，不是业务结论。

当前质量提示包括：

- `missing_source_pk`
- `missing_sku_code_candidate`
- `missing_write_time`
- `source_schema_changed`
- `write_time_watermark_regressed`
- `selling_points_sparse_coverage`
- `not_seen_in_current_scan`

这些提示的作用是告诉后续模块是否需要谨慎处理，不代表 SKU 本身好坏，也不代表某项产品能力不存在。

## 8. 影响模块映射

M00 根据原始表变化映射后续重算范围：

- `week_sales_data` 影响 M01、M02、市场画像、召回、评分、选择和报告链路。
- `attribute_data` 影响 M01、M02、参数画像、卖点激活、画像、召回、评分、选择和报告链路。
- `selling_points_data` 影响 M01、M02、基础卖点、卖点评论验证、画像、召回、评分、选择和报告链路。
- `comment_data` 影响 M01、M02、评论证据、评论信号、卖点评论验证、画像、召回、评分、选择和报告链路。

对业务用户不需要展示完整模块号，只需要解释为：

```text
本批原始数据中该 SKU 有新增或变化，后续相关分析需要重算。
```

## 9. 执行入口

CLI 推荐入口：

```bash
python -m app.cli.catforge_data prepare-new-data --register-source-batch incremental --format json
```

只登记源批次的 API 入口：

```text
POST /api/mvp/core3/v2/projects/{project_id}/source-batches/register
```

核心实现：

- `apps/api-server/app/services/core3_real_data/source_registry_service.py`
- `apps/api-server/app/services/core3_real_data/source_registry_repositories.py`

测试覆盖：

- `apps/api-server/tests/core3_real_data/test_m00_source_registry_runner.py`
- `apps/api-server/tests/core3_real_data/test_catforge_data_cli.py`

## 10. 当前已知边界

- M00 不判断评论内容质量，评论过滤在 M01。
- M00 不生成清洗表，M01 才会生成 `core3_clean_*`。
- M00 不保证所有缺失都是问题，只记录缺失和变化事实。
- M00 当前没有跨进程锁，外部调度需避免同项目同批次并发登记。
