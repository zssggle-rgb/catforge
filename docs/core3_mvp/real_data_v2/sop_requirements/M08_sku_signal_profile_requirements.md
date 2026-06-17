# M08 SKU 综合信号画像 SOP 需求

## 0. 单模块强化状态

本文件已按“单模块逐一强化”要求完成第一轮强化。下一步应处理 M09 用户任务模块。

## 1. 模块目标

M08 把 M03 参数、M04b 最终卖点、M06 评论下游信号、M07 市场画像合并成 SKU 级统一信号画像，作为 M09-M15 的默认特征入口。

M08 要解决五个问题：

1. 下游模块不应各自回读参数、卖点、评论、市场散表，而应先消费统一 SKU 画像。
2. 每个 SKU 的参数、卖点、评论、市场覆盖情况、证据缺口和风险要集中表达。
3. 85E7Q 这类“参数强、评论多、市场有、结构化卖点缺失”的 SKU，画像必须能准确表达强项与证据缺口。
4. 任务、客群、战场、候选召回、组件评分和报告，需要的是同一套可追溯特征，而不是各模块临时拼口径。
5. 增量运行时，M08 要生成 profile hash，只有画像变化才触发后续模块重算。

M08 不生成新的业务结论，不判断任务、客群、战场或竞品。它是“统一特征装配层”和“下游接口层”。

## 2. 设计依据

本模块依据：

- `cankao/CatForge_竞品生成SOP_详细指导_v1.md` 的 M08 要求。
- `cankao/catforge_sop_md/modules/M08_SKU 综合信号画像.md`。
- M03 已强化后的标准参数画像。
- M04b 已强化后的最终卖点激活。
- M06 已强化后的评论下游信号。
- M07 已强化后的市场画像与可比池基线。
- [00 真实样例数据基线](00_real_data_baseline.md)。
- 数据分层原则：下游默认消费 M08，不直接读取原始表做业务判断。

## 3. 上游输入

### 3.1 必须输入

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| `core3_clean_sku` | M01 | SKU 主数据、品牌、品类、跨表覆盖 |
| `core3_extract_param_value` | M03 | 标准参数明细 |
| `core3_sku_param_profile` | M03 | SKU 级参数画像、完整度、冲突 |
| `core3_sku_claim_activation` | M04b | 最终卖点激活、评论验证、缺失信号 |
| `core3_sku_claim_comment_validation` | M04b | 评论对卖点的体验验证 |
| `core3_sku_comment_signal_profile` | M06 | 七类评论信号摘要 |
| `core3_comment_downstream_signal` | M06 | 聚合评论信号 |
| `core3_sku_market_profile` | M07 | 市场画像 |
| `core3_market_signal` | M07 | 市场信号 |
| `core3_comparable_pool_baseline` | M07 | 可比池摘要 |
| `core3_evidence_atom` | M02 | evidence 追溯 |

### 3.2 明确不消费

