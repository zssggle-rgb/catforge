# M01 清洗与质量过滤当前实现说明

本文档记录 `hotfix/data-preprocess-20260618` 分支中 M01 的当前实现。M01 是数据预处理的核心清洗层：它把 M00 登记过的原始行转为可消费的清洗事实，并在这一层拦截空评论、默认评论、低质评论和服务履约类评论。

## 1. 模块定位

M01 的职责：

- 读取 M00 source batch 中可处理的原始行。
- 回读 4 张原始表并按领域清洗。
- 生成 SKU、量价、属性、卖点、评论、句子和评论维度清洗表。
- 生成数据质量信息。
- 生成 SKU 级覆盖摘要和初步清洗画像。
- 对评论做快速预过滤，避免大量无效评论进入后续分析。

M01 不做：

- 不生成 evidence atom，M02 负责。
- 不生成参数画像、卖点激活、评论语义、用户任务、目标客群、价值战场或竞品结论。
- 不把缺失解释成“没有”。
- 不把服务履约评论作为产品体验事实。

## 2. 输入边界

M01 只读取 M00 已登记且 source batch 可消费的范围。

必须有：

```text
core3_source_batch
core3_source_row_registry
```

并回读原始表：

```text
week_sales_data
attribute_data
selling_points_data
comment_data
```

如果 source batch 不存在或不可消费，M01 返回 blocked，不写业务清洗事实。

## 3. 输出边界

M01 写入：

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

其中 `core3_data_quality_issue` 是 M01 派生出来的质量信息，不来自原始 4 张表。它进入 M02 时只能作为质量提示 evidence，不能被当作产品事实本身。

## 4. 分领域清洗规则

### 4.1 量价清洗

来源表：

```text
week_sales_data
```

输出表：

```text
core3_clean_market_weekly
```

当前处理：

- 解析 `date_value` 为周度 `period_week_index`。
- 解析 `sales_volume`、`sales_amount`、`avg_price` 为数值。
- 校验 `avg_price` 是否与 `sales_amount / sales_volume` 匹配。
- 保留渠道和平台字段。
- 生成量价清洗 hash。

质量提示包括：

- 周期无法解析。
- 数值无法解析。
- 均价校验不一致。

### 4.2 属性清洗

来源表：

```text
attribute_data
```

输出表：

```text
core3_clean_attribute
```

当前处理：

- 规范化属性名和值。
- 判断属性值是否 present、null、空字符串、`-`、unknown 等。
- 从属性值中抽取数字候选和单位候选。
- 生成属性冲突分组键。

彩电属性缺失口径：

- 原始表没有某些属性是正常情况，不在 M01 阶段阻断。
- M01 统计 unknown/missing，但不把所有属性缺失直接判定为质量失败。
- 缺失是 unknown，不是 false。

### 4.3 卖点清洗

来源表：

```text
selling_points_data
```

输出表：

```text
core3_clean_claim
core3_clean_claim_sentence
```

当前处理：

- 清洗卖点原文。
- 从 `variable` 中解析 `claim_seq`，例如“卖点1”。
- 抽取标题提示和结构提示。
- 按句子切分生成 `core3_clean_claim_sentence`。

如果卖点原文缺失，M01 不生成 claim 清洗事实。SKU 级会记录：

```text
claim_coverage_missing
```

业务解释必须是：

```text
结构化卖点数据缺失，不代表该 SKU 没有卖点。
```

### 4.4 评论清洗

来源表：

```text
comment_data
```

输出表：

```text
core3_clean_comment
core3_clean_comment_sentence
core3_clean_comment_dimension
```

当前处理：

- 规范化评论正文。
- 解析评论时间。
- 清洗平台、URL、评论 ID、情感字段。
- 清洗原始评论维度：一级、二级、三级维度。
- 计算评论正文 hash 和分段文本 hash。
- 标记低价值评论。
- 只对非低价值评论生成句子。

评论句子切分在 M01 完成，不在 M02 完成。

## 5. 评论快速过滤口径

M01 当前过滤三类评论：

1. 空评论或正文缺失。
2. 默认/模板化评价，例如“好”“很好”“不错”“满意”“此用户未及时填写评价内容”等。
3. 服务履约类评论，例如客服、物流、安装、售后、退换货、维修等。

服务履约类评论统一并入：

```text
low_value_comment
```

不再新增 `service_fulfillment_comment` 类型，避免和服务履约低价值口径重复。

M01 对这类评论的处理是：

- `core3_clean_comment` 中保留原始清洗记录。
- `low_value_flag = true`。
- `low_value_reason` 包含“服务履约评价”。
- 进入清洗统计和质量统计。
- 不生成 `core3_clean_comment_sentence`。
- 后续 M02 不生成评论语义 evidence。

业务汇报口径：

