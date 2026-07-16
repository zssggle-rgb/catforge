# CatForge 竞品画像 V1.1 详细设计

状态：G27 已冻结

日期：2026-07-15

## 0. 2026-07-16 架构纠偏（优先级最高）

本节覆盖本文后续与之冲突的旧设计。旧设计错误地把“保存现有竞品智能体结果”扩成了 category-wide recall 和七维关系重算，65E7Q 因此从现有智能体的 20 款实际候选膨胀为 353 款，偏离原需求且不具备可接受的单 SKU 生成性能。

纠偏后的唯一生成链路为：

```text
current published upstream scope
             |
             v
existing competitor-set live analysis
(same_size_price_candidates -> existing atoms -> M12D -> enrich -> role -> Top 3)
             |
             v
AgentSnapshotTypedWrapper
(只校验、分离 candidate pool order / analysis order / priority order、生成 hash)
             |
             v
Version + shared SKU Snapshot + Profile + Pair + Selection
(当前不人为生成 7 × relation rows)
             |
             v
AgentSnapshotReader -> no-score Adapter -> Pure Renderer
```

实现合同：

- `competitor_profile_agent_snapshot_schemas.py`：对现有智能体完成后的目标、候选和逐款分析结果建立 typed contract；嵌套成熟结果保真保存，不重新解释。
- `competitor_profile_agent_snapshot_generation.py`：只运行一次现有智能体，包装并落盘；不得调用 `CandidateRecallEngine`、`PairFeatureBuilder`、`PairAnalysisCalculator`、V1.1 selector。
- `competitor_profile_agent_snapshot_repository.py`：复用 0047 表和版本状态机，原子保存 shared snapshots、profile、20 个实际 pair 和最多 3 个 selection；compact 只读 header/index，不读取 `analysis_snapshot_json`。
- `CompetitorProfileV11Reader`：先识别 agent snapshot method；命中后返回已保存结果，旧 V1.1 method 继续走原 reader，二者互不篡改。
- `sop_orchestrators.py`：agent snapshot 命中后直接进入 saved renderer；读取路径的召回、分析、打分、角色分配、排序、选择调用数必须为 0。
- `competitor_answer.py`：saved renderer 只按 `analysis_order` 展示全部候选、按 `priority_order` 取重点竞品；不调用 `_enrich_competitor`、`_sort_key`、`_assign_top_roles` 或 `_select_top_competitors`。

性能与存储合同（agent snapshot method v2）：

- 每个 SKU 的 fact brief、claim value、claim contribution 和采购理由只进入一份 `gzip+base64+json` shared snapshot；编码固定 `mtime=0`，保证 hash 可重复。
- profile 中目标 SKU 的重资产字段只保存 `target_snapshot_ref`；pair 中候选重资产字段只保存 `candidate_snapshot_ref` 和 snapshot result hash。
- profile 继续保存购买池、语义/参数/销量重合、价值锚点、替代压力、市场验证、业务得分、角色、门槛结果和三个顺序，不能以压缩为由删除分析结论。
- full Reader 一次批量读取目标与候选 shared snapshots 并校验引用/hash，Adapter 解压还原成熟智能体 payload；compact Reader 不读取或解压 shared payload。
- 不允许为每个 pair 重复保存同一 SKU 的 2—3MB 卖点价值原始结构，也不允许在 profile 与 snapshot 各复制一份。

幂等合同：同 version、target 和相同 profile hash 返回 reused；同一键不同结果必须 fail-closed，不能覆盖已保存草稿。正式读取仍只允许 current published；draft 必须显式 version + scope + preview opt-in。

## 1. 设计结论

V1.1 复用现有竞品分析智能体的完整分析结果以及 V1 的版本、Repository 和批量生成能力，不另建一套竞品算法。生成方法以第 0 节为准。

改造点只有三层：

1. 将现有中间过程中的完整多维结果转换成持久化分析合同，不再在 materializer 中压缩丢失；
2. 将候选范围、分维度可用性、结论强度和复核状态拆开，取消跨维度全局拦截；
3. 为竞品分析智能体提供稳定读取适配器，使智能体直接读取画像数据，不调用旧原子能力。

## 2. 数据流

