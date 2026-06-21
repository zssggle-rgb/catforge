# M05C 评论事实画像 SOP 需求

## 0. 定位

M05C 是新事实层的“评论事实画像”模块族，承接 M02 评论 evidence、M03B SKU 参数事实画像、M04C SKU 卖点事实画像和 M07 市场画像，把真实用户评论转成可追溯、可查询、可供后续语义能力层消费的评论事实。

M05C 不沿用旧 M06 的用户任务、目标客群、价值战场 seed，也不直接输出用户任务、目标客群、价值战场或竞品结论。它只回答：

1. 当前品类评论应从哪些事实维度观察。
2. 某个 SKU 的评论真实支持了哪些产品体验、参数和卖点。
3. 某个 SKU 的评论反证了哪些参数或卖点。
4. 评论中出现了哪些人群、用途、尺寸/空间、价格/价值、品牌力、竞品提及和产品风险线索。
5. 每个评论事实维度覆盖哪些 SKU，证据是什么。

M05C 是事实层，不是结论层。

## 1. 模块拆分

| 子能力 | 生命周期 | 职责 |
| --- | --- | --- |
| M05C-A 评论事实维度 taxonomy | 人工/LLM 产物，不写生成程序 | 由分析者按品类读取真实评论、标准参数、标准卖点和市场维度后生成并发布 taxonomy |
| M05C-B SKU 评论事实画像与维度统计 | 工程程序，高频，新数据批次运行 | 使用已发布 taxonomy，把每个 SKU 的 M02 评论句映射成评论事实原子，聚合成 SKU 评论事实画像，并像参数/卖点一样生成评论维度统计与覆盖 |
| M05C-C 评论事实查询能力 | 高频，读取 M05C-B 结果 | 支持查询某个 SKU、某个维度、某个人群/用途/品牌力/竞品线索覆盖哪些 SKU |

业务讨论中提到的“m05b”对应本设计中的 M05C-B，也就是“SKU 评论事实画像与维度统计”生成阶段。该阶段必须使用 LLM 完成评论语义分类、正负向判断、人群/用途/品牌力/竞品线索识别和复杂句拆解；规则只作为候选召回和低风险保护，不替代 LLM。M05C-C 是查询阶段，只读取 M05C-B 结果，不调用 LLM。

M05C-A 不实现 taxonomy 生成 runner，不进入 `catforge_pipeline`，也不由 Claude Code 在运行时自动归纳。每个新品类的评论事实 taxonomy 由分析者先生成文档和资产文件，经人工确认后发布。

如果品类没有已发布评论事实 taxonomy，M05C-B 必须阻断。M05C-B 不能运行时自动借用其他品类 taxonomy，也不能自动新增标准维度。

## 2. 与既有 M05/M06/M08.4 的边界

| 模块 | 新定位 |
| --- | --- |
| M05 | 历史评论基础证据层，可保留；新链路主语料直接以 M02 `comment_sentence` 为准 |
| M06 | 历史评论下游信号抽取，依赖旧 seed，不作为新事实层依据 |
| M08.4 | 历史评论原生业务维度发现，可作为参考，但不作为新标准评论维度发布来源 |
| M05C | 新评论事实 taxonomy、句级评论事实原子、SKU 评论事实画像和维度覆盖索引 |

M05C 不能直接使用旧 M06 的用户任务、目标客群、价值战场预设。评论中的人群和用途只能保留为事实线索，后续再由语义能力层生成用户任务和目标客群。

新链路落地后，主执行顺序不再要求运行旧 M05 和旧 M06：

```text
M00 原始数据登记
-> M01 清洗过滤
-> M02 Evidence 原子层
-> M03B SKU 参数事实画像
-> M04C SKU 卖点事实画像
-> M07 市场画像
-> M05C SKU 评论事实画像
-> 新语义能力层：用户任务、目标客群、价值战场
-> 新画像层和竞品分析层
```

旧 M05/M06 只保留以下用途：

1. 历史结果回看。
2. 迁移期对照验证。
3. 尚未迁移的旧 M08-M16 链路临时兼容。

一旦下游语义能力层改为消费 M05C 输出，旧 M05/M06 不再进入常规执行计划。

## 3. 输入

### 3.1 M05C-A 人工生成输入

