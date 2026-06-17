# M02 Evidence 原子层 SOP 需求

## 0. 单模块强化状态

本文件已按“单模块逐一强化”要求完成第一轮强化。下一步应处理 M03 参数字段画像与标准参数抽取。

## 1. 模块目标

M02 把 M01 清洗后的事实和质量问题转换成全链路可复用的 evidence 原子，解决“任何后续结论能追溯到哪条真实数据、哪条清洗事实、质量状态如何”的问题。

M02 的目标不是做业务判断，而是建立证据底座：

1. 为市场、参数、卖点、评论、评论维度、质量问题生成统一 `evidence_id`。
2. 保留原始表、原始行、清洗表、清洗行、原值、清洗值和质量状态。
3. 给出证据可用性的基础置信度，供下游评分降权。
4. 支持增量失效和版本追溯，旧 evidence 不物理删除。
5. 约束下游模块：所有业务结论必须引用 evidence，不能只保存结论。

## 2. 设计依据

本模块依据：

- `cankao/CatForge_竞品生成SOP_详细指导_v1.md` 的 M02 要求。
- `cankao/catforge_sop_md/modules/M02_Evidence 原子层.md`。
- M00 已强化后的来源登记设计。
- M01 已强化后的清洗事实表和质量诊断设计。
- [00 真实样例数据基线](00_real_data_baseline.md)。
- 数据分层原则：Evidence 是清洗事实之后、业务抽取之前的独立层。

## 3. 上游输入

M02 消费 M01 的清洗表和质量问题表：

| 上游表 | 生成的 evidence 类型 | 说明 |
| --- | --- | --- |
| `core3_clean_sku` | `sku_fact` | SKU 主数据覆盖和跨表一致性事实 |
| `core3_clean_market_weekly` | `market_fact` | 周销量、销额、均价、渠道、平台事实 |
| `core3_clean_attribute` | `param_raw` | 原始参数名和值的清洗事实 |
| `core3_clean_claim` | `promo_raw` | 原始宣传卖点清洗事实 |
| `core3_clean_claim_sentence` | `promo_sentence` | 宣传卖点句级事实 |
| `core3_clean_comment` | `comment_raw` | 评论原文和分段清洗事实 |
| `core3_clean_comment_sentence` | `comment_sentence` | 评论句级事实 |
| `core3_clean_comment_dimension` | `comment_dimension` | 原始评论维度弱标签事实 |
| `core3_data_quality_issue` | `quality_issue` | 数据质量问题 evidence |

M02 还需要读取 M00 的 `core3_source_row_registry`，用于补充原始表、原始主键、来源行和行级 hash。

## 4. 本模块不做什么

- 不判断参数是否属于标准参数，M03 负责。
- 不判断卖点是否成立，M04a/M04b 负责。
- 不解释评论语义，M05/M06 负责。
- 不从评论维度直接生成任务、客群、战场或卖点。
- 不把质量问题当成业务事实。
- 不把缺结构化卖点解释为“没有卖点”。
- 不做市场画像、SKU 画像或竞品评分。

## 5. Evidence 分层和粒度

M02 输出的 evidence 是“事实证据”或“质量证据”，不是“业务结论证据”。

### 5.1 事实证据

事实证据来自清洗表：

| 类型 | 粒度 | 下游主要用途 |
| --- | --- | --- |
| `sku_fact` | SKU 覆盖粒度 | M08 识别 SKU 数据覆盖，M16 复核 |
| `market_fact` | SKU + 周期 + 平台粒度 | M07 市场画像，M13 市场压力 |
| `param_raw` | SKU + 参数名粒度 | M03 参数抽取，M04a 卖点激活 |
| `promo_raw` | SKU + 卖点序号粒度 | M04a 宣传卖点切分 |
| `promo_sentence` | SKU + 卖点句粒度 | M04a 语义候选 |
| `comment_raw` | 评论原文粒度 | M05 评论基础证据 |
| `comment_sentence` | 评论句粒度 | M05/M06 评论信号抽取 |
| `comment_dimension` | 评论原始维度路径粒度 | M05 弱标签参考 |