```text
published/current M03B—M12D
             |
             v
CompetitorProfileInputProvider              V1 复用
             |
             v
CandidateRecall + PairFeature               V1 复用
             |
             +----> VersionSkuAnalysisSnapshotBuilder  新增
             |
             v
PurchasePool + ValueSubstitution
+ PriceVolumePressure + RelationEvaluation  V1 算法复用、门槛语义修改
             |
             v
PairAnalysisCalculator                      新增编排，调用成熟锚点/压力计算器
             |
             v
PairAnalysisAssembler                       新增，只组装完整多维过程
             |
             v
KeyCompetitorSelector V1.1                  修改为问题级选择，不用全局 status 拦截
             |
             v
CompetitorProfileMaterializer               扩展持久化合同
             |
             v
Version + SKU Snapshot + Profile + Pair + Relation + Selection
             |
             v
CompetitorProfileReader V1.1
             |
             v
CompetitorAnalysisProfileAdapter            新增，只做字段适配
             |
             v
PureCompetitorAnswerRenderer                新增纯展示入口
             |
             v
智能体语言与展示层
```

展示层不进入画像生成模块，也不反向决定画像字段命名。适配器映射的是画像已经保存的分析结果，而不是供旧链重算的原始输入。纯展示入口不得调用 enrichment、打分、角色分配、排序或 Top 3 选择。

## 3. 现有模块复用表

| 能力 | 现有模块 | V1.1 处理 |
| --- | --- | --- |
| 权威版本读取 | `competitor_profile_input_provider.py` | 直接复用 |
| 全量候选召回 | `competitor_profile_candidate_recall.py` | 直接复用 |
| 候选确定性 | `competitor_profile_candidate_determinism.py` | 直接复用 |
| pair 原始对齐 | `competitor_profile_pair_feature.py` | 保留完整输出并进入持久化装配 |
| 购买池与战场 | `competitor_profile_purchase_pool.py` | 复用计算，补充分维度得分 |
| 采购理由和用户价值 | `competitor_profile_value_substitution.py` | 复用完整 assessment，不只保留 family 摘要 |
| 量价压力 | `competitor_profile_price_volume_pressure.py` | 复用，补市场验证 DTO |
| 价值锚点 15 分制 | `anchor_substitutability.py` | 由 `PairAnalysisCalculator` 调用成熟 `ValueAnchorMatcher`，完整持久化输出 |
| 替代压力 10 分制 | `replacement_pressure.py` | 由 `PairAnalysisCalculator` 调用成熟 `ReplacementPressureClassifier`，完整持久化输出 |
| 购买压力对比 | `purchase_pressure_comparison.py` | 由 `PairAnalysisCalculator` 调用成熟 `PurchasePressureComparator`，完整持久化逐项结果 |
| 七类关系 | `competitor_profile_relation_evaluation.py` | 保留关系计算，修改 review/status 传播 |
| 重点选择 | `competitor_profile_key_competitor_selection.py` | 改为问题级资格和可用权重排序 |
| 主画像 | `competitor_profile_materializer.py` | 保存完整分析快照和结论 |
| Repository/lifecycle | V1 Repository/lifecycle | 扩展新表/字段，状态机不变 |
| Reader/consumption | V1 Reader/consumption | 新增 V1.1 typed 读取合同 |
| 竞品智能体 | `sop_orchestrators.py` | 用 reader + adapter 替换旧原子调用 |
| 业务生成器 | `competitor_answer.py` | 拆出纯展示入口；原分析入口仅保留兼容，不得用于画像消费 |

`PairAnalysisCalculator` 必须冻结上述成熟计算器的 method/config version。`PairAnalysisAssembler` 只做 typed 组装和 hash，不得根据 V1 的简化 evidence summary 反推 15 分制、10 分制或购买压力结果。

## 4. Typed Schema

### 4.1 通用状态

新增枚举：

```text
PairScopeStatus = analyzable | excluded
DimensionAvailability = available | partial | unknown | conflict
ConclusionStrength = strong | supported | directional | reference | unknown
ComparisonRole =
  direct_competitor | price_adjacent | downtrade_diversion |
  uptrade_alternative | same_brand_ladder | scenario_alternative |
  value_substitute | configuration_benchmark | market_reference
```