```text
客服、物流、安装、售后等服务履约评价在 M01 并入低价值评论，只保留质量统计，不进入后续产品分析。
```

## 6. 量价周度覆盖解释

M01 在 `core3_clean_sku.coverage_json.market.weekly_coverage` 中生成 SKU 级周度覆盖解释。

当前规则：

- SKU+周只要任一平台有量价行，即视为该 SKU 该周有覆盖。
- 同一周只有一个平台有数据是正常情况，解释为单平台销售或平台特供。
- 首周前缺失按新品、晚进入样本解释，不直接视为漏数。
- 末周后缺失按退市、离开样本解释，不直接视为漏数。
- 首次观察周与最后观察周之间的缺失才记为内部断档软提示。

关键字段：

```text
active_week_count
missing_week_count
leading_absence_week_count
trailing_absence_week_count
internal_gap_week_count
single_platform_week_count
single_platform_is_normal
soft_warning_codes
business_interpretation_cn
```

如果存在内部断档，会出现：

```text
soft_warning_codes = ["market_internal_gap"]
```

这仍然是软提示，不是处理失败。

## 7. SKU 清洗画像

M01 会聚合生成 `core3_clean_sku`。

主要内容：

- SKU、型号、品牌、品类。
- 来源表覆盖情况。
- 市场、属性、卖点、评论覆盖。
- 周度量价覆盖解释。
- 评论初步过滤统计。
- 跨表品牌/型号/品类冲突。
- 缺失信号，例如结构化卖点缺失。
- 质量状态和是否需要复核。

`core3_clean_sku` 是后续事实分析的基础，但还不是用户画像或竞品结论。

## 8. 数据质量信息

M01 生成 `core3_data_quality_issue`。

常见质量类型：

- `unknown_value`
- `invalid_number`
- `price_check_mismatch`
- `claim_seq_parse_failed`
- `claim_coverage_missing`
- `cross_table_conflict`
- `comment_dimension_missing`
- `duplicate_comment_text`

低价值评论不会放大成大量 row-level quality issue，避免 100 多万评论导致质量问题表膨胀。

质量信息的解释：

- 它是 M01 清洗派生信息。
- 它不是原始输入表。
- 它可以进入 M02 成为质量提示 evidence。
- 后续分析只能把它作为约束、解释和复核依据，不能当作产品正向/负向事实。

## 9. 大数据保护

M01 当前按 source row chunk 处理，默认：

```text
M01_DEFAULT_SOURCE_ROW_CHUNK_SIZE = 1000
```

runner 每个 chunk：

- 回读该 chunk 的原始行。
- 清洗并写入领域表。
- `flush` 后按配置 `commit`。
- `expunge_all` 释放 ORM 对象。

CLI 的 `prepare-new-data` 又按 SKU 分批调用 M01，默认：

```text
--sku-batch-size 50
```

这两个分批机制共同降低 205 上 100 万级评论数据处理时的内存压力。

## 10. 执行入口

CLI 推荐入口：

```bash
python -m app.cli.catforge_data prepare-new-data --format json
```

只跑已有 batch 的清洗与证据准备：

```bash
python -m app.cli.catforge_data prepare-new-data \
  --register-source-batch none \
  --batch-id latest \
  --sku-batch-size 50 \
  --format json
```

API 入口：

```text
POST /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/cleaning/run
GET  /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/cleaning/summary
GET  /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/cleaning/skus
GET  /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/quality-issues
```

核心实现：

- `apps/api-server/app/services/core3_real_data/cleaning_runner.py`
- `apps/api-server/app/services/core3_real_data/cleaning_quality_service.py`
- `apps/api-server/app/services/core3_real_data/cleaning_repositories.py`
- `apps/api-server/app/services/core3_real_data/cleaning_normalizers.py`

测试覆盖：

- `apps/api-server/tests/core3_real_data/test_m01_cleaning_runner.py`
- `apps/api-server/tests/core3_real_data/test_m01_cleaning_domain_cleaners.py`
- `apps/api-server/tests/core3_real_data/test_m01_cleaning_coverage_quality.py`
- `apps/api-server/tests/core3_real_data/test_m01_cleaning_repositories.py`
- `apps/api-server/tests/core3_real_data/test_m01_no_business_outputs.py`
- `apps/api-server/tests/core3_real_data/test_catforge_data_cli.py`

## 11. 当前已知边界

- M01 只做初步过滤和清洗，不做复杂评论语义判断。
- 服务履约评论当前直接并入低价值评论，不进入后续产品分析。
- M01 不单独提供“只补跑 M01 不跑 M02”的对外业务命令；CLI 的业务口径默认是准备到可分析，即 M00+M01+M02。
- M01 质量统计中的缺失和冲突需要业务解释，不能直接写成产品结论。
