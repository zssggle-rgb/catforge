# M02 Evidence 原子层当前实现说明

本文档记录当前整合分支中 M02 的实现。M02 是事实分析前的 evidence 原子层：它只把 M01 清洗事实转成可追踪 evidence，不生成业务画像、用户任务、目标客群、价值战场或竞品结论。

## 1. 模块定位

M02 的职责：

- 读取 M01 清洗事实。
- 按 SKU 分区生成 evidence atom。
- 建立 evidence link。
- 计算 evidence 置信度和复核状态。
- 过滤低价值、重复、模板类评论，不让它们进入后续产品评论语义链路。
- 对历史已生成但本轮不再可消费的评论 evidence 标记 inactive。

M02 不做：

- 不从原始 4 张表直接读数据。
- 不做评论语义抽取。
- 不抽取用户任务、目标客群、价值战场。
- 不做竞品召回、评分或三竞品选择。
- 不生成最终业务结论或报告。

## 2. 输入边界

M02 只读取 M01 输出表：

```text
core3_clean_sku
core3_clean_market_weekly
core3_clean_attribute
core3_clean_claim
core3_clean_claim_sentence
core3_clean_comment
core3_clean_comment_sentence
core3_clean_comment_dimension
core3_data_quality_issue
```

`core3_data_quality_issue` 虽然会进入 M02，但它代表质量提示，不是产品事实。

如果 M00 batch 不存在或不可消费，M02 返回 blocked。

## 3. 输出边界

M02 写入：

```text
core3_evidence_atom
core3_evidence_link
```

当前 evidence 类型：

| M01 来源表 | evidence_type | 粒度 |
| --- | --- | --- |
| `core3_clean_sku` | `sku_fact` | SKU |
| `core3_clean_market_weekly` | `market_fact` | 行 |
| `core3_clean_attribute` | `param_raw` | 字段 |
| `core3_clean_claim` | `promo_raw` | 行 |
| `core3_clean_claim_sentence` | `promo_sentence` | 句子 |
| `core3_clean_comment` | `comment_raw` | 行 |
| `core3_clean_comment_sentence` | `comment_sentence` | 句子 |
| `core3_clean_comment_dimension` | `comment_dimension` | 维度 |
| `core3_data_quality_issue` | `quality_issue` | 质量 |

M02 输出中禁止出现：

```text
param_code
claim_code
task_code
target_group_code
battlefield_code
competitor_sku_code
candidate_sku_code
business_conclusion
report_payload
```

这些都属于 M03 及以后模块或报告层。

## 4. Evidence 身份与版本

当前版本：

```text
module_version = m02-evidence-atom-0.1.0
evidence_version = m02_evidence_v1
confidence_rule_version = m02_confidence_v1
partition_strategy = sku_partition_v1
```

M02 根据以下信息生成稳定 `evidence_key`：

- `project_id`
- `category_code`
- `evidence_type`
- `clean_table`
- `clean_record_key`
- `evidence_field`
- `evidence_version`

`evidence_key` 决定当前 evidence 是否复用、更新或 supersede。

## 5. 评论过滤延续规则

M01 已把低价值评论标记出来。M02 会继续执行过滤，确保这些评论不会变成下游评论语义 evidence。

M02 当前过滤：

1. M01 标记的 `low_value_flag = true` 评论。
2. M01 已识别并拦截的服务履约类评论。
3. 重复评论中的非代表评论。
4. 模板类非业务评论，例如“好”“很好”“不错”“满意”“此用户未及时填写评价内容”等。
5. 包含非业务服务模板的评论，例如“送装一体”“京东服务”等。

对应统计字段出现在每个分区摘要中：

```text
skipped_low_value_comment_count
skipped_service_fulfillment_count
skipped_duplicate_comment_count
skipped_template_comment_count
```

这些评论不会生成当前状态的：

```text
comment_raw
comment_sentence
comment_dimension
```

如果历史上已经生成过相关 current evidence，本轮会将其标记为 inactive。

## 6. Inactive 规则

M02 不直接删除旧 evidence，而是标记状态：