`review_required: bool` 和 `review_items` 独立存在，不属于上述枚举。

### 4.2 `VersionSkuAnalysisSnapshot`

同一个画像版本中的每个 SKU 只保存一次：

```text
competitor_profile_version_id
project_id/category_code/release_scope_key
sku identity
product_form_facts
market_snapshot
fact_sections
semantic_profiles
claim_value_snapshot
purchase_reason_snapshot
module_availability
source_lineage/evidence_refs/limitations
input_fingerprint/result_hash
```

`fact_sections` 使用领域结构而不是展示字符串：

- parameter items：code、actual value、unit、tier、known；
- claim items：claim code、role、supporting parameter codes；
- battlefield/task/audience items：code、roles、confidence；
- claim value items：value code、role、market summary、user realization；
- purchase reason anchors：anchor code、role、establishment、user validation、pressure。

SKU 快照必须无损覆盖旧链读取的 M12C/M12D 字段：`claim_values`、`estimated_contribution`、`pool_effect`、`context`、`scorecard`、`claim_contribution.attributions`、positive claims、SKU gap、confidence、`fact_claim_codes`，以及 supported/contradicted/unsupported 状态。`business_claim_type`、业务价值标签/含义、市场位置、SKU 可解释价差/销量差必须成为正式领域字段，不能只留在 `raw_details`。G28 先形成“旧 atom 字段 → V1.1 typed 字段”映射矩阵，G29 schema 合同要求覆盖率 100%；重复观测必须保留原始值、稳定数组位置和顺序，不得按值去重。

### 4.3 `DimensionAnalysisResult`

所有 pair 维度使用统一外壳：

```text
dimension_code
availability
target_items
candidate_items
shared_items
target_only_items
candidate_only_items
raw_score
available_weight
normalized_score
calculation_components
conclusion_strength
conclusion:
  conclusion_code
  subject
  direction
  metrics
  supporting_fact_refs
  audit_summary_cn
review_required/review_items
evidence_refs/limitations
result_hash
```

`target_items` 和 `candidate_items` 保存 code、roles、actual values 和 known 状态。展示名称由 taxonomy 翻译，不在每个 pair 重复保存。

参数/卖点条目增加 `feature_market_status=foundational|differentiating|unknown`、prevalence numerator/denominator/ratio/source 和 supported/contradicted/unsupported。原始差异永远保留；`foundational` 不贡献差异得分、重点理由或产品建议。

### 4.4 `ValueAnchorAnalysisResult`

```text
target_core_anchors
candidate_core_anchors
shared_anchors
target_stronger_anchors
candidate_stronger_anchors
weak_expression_anchors
proposition_only_anchors
purchase_pressure_comparison
match_details
anchor_substitutability_score       0—15
anchor_substitutability_level
raw_score/available_weight/normalized_score
conclusion_strength/conclusion
review_items/evidence_refs/limitations
calculator_method_version/calculator_config_version
```

`primary_direct_eligible` 仅作为“强直接竞争话术”的结论强度条件，不再决定该候选是否继续参与其他维度和重点分析。

### 4.5 `ReplacementPressureAnalysisResult`

```text
primary_pressure_type
auxiliary_pressure_types
pressure_components
replacement_pressure_score          0—10
replacement_pressure_level
affected_purchase_reasons
business_effect
conclusion_strength/conclusion
review_items/evidence_refs/limitations
calculator_method_version/calculator_config_version
```

`strong_pressure_allowed` 只控制强话术，不能把候选从价格、配置、场景或价值分析中删除。

本设计所有 `conclusion` 统一使用 4.3 的机器可读结构；`audit_summary_cn` 只是审计摘要，不能代替 conclusion code、direction、metrics 和 supporting fact refs。

### 4.6 `PairAnalysisSnapshot`

```text
target/candidate identity refs
scope_status/exclusion_reason_code
recall_sources/recall_facts/recall_rank
purchase_pool
dimensions:
  battlefield_overlap
  user_task_overlap
  target_group_overlap
  parameter_comparison
  claim_comparison
  user_realization_comparison
  purchase_reason_comparison
value_anchor_analysis
replacement_pressure_analysis
market_validation
comparison_roles/primary_role
score_breakdown
legacy_competitor_score
legacy_basis:
  semantic_overlap_score
  param_claim_overlap_score
  sales_closeness_score
business_questions
overall_conclusion_strength/overall_conclusion
review_required/review_items
evidence_refs/limitations
input_fingerprint/result_hash
```