### 5.2 质量证据

质量证据来自 `core3_data_quality_issue`：

- 参数 unknown。
- 卖点覆盖缺失。
- 评论低价值文本。
- 评论重复或拆行。
- 量价校验异常。
- 跨表主数据冲突。

质量证据只说明“数据质量或覆盖风险”，不能直接说明“业务能力弱”。

示例：

```text
85E7Q 没有结构化卖点行
=> 生成 claim_coverage_missing 的 quality_issue evidence
=> 不生成“85E7Q 没有卖点”的 promo evidence
```

## 6. Evidence ID 规则

### 6.1 稳定 ID

`evidence_id` 必须稳定、可重复生成。建议由以下字段计算：

```text
evidence_id = hash(
  project_id,
  category_code,
  evidence_type,
  source_row_id,
  clean_table,
  clean_record_key,
  evidence_field,
  evidence_version
)
```

### 6.2 版本字段

M02 必须记录：

- `evidence_version`：evidence 生成规则版本。
- `clean_hash`：来自 M01 的清洗结果 hash。
- `source_row_hash`：来自 M00 的原始行 hash。
- `asset_version`：后续资产版本占位，MVP 可为默认版本。

清洗规则变化导致同一事实重新生成时，应保留旧 evidence 并更新 current 状态。

## 7. 处理流程

1. 读取 M01 本批次 clean insert/changed 的清洗事实。
2. 对每条清洗事实确定 evidence 类型和粒度。
3. 生成稳定 `evidence_id`。
4. 填充来源信息：原始表、原始主键、`source_row_id`、清洗表、清洗行键。
5. 填充事实信息：字段名、原值、清洗值、数值候选、文本候选、时间、渠道、平台等。
6. 根据 M01 `quality_status` 和 `quality_flags` 计算基础置信度。
7. 为 M01 质量问题生成 `quality_issue` evidence。
8. 对清洗行已失效或 hash 变化的旧 evidence 标记为 inactive。
9. 输出 evidence atom 和可选 evidence link，供下游引用。

## 8. 输出数据契约

### 8.1 `core3_evidence_atom`

| 字段 | 说明 |
| --- | --- |
| `evidence_id` | 稳定证据 ID |
| `project_id` | 项目 |
| `category_code` | 品类，MVP 为 TV |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号展示名 |
| `brand_name` | 品牌 |
| `evidence_type` | 证据类型 |
| `evidence_grain` | row/field/sentence/dimension/quality |
| `source_table` | 原始表 |
| `source_pk` | 原始主键 |
| `source_row_id` | 来源行 |
| `source_row_hash` | 原始行 hash |
| `clean_table` | 清洗表 |
| `clean_record_key` | 清洗行键 |
| `clean_hash` | 清洗结果 hash |
| `raw_field` | 原始字段 |
| `raw_value` | 原值 |
| `clean_field` | 清洗字段 |
| `clean_value` | 清洗值 |
| `numeric_value` | 数值候选 |
| `unit_value` | 单位候选 |
| `text_value` | 文本候选 |
| `evidence_time` | 证据发生时间 |
| `period_raw` | 市场周期原值 |
| `channel_type` | 渠道 |
| `platform_type` | 平台 |
| `quality_status` | ok/warn/error |
| `quality_flags` | 质量标签 |
| `base_confidence` | 证据可用性基础置信度 |
| `evidence_status` | current/inactive/superseded |
| `evidence_version` | evidence 规则版本 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

### 8.2 `core3_evidence_link`

用于描述一个证据与其它证据的弱关联，首版主要服务评论拆行、评论维度和质量问题关联。