| 输入 | 来源 | 必需 | 用途 |
| --- | --- | --- | --- |
| M02 评论句 evidence | `core3_evidence_atom`，`evidence_type='comment_sentence'` | 是 | 从真实评论归纳标准评论事实维度 |
| M02 评论原文 evidence | `core3_evidence_atom`，`evidence_type='comment_raw'` | 是 | 统计评论单元、回溯原文 |
| M02 评论质量 evidence | `quality_issue` | 否但建议 | 识别低价值、服务履约、重复、模板等过滤边界 |
| M03B 标准参数 taxonomy | 参数事实层 | 是 | 作为品类级评论维度锚点 |
| M04C 标准卖点 taxonomy | 卖点事实层 | 是 | 作为品类级评论维度锚点 |
| M07 市场画像维度 | 市场画像层 | 否但建议 | 为价格区间、尺寸区间、市场位置评论线索提供锚点 |
| 人工/LLM 归纳草案 | `09_tv_comment_fact_dimension_draft.md` | 是 | 首版 TV 评论事实维度来源 |

M05C-A 可以由分析者使用 LLM 辅助归纳 taxonomy，但这不是运行时程序。发布后的 taxonomy 必须版本化、可审计、可复现，并作为 M05C-B 的只读资产输入。

### 3.2 M05C-B 输入

| 输入 | 来源 | 必需 | 用途 |
| --- | --- | --- | --- |
| 已发布评论事实 taxonomy | M05C-A | 是 | 标准维度、子维度、关键词、正负向表达、关联参数/卖点 |
| M02 评论句 evidence | `core3_evidence_atom`，`comment_sentence` | 是 | 句级评论事实抽取主语料 |
| M02 评论原文 evidence | `core3_evidence_atom`，`comment_raw` | 是 | 聚合评论数、回溯原文 |
| SKU 参数画像 | M03B `core3_sku_param_profile`、`core3_sku_param_dimension_tier` | 是 | 判断本 SKU 参数是否被本 SKU 评论支持或反证 |
| SKU 卖点画像 | M04C `core3_sku_claim_fact_profile`、`core3_sku_claim_fact` | 是 | 判断本 SKU 卖点是否被本 SKU 评论支持或反证 |
| SKU 市场画像 | M07 `core3_sku_market_profile` 等 | 否但建议 | 辅助价格、尺寸、市场位置评论解释 |
| 批次信息 | M00 | 是 | batch 边界、增量重跑范围 |

M05C-B 必须通过 LLM 生成句级评论事实。工程实现允许三种运行模式：

| 运行模式 | 用途 | 行为 |
| --- | --- | --- |
| `required` | 205 实库验证和正式需要确认调用模型的运行 | 未配置或调用失败即失败 |
| `auto` | 普通开发联调 | 配置了 LLM 就调用；未配置时可退回规则候选并给 warning |
| `off` | 本地确定性单元测试 | 不调用外部 LLM，仅用规则/fixture |

测试不得调用真实外部 LLM，必须使用 `off`、fake LLM 或 mock。

### 3.3 禁止输入

M05C-B 不允许绕过 M02 直接读取原始 `comment_data` 做业务判断。M01 只能作为抽样审计或误过滤恢复池，不能作为主分析语料。

M05C-B 必须按 `product_category` 加载 taxonomy：

| `product_category` | taxonomy 状态 | M05C-B 行为 |
| --- | --- | --- |
| `tv` | 首版 TV taxonomy 发布后可用 | 正常执行 |
| `ac`、`washer` 等其他品类 | 未发布前不可用 | 阻断并提示“该品类评论事实 taxonomy 未发布” |

后续新增品类时，不改 M05C-B 主流程，只新增该品类的人工 taxonomy 资产和必要的规则映射。

## 4. 输出

M05C-B 必须输出四类程序结果；评论事实 taxonomy 是 M05C-A 的人工发布资产，不由程序生成。

### 4.1 评论事实 taxonomy 人工发布资产

每个品类一套 taxonomy，至少包含：

- 一级评论事实维度。
- 二级评论事实维度。
- 维度定义。
- 包含规则和排除规则。
- 正向表达、负向表达、中性表达。
- 人群、用途、尺寸空间、价格价值、品牌力、竞品提及的抽取规则。
- 可关联标准参数。
- 可关联标准卖点。
- 服务履约隔离规则。
- 下游使用策略。

TV 首版 taxonomy 应以 `09_tv_comment_fact_dimension_draft.md` 为输入，至少覆盖：