`score_breakdown` 必须包含：

```text
dimension weights
dimension raw scores
dimension availability
available_weight
raw_total
normalized_total
ranking_tiebreakers
```

`market_validation` 必须保存完整 `sales_overlap_snapshot`：method、window、overlap_weeks、target/candidate overall_weekly_volume、target/candidate overlap_weekly_volume、volume_gap、volume_ratio 和 boundary。上述字段不得在 adapter 中补算。

未知维度不写 0；`normalized_total = raw_total / available_weight`，同时保留 coverage，防止少量已知维度被错误放大。维度量纲、归一规则、权重和 weighted contribution 都必须版本化持久化。

### 4.7 `SkuCompetitionAnalysisSummary`

```text
target_sku_code
analysis_candidate_count
dimension_availability_counts
conclusion_strength_counts
priority_competitors 0—3
role_buckets
competitive_advantages
substitutable_values
configuration_differences
price_volume_pressures
unknown_dimensions/review_items/limitations
input_fingerprint/result_hash
```

## 5. 数据库设计

### 5.1 新表

新增 `core3_competitor_profile_sku_snapshot`：

| 列 | 用途 |
| --- | --- |
| `competitor_profile_sku_snapshot_id` | PK |
| `competitor_profile_version_id` | 版本 FK |
| `project_id/category_code/release_scope_key` | scope 隔离 |
| `sku_code` | SKU 唯一键 |
| `snapshot_json` | typed SKU snapshot |
| `module_availability_json` | 模块可用性 |
| `evidence_refs_json/source_lineage_json` | 追溯 |
| `input_fingerprint/result_hash` | 幂等和审计 |

唯一约束：`(competitor_profile_version_id, sku_code)`。

工程约束：

- 继承项目现有 `AuditMixin`；
- version 表增加 `(competitor_profile_version_id, project_id, category_code, release_scope_key)` 唯一键；snapshot 使用同四列复合外键并设置 `ON DELETE CASCADE`，在数据库层保证 project/category/release scope 与 version 一致；
- 增加 `(competitor_profile_version_id, project_id, category_code, release_scope_key, sku_code)` 读取索引。

该表避免在十几万 pair 中重复保存相同 SKU 的事实画像。

### 5.2 Pair 表扩展

`core3_sku_competitor_profile_pair` 新增：

- `scope_status`；
- `analysis_snapshot_json`；
- `analysis_conclusion_strength`；
- `analysis_score`；
- `analysis_available_weight`；
- `analysis_result_hash`；
- `analysis_review_required`。

现有 `pair_payload_json`、关系、问题可用性和市场事实保留。V1.1 reader 以 `analysis_snapshot_json` 为多维权威结果；V1 reader 继续读取旧 payload。

新增 V1.1 conditional checks：

- V1.1 pair 的 `scope_status` 必须合法；
- available weight/normalized score 使用冻结范围；
- `scope_status=excluded` 必须携带五类 hard exclusion code 之一；
- `scope_status=analyzable` 不得由旧 `candidate_status` 阻止保存或选择；
- V1.1 完整状态下 analysis snapshot/result hash 等必填，V1 历史行不追补、不改写。

现有 `ck_core3_cp_pair_selected_status` 只对 V1 旧合同继续生效；V1.1 必须使用 conditional check 或独立选择状态列，使 `selected=true` 只受 `scope_status=analyzable` 和问题级非 unknown 结论控制，旧 `candidate_status in ('eligible','limited')` 不得成为 V1.1 约束。

Pair 新增 `(competitor_profile_version_id, target_sku_code, scope_status)` 和按 version/target/candidate 读取索引，支持 full、compact 和 question-specific 无 N+1 回读。

### 5.3 Profile 表扩展

`core3_sku_competitor_profile` 新增：

- `analysis_summary_json`；
- `analysis_result_hash`；
- `analysis_candidate_count`；
- `analysis_available_dimension_count`；
- `analysis_review_item_count`。

### 5.4 Selection 表扩展