| 字段 | 说明 |
| --- | --- |
| `link_id` | 关联 ID |
| `from_evidence_id` | 起始 evidence |
| `to_evidence_id` | 目标 evidence |
| `link_type` | same_comment/same_sentence/has_dimension/has_quality_issue/same_source_row |
| `confidence` | 关联可信度 |
| `created_at` | 创建时间 |

MVP 如果不实现单独 link 表，也必须在 `core3_evidence_atom` 中保留能重建关联的键，例如 `comment_id`、`comment_text_hash`、`segment_text_hash`、`source_row_id`。

## 9. Evidence 类型规则

### 9.1 市场 evidence

`market_fact` 必须从 `core3_clean_market_weekly` 生成。

最小证据字段：

- 周期。
- 渠道和平台。
- 销量。
- 销额。
- 均价。
- 均价校验状态。

市场 evidence 是事实，不在 M02 计算趋势、份额或价格带。

### 9.2 参数 evidence

`param_raw` 必须从 `core3_clean_attribute` 生成。

最小证据字段：

- 原始属性名。
- 清洗属性名。
- 原始属性值。
- 清洗属性值。
- 数字候选和单位候选。
- value presence。

unknown 参数可以生成 evidence，但 `base_confidence` 应降低，并明确 `quality_flags`。unknown evidence 用于说明“该字段缺失或未知”，不是 false 证据。

### 9.3 卖点 evidence

`promo_raw` 和 `promo_sentence` 分别从 `core3_clean_claim`、`core3_clean_claim_sentence` 生成。

最小证据字段：

- 卖点序号。
- 原始宣传文本。
- 清洗文本。
- 句级文本。
- 标题或句子角色弱提示。

未覆盖卖点的 SKU 不生成 promo evidence，只生成质量问题 evidence。

### 9.4 评论 evidence

`comment_raw` 和 `comment_sentence` 分别从 `core3_clean_comment`、`core3_clean_comment_sentence` 生成。

最小证据字段：

- 评论 ID。
- 评论正文 hash。
- 分段 hash。
- 句级文本。
- 原始情感和清洗情感。
- 低价值标记。
- 重复组键。

低价值评论可以生成 evidence，但 `base_confidence` 必须低，并且下游默认不得把它作为强支撑。

### 9.5 评论维度 evidence

`comment_dimension` 从 `core3_clean_comment_dimension` 生成。

维度 evidence 只代表上传数据中的原始弱标签：

```text
送装维保 / 安装服务 / 安装整体服务
产品质量 / 显示画质 / 画质整体评价
```

M02 不把这些维度转换成用户任务、客群、战场或卖点。

### 9.6 质量 evidence

`quality_issue` 从 `core3_data_quality_issue` 生成。

质量 evidence 用于：

- 降低下游置信度。
- 触发 M16 复核。
- 在 M15 报告中说明数据限制。

质量 evidence 不得被当成业务事实。例如“卖点覆盖缺失”不能解释为“商品没有卖点”。

## 10. 基础置信度规则

`base_confidence` 只代表证据可用性，不代表业务结论正确性。

| 证据情况 | 建议基础置信度 |
| --- | ---: |
| 结构化市场量价，数值解析成功且均价校验通过 | 0.95 |
| 结构化参数，非 unknown，字段来源明确 | 0.90 |
| 结构化卖点原文，来源明确 | 0.85 |
| 卖点句级文本，切句清晰 | 0.80 |
| 评论原文有效，非低价值，非明显重复 | 0.75 |
| 评论句级文本有效，非低价值 | 0.70 |
| 评论原始维度弱标签 | 0.55 |
| 参数 unknown 或缺失质量 evidence | 0.35 |
| 默认评价、空评价、低价值评论 | 0.25 |
| 数值异常、跨表冲突等 error 质量 evidence | 0.20 |

置信度可以由规则版本配置，但必须记录版本。

## 11. 增量与失效策略

M02 处理 M01 的 clean hash 变化：