| 一级维度 | 说明 |
| --- | --- |
| `picture_screen_experience` | 画质、屏幕、清晰度、亮度、色彩、控光、护眼、防眩、拖影 |
| `audio_cinema_experience` | 音质、音效、音量、影院/观影沉浸 |
| `system_interaction_experience` | 系统流畅、开机、广告、遥控、语音、投屏、联网、内容应用 |
| `gaming_motion_experience` | 游戏、主机、高刷、低延迟、HDMI2.1、看球/运动流畅 |
| `appearance_installation_space` | 尺寸、客厅/卧室、观看距离、挂墙、超薄、全面屏、壁画、家装适配 |
| `price_value_perception` | 性价比、价格、补贴、同价位、预算、值不值 |
| `audience_signal` | 老人、孩子、父母、家庭、年轻玩家、租房/农村/送礼/自用 |
| `use_case_signal` | 客厅主电视、卧室副电视、观影、追剧、体育、游戏、投屏、会议/商用 |
| `brand_power_signal` | 品牌信任、复购、口碑推荐、品牌忠诚 |
| `competitor_comparison_signal` | 跨品牌/型号比较、替换来源、明确竞品提及 |
| `product_quality_risk` | 画质、音质、系统、屏幕、故障、耐用等产品风险 |
| `service_fulfillment_excluded` | 安装、送货、客服、售后等服务履约隔离 |

### 4.2 句级评论事实原子

每条 M02 评论句可以生成 0-N 条评论事实原子。关键字段：

```text
sku_code
sentence_evidence_id
comment_dimension_code
comment_subdimension_code
polarity
evidence_strength
audience_signal
use_case_signal
size_space_signal
price_value_signal
brand_power_signal
competitor_comparison_signal
linked_sku_param_codes
linked_sku_claim_codes
support_relation
confidence
evidence_text
```

`support_relation` 必须区分：

| 关系 | 含义 |
| --- | --- |
| `supports_sku_param` | 本 SKU 有该参数，评论正向支持 |
| `contradicts_sku_param` | 本 SKU 有该参数，评论反向证伪或削弱 |
| `supports_sku_claim` | 本 SKU 有该卖点，评论正向支持 |
| `contradicts_sku_claim` | 本 SKU 有该卖点，评论反向证伪或削弱 |
| `comment_only_product_fact` | 评论有产品体验，但本 SKU 参数/卖点未覆盖 |
| `audience_signal_only` | 仅人群线索 |
| `use_case_signal_only` | 仅用途线索 |
| `brand_power_signal_only` | 仅品牌力线索 |
| `competitor_signal_only` | 仅竞品线索 |
| `service_excluded` | 服务履约隔离，不进入产品事实 |

### 4.3 SKU 评论事实画像

每个 SKU 一条聚合画像，至少包含：

- 评论覆盖：评论句数、评论原文数、可用句数、低置信句数。
- 评论事实维度分布。
- 产品体验正负面摘要。
- 参数被评论支持、反证、未提及清单。
- 卖点被评论支持、反证、未提及清单。
- 评论新增产品事实候选。
- 人群线索。
- 用途线索。
- 尺寸/空间线索。
- 价格/价值线索。
- 品牌力线索。
- 竞品提及线索。
- 产品质量风险。
- 典型正向证据句。
- 典型负向证据句。
- 复核项。

### 4.4 评论事实维度统计与覆盖

M05C-B 不只生成每个 SKU 的评论事实画像，还必须像 M03B 参数档位覆盖、M04C 卖点位置覆盖一样，生成品类批次级的评论事实维度统计。

统计粒度至少包括：

| 统计粒度 | 示例 | 用途 |
| --- | --- | --- |
| 评论事实维度 | `picture_screen_experience` | 看哪些 SKU 有画质评论证据，正负面分布如何 |
| 评论事实二级维度 | `clarity_resolution`、`anti_reflection` | 看具体体验点覆盖哪些 SKU |
| 人群线索 | 老人、孩子、家庭、租房 | 支撑后续目标客群生成 |
| 用途线索 | 客厅观影、卧室、游戏、投屏 | 支撑后续用户任务生成 |
| 尺寸/空间线索 | 75 寸合适、客厅距离、挂墙 | 支撑尺寸段和空间适配分析 |
| 价格/价值线索 | 性价比、同价位、补贴、贵/便宜 | 支撑价格价值判断 |
| 品牌力线索 | 信任、复购、推荐、忠诚 | 支撑品牌力画像 |
| 竞品提及线索 | 索尼、TCL、小米等明确提及或比较 | 支撑竞品候选与替换来源分析 |
| 参数评论支持 | `declared_refresh_rate_hz` 被评论支持/反证 | 连接参数事实和评论事实 |
| 卖点评论支持 | `tv_claim_high_refresh_rate` 被评论支持/反证 | 连接卖点事实和评论事实 |