`core3_sku_competitor_profile_selection` 新增：

- `selection_policy_version`；
- `selection_score`；
- `selection_available_weight`；
- `selection_conclusion_strength`；
- `selection_role_codes_json`；
- `selection_score_breakdown_json`。

Relation 表为 V1.1 新增独立 `analysis_relation_status` 或等价版本条件列，合法值只为 `passed|limited|unassessable|failed`；旧 `ck_core3_cp_relation_status` 和旧 `review_required` 状态只服务 V1 历史行。V1.1 的 review/conflict 使用独立 overlay 字段，不得塞回 relation status。

Repository 单 SKU 原子事务必须同时覆盖 SKU snapshots、profile、pairs、relations 和 selections；任一写入或约束失败时全部回滚。

## 6. 门槛执行设计

### 6.1 候选范围阶段

`CandidateEligibilityClassifier` 改名语义为 `CandidateScopeClassifier`，保留类名兼容。

输出：

- `scope_status=excluded`：`exclusion_reason_code` 只能是 `self_pair`、`project_mismatch`、`category_mismatch`、`candidate_outside_manifest`、`identity_decode_failed`；
- `scope_status=analyzable`：其余候选全部继续进入多维计算；
- 原 provisional question readiness 保留为提示，不再提前剥夺关系计算资格。

authority 缺失、taxonomy unknown、lineage 缺失以及同 scope 证据冲突，在 identity 已知时均为 `analyzable + review overlay`，不得扩展 hard exclusion 枚举。

### 6.2 分维度阶段

每个维度独立计算 availability、strength 和 review：

- upstream `review_required` 仅进入引用该记录的维度；
- 同一模块多条记录中存在可用正式记录时，保留可用结果并把冲突项写入 review items；
- 维度 unknown 不生成伪差异；
- conflict 保存双方冲突事实，不自动升级为候选全局 review。

### 6.3 关系阶段

七类关系仍各保存一条 assessment，但关系状态改为：

- `passed`：证据支持；
- `limited`：能形成方向性关系；
- `unassessable`：该关系所需维度未知；
- `failed`：已知事实明确不满足。

`review_required`、`review_items` 和 `conflict_dimensions` 是独立 overlay，不属于 relation status。`limited + review_required=true` 仍可参与方向性关系和专项重点选择，不得令 pair candidate status 变成统一 `review_required`。

### 6.4 问题阶段

`QuestionEligibility` 从“候选准入”改为“答案强度”：

```text
eligible    -> 可输出 strong/supported 结论
limited     -> 可输出 directional/reference 结论
unavailable -> 只返回该问题所缺维度
```

重点选择从问题级 `eligible` 和 `limited` 候选中计算。`limited` 只要能独立回答一个产品问题，就可以进入重点名单，但必须携带结论强度。

## 7. 排序与重点选择

### 7.1 分数兼容

冻结现有竞品分析的六个主体维度：

| 维度 | 权重 |
| --- | ---: |
| 购买池 | 20% |
| 价值战场 | 25% |
| 用户任务 | 15% |
| 目标客群 | 15% |
| 价值锚点 | 15% |
| 替代压力 | 10% |

市场销量用于验证和同分排序，不替代主体竞争判断。

V1.1 可以在后续版本调整权重，但首个兼容版本必须保存并复现上述分数构成，便于解释新旧差异。

### 7.2 选择规则

1. 只排除 `scope_status=excluded`；
2. 计算所有已知维度，不因单个 unknown/review 停止；
3. `available_weight` 只用于覆盖率解释和归一，不设置阻止保存、问题参与或重点选择的最低值；
4. G29 冻结不设 coverage 最低门槛的确定性排序公式；`normalized_score` 不得单独放大低覆盖 pair，coverage 只影响问题结论强度和同分排序，G28 golden diff 必须证明没有形成显性或隐性淘汰；
5. 最多选择 3 款，并保留角色多样性；
6. 未选候选保存得分、覆盖率、角色和具体未选原因；
7. 旧 Top 3 必须进入兼容排序，除非 hard scope exclusion；
8. 新旧 Top 3 不一致时输出 machine-readable diff。

