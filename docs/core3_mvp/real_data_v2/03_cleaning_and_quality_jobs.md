# 03 清洗、质量诊断与规范化任务

## 1. 任务拆分

清洗阶段不是一个函数，也不是一个 SQL。建议拆成以下服务模块：

```text
real_data/
  source_scan.py
  quality_rules.py
  sales_cleaner.py
  param_cleaner.py
  claim_cleaner.py
  comment_cleaner.py
  evidence_writer.py
  incremental.py
```

统一执行入口只做调度：

```text
real_data_pipeline.run_cleaning(project_id, mode)
```

## 2. 原始行登记任务 `source_scan`

职责：

- 读取 4 张原始表。
- 生成 row key 和 row hash。
- 判断新增、变化、跳过。
- 产出受影响 SKU 集。

不做：

- 不解析业务含义。
- 不生成竞品。
- 不写 SKU 画像。

验收：

- 同一批数据重复扫描，第二次应全部 `unchanged`。
- 新增一条评论，只产生该评论所属 SKU 的影响范围。

## 3. 通用质量规则

### 3.1 unknown 规则

统一 unknown 值：

```text
""
" "
"-"
"--"
"未知"
"暂无"
"无数据"
"null"
"None"
NULL
```

unknown 处理：

- 参数 unknown 不等于不支持。
- 卖点 unknown 不等于没有卖点。
- 评论 unknown 不参与主题率分母。
- 市场数值 unknown 不参与加权均价。

### 3.2 数值规则

- 销量、销额、均价不得为负。
- 销量为 0 时不能用销额除以销量。
- `avg_price` 与 `sales_amount / sales_volume` 差异超过阈值，记录 warning。
- 极端价格只标记，不直接删除，除非明显解析失败。

### 3.3 字符规则

- 全角半角统一。
- 连续空白压缩。
- 中英文括号统一。
- 型号保留大小写展示值，另存 normalized key。
- 不在清洗层做过度语义替换。

## 4. 周销清洗任务

输入：

- `week_sales_data`
- `core3_source_row_registry` 中 new/changed 的销售行。

输出：

- `core3_clean_market_fact`
- `evidence_item`
- `core3_data_quality_issue`

关键处理：

1. 周期解析：

```text
26W23 -> 2026W23
```

如果后续出现 `2026W23`、`2026-23`，解析器要兼容。

2. 渠道标准化：

```text
线上 -> 线上
线下 -> 线下
专业电商 -> 专业电商
内容电商 -> 内容电商
```

3. 聚合粒度：

```text
sku_code + period + channel_group + channel_type
```

4. 价格校验：

```text
calc_avg_price = sales_amount / sales_volume
price_calc_delta = abs(avg_price - calc_avg_price) / calc_avg_price
```

当差异超过 10% 记录 warning。

## 5. 参数清洗任务

输入：`attribute_data`

输出：`core3_clean_param_fact`

处理步骤：

1. 模型识别：

```text
model_code -> sku_code
model -> model_name
brand -> brand
```

2. 字段转长表：

如果原始表已经是长表，直接映射；如果后续变成宽表，除 SKU 标识列外全部展开为参数行。

3. 字段名规范化：

```text
清晰度2 -> 清晰度2
屏幕刷新率 -> 屏幕刷新率
MINILED -> miniled normalized key
HDMI参数 -> hdmi参数 normalized key
```

4. 值预处理：

提取但不最终判断：

- 数字。
- 单位。
- 百分比。
- 布尔关键词。
- 枚举关键词。

5. evidence：

每个非跳过参数行生成 evidence，保存原字段名、原值、清洗值。

## 6. 卖点清洗任务

输入：`selling_points_data`

输出：

- `core3_clean_claim_fact`
- `core3_clean_claim_sentence`

处理步骤：

1. 合并标题和正文，但保留来源字段。
2. 按 `。！？；\n` 和项目符号切句。
3. 保留原句顺序。
4. 抽取数值实体：

```text
144Hz
5200nits
3500分区
HDMI2.1
4GB+64GB
```

5. 抽取技术实体：

```text
Mini LED
量子点
高刷
护眼
AI
低延迟
HDR
杜比
```

6. 没有卖点行的 SKU 标记缺失，不推断为不具备卖点。

## 7. 评论清洗任务

输入：`comment_data`

输出：

- `core3_clean_comment_fact`
- `core3_clean_comment_sentence`
- `core3_clean_comment_dimension_fact`

处理步骤：

1. 去重：

优先使用：

```text
sku_code + comment_id
```

如果 `comment_id` 缺失，使用：

```text
sku_code + normalized_comment_text_hash
```

2. 维度拆行处理：

同一个评论多维度拆行时：

- 评论正文只保留一条。
- 维度路径单独保存多条。
- 统计评论主题时按去重评论正文计算。

3. 默认好评过滤：

以下只作为低价值评论，不进入产品体验主题：

```text
此用户没有填写评价
默认好评
好评
```

4. 分句：

长评论拆成句级 evidence，便于主题和情感判断。

5. 初步类型：

规则识别：

- 产品体验。
- 服务体验。
- 物流安装。
- 价格感知。
- 未知。

服务体验句不能直接激活产品卖点。

## 8. 数据质量输出

质量 issue 分级：

| 级别 | 含义 | 示例 |
| --- | --- | --- |
| critical | 该行无法进入分析 | SKU 缺失、周期无法解析 |
| warning | 可进入分析但降低置信度 | 均价校验异常、参数冲突 |
| info | 只做提示 | 某 SKU 缺结构化卖点 |

页面展示口径：

- 不显示 `critical/warning/info` 英文。
- 展示“不可分析项”、“需谨慎解读项”、“数据提示”。

## 9. 清洗阶段验收

必须通过：

1. 原始表不被修改。
2. 清洗表可重复重算。
3. 新增评论只影响该 SKU 的评论清洗和后续画像。
4. 85E7Q 即使没有结构化卖点，也能通过参数和评论进入后续分析，但卖点置信度降低。
5. 评论重复维度不导致声量被放大。
6. unknown 不被当作 false。

