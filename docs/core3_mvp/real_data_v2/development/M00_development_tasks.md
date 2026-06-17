# M00 原始数据批次与行登记开发任务

## 1. 模块目标

M00 的开发目标是实现真实数据 v2 的原始数据接入登记层，为后续 M01 清洗、M02 evidence 和 M16 增量编排提供稳定入口。

M00 必须实现：

1. 读取四张原始表的 schema、水位和候选扫描行。
2. 创建原始数据扫描批次。
3. 为每条原始行生成稳定 `source_row_id` 和 `row_hash`。
4. 判断 `insert/update/no_change/not_seen_in_current_scan/skipped`。
5. 聚合受影响 SKU 和建议影响模块。
6. 输出接入级质量提示和复核标记。
7. 保证原始表只读，不做清洗、不做 evidence、不做业务结论。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| INFRA 任务 | `docs/core3_mvp/real_data_v2/development/INFRA_development_tasks.md` |
| M00 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M00_source_batch_registry_requirements.md` |
| M00 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M00_source_batch_registry_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| 总体架构 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |

## 3. 本次范围

### 3.1 必须实现

| 能力 | 说明 |
| --- | --- |
| 批次表 | `core3_source_batch` |
| 行登记表 | `core3_source_row_registry` |
| 受影响 SKU 表 | `core3_source_impacted_sku` |
| 原始表只读 repository | 只读 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data` |
| schema snapshot | 字段名、类型、nullable、schema hash |
| 输入水位 | id 范围、write_time 范围、扫描模式 |
| row hash | `m00_row_hash_v1`，保留 null/空/`-`/unknown 语义 |
| operation type | insert/update/no_change/not_seen_in_current_scan/skipped |
| affected modules | 按原始表变化映射 M01-M15 |
| M00 runner | `SourceRegistryRunner.register_batch(...)` |
| M00 查询 API | 运营/技术查看接口，非高层报告接口 |
| 测试 | hash、repository、runner、fixture、API 边界 |

### 3.2 明确不做

M00 不做：

- 不清洗字段值。
- 不把 `model_code` 改成最终 SKU。
- 不识别 unknown/false/空值的业务含义。
- 不做参数归一、卖点激活、评论去重或评论分类。
- 不生成 evidence。
- 不生成任务、客群、战场、候选、评分、竞品和报告。
- 不更新 `core3_pipeline_watermark`，该水位由 M16 验收后更新。
- 不修改原始四表。
- 不改前端页面。
- 不部署 205。

## 4. 要改文件

### 4.1 后端新增文件

```text
apps/api-server/app/services/core3_real_data/source_registry_service.py
apps/api-server/app/services/core3_real_data/source_registry_repositories.py
apps/api-server/app/services/core3_real_data/source_registry_schemas.py
apps/api-server/tests/core3_real_data/test_m00_source_registry_hash.py
apps/api-server/tests/core3_real_data/test_m00_source_registry_repositories.py
apps/api-server/tests/core3_real_data/test_m00_source_registry_runner.py
apps/api-server/tests/core3_real_data/test_m00_source_registry_api.py
```

### 4.2 后端可能修改文件

| 文件 | 修改原因 |
| --- | --- |
| `apps/api-server/app/models/entities.py` | 新增 M00 三张表模型 |
| `apps/api-server/alembic/versions/0006_core3_real_data_source_registry.py` | 新增 M00 表迁移 |
| `apps/api-server/app/schemas/core3_real_data.py` | 增加 M00 请求/响应 schema |
| `apps/api-server/app/api/core3_real_data.py` | 增加 M00 内部/运营 API |
| `apps/api-server/app/main.py` | 若 API_development_tasks 尚未统一注册 v2 router，M00 可暂不注册 |
| `apps/api-server/tests/core3_real_data/conftest.py` | 增加 M00 fixture 和 fake raw repository |

### 4.3 预计引用 INFRA 文件

```text
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/hash_utils.py
apps/api-server/app/services/core3_real_data/run_context.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/app/services/core3_real_data/repositories.py
```

## 5. 不允许改文件

M00 编码阶段不允许修改：

```text
apps/api-server/app/services/core3_mvp/*
apps/factory-web/src/pages/core3/*
apps/factory-web/src/pages/core3RealData/*
apps/factory-web/src/App.tsx
apps/factory-web/src/styles.css
docker-compose.yml
docker-compose.cloud.yml
scripts/deploy.sh
```

