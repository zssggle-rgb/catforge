# 01 从原始表到三竞品的完整流水线

## 1. 总览

真实数据版 Core3 MVP 应按以下阶段执行。

```text
S0 原始表接入登记
S1 原始行质量扫描
S2 清洗规范化
S3 字段画像与文本画像
S4 参数抽取与标准参数激活
S5 卖点切分、语义抽取与标准卖点激活
S6 评论分句、主题、情感、产品/服务分类
S7 资产候选生成和映射候选生成
S8 SKU 市场画像
S9 SKU 语义画像
S10 用户任务、目标客群、价值战场反推
S11 目标 SKU 候选池召回
S12 组件评分和三槽位选择
S13 证据卡和业务报告生成
```

S0 到 S7 是 CatForge 工厂侧生产能力，S8 到 S13 是 Core3 MVP 展示链路。

## 2. S0 原始表接入登记

输入表：

- `week_sales_data`
- `attribute_data`
- `selling_points_data`
- `comment_data`

这 4 张表视为上传原始表。即使它们已经在 PostgreSQL 中，也不代表它们是可直接分析的规范表。

处理动作：

1. 读取每张原始表的行数、字段列表、`write_time` 范围。
2. 为每行生成稳定 `source_row_key`：

```text
source_table + model_code/model + business_key + write_time + row_hash
```

3. 生成 `raw_row_hash`：

```text
sha256(canonical_json(raw_row_selected_fields))
```

4. 写入原始行登记表，标记新增、变化、已处理、跳过。

输出：

- `core3_source_batch`
- `core3_source_row_registry`
- 受影响 SKU 集合 `impacted_sku_codes`

## 3. S1 原始行质量扫描

扫描维度：

- 必填字段缺失。
- `model_code` 与 `model` 可用性。
- 周期格式是否可解析。
- 销量、销售额、均价是否为非负数。
- 参数值 unknown 比例。
- 评论空文本、模板文本、重复文本比例。
- 卖点表覆盖 SKU 数。
- 不同表之间 SKU 覆盖交集。

输出：

- `core3_data_quality_issue`
- `core3_data_quality_snapshot`

质量扫描不阻断全部流程，只阻断不可分析行。页面用业务语言提示“本次样例数据中，部分型号缺少结构化卖点，系统将用参数和评论补充判断，相关结论置信度会降低”。

## 4. S2 清洗规范化

清洗目标不是直接生成结论，而是把原始表转换成 CatForge canonical schema。

### 4.1 周销清洗

输入：`week_sales_data`

输出：`core3_clean_market_fact`

清洗内容：

- `category=彩电` 统一为 `TV`。
- `date_value=26W23` 解析为 `period_year=2026`、`period_week=23`、`period_type=week`。
- `channel=线上`、`platform=专业电商` 映射为渠道大类和渠道细分。
- 数值字段转 decimal。
- 同 SKU、同周期、同渠道的重复行聚合。
- `avg_price` 与 `sales_amount / sales_volume` 差异过大时标记 issue。

### 4.2 参数清洗

输入：`attribute_data`

输出：`core3_clean_param_fact`

清洗内容：

- 宽字段或长字段都转成 `sku_code + raw_param_name + raw_param_value`。
- 空、`-`、`未知`、`None` 转为 `unknown`。
- 字段名做全角半角、空格、大小写、符号规范化。
- 参数值保留原值，同时预处理可解析数值片段。
- 不在清洗阶段做最终标准参数判断。

### 4.3 卖点清洗

输入：`selling_points_data`

输出：

- `core3_clean_claim_fact`
- `core3_clean_claim_sentence`

清洗内容：

- 保留卖点标题、卖点正文、顺序。
- 按中文标点、项目符号、换行切句。
- 识别明显广告模板和空句。
- 对没有结构化卖点的 SKU 标记 `claim_missing=unknown`，不能标记为“没有卖点”。

### 4.4 评论清洗

输入：`comment_data`

输出：

- `core3_clean_comment_fact`
- `core3_clean_comment_sentence`
- `core3_clean_comment_dimension_fact`

清洗内容：

- 原始评论按 `comment_id` 和正文 hash 去重。
- 同一评论被多个维度拆行时，正文只保留一条，维度另存。
- 过滤空评论、默认好评模板、纯符号、过短文本。
- 评论按句切分。
- 保留原始一级/二级/三级维度作为弱标签，不直接当成系统主题结论。

## 5. S3 字段画像与文本画像

### 5.1 参数字段画像

对 `core3_clean_param_fact.raw_param_name` 聚合：

- 覆盖 SKU 数。
- 非空率。
- unknown 率。
- 唯一值数量。
- top 原始值。
- 数值/单位形态。
- 与预制参数 alias 的匹配置信度。

输出：

- `core3_param_field_profile`
- `core3_candidate_param_alias`

### 5.2 宣传文本画像

对 `core3_clean_claim_sentence` 做：

- 分词。
- n-gram 短语抽取。
- 数值实体抽取。
- 技术词识别。
- 高频短语覆盖率。
- 与价格、销量、评论主题共现。

输出：

- `core3_text_token`
- `core3_phrase_profile`
- `core3_candidate_claim`

### 5.3 评论文本画像

对 `core3_clean_comment_sentence` 做：