```text
evidence_status = inactive
is_current = false
inactive_reason = <reason>
```

当前评论过滤相关 inactive reason：

- `low_value_skipped`
- `duplicate_representative_skipped`
- `comment_template_skipped`

被 inactive 的 evidence 关联 link 也会被标记 inactive，避免后续模块继续引用旧证据。

## 7. 分区与大数据保护

M02 当前按 SKU 分区执行：

```text
partition_strategy = sku_partition_v1
```

如果 CLI 调用，默认：

```text
--evidence-sku-batch-size 1
```

M02 内部每个 SKU 分区会：

- 构建该 SKU 的评论过滤集合。
- 只读取该 SKU 相关 M01 清洗事实。
- 生成/复用/supersede evidence atom。
- 预加载该分区 evidence link。
- 标记 obsolete link inactive。
- `flush` 并 `expunge_all` 释放 ORM 对象缓存。

该设计用于避免 205 上 100 万级评论数据一次性读入内存。

## 8. Evidence link

M02 会基于当前 evidence 建立证据关系。

当前 link 的作用是保留可追溯关系和替代关系，供后续查询 evidence trace、SKU evidence、报告证据卡等能力使用。

M02 不在 link 中写入业务结论，也不把 link 当成竞争关系或价值战场关系。

## 9. 置信度与复核

M02 为 evidence 计算：

```text
base_confidence
confidence_level
review_required
review_status
```

如果存在低置信或需要复核 evidence，M02 返回 warning，而不是 failed。

warning 代表：

```text
证据可用，但后续分析或展示时需要保留质量/置信度提示。
```

## 10. 执行入口

CLI 推荐入口：

```bash
python -m app.cli.catforge_data prepare-new-data --format json
```

CLI 默认在 M01 成功后继续跑 M02。已有 batch 重新准备：

```bash
python -m app.cli.catforge_data prepare-new-data \
  --register-source-batch none \
  --batch-id latest \
  --evidence-sku-batch-size 1 \
  --format json
```

API 入口：

```text
POST /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/evidence/run
GET  /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/evidence/summary
GET  /api/mvp/core3/v2/projects/{project_id}/evidence/{evidence_id}
GET  /api/mvp/core3/v2/projects/{project_id}/skus/{sku_code}/evidence
```

核心实现：

- `apps/api-server/app/services/core3_real_data/evidence_atom_service.py`
- `apps/api-server/app/services/core3_real_data/evidence_atom_repositories.py`
- `apps/api-server/app/services/core3_real_data/evidence_mappers.py`
- `apps/api-server/app/services/core3_real_data/evidence_payloads.py`
- `apps/api-server/app/services/core3_real_data/evidence_links.py`
- `apps/api-server/app/services/core3_real_data/evidence_confidence.py`

测试覆盖：

- `apps/api-server/tests/core3_real_data/test_m02_evidence_runner.py`
- `apps/api-server/tests/core3_real_data/test_m02_evidence_repositories.py`
- `apps/api-server/tests/core3_real_data/test_m02_no_business_outputs.py`
- `apps/api-server/tests/core3_real_data/test_catforge_data_cli.py`

## 11. 205 当前验证结论

本分支在 205 上验证过大批次 M02：

- 批次：`m00_20260619084551_857df63b`
- SKU 数：448
- current evidence：约 230,534 条
- evidence link：约 472,434 条
- 全量 M02 用时：约 40 分 25 秒
- API 容器内存峰值观察：约 562 MB
- 空闲回落：约 177 MB

结论：

```text
按 SKU 分区、每 SKU evidence batch size 为 1 的情况下，当前 M02 不会像早期大查询那样把 205 内存打满。
```

## 12. 当前已知边界

- 当前 CLI 没有公开的“只补跑 M02”子命令；需要通过 API、runner 或后续新增 CLI。
- M02 不做评论业务语义，只准备 evidence。
- M02 过滤规则仍是规则型快速过滤，复杂服务/产品混合评论需要后续产品评论分析进一步判断。
- 质量 issue evidence 不能被下游解释成产品事实，只能作为约束和复核依据。