不允许修改原始四表结构：

```text
week_sales_data
attribute_data
selling_points_data
comment_data
```

不允许使用 `git add .`。本任务只能 stage 本模块新增或修改的文件。

## 6. 数据库迁移任务

### 6.1 migration 文件

建议新增：

```text
apps/api-server/alembic/versions/0006_core3_real_data_source_registry.py
```

如果 INFRA 尚未完成 foundation migration，则 M00 编码不得强行把 INFRA 表混入 M00 migration；应先完成 INFRA 编码。

### 6.2 新增表

M00 migration 只新增三张表：

| 表 | 用途 |
| --- | --- |
| `core3_source_batch` | 一次原始数据扫描或登记批次 |
| `core3_source_row_registry` | 每批每行原始数据登记和变化状态 |
| `core3_source_impacted_sku` | 批次级受影响 SKU 聚合 |

### 6.3 `core3_source_batch` 字段

必须落地的字段：

```text
batch_id
project_id
category_code
run_id
module_run_id
batch_type
source_system
source_database
source_schema
source_tables
ruleset_version
module_version
hash_version
scan_started_at
scan_finished_at
input_watermark_json
row_counts_json
write_time_range_json
source_pk_range_json
schema_snapshot_json
impacted_sku_count
affected_module_summary_json
quality_summary_json
status
review_required
review_status
review_reason
error_code
error_message
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `batch_id` |
| 索引 | `project_id, category_code, created_at` |
| 索引 | `project_id, category_code, status` |
| 索引 | `run_id` |
| 索引 | `module_run_id` |

### 6.4 `core3_source_row_registry` 字段

必须落地的字段：

```text
row_registry_id
batch_id
project_id
category_code
source_table
source_pk
source_pk_strategy
source_row_id
row_hash
hash_version
previous_batch_id
previous_row_hash
previous_operation_type
sku_code_candidate
model_name_raw
brand_raw
category_raw
write_time
business_key_json
source_field_presence_json
operation_type
change_reason
affected_modules
quality_hint
review_required
review_status
created_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `row_registry_id` |
| 唯一键 | `batch_id, source_table, source_pk`，source_pk 非空时 |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `source_table, source_pk` |
| 索引 | `source_row_id` |
| 索引 | `sku_code_candidate` |
| 索引 | `operation_type` |
| 索引 | `review_required` |

### 6.5 `core3_source_impacted_sku` 字段

必须落地的字段：

```text
impacted_sku_id
batch_id
project_id
category_code
sku_code_candidate
model_name_raw
brand_raw
source_tables
operation_summary_json
affected_modules
impact_reason
impact_level
needs_recompute
review_required
review_status
review_reason
created_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `impacted_sku_id` |
| 唯一键 | `batch_id, sku_code_candidate` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code_candidate` |
| 索引 | `needs_recompute` |
| 索引 | `review_required` |

### 6.6 downgrade

downgrade 必须只删除 M00 三张表，不影响旧 Core3 MVP 表和原始表。

删除顺序：

```text
core3_source_impacted_sku
core3_source_row_registry
core3_source_batch
```

## 7. model/schema 任务

### 7.1 SQLAlchemy model

在当前项目首版可继续追加到：

```text
apps/api-server/app/models/entities.py
```

建议新增类：

```text
Core3SourceBatch
Core3SourceRowRegistry
Core3SourceImpactedSku
```

要求：

- 只追加，不修改旧 `Core3PipelineRun`、`Core3SkuMarketProfile` 等旧 MVP 类。
- JSON 字段沿用当前项目的 SQLAlchemy `JSON`，迁移在 PostgreSQL 下应使用 JSONB 或兼容 JSON。
- 时间字段使用当前项目已有 `AuditMixin` 或清晰的 `DateTime` 字段。

### 7.2 Pydantic schema

在：

```text
apps/api-server/app/schemas/core3_real_data.py
```

新增：

| schema | 用途 |
| --- | --- |
| `Core3SourceBatchRegisterRequest` | 手工触发 M00 登记 |
| `Core3SourceBatchOut` | 批次摘要 |
| `Core3SourceRowRegistryOut` | 行登记查询 |
| `Core3SourceImpactedSkuOut` | 受影响 SKU 查询 |
| `Core3SourceBatchListOut` | 批次列表 |
| `Core3SourceTableWatermarkOut` | 水位摘要 |