结论强度按问题相关事实决定：成熟计算器允许强结论且必需事实已知为 `strong`；正常结果只有非关键缺失为 `supported`；至少一个直接相关维度已知为 `directional`；只能给事实参照为 `reference`；全部直接相关维度未知才为 `unknown`。任何非 `unknown` 结论均可参与对应问题和重点选择。

## 8. 读取与智能体适配

### 8.1 Reader

新增 `CompetitorProfileAnalysisDTO`：

- target snapshot；
- SKU summary；
- priority selections；
- full analyzable pair index；
- 按 candidate 或 question 读取 pair analysis；
- evidence index；
- profile/version/result hash。

Reader 只读取保存结果，不访问 M03B—M12D。

### 8.2 Adapter

新增 `CompetitorProfileAgentAdapter`，将画像中已完成分析的领域 DTO 映射为纯展示入口需要的：

```text
target_snapshot
sku_competition_summary
candidates[].identity
candidates[].candidate_snapshot_ref/result_hash
candidates[].recall_rank
candidates[].dimension_results
candidates[].value_anchor_analysis
candidates[].replacement_pressure_analysis
candidates[].purchase_pressure_comparison
candidates[].market_validation
candidates[].comparison_roles
candidates[].score_breakdown
candidates[].business_questions
candidates[].conclusions
priority_order
```

Adapter 规则：

- 只允许字段重命名、code 翻译和数据结构组装；
- 不允许重新计算得分、关系、压力或排序；
- 缺失字段必须显式返回 unknown，不调用旧 atom 补齐；
- adapter 构造入口只接受 authoritative projection；legacy/raw key 统一大小写及 snake/camel 后按准确路径拒绝，唯一保留的 `legacy_candidate_count` 只能是 summary 路径的整数；所有自由 JSON 容器非空即失败，须先扩展 typed consumer DTO，对外序列化也不包含这些容器或任何兼容 raw bag；
- serializer 每次输出前重跑同一 fail-closed 边界并重算 receipt/projection hash；禁止合法构造后通过原地修改嵌套 model/list/dict 绕过合同；
- adapter 输出带 `source=competitor_profile_v1_1`、profile version 和 result hash；source receipt 同时锁定 target/candidate snapshot、pair、summary 和完整 adapter projection hash，任一字段被改写都必须失败；
- 正文 fact ID 全局唯一，fact index 的 code、source path、evidence keys 必须与正文逐项一致，不能用 index 自证正文中不存在或不同内容的事实；
- adapter 单元测试保证不会访问 AtomicHandlers、`_enrich_competitor`、`_sort_key`、`_assign_top_roles`、`_select_top_competitors` 或任何分析计算器。

新增 `render_competitor_answer_from_profile()` 纯展示入口。该入口只消费 adapter 结果组织现有业务结构；旧 `build_competitor_answer()` 的现场分析路径保留兼容，但 V1.1 智能体不得调用。测试中对所有分析、角色、排序和选择函数设置 fail-fast spy，只要发生一次调用即失败。

### 8.3 智能体路由

开发预览：显式 profile version 读取 draft。

正式模式：只读 current published V1.1。没有正式画像时返回画像不可用，不静默切回旧路径。旧路径保留为显式运维回退命令，不作为正式默认行为。

## 9. 生成与性能

- Category input 和 SKU snapshot 一次批量读取；
- target/candidate 通过 snapshot id 引用，不复制重 JSON；
- pair analysis 只保存 code、actual value、得分、结论和 refs，不保存评论全文；
- evidence refs 继续使用 V1 dictionary/pointer 压缩；
- 单 SKU 事务写入 snapshot 引用、profile、pair、relation、selection；
- category 生成按现有 checkpoint 和失败隔离执行；
- 性能验收使用 TV 最大候选 SKU 和 AC 最大候选 SKU；
- G28 实测旧链单 SKU、单 pair 和最大候选 SKU 的时延/内存/字段量，G29 冻结数值预算；G39 在本地等价数据集通过 compact readback 和 SQL 次数基准；G41A/G41B 再在 205 实测 compact readback 不高于 2 秒且无 N+1；若存储超预算优先字典化和共享，不裁剪分析维度。

## 10. 版本和迁移