```text
same clean_record_key + same clean_hash => evidence no_change
same clean_record_key + different clean_hash => old evidence inactive, new evidence current
clean_record_key not seen in current full scan => evidence inactive
quality issue resolved => old quality evidence inactive
```

要求：

- 不物理删除旧 evidence。
- 下游历史报告引用旧 evidence 时仍可追溯。
- 新版本报告只默认引用 `current` evidence。
- evidence 失效必须记录原因。

## 12. 与下游模块关系

### 给 M03 的承诺

- M03 只从 `param_raw` evidence 抽取标准参数。
- M03 可以使用 unknown evidence 判断字段缺失，但不能把 unknown 当 false。

### 给 M04a/M04b 的承诺

- M04a 使用 `promo_raw`、`promo_sentence`、`param_raw` evidence 做基础卖点激活。
- M04b 使用 M06 评论信号及其 evidence 做评论增强。
- 对没有结构化卖点的 SKU，只能看到质量缺口 evidence，不能看到伪造 promo evidence。

### 给 M05/M06 的承诺

- M05 使用 `comment_raw`、`comment_sentence`、`comment_dimension` evidence 生成评论基础证据。
- M06 在 M05 基础上抽取任务、客群、战场、卖点、痛点等下游信号。
- M02 的评论维度只是弱标签。

### 给 M07/M08 的承诺

- M07 使用 `market_fact` evidence 做市场画像。
- M08 汇总 SKU 画像时必须保留 evidence 引用和质量风险。

### 给 M12-M15 的承诺

- 候选召回、组件评分、核心竞品选择和报告都必须能回溯到 M02 evidence。
- M15 展示时可把 evidence 转成中文证据摘要，但不能丢失 evidence_id。

### 给 M16 的承诺

- M16 可基于 evidence 状态、置信度和质量 evidence 编排重算与复核。

## 13. 真实数据约束

当前 205 样例数据对 M02 的硬约束：

- 85E7Q 有参数和评论 evidence，应完整生成；结构化卖点 evidence 应为空，但要有卖点覆盖缺失质量 evidence。
- 卖点只覆盖 5 个型号，M02 不得把卖点 evidence 扩展到其它 30 个未覆盖型号。
- 评论表存在维度拆行和重复正文，M02 必须能通过 `comment_id`、正文 hash、分段 hash 和 evidence link 保留关系。
- 评论维度空值高，空维度生成低置信质量 evidence 或维度缺失标记，不能当中立业务信号。
- 情感为空的评论必须是 unknown，不是中立。
- 市场数据只有线上和两个平台，market evidence 不得生成线下相关证据。
- 当前品牌只有海信，evidence 只记录品牌事实，不判断是否内部竞品。

## 14. 复核触发条件

M02 应向 M16 输出复核或 warning：

- 某批次清洗事实没有生成 evidence。
- evidence 无法回溯到 `source_row_id`。
- 同一 clean fact 生成重复 current evidence。
- 大量 evidence 置信度低。
- 某 SKU 关键 evidence 域缺失，例如 85E7Q 缺 promo evidence。
- 评论 evidence 重复组异常集中。
- quality issue evidence 数量异常升高。
- 旧 evidence 被失效但没有新 current evidence。

## 15. 验收标准

| 验收项 | 标准 |
| --- | --- |
| 清洗事实都有对应 evidence 或明确跳过原因 | 必须 |
| evidence 可追溯到 M01 清洗行和 M00 原始行 | 必须 |
| `evidence_id` 稳定可重复生成 | 必须 |
| unknown evidence 与 false 证据严格区分 | 必须 |
| 质量 evidence 不被当成业务事实 | 必须 |
| 评论多维度、多分段、多重复关系可追溯 | 必须 |
| 旧 evidence 逻辑失效、不物理删除 | 必须 |
| 下游结论必须引用 evidence_id | 必须 |
| 85E7Q 不生成伪造卖点 evidence | 必须 |
| M02 不做参数、卖点、任务、战场或竞品判断 | 必须 |