| 数据 | 处理 |
| --- | --- |
| 原始 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data` | 不直接读取 |
| M09 任务结果 | M08 是 M09 上游 |
| M10 客群结果 | M08 是 M10 上游 |
| M11 战场结果 | M08 是 M11 上游 |
| M12-M15 竞品和报告结果 | M08 是它们的上游 |

## 4. 本模块不做什么

- 不重新抽取参数。
- 不重新激活卖点。
- 不重新解析评论。
- 不重新计算市场指标。
- 不生成最终用户任务。
- 不生成目标客群。
- 不生成价值战场。
- 不召回候选 SKU。
- 不做竞品评分或核心三竞品选择。
- 不把数据缺失解释成业务能力弱。

## 5. 画像结构

M08 的 SKU 画像由八个部分组成：

| 画像部分 | 来源 | 作用 |
| --- | --- | --- |
| 主数据画像 | M01 | SKU、型号、品牌、品类、数据覆盖 |
| 参数画像 | M03 | 尺寸、画质、背光、游戏、音频、系统、护眼参数 |
| 卖点画像 | M04b | 最终卖点激活、参数/宣传/评论构成、缺失信号 |
| 评论画像 | M06 | 卖点验证、任务线索、客群线索、战场支撑、风险、价格、服务 |
| 市场画像 | M07 | 价格、销量、销额、平台、分位、趋势 |
| 可比池摘要 | M07 | 同尺寸、同价、平台重合、样本状态 |
| 质量风险画像 | M01-M07 | unknown、卖点缺失、评论重复、样本不足、冲突 |
| 证据索引 | M02-M07 | 核心 evidence、证据覆盖、回溯入口 |

## 6. 合并规则

### 6.1 主数据合并

以 `core3_clean_sku` 为主：

- `sku_code`
- `model_name`
- `brand_name`
- `category_code`
- `source_tables`
- `coverage_json`

跨表冲突不能静默覆盖，必须进入 `profile_quality_flags`。

### 6.2 参数摘要

从 M03 汇总：

- 核心参数：尺寸、分辨率、Mini LED/OLED/QLED、亮度、分区、刷新率、HDMI、音频、内存、存储、语音、护眼等。
- 参数完整度。
- unknown 参数数。
- 参数冲突数。
- 口径不确定，例如刷新率原生/系统不明确。

M08 不重新解析参数，只保留 M03 的标准结果和质量状态。

### 6.3 卖点摘要

从 M04b 汇总：

- high/medium/low/unknown 的最终卖点。
- `activation_basis`：`param_and_promo`、`param_only`、`promo_only`、`comment_enhanced`、`comment_only_hint`。
- `perception_status`：validated/weak_perception/contradicted/insufficient_comment/not_applicable。
- 缺失信号：例如 `missing_structured_claim`。
- 评论验证和风险。

M08 必须保留“参数支撑、宣传支撑、评论验证”的拆分，不能只保存一个总分。

### 6.4 评论信号摘要

从 M06 汇总七类信号：

- `claim_validation`
- `task_cue`
- `target_group_cue`
- `battlefield_support`
- `pain_point`
- `price_perception`
- `service_signal`

M08 不把这些信号升级为最终任务、客群或战场，只为 M09-M11 提供统一输入。

### 6.5 市场摘要

从 M07 汇总：

- 观察窗口。
- 加权均价、最新均价。
- 总销量、总销额。
- 平台占比。
- 价格分位、销量分位、销额分位。
- 同尺寸和同价可比池摘要。
- 样本充分性。

M08 不把市场信号解释成卖点或评论结论。

## 7. 数据完整度

M08 输出整体数据完整度，也要输出分域完整度。

建议首版：

```text
data_completeness_score =
  sku_master_completeness * 0.10
  + param_completeness * 0.25
  + claim_completeness * 0.20
  + comment_completeness * 0.20
  + market_completeness * 0.25