- 分词。
- 高频短语。
- 产品体验/服务体验/物流安装/价格感知/未知初判。
- 正负向词和否定窗口。
- 新主题候选。

输出：

- `core3_text_token`
- `core3_phrase_profile`
- `core3_candidate_comment_topic`

## 6. S4 参数抽取与标准参数激活

输入：

- 清洗参数。
- 卖点文本中的数值实体。
- 型号名中的尺寸等弱线索。
- 预制标准参数库。
- 候选参数别名。

来源优先级：

```text
清洗参数 exact alias
  > 清洗参数 fuzzy alias
  > 卖点文本数值抽取
  > 型号名抽取
  > 评论弱提示
```

输出：

- `core3_sku_param_normalized`
- 参数 evidence。
- 参数冲突表。

评论只能作为弱提示，不能单独证明硬规格。

## 7. S5 卖点切分、语义抽取与标准卖点激活

输入：

- 清洗卖点句。
- 标准参数结果。
- 评论主题初步结果。
- 预制标准卖点库。
- 候选卖点。

处理：

1. 从卖点句抽取技术实体：Mini LED、刷新率、亮度、分区、HDMI、护眼、音响、AI、系统等。
2. 匹配标准卖点关键词和规则。
3. 用参数证据、宣传证据、评论证据计算激活分。
4. 把未知信号重归一，不当 0。
5. 低置信或新词进入候选资产，不进入高置信报告。

输出：

- `core3_claim_sentence_hit`
- `core3_sku_claim_activation`
- `core3_candidate_claim`

## 8. S6 评论主题、情感与产品/服务分类

输入：

- 清洗评论句。
- 预制评论主题库。
- 原始维度弱标签。
- 候选评论主题。

处理：

- 先分产品体验、服务体验、物流安装、价格感知、未知。
- 再做多标签主题命中。
- 每句最多保留 top3 主题。
- 情感用正负词、否定窗口、程度词计算。
- 原始维度只用于辅助，不直接覆盖系统判断。

输出：

- `core3_comment_sentence_topic`
- `core3_sku_comment_topic_summary`
- `core3_candidate_comment_topic`

## 9. S7 资产候选和映射候选生成

候选资产类型：

- 候选参数别名。
- 候选标准参数。
- 候选标准卖点。
- 候选评论主题。
- 候选用户任务。
- 候选目标客群。
- 候选价值战场。
- 候选映射关系。

候选不等于批准资产。MVP 第一版可以使用完整 seed 作为 approved baseline，同时把新发现进入候选表，供后续复核。

输出：

- `category_asset_*` 候选记录或 `core3_candidate_*` 表。
- 复核队列。

## 10. S8 SKU 市场画像

输入：`core3_clean_market_fact`

输出：`core3_sku_market_profile`

指标：

- 近 23 周销量、销额。
- 加权均价。
- 最新周均价。
- 渠道占比。
- 价格趋势。
- 销量趋势。
- 同尺寸/同价格带分位。
- 样本充足度。

## 11. S9 SKU 语义画像

输入：

- `core3_sku_param_normalized`
- `core3_sku_claim_activation`
- `core3_sku_comment_topic_summary`

输出：`core3_sku_semantic_profile`

画像包括：

- 核心参数强弱。
- 激活卖点及三类证据分。
- 评论关注点和情感。
- 缺失信号。
- 冲突信号。
- 画像置信度。

## 12. S10 用户任务、目标客群、价值战场反推

输入：

- 市场画像。
- 语义画像。
- approved seed 资产和映射。
- 候选资产仅作为低置信提示。

输出：

- `core3_sku_task_score`
- `core3_sku_target_group_score`
- `core3_sku_battlefield_score`

推导顺序：

```text
参数和卖点说明“产品能解决什么任务”
评论说明“用户实际感知到什么”
价格、销量、渠道说明“市场是否验证这个任务”
任务组合推导客群
任务、客群、卖点组合和市场验证推导战场
```

## 13. S11 候选池召回

候选池不按品牌排除：

```text
all_skus - target_sku
```

硬过滤：

- 不同类目。
- 无任何可比市场数据且无参数数据。
- 尺寸完全不可比，除非战场规则允许。

软召回条件：

- 同尺寸或相邻尺寸。
- 同价位或形成价格压力。
- 同任务。
- 同价值战场。
- 同渠道。
- 近期销量强或价格下探。

输出：`core3_competitor_candidate`

## 14. S12 组件评分和三槽位选择

组件分：

- 尺寸相似。
- 价格相似。
- 渠道重合。
- 标准参数相似。
- 参数优势。
- 标准卖点相似。
- 评论关注点相似。
- 用户任务相似。
- 价值战场相似。
- 销量强度。
- 价格压力。
- 价格下探风险。

三槽位：

- 正面对打：最像、最抢同一批用户。
- 价格/销量挤压：用更低价、更强销量或促销下探形成压力。
- 高端标杆/潜在下探：参数、战场或销量更强，或价格下探后会压到目标。

不能用综合 Top3 代替三槽位。

## 15. S13 证据卡和业务报告生成

输出：

- 目标型号主画像。
- 主战场推导链。
- 候选池收敛过程。
- 三竞品结论。
- 每个竞品的证据卡。
- 数据不足说明。

页面语言必须是业务语言，不展示内部字段名、英文枚举、UUID、`source_type`、`task_code`。