### 7.3 枚举

新增或复用 INFRA 枚举：

| 枚举 | 值 |
| --- | --- |
| `Core3SourceBatchType` | `full`、`incremental` |
| `Core3SourceBatchStatus` | `running`、`registered`、`registered_with_warning`、`failed` |
| `Core3SourceOperationType` | `insert`、`update`、`no_change`、`not_seen_in_current_scan`、`skipped` |
| `Core3SourceImpactLevel` | `none`、`low`、`medium`、`high` |

## 8. repository 任务

### 8.1 文件

新增：

```text
apps/api-server/app/services/core3_real_data/source_registry_repositories.py
```

### 8.2 Repository 类

| 类 | 职责 |
| --- | --- |
| `RawSourceRepository` | 只读四张原始表 |
| `SourceBatchRepository` | 创建、更新、查询 `core3_source_batch` |
| `SourceRowRegistryRepository` | 批量写入、历史查询、行登记查询 |
| `SourceImpactedSkuRepository` | 聚合写入、查询受影响 SKU |

### 8.3 `RawSourceRepository`

必须提供：

| 方法 | 说明 |
| --- | --- |
| `list_source_tables()` | 返回四张原始表配置 |
| `inspect_table(source_table)` | 字段、类型、nullable、schema hash |
| `get_table_watermark(source_table)` | 行数、id min/max、write_time min/max、distinct model_code |
| `iter_rows(source_table, scan_plan)` | 只读迭代候选行 |
| `get_row_by_source_ref(source_table, source_pk)` | 后续 M01/M02 受控追溯 |

禁止提供：

```text
insert_raw
update_raw
delete_raw
truncate_raw
```

### 8.4 历史查询

`SourceRowRegistryRepository` 必须支持：

```text
find_latest_by_source(project_id, category_code, source_table, source_pk, hash_version)
```

查询条件：

- 同项目。
- 同品类。
- 同 source_table。
- 同 source_pk。
- 同 hash_version。
- 批次状态为 `registered` 或 `registered_with_warning`。
- 按 `created_at desc` 取最新。

### 8.5 幂等写入

同一 `batch_id + source_table + source_pk`：

- 已存在且字段一致：允许跳过。
- 已存在但字段不一致：本次 runner 失败，不能覆盖。

## 9. service 任务

### 9.1 文件

新增：

```text
apps/api-server/app/services/core3_real_data/source_registry_service.py
```

### 9.2 组件

| 组件 | 职责 |
| --- | --- |
| `SourceSchemaInspector` | 生成 schema snapshot 和 schema hash |
| `SourceScanPlanner` | 根据 full/incremental 和水位生成扫描计划 |
| `SourceRowHashService` | 生成 `m00_row_hash_v1` |
| `SourceFieldPresenceService` | 生成 `source_field_presence_json` |
| `SourceOperationClassifier` | 判断 operation_type |
| `SourceQualityService` | 生成行级和批次级质量提示 |
| `SourceImpactPlanner` | 根据 source_table 和 operation 聚合 affected_modules |
| `SourceRegistryRunner` | 编排 M00 全流程 |

### 9.3 hash 字段白名单

首版必须内置四张表的 M00 字段白名单：

| 表 | 参与 hash 字段 |
| --- | --- |
| `week_sales_data` | `model_code`、`category`、`brand`、`model`、`date_value`、`channel`、`platform`、`sales_volume`、`sales_amount`、`avg_price`、`write_time` |
| `attribute_data` | `model_code`、`category`、`brand`、`model`、`attr_name`、`attr_value`、`write_time` |
| `selling_points_data` | `model_code`、`category`、`brand`、`model`、`variable`、`selling_point`、`write_time` |
| `comment_data` | `model_code`、`category`、`brand`、`model`、`comment_id`、`comment_content`、`comments_segments`、`primary_dim`、`secondary_dim`、`third_dim`、`sentiment`、`write_time` |

### 9.4 质量规则

必须实现：

| code | 级别 |
| --- | --- |
| `missing_source_pk` | blocked/skipped |
| `missing_sku_code_candidate` | review |
| `missing_write_time` | warning |
| `duplicate_source_pk_in_scan` | blocked/review |
| `source_schema_changed` | review |
| `row_count_drop_suspected` | review |
| `write_time_watermark_regressed` | warning |
| `comment_duplicate_import_suspected` | warning |
| `selling_points_sparse_coverage` | warning |