```

分域完整度：

| 维度 | 计算口径 |
| --- | --- |
| `sku_master_completeness` | SKU、型号、品牌、品类是否稳定 |
| `param_completeness` | 核心参数覆盖率、unknown 率、冲突率 |
| `claim_completeness` | 结构化卖点覆盖、最终卖点激活、缺失状态 |
| `comment_completeness` | 去重评论数、有效句数、低价值率、信号覆盖 |
| `market_completeness` | 有效周数、价格/销量/销额、平台、可比池 |

缺失不等于负向能力。完整度用于置信度和复核，不直接作为业务结论。

## 8. 风险与缺失信号

M08 必须统一输出风险：

| 风险 | 来源 | 说明 |
| --- | --- | --- |
| `missing_structured_claim` | M04a/M04b | 结构化卖点缺失 |
| `param_unknown_high` | M03 | 参数 unknown 率高 |
| `param_conflict` | M03 | 同参数多值或口径冲突 |
| `comment_low_value_high` | M05/M06 | 低价值评论占比高 |
| `comment_service_dominant` | M05/M06 | 服务评论占比过高 |
| `comment_signal_insufficient` | M06 | 评论信号不足 |
| `market_sample_limited` | M07 | 市场样本有限 |
| `market_missing` | M07 | 无市场数据或关键市场字段缺失 |
| `comparable_pool_insufficient` | M07 | 可比池过小 |
| `evidence_low_confidence` | M02-M07 | 核心证据置信度低 |

## 9. 输出数据契约

### 9.1 `core3_sku_signal_profile`

| 字段 | 说明 |
| --- | --- |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `brand_name` | 品牌 |
| `source_tables` | 数据来源覆盖 |
| `size_segment` | 尺寸段 |
| `price_band` | 价格带 |
| `main_platform` | 主平台 |
| `core_params_json` | 核心参数摘要 |
| `param_profile_json` | 参数完整度、unknown、冲突 |
| `claim_activation_summary_json` | 最终卖点摘要 |
| `claim_evidence_breakdown_json` | 参数/宣传/评论证据拆分 |
| `comment_signal_summary_json` | 七类评论信号摘要 |
| `market_summary_json` | 市场画像摘要 |
| `comparable_pool_summary_json` | 可比池摘要 |
| `missing_signals_json` | 缺失信号 |
| `risk_signals_json` | 风险信号 |
| `data_completeness_score` | 整体数据完整度 |
| `domain_completeness_json` | 分域完整度 |
| `confidence` | 画像置信度 |
| `profile_status` | ready/limited/review_required/insufficient |
| `evidence_ids` | 核心证据 |
| `profile_hash` | 画像 hash |
| `feature_version` | 特征版本 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

### 9.2 `core3_sku_signal_evidence_matrix`

用于下游和报告快速判断各类证据是否可用。

| 字段 | 说明 |
| --- | --- |
| `sku_code` | SKU |
| `domain` | sku/param/claim/comment/market/pool/quality |
| `evidence_count` | 证据数 |
| `high_confidence_count` | 高置信证据数 |
| `low_confidence_count` | 低置信证据数 |
| `missing_flag` | 是否缺失 |
| `risk_flags` | 风险 |
| `representative_evidence_ids` | 代表证据 |
| `domain_confidence` | 分域置信度 |

### 9.3 `core3_sku_downstream_feature_view`

面向下游模块的特征视图，减少下游重复拼装。

| 字段 | 说明 |
| --- | --- |
| `sku_code` | SKU |
| `for_module` | M09/M10/M11/M11.5/M12/M13/M14/M15 |
| `feature_payload_json` | 模块所需特征 |
| `feature_quality_flags` | 特征风险 |
| `required_missing_fields` | 必需但缺失字段 |
| `evidence_ids` | 证据 |
| `profile_hash` | 依赖画像 hash |

MVP 可先用 JSON 视图实现，但需求上必须保证每个下游模块的特征边界清晰。

## 10. 下游特征边界

### 给 M09 用户任务

提供：

- 参数任务支撑。
- 最终卖点激活。
- `task_cue` 评论线索。
- 价格价值感、市场分位、销量信号。
- 缺失和风险。

M09 不能直接读取 M03/M04b/M06/M07 散表，除非通过 M08 evidence 回溯。

### 给 M10 目标客群

提供：

- M09 任务结果之外的 SKU 基础画像。
- `target_group_cue` 评论线索。
- 价格带、平台、市场位置。
- 服务信号和风险。

### 给 M11 价值战场

提供：

- 最终卖点激活。
- `battlefield_support` 评论信号。
- 市场分位和样本状态。
- 风险和缺失。

### 给 M11.5 卖点价值分层

提供：

- 最终卖点激活。
- 可比池摘要。
- 市场基线。
- 评论验证和风险。

M11.5 仍需结合战场结果，不由 M08 输出价值层级。

### 给 M12/M13/M14

提供：

- SKU 可比基础：尺寸、价格、平台、市场强度。
- 参数和卖点摘要。
- 评论信号摘要。
- 证据完整度和风险。

竞品召回和评分不能绕过 M08 直接拼原始数据。

### 给 M15 报告

提供：

- 业务可读的 SKU 画像。
- 证据矩阵。
- 缺失和风险说明。
- 代表 evidence。

M15 不展示 M08 的内部 JSON 字段名，而是转换为业务语言。

## 11. 85E7Q 样例要求

85E7Q 的 M08 画像必须能表达：

| 维度 | 画像要求 |
| --- | --- |
| 主数据 | `model_code=TV00029115`，型号 85E7Q |
| 参数 | 85 英寸、4K、300HZ、MiniLED、5200 亮度、3500 分区、HDMI2.1、4GB/64GB、海信星海 |
| 卖点 | 结构化卖点缺失，技术型卖点可有 `param_only` 基础和评论体验验证，但不能伪造宣传证据 |
| 评论 | 3621 行评论、1648 个去重评论 ID，需区分画质、看球、音效、价格、智能、服务信号 |
| 市场 | 26W01-26W23 周量价，线上渠道，专业电商/平台电商 |
| 可比池 | 85 寸同尺寸池和 75/100 相邻尺寸池 |
| 风险 | `missing_structured_claim`、评论重复/服务占比、样本池有限 |
| 状态 | 可做 MVP 分析，但部分卖点和全市场竞品覆盖需复核 |

## 12. 真实数据约束

当前 205 样例数据对 M08 的硬约束：

- 市场有 35 个型号，参数有 35 个型号，评论有 33 个型号，卖点只有 5 个型号。
- M08 不能只为四类数据都齐全的 SKU 生成画像；必须支持部分缺失。
- 当前所有品牌均为海信，画像不做品牌内外判断。
- 当前渠道只有线上，不生成线下字段结论。
- 评论行数大但重复明显，画像必须使用 M05/M06 的去重和质量口径。
- 卖点缺失不能当成无卖点。
- unknown 参数不能当 false。

## 13. 复核触发条件

以下情况进入复核或 warning：

- SKU 缺市场、参数、评论中任一关键域，但仍进入核心分析。
- 目标 SKU 或高销量 SKU 缺结构化卖点。
- 参数冲突或刷新率/HDMI 等关键口径不明确。
- 评论有效信号不足或服务评论占比过高。
- 市场样本不足或可比池不足。
- M08 画像较上一版本发生重大变化。
- 下游必需特征缺失。
- 核心 evidence 置信度低。

## 14. 增量重算要求

| 输入变化 | M08 动作 | 下游影响 |
| --- | --- | --- |
| M03 参数画像变化 | 重算对应 SKU 参数摘要和完整度 | M09-M16 |
| M04b 卖点激活变化 | 重算卖点摘要和证据拆分 | M09-M16 |
| M06 评论信号变化 | 重算评论摘要和风险 | M09-M16 |
| M07 市场画像或可比池变化 | 重算市场摘要和池摘要 | M09-M16 |
| M02 evidence 状态变化 | 更新证据矩阵和置信度 | M09-M16 |
| M01 SKU 主数据变化 | 重算主数据和覆盖 | M08-M16 |

如果 `profile_hash` 未变化，不触发下游重算。

## 15. 验收标准

| 验收项 | 标准 |
| --- | --- |
| 有效 SKU 都能生成画像 | 必须 |
| 支持部分数据缺失 SKU | 必须 |
| 参数、卖点、评论、市场分域摘要齐全 | 必须 |
| 结构化卖点缺失可表达 | 必须 |
| unknown 不当 false | 必须 |
| 评论使用 M05/M06 去重和质量口径 | 必须 |
| 画像包含 evidence matrix | 必须 |
| 画像包含 profile_hash | 必须 |
| M09-M15 优先消费 M08 | 必须 |
| M08 不生成任务、客群、战场或竞品结论 | 必须 |
| 85E7Q 画像能表达强项和证据缺口 | 必须 |