每个统计项至少包含：

- 覆盖 SKU 数。
- 覆盖评论数。
- 覆盖句子数。
- 正向、负向、混合、中性数量。
- 强证据数量。
- 支持/反证的参数和卖点数量。
- 覆盖 SKU 清单。
- Top SKU。
- 代表证据句。
- 样本是否充足。
- 是否需要复核。

M05C-C 只负责读取这些统计结果并提供查询，不重新计算统计。

### 4.5 评论事实查询覆盖

为以下查询生成覆盖索引：

- 某个评论事实维度覆盖哪些 SKU。
- 某个人群线索覆盖哪些 SKU。
- 某个用途线索覆盖哪些 SKU。
- 某个品牌力信号覆盖哪些 SKU。
- 某个竞品/品牌被哪些 SKU 评论提及。
- 某个标准参数被评论支持或反证的 SKU。
- 某个标准卖点被评论支持或反证的 SKU。

## 5. 评论事实判断规则

### 5.1 品类层与 SKU 层必须分开

标准参数、标准卖点在生成评论事实 taxonomy 时只是品类级锚点，不能推出某个 SKU 被评论支持。

SKU 层必须回到本 SKU：

1. 本 SKU 是否有该参数事实。
2. 本 SKU 是否有该卖点事实。
3. 本 SKU 评论是否出现一致或相反体验证据。

### 5.2 缺失不是 false

除 M03B 已明确定义为 `false_by_absence` 的参数外，缺失参数不能当作没有该功能。

评论中出现体验但参数缺失时，只能输出：

- `comment_only_product_fact`
- `param_missing_review_required`
- `claim_missing_review_required`

不能自动补参数或补卖点。

### 5.3 服务履约隔离

安装、送货、客服、售后、保修、师傅态度等服务履约内容不得进入产品评论事实画像。

如果一句评论同时包含服务和产品事实，必须拆句或拆事实，只保留产品事实部分进入产品画像。

### 5.4 品牌力是正式评论事实

品牌信任、复购、朋友推荐、家人推荐、大品牌、老牌子、一直用等表达必须作为 `brand_power_signal` 保存。它不是噪声，也不能只作为竞品排除项。

跨品牌/型号比较、替换来源和明确“比/对比/比较”才进入 `competitor_comparison_signal`。

### 5.5 负向判断不能只靠关键词

“不卡顿”“无广告”“不反光”“不刺眼”是正向，不得因命中“卡顿/广告/反光/刺眼”而标负向。

M05C 必须区分：

- 正向否定：无广告、不卡、不反光、不刺眼。
- 负向表达：广告多、卡顿、反光严重、刺眼。
- 混合表达：整体好但略有反光。
- 不确定：语义不足或上下文缺失。

## 6. LLM 要求

M05C 必须支持 LLM。规则只能做快速预分类、低风险直接命中和候选召回，不能完全替代 LLM。

LLM 使用要求：

1. 按 SKU 分块处理，避免一次输入跨太多 SKU。
2. 每批默认 20 条句子；如模型稳定且超时率低，可按部署情况调大。
3. 每批输入只包含必要 taxonomy 摘要、本 SKU 参数摘要、本 SKU 卖点摘要和评论句。
4. 输出必须是 JSON，符合固定 schema。
5. `llm-mode=required` 时未配置或调用失败必须失败；`llm-mode=auto` 时可降级为规则候选并给 warning；`llm-mode=off` 仅用于确定性测试。
6. 测试环境不得调用外部 LLM，必须用 mock 或 deterministic fake。

LLM 配置必须从环境变量读取，不得把 API key 写入代码或文档。

## 7. CLI 与 Claude Code skill 要求

### 7.1 执行 CLI

`catforge_pipeline` 只负责执行 M05C-B，不负责生成 M05C-A taxonomy，也不承担 M05C-C 查询。必须新增自然语言和原子命令：

```bash
python -m app.cli.catforge_pipeline ask "生成彩电评论事实画像" --llm-mode required --format json
python -m app.cli.catforge_pipeline ask "重新生成 TV00030054 的评论事实画像" --llm-mode required --format json
python -m app.cli.catforge_pipeline run-comment-profile --product-category tv --batch-id latest --llm-mode required --format json
python -m app.cli.catforge_pipeline run-comment-profile --product-category tv --sku-code TV00030054 --llm-mode required --format json
python -m app.cli.catforge_pipeline run-comment-profile --product-category tv --llm-mode required --llm-batch-size 20 --format json
```