### 9.5 影响模块映射

必须实现表到模块映射：

| 表 | affected_modules |
| --- | --- |
| `week_sales_data` | M01、M02、M07、M08、M09、M10、M11、M11.5、M12、M13、M14、M15 |
| `attribute_data` | M01、M02、M03、M04a、M08、M09、M10、M11、M11.5、M12、M13、M14、M15 |
| `selling_points_data` | M01、M02、M04a、M04b、M08、M09、M10、M11、M11.5、M12、M13、M14、M15 |
| `comment_data` | M01、M02、M05、M06、M04b、M08、M09、M10、M11、M11.5、M12、M13、M14、M15 |

M16 不写入 affected_modules。M16 是消费者。

## 10. runner/API 任务

### 10.1 Runner

实现：

```text
SourceRegistryRunner.register_batch(
  project_id,
  category_code,
  batch_type,
  source_tables,
  ruleset_version,
  module_version,
  hash_version,
  run_id=None,
  module_run_id=None
)
```

返回：

```text
batch_id
status
impacted_sku_count
review_required
affected_module_summary
row_counts
quality_summary
```

### 10.2 Runner 步骤

1. 创建 `core3_source_batch`，状态 `running`。
2. 读取 schema 和水位。
3. 选择扫描行。
4. 生成 source 标识、field presence、row hash。
5. 对比历史行登记。
6. 写入 `core3_source_row_registry`。
7. 聚合 `core3_source_impacted_sku`。
8. 生成批次质量摘要。
9. 更新批次状态。
10. 返回 runner result。

### 10.3 API

M00 API 是内部/运营 API。可以在 `API_development_tasks.md` 中统一实现；如果 M00 编码阶段先实现，必须使用 v2 路径：

| 方法 | 路径 |
| --- | --- |
| POST | `/api/mvp/core3/v2/projects/{project_id}/source-batches/register` |
| GET | `/api/mvp/core3/v2/projects/{project_id}/source-batches/{batch_id}` |
| GET | `/api/mvp/core3/v2/projects/{project_id}/source-batches/{batch_id}/rows` |
| GET | `/api/mvp/core3/v2/projects/{project_id}/source-batches/{batch_id}/impacted-skus` |

API 不进入高层页面，不展示给业务领导主屏。

## 11. 测试任务

### 11.1 单元测试

| 测试 | 断言 |
| --- | --- |
| source row id | `week_sales_data:123` 稳定生成 |
| row hash 字段顺序 | 字段顺序变化 hash 不变 |
| row hash 缺失语义 | null、空、`-`、unknown hash payload 不混淆 |
| insert | 无历史时为 insert |
| update | 同源行 hash 变化为 update |
| no_change | 同源行 hash 不变为 no_change |
| skipped | 缺主键时 skipped + `missing_source_pk` |
| affected modules | 四张表映射正确 |

### 11.2 Repository 测试

| 测试 | 断言 |
| --- | --- |
| create batch | 初始状态 `running` |
| finish batch | 状态可更新为 registered/registered_with_warning/failed |
| unique row | 同一 batch/table/pk 不重复 |
| latest history | 能找到上一成功批次同源行 |
| impacted sku unique | 同一 SKU 多表变化只生成一条 impacted |
| raw source readonly | repository 不提供写原始表方法 |

### 11.3 Runner 测试

| 场景 | 断言 |
| --- | --- |
| 首次 full | 四张表 fixture 行均为 insert |
| incremental 无历史 | 自动 fallback full |
| incremental 新 id | 新行 insert，旧行 no_change |
| overlap 未变 | no_change 不进 impacted |
| full 历史缺失 | 生成 not_seen_in_current_scan |
| schema 变化 | batch registered_with_warning |
| missing write_time | warning，不阻断 |
| selling points sparse | warning，不阻断 |

### 11.4 API 测试

如果本模块实现 API，必须测试：

- register 成功。
- 查询 batch。
- 查询 rows 分页。
- 查询 impacted SKUs。
- 非法 `batch_type` 返回 422 或 400。
- 不存在 batch 返回 404。

## 12. 205/85E7Q 验收