- V1.1 业务结构只通过新 revision `0047` 增加；工程复核发现历史
  `0046` 直接导入可变 ORM 后，将其等价冻结为自包含 V1 DDL，不改变任何
  已部署 V1 表、列、约束或索引，并由 SQLite/PostgreSQL 双方言 golden hash
  防止后续漂移；
- 新表和列 nullable 兼容 V1 历史草稿；
- V1.1 typed reader 要求新字段完整，不能读取 V1 伪装为 V1.1；
- V1.1 profile 使用新的 schema/rule/method/config version；
- draft 幂等规则沿用：相同输入复用，不同结果不原地覆盖；
- published/current 不在本任务链自动执行；
- downgrade 在以下任一条件成立时拒绝删表/列并要求 forward fix：version 表已存在使用 V1.1 schema/profile/method version 的行、存在 V1.1 snapshot 行、或 V1.1 分析列已有值。旧 0046 表中仅有 V1 草稿不算 V1.1 数据，不能因此永久阻断 migration 回退。

## 11. 测试设计

### 11.1 合同测试

- unknown 不变 0/false；
- review overlay 不改变 scope status；
- relation status 只允许 passed/limited/unassessable/failed；
- 每个 pair 维度覆盖完整；
- score 三元组一致；
- 旧 atom 字段到 V1.1 typed 字段映射覆盖率 100%；
- machine-readable conclusion 的 code/subject/direction/metrics/fact refs 完整；
- snapshot version/scope/category 一致；
- runtime boundary 不泄露 prompt/Gold Set。

### 11.2 门槛回归

- M12D review 但 M07/参数/语义可用，候选继续计算；
- 战场冲突只影响战场和依赖关系；
- 用户兑现缺失仍可输出配置/量价方向；
- 某关系 failed 不影响其他关系；
- limited 候选可以进入独立重点主题；
- limited + review_required 候选仍可进入方向性和专项重点选择；
- hard scope error 仍可靠阻断。

hard exclusion 参数化测试只接受五个冻结枚举；identity 已知时的 lineage missing、taxonomy unknown 和同 scope conflict 必须保持 analyzable。

### 11.3 兼容基线

冻结同一上游快照上的旧智能体结果：

- 65E7Q 全候选和 Top 3，并逐个记录排除原因；
- 每个 Top 3 的六维得分、锚点、压力、配置和量价；
- 一款 TV 缺 M12D/复核样本；
- 一款 AC 完整样本和一款 AC 局部缺失样本。

本地 fixture matrix 还必须覆盖：完整 pair、M12D missing、M05C review、battlefield conflict、market-only、config-only、AC complete、AC partial，以及 HDMI 2.1 foundational feature。

V1.1 逐字段比较。旧链已知字段变 unknown、字段缺失、旧候选在无 hard exclusion code 时消失或 unknown 被填 0 均为失败；旧 Top 3 完整字段覆盖率必须达到 100%。

### 11.4 消费回归

- 智能体只读取一次画像；
- AtomicHandlers 调用次数为 0；
- adapter 输出满足纯展示入口合同；
- `_enrich_competitor`、`_sort_key`、`_assign_top_roles`、`_select_top_competitors` 和全部分析计算器调用次数为 0；
- 同一 profile version 重复读取 hash 一致；
- 问题路由只选择已有维度，不重算。

### 11.5 性能与持久化

- migration upgrade/downgrade guard；
- SKU snapshot 不重复；
- pair 不重复；
- 无 N+1；
- 全量 candidate 不截断；
- 单 SKU 和批量重试幂等；
- 生成中断后 checkpoint 续跑；
- 完整 hash readback。

competitor answer、PM report 和 Feishu publish 回归只能使用 mock/offline renderer，不发送外部消息、不创建飞书文档。

## 12. 验收顺序

1. 冻结旧智能体兼容基线；
2. 完成 schema、migration、repository 和 reader；
3. 完成多维分析持久化和门槛重构；
4. 完成 adapter 和智能体预览读取；
5. 本地测试与评审；
6. 205 只部署代码和 migration；
7. 只生成 65E7Q V1.1 draft，验收数据合同和智能体零重算；
8. 通过后验收 AC 单 SKU；
9. 双品类通过后生成 TV/AC 全量 V1.1 draft；
10. 全量只读质量复核后，另行决定 review/publish/current。