执行 CLI 必须支持：

- `--batch-id latest`
- `--product-category tv`
- `--sku-code` 可重复
- `--llm-mode required|auto|off`
- `--llm-batch-size`
- `--max-sentences-per-sku` 调试限流
- `--force-rebuild`
- `--format json`

`--product-category` 必须参与 taxonomy 选择。首版只要求 TV 可执行；其他品类在 taxonomy 未发布时必须返回明确错误，不得静默使用 TV taxonomy。

### 7.2 查询 CLI

`catforge_insight` 必须新增自然语言和原子命令。`comment-taxonomy` 是读取已发布 taxonomy 资产，不是生成 taxonomy：

```bash
python -m app.cli.catforge_insight ask "查 TV00030054 的评论事实画像" --format json
python -m app.cli.catforge_insight ask "查彩电评论事实维度" --format json
python -m app.cli.catforge_insight ask "查画质评论维度覆盖哪些 SKU" --sku-limit 100 --format json
python -m app.cli.catforge_insight ask "查评论里品牌力强的 SKU" --sku-limit 100 --format json
python -m app.cli.catforge_insight ask "查评论里提到索尼的 SKU" --sku-limit 100 --format json
python -m app.cli.catforge_insight ask "查哪些 SKU 的高刷卖点被评论支持" --sku-limit 100 --format json
```

原子命令建议：

```bash
python -m app.cli.catforge_insight sku-comment-profile --sku-code TV00030054 --include-comment-facts --format json
python -m app.cli.catforge_insight comment-taxonomy --product-category tv --format json
python -m app.cli.catforge_insight comment-dimension-coverage --dimension-code picture_screen_experience --sku-limit 100 --format json
python -m app.cli.catforge_insight comment-dimension-coverage --coverage-type brand_power_signal --query "值得信赖" --sku-limit 100 --format json
python -m app.cli.catforge_insight comment-dimension-coverage --coverage-type param_support --coverage-key declared_refresh_rate_hz --sku-limit 100 --format json
python -m app.cli.catforge_insight comment-dimension-coverage --coverage-type claim_support --coverage-key tv_claim_high_refresh_rate --sku-limit 100 --format json
```

### 7.3 Claude Code skill

必须更新两个 skill：

| Skill | 需要新增的自然语言能力 |
| --- | --- |
| `catforge-pipeline` | 生成/重跑评论事实画像；支持全量、指定 SKU、限流、LLM required/auto/off |
| `catforge-insight` | 查询 SKU 评论事实画像、评论事实维度、维度覆盖 SKU、品牌力 SKU、竞品提及 SKU、参数/卖点评论支持情况 |

skill 必须要求 Claude Code 优先使用自然语言 `ask`，只有在意图明确时才用原子命令。

## 8. 性能与稳定性要求

M05C 必须按 SKU 分批处理，不能一次把全量评论加载到内存。

默认建议：

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `sku_chunk_size` | 运行器内部按 SKU 逐个处理 | 每次只加载当前 SKU 的评论句和上下文 |
| `llm_batch_size` | 20 | 每次 LLM 输入句子数 |
| `max_parallel_llm_requests` | 1 | 205 默认串行，避免 CPU/内存和网络压力 |
| `commit_every_sku_chunk` | true | 每个 SKU chunk 提交一次 |

100 万级原始评论场景下，M05C 只读取 M02 已过滤后的评论句，不能回扫 M01 全量评论做主处理。

## 9. 验收标准

1. 能加载已发布 TV 评论事实 taxonomy。
2. 能对指定 1-2 个 SKU 生成可解释的评论事实画像。
3. 能全量处理当前 205 TV M02 评论句，不造成 205 SSH/API 不可用。
4. 能查询某 SKU 的评论事实画像。
5. 能查询某评论维度覆盖 SKU。
6. 能查询品牌力、竞品提及、人群、用途、价格价值、尺寸空间覆盖 SKU。
7. 能查询某标准参数/标准卖点被评论支持或反证的 SKU。
8. 服务履约不进入产品评论事实画像。
9. 品牌力作为正式事实维度输出。
10. 测试不依赖外部 LLM。
11. 指定未发布 taxonomy 的品类时，M05C-B 必须阻断并返回明确错误。