### 12.1 fixture 验收

基于 INFRA 的 85E7Q fixture，M00 必须验证：

| 事实 | 期望 |
| --- | --- |
| `TV00029115` 存在 | 登记为 `sku_code_candidate` |
| 有周销行 | 影响 M07 及下游 |
| 有属性行 | 影响 M03、M04a、M08 及下游 |
| 无结构化卖点行 | 不报错、不补造卖点 |
| 有评论行 | 影响 M05、M06、M04b 及下游 |
| 同品牌候选存在 | M00 不做品牌过滤 |

### 12.2 205 阶段验收

M00 阶段性连接 205 验收时，预期：

| 表 | 预期 |
| --- | --- |
| `week_sales_data` | 1326 行、35 型号 |
| `attribute_data` | 2843 行、35 型号 |
| `selling_points_data` | 65 行、5 型号 |
| `comment_data` | 62426 行、33 型号 |

85E7Q 预期：

| 数据域 | 行数参考 |
| --- | ---: |
| 周销 | 46 |
| 属性 | 81 |
| 结构化卖点 | 0 |
| 评论 | 3621 |

这些数值用于 sanity check，不应写死为业务逻辑。测试可以允许小范围变化，但必须在验收报告中说明实际行数。

## 13. 完成标准

M00 编码完成必须满足：

1. M00 三张表 migration 可执行。
2. M00 三个 model 可创建。
3. schema 支持 M00 请求和查询响应。
4. `RawSourceRepository` 只读四张原始表。
5. `SourceRegistryRunner` 可执行 full。
6. incremental 无历史时 fallback full。
7. row hash 稳定且保留缺失语义。
8. operation_type 判断正确。
9. 受影响 SKU 可聚合。
10. affected_modules 可被 M16 消费。
11. 85E7Q 无结构化卖点时不报错、不补卖点。
12. M00 不生成 evidence、画像、竞品或报告结论。
13. 相关 pytest 通过。
14. 旧 `test_core3_mvp.py` 不被破坏。

## 14. 风险和回滚

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 原始表字段和设计不一致 | 扫描失败 | schema snapshot + warning，缺必要字段才 failed |
| `write_time` 噪声造成大量 update | 增量误触发 | 首版记录 warning，后续升 hash_version |
| 评论表太大导致测试慢 | 本地测试慢 | 单元用小 fixture，205 只做阶段验收 |
| 旧 `core3_pipeline_run` 命名冲突 | 旧 MVP 失败 | M00 不改旧表 |
| 行登记重复写入 | 重跑不幂等 | 唯一键 + 字段一致跳过 |
| 下游绕过 M00 读原始表 | 增量边界失效 | repository 边界和测试约束 |

回滚：

1. migration downgrade 删除 M00 三张表。
2. 删除 M00 service/repository/schema/API 文件。
3. 不需要恢复原始表，因为 M00 不写原始表。
4. 不影响旧 `core3_mvp` 代码。

## 15. 下游依赖

| 下游模块 | 依赖 M00 的内容 |
| --- | --- |
| M01 | `batch_id`、`source_row_id`、`source_table`、`source_pk`、`operation_type` |
| M02 | `source_row_id`、source reference |
| M03-M07 | M01/M02 基于 M00 的变化范围生成清洗和 evidence |
| M16 | batch 状态、受影响 SKU、affected modules、input watermark、质量摘要 |
| API | 批次查询、行登记查询、受影响 SKU 查询 |

## 16. 子任务执行建议

M00 编码建议拆成 7 个小任务：

| 子任务 | 内容 |
| --- | --- |
| M00-A | migration + model |
| M00-B | schema + enum |
| M00-C | RawSourceRepository + schema inspector |
| M00-D | row hash、field presence、operation classifier |
| M00-E | SourceRegistryRunner full 模式 |
| M00-F | incremental、impacted SKU、quality summary |
| M00-G | API + tests + 85E7Q fixture 验收 |

每个子任务都必须能单独测试。

## 17. 下次任务

下次应生成：

```text
docs/core3_mvp/real_data_v2/development/M01_development_tasks.md
```

M01 文档需要基于 M00 的 `core3_source_batch` 和 `core3_source_row_registry`，拆清四类清洗事实表、质量诊断、重复识别、unknown/null/空字符串/`-` 处理、评论拆行保留和增量清洗策略。
