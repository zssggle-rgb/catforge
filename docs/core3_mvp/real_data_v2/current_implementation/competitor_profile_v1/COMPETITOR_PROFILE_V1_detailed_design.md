# CatForge 竞品画像 V1 详细设计

状态：G04 设计冻结

日期：2026-07-14

## 1. 设计结论

竞品画像 V1 使用独立版本、独立表和独立读取服务，不改写旧 M12/M13/M14，也不把当前 `competitor-set` 的现场结果直接搬入新表。

核心数据模型由五层组成：

1. `profile_version`：锁定品类、serving scope、全部权威输入版本、方法配置和发布状态；
2. `sku_profile`：保存目标 SKU 的竞争决策结论、候选状态分布和 0—3 款重点结果；
3. `sku_pair`：保存 target×candidate 的完整召回、购买池、量价、证据族和问题可用性；
4. `pair_relation`：保存七类关系各自的 passed/failed/unknown/review 结果；
5. `key_selection`：保存重点竞品决策主题、入选顺序和独立信息理由。

竞品分析智能体、卡片、两份报告、深入问答和用户卖点价值画像只读取同一 `competitor_profile_version_id` 的保存结果。展示层不再召回、比较、评分或重排候选。

## 2. 模块边界

```text
Published input assets
  M03B M04C M05C M07 M09C M10C M11C M11D M12C M12D
                    |
                    v
CompetitorProfileInputProvider  -- exact authority + serving scope
                    |
                    v
CandidateRecallService          -- full manifest, no fixed count
                    |
                    v
PairFeatureBuilder              -- one deterministic pair DTO
                    |
                    v
RelationEligibilityService      -- all seven relation assessments
                    |
                    v
QuestionEligibilityResolver     -- per-question availability
                    |
                    v
KeyCompetitorSelector           -- minimal 0-3 decision set
                    |
                    v
CompetitorProfileMaterializer   -- draft bundle + hashes
                    |
                    v
CompetitorProfileRepository     -- five tables, one transaction/SKU
                    |
                    v
CompetitorProfileReader         -- current published or explicit preview
                    |
       +------------+-------------+------------+----------------+
       |                          |            |                |
 competitor agent          card/reports      QA      sellpoint-value profile
```

边界规则：

- V1 输入 provider 只读上游已发布/current 画像；不允许用上游 draft 生成竞品画像；
- 计算服务为确定性纯函数，不访问数据库、不调用外部 LLM；
- repository 只负责版本和持久化约束，不重算业务关系；
- reader 只组装保存画像，不从原始画像补结论；
- renderer 只把业务 DTO 转成中文内容，不接收内部阈值和生成模板。

## 3. 版本身份与 serving scope

### 3.1 版本主键

每个画像版本由以下业务键唯一标识：

```text
project_id
category_code
release_scope_key
profile_version
rule_version
```

`release_scope_key` 由 product category、analysis population、M07 analysis window、taxonomy version 和 serving scope identity 计算。`storage_batch_id` 只用于记录版本写入归属和外键，不代表全部输入都来自该批次。

### 3.2 ServingScope

`ServingScope` 必须包含：

- `project_id`；
- `category_code` / `product_category`；
- `analysis_population`；
- `market_window`；
- `taxonomy_version`；
- `storage_batch_id`；
- `source_batch_ids`，稳定排序且非空；
- 每个模块的 `profile_version`、`rule_version`、`schema_version`、`release_status` 和 `is_current`；
- 允许的 SKU 主数据前缀或 category membership 版本；
- authoritative SKU count 和 SKU manifest hash。

TV 可包含 G02 验证的三个 source batch，AC 可包含一个；两者使用相同 schema 表达。provider 不得假设 source batch 只有一个。

### 3.3 精确输入权威

输入版本以 `SourceAuthorityRef` 保存，键为模块代码，至少包括：

- M03B `m03b_tv_param_profile_v0.2` / `m03b_ac_param_profile_v0.2`；
- M04C、M05C、M07、M09C、M10C、M11C、M11D、M12C 的本次选定发布版本；
- TV M12D `m12d_tv_purchase_reason_profile_v0_3`；
- AC M12D `m12d_ac_purchase_reason_profile_v0_4`。

实际常量在 G09 从发布注册表读取，不在设计中把当前版本永久写死。版本不存在、品类不一致、taxonomy 冲突或记录越出 source batch scope 时，输入 bundle 构建失败，不能回退“最新行”。

## 4. 版本化配置

`CompetitorProfileMethodConfig` 由下列子配置组成，并整体参与版本 input fingerprint：

| 配置 | 作用 |
| --- | --- |
| `recall_config` | 同预算 ±15%、相邻预算、升降档 8%/15% 强差、召回入口开关 |
| `category_compatibility_config` | TV 尺寸兼容；AC 形态、能力段、适用空间兼容 |
| `generic_value_config` | taxonomy generic/table-stake 标记和覆盖率阈值 |
| `evidence_family_config` | F1—F5 source mapping 与 lineage 去重规则 |
| `relation_gate_config` | 七类关系的必需/可选门槛 |
| `question_eligibility_config` | 每个问题所需关系和数据族 |
| `key_selection_config` | 四个决策主题、置信度门槛、最多三款 |
| `quality_config` | ready/partial/blocked、review、发布质量门禁 |

每个配置有独立 `config_version`，版本表保存 `method_versions_json`。阈值或映射调整必须生成新配置版本和新画像草稿。

## 5. Typed Schema

所有运行 schema 继承一个 `CompetitorProfileBaseModel`：

- `extra="forbid"`；
- Decimal 固定四位计算精度；
- enum 序列化为稳定字符串；
- list/hash 前使用稳定业务键排序；
- runtime boundary validator 禁止 prompt、Gold Set、内部调参样本和 benchmark 进入持久化 DTO。

### 5.1 枚举

| Enum | 取值 |
| --- | --- |
| `ReleaseStatus` | draft, review, published, deprecated |
| `ReleaseQualityStatus` | unassessed, ready, limited, blocked |
| `AnalysisState` | ready, partial, blocked |
| `ConclusionState` | available, no_priority_competitor, insufficient_evidence |
| `CandidateStatus` | eligible, limited, review_required, blocked, recalled_only, reference_only |
| `RelationCode` | direct_substitute, same_budget_alternative, downtrade_diversion, uptrade_alternative, same_brand_ladder, scenario_substitute, same_value_substitute |
| `RelationStatus` | passed, limited, unassessable, failed, review_required |
| `PurchasePoolLevel` | P0, P1, P2, P3, unknown |
| `QuestionAvailability` | eligible, limited, unavailable |
| `ConfidenceLevel` | high, medium, low, unknown |
| `EvidenceFamily` | F1_purchase_reason, F2_task_value_scene, F3_audience_need, F4_user_realization, F5_capability_expression |
| `ReferencePurpose` | G03 定义的七个 reference purpose |
| `DecisionTopic` | purchase_choice, price_scale_pressure, portfolio_or_scenario, value_route |
| `FreshnessStatus` | current, stale, unknown |

### 5.2 输入 DTO

`CompetitorProfileVersionRequest`：

- 版本 identity、serving scope、method configs；
- authoritative SKU manifest；
- generated_by；
- version input fingerprint 和 expected result hash；
- V1 的 `allow_preview_inputs` 固定为 false。这里的 preview 只用于读取已经保存的竞品画像草稿，不扩展到上游画像；如未来需要上游 preview，必须新增逐模块 version ID、scope 校验和独立评审，不能使用“最新 draft”隐式回退。

`CategoryInputBundle`：

- version request；
- `sku_by_code`；
- M03B—M12D 的按 SKU 批量快照；
- category prevalence、price/volume distribution、brand ladder index；
- source availability 和 source lineage index；
- 不包含评论全文，只包含关系计算所需聚合事实和 evidence refs。

`TargetInputBundle`：

- target identity；
- target 各模块快照；
- 全量 candidate recall facts；
- target input fingerprint；
- missing/lineage issues。

### 5.3 Pair DTO

`CompetitorPairDraft` 至少包含：

- scope 与 target/candidate identity；
- 全部 `recall_sources`、召回事实和 manifest order key；
- candidate status 与 competitor/reference memberships；
- `PurchasePoolAssessment`；
- 五个 `EvidenceFamilyAssessment`；
- `PairMarketComparison`；
- 参数、卖点、用户兑现和采购理由差异摘要；
- 七个 `RelationAssessment`；
- 全部 `QuestionEligibility`；
- reference purposes；
- relation confidence、overall review 状态；
- evidence refs、lineage、limitations、risk flags；
- input fingerprint 和 result hash。

target 和 candidate 不得相同。同一个 target profile 下 candidate SKU 唯一；competitor/reference 是 membership 字段，不复制两条 pair。

### 5.4 购买池 DTO

`PurchasePoolAssessment`：

- level；
- category/product-form compatibility；
- size/capacity/task substitutability；
- budget reachability；
- task/value scene overlap；
- 每个 gate 的 `known/pass/reason_code`；
- evidence refs、confidence、limitations；
- result hash。

必要 gate 未知时 level=unknown；不得把 unknown 序列化为 false。

### 5.5 证据族 DTO

`EvidenceFamilyAssessment`：

- family code；
- status `supporting/discriminative/generic/missing/conflict`；
- matched value/task/reason codes；
- target/candidate strength 和方向；
- independent lineage keys；
- generic/table-stake reason；
- source refs；
- confidence。

同 lineage key 出现在多个模块时只计一个独立族，但所有 source refs 继续保留审计。

### 5.6 量价 DTO

`PairMarketComparison`：

- M07 authority、analysis population/window；
- target/candidate weighted price；
- price gap 和 pct；
- target/candidate average weekly volume；
- volume gap 和 ratio；
- target/candidate pool percentile；
- total sales/amount、active weeks 作为解释字段；
- common week/platform diagnostics；
- comparability status 和 unknown reasons；
- `causal_claim=false` 固定值；
- result hash。

任何分母为零或关键事实缺失时，对应衍生字段为 null，不能填 0。

### 5.7 关系 DTO

`RelationAssessment`：

- relation code；
- status；
- primary/auxiliary 标记由 materializer 在全部关系完成后确定；
- gate results，必要和可选门槛分开；
- relation confidence level；
- supporting evidence families；
- business effect direction；
- eligible question codes；
- failed/unassessable/review reasons；
- evidence refs、limitations、result hash。

七个 relation code 必须各有一条 assessment。缺一条属于 schema 错误，不允许 materialize。

### 5.8 问题可用性 DTO

`QuestionEligibility`：

- question code；
- availability；
- usable relation codes；
- required and available evidence families；
- missing inputs；
- business boundary code；
- reason_cn 供 QA/报告引用；
- result hash。

问题 codes：

1. `purchase_choice`；
2. `price_volume_pressure`；
3. `value_substitution`；
4. `configuration_follow`；
5. `same_brand_portfolio_role`；
6. `scenario_solution`；
7. `price_ladder_defense`；
8. `key_competitor_selection`。

### 5.9 重点选择 DTO

`KeyCompetitorSelectionDraft`：

- target/candidate；
- selection rank 1—3；
- primary decision topic；
- covered decision topics；
- primary and auxiliary relations；
- selection reason_cn；
- independent information reason_cn；
- price/value pressure summary；
- evidence refs；
- confidence；
- result hash。

每个 candidate 最多一条 selected row；rank 连续且最多 3。未入选理由保存在 pair 的 `non_selection_reason_code/cn`，禁止只写 rank>3。

### 5.10 SKU 主画像 DTO

`SkuCompetitorDecisionProfileDraft`：

- target identity 和 target market summary；
- analysis state、conclusion state、profile confidence；
- manifest/eligible/limited/review/blocked/reference 计数；
- relation status distribution；
- 0—3 款重点竞品摘要；
- main competitive advantages；
- substitutable user values；
- price and scale pressures；
- same-brand portfolio findings；
- configuration follow / do-not-follow findings；
- no-conclusion reason when insufficient；
- source lineage、evidence refs、limitations；
- QA index；
- input fingerprint 和 result hash。

`ready + no_priority_competitor` 表示数据充分但没有候选达到重点门槛；`partial + insufficient_evidence` 表示数据不足。两者不得合并成“没有竞品”。

## 6. 数据库设计

### 6.1 `core3_competitor_profile_version`

关键列：

- `competitor_profile_version_id` PK；
- project/category/product_category/storage_batch/release_scope；
- profile/schema/rule/method/config versions；
- serving scope、source authority、source batch IDs；
- authoritative SKU manifest hash；
- status/quality/current/freshness；
- SKU 和 pair/relation/selection 计数；
- input/candidate/result hashes；
- review/publish/current audit actor/time/reason；
- processing status 和 safe error summary。

约束：

- category_code=product_category；
- count 均非负且状态计数不超过 sku_count；
- current 只能是 published；
- 同 release scope 最多一个 current published；
- 业务版本键唯一；
- published 后内容列不可由 repository 修改。

### 6.2 `core3_sku_competitor_profile`

一行一个 target SKU/版本。保存主画像 JSON、状态计数、profile confidence、source lineage、evidence summary、limitations 和 hashes。

唯一约束：`(competitor_profile_version_id, target_sku_code)`。

### 6.3 `core3_sku_competitor_profile_pair`

一行一个 target×candidate。保存 recall、membership、candidate status、purchase pool、five-family assessments、market comparison、question eligibility、reference purposes、selection state、evidence 和 hashes。

约束：

- `(sku_competitor_profile_id, candidate_sku_code)` 唯一；
- target != candidate；
- competitor/reference membership 至少一个为 true；
- selected=true 时 candidate status 必须 eligible/limited；
- confidence 在 0—1；
- scope 必须与 parent profile/version 一致。

### 6.4 `core3_sku_competitor_profile_relation`

一行一个 pair×relation code，七类关系全量保存。

唯一约束：`(sku_competitor_profile_pair_id, relation_code)`。relation code/status/confidence 使用 check constraints；passed/limited 必须有至少一个 eligible question，failed/unassessable 必须有 reason code。

### 6.5 `core3_sku_competitor_profile_selection`

只保存已选 0—3 款重点竞品。

唯一约束：

- `(sku_competitor_profile_id, selection_rank)`；
- `(sku_competitor_profile_id, candidate_sku_code)`；
- rank 在 1—3；
- candidate pair 必须属于同一 profile 且不是 reference-only/review/blocked。

### 6.6 索引

至少包括：

- version scope/status/current；
- version source/quality JSONB GIN；
- target SKU/profile version；
- pair target/candidate 双向查找；
- pair candidate status、selected、same brand、reference purpose GIN；
- relation code/status/confidence；
- selection profile/rank/topic；
- input/result hashes；
- review-required partial indexes。

SQLite 单元测试保留等价唯一和 check 约束；PostgreSQL 使用 partial unique index 保证一个 current published。

### 6.7 删除与回退

- draft 可以按明确版本删除，FK cascade 清理其子记录；
- review/published/deprecated 禁止物理删除；
- published 不原地 rewrite；
- deprecated 保留完整历史；
- migration downgrade 只在没有任何数据时允许自动执行；存在画像数据时必须失败并给出安全错误，避免误删历史。

## 7. Repository 合同

`CompetitorProfileRepository` 公共方法：

```text
create_version(request) -> VersionRecord
get_version(version_id | business_key) -> VersionRecord | None
list_versions(scope, status, pagination) -> list[VersionRecord]
replace_draft_bundle(bundle) -> ProfileReadBundle
get_profile(version_id, target_sku) -> ProfileReadBundle | None
get_current_published_profile(release_scope_key, target_sku) -> ProfileReadBundle | None
list_profile_progress(version_id, pagination) -> lightweight rows
list_pairs(profile_id, filters, pagination) -> pair rows
list_relations(pair_id, filters) -> relation rows
list_selections(profile_id) -> 0-3 selection rows
review_version(version_id, actor, quality) -> VersionRecord
publish_version(version_id, actor, release_note) -> VersionRecord
set_current_version(version_id, actor, expected_current_version_id) -> VersionRecord
deprecate_version(version_id, actor, reason) -> VersionRecord
diff_profiles(from_version, to_version, target_sku) -> ProfileDiff
```

写入规则：

- 只有非 current draft 可 `replace_draft_bundle`；
- 一个 SKU bundle 在单事务内 bulk upsert profile、pairs、relations、selections，再 readback 校验 hash；
- review 后冻结所有 analytical child rows；
- publish 只改变版本/子行 release status，不切 current；
- `set_current_version` 是独立、显式、有 compare-and-swap 的事务；
- current switch 锁定 release scope，expected current 不一致时失败，不自动覆盖；
- 所有异常对用户返回安全错误码，详细堆栈只进服务日志。

## 8. 生成服务合同

### 8.1 InputProvider

`CompetitorProfileInputProvider`：

```text
resolve_serving_scope(request)
list_authoritative_sku_codes(request)
load_category_input_bundle(request)
load_target_input(category_bundle, target_sku)
```

G02 覆盖边界必须保持：TV M04C/M05C/... 缺失时记录 module availability，不从别的 SKU 或旧 M12—M14 补值；M03B 历史 AC v0.1 串在 TV category 的记录必须被 exact rule/product category/prefix gate 阻断。

### 8.2 Materializer

`CompetitorProfileMaterializer.materialize(target_bundle, config)`：

1. 校验 target scope；
2. 构建 full recall manifest；
3. 稳定排序并为每个 pair 构建事实；
4. 评估购买池和五证据族；
5. 评估七类关系；
6. 解析问题级可用性和 candidate status；
7. 分类 reference purposes；
8. 选择最小 0—3 决策集合；
9. 汇总 SKU 主画像和 QA index；
10. 计算 child/profile hashes，返回 typed draft bundle。

任何单 pair 失败不允许默默删除：可恢复数据错误转为 pair blocked/review；程序错误使该 target SKU 生成失败，由 lifecycle 隔离。

### 8.3 生命周期服务

- `ensure_version`：相同 business key+input fingerprint 幂等复用 draft；不同 fingerprint 不允许复用同 profile version；
- `generate_draft`：单 SKU 事务生成并回读；
- `batch_generate`：按稳定 SKU 顺序分页，逐 SKU 事务、失败隔离、可续跑；
- `review`：运行完整性、跨品类、hash、状态计数和业务 QA；
- `publish`：需要非 system 明确审批人，只允许 review/ready，limited 需要显式 allow；
- `set_current`：与 publish 分开，必须再次显式审批；
- `diff`：比较候选集合、关系状态、量价、重点选择和主画像结论；
- `stale`：上游 authority 或 serving scope fingerprint 变化时标记，不能原地改写 analytical result。

本任务链 G23—G26 只允许 ensure/generate/readback/diff draft，不允许 review、publish 或 set_current。

## 9. 生命周期状态机

```text
create -> draft -> review -> published -> deprecated
          |          |          |
          |          |          +-- set_current / unset_current metadata only
          |          +-- immutable analytical content
          +-- analytical child rows writable
```

允许转换：

| From | To | 条件 |
| --- | --- | --- |
| none | draft | identity、scope、input fingerprint 合法 |
| draft | review | generation complete、readback/hash/QA 完成 |
| review | published | quality ready；limited 需显式批准；非 system 审批人 |
| published | deprecated | 已有替代版本或明确原因；历史保留 |
| published non-current | current published | 独立 set_current、scope lock、expected-current CAS |
| current published | non-current published | 只能作为同一 set_current 事务的一部分 |

禁止转换：

- draft 直接 published/current；
- review/current；
- published 回 draft；
- published 原地写 child；
- publish 自动 current；
- 创建新 draft 自动取消旧 current；
- 失败时先清旧 current 再尝试切新版本。

## 10. 质量与发布门禁

### 10.1 SKU 质量

| analysis state | conclusion state | 含义 |
| --- | --- | --- |
| ready | available | 有正式关系和可用竞争结论 |
| ready | no_priority_competitor | 数据充分，但没有候选达到重点竞品门槛 |
| partial | available | 只有部分问题有结论，其他明确 unavailable |
| partial | insufficient_evidence | 证据不足，业务输出为“当前数据不足，无法形成竞品结论” |
| blocked | insufficient_evidence | 品类/版本/lineage 等 blocking 问题，必须复核 |

### 10.2 版本质量

- `ready`：authoritative SKU 全部有 profile row，无 generation failure、跨品类、hash mismatch 或 P0/P1 问题；
- `limited`：覆盖完整，但存在真实上游缺失导致的 partial/insufficient SKU；必须保存 SKU 清单和问题范围；
- `blocked`：漏 SKU、generation failure、scope/category 冲突、hash mismatch 或发布安全门禁失败；
- `unassessed`：尚未完成 review。

发布完整性按 authoritative manifest 验证，而不是要求每个 SKU 都有正向结论。正式读取时，有结论 SKU 返回保存结论；证据不足 SKU 返回明确的 insufficient result，不允许临时 fallback 重算。

### 10.3 关键 QA

- 版本 authoritative SKU 数与 profile rows 一致；
- 每个 pair 有且仅有七条关系；
- candidate/reference membership 与 status 合法；
- selected rows 为 0—3，rank 连续且 pair 可选；
- 量价 scope 同口径，null 未填零；
- relation/question/profile hashes 回读一致；
- TV/AC 无 SKU、taxonomy、rule、source batch 串线；
- card/report/QA/sellpoint consumer 的 profile version ID 一致；
- runtime export 无 factory-only keys。

## 11. Reader 与消费者合同

### 11.1 读取模式

`CompetitorProfileReader.read(target, mode, profile_version=None)`：

- `formal`：只读 current published；无 current 时返回 `profile_unavailable`；
- `preview`：必须传 profile version 和 `allow_draft_preview=true`；返回 `preview=true` 标记；
- 不允许 formal 自动回退旧 M12/M13/M14、现场 `competitor-set` 或 sellpoint reference pool；
- 一个请求解析出 version ID 后，后续所有 bundle/QA/report 读取锁定该 ID。

### 11.2 竞品分析智能体

智能体只负责 SKU 解析、reader 调用、输出路由和基于 QA index 的深入问答。以下行为禁止：

- 调用 same-size candidates 重新召回；
- 为报告重新计算 pair 分数；
- 重新挑 Top 3；
- 把 reference-only 写成竞品；
- 不同报告链接读取不同 profile version。

### 11.3 卡片与报告

reader 输出两个 DTO：

- `CompetitorProfileBusinessDTO`：中文业务字段，供卡片和产品经理报告；
- `CompetitorProfileEvidenceDTO`：方法状态、证据和限制，供分析佐证报告和审核。

业务 DTO 不包含表名、模块号、snake_case、hash、阈值和内部状态码。证据 DTO 可展示数据边界，但不得暴露 prompt/Gold Set。

### 11.4 用户卖点价值画像

输入 provider 必须保存：

- consumed competitor profile version ID；
- eligible/limited candidates by question；
- same-value/same-budget/downtrade/uptrade/same-brand relations；
- pair market comparison；
- reference purposes；
- key selections。

卖点价值画像可以在自己的方法合同内使用 reference pool 做市场合成和价值量化，但不能改变竞品关系或把 reference donor 升级为正式竞品。

## 12. API/CLI 设计

第一阶段优先服务层与 CLI，不扩大 runtime export。现有扁平 CLI 使用下列等价命令；生成请求通过 `--request-json` 传入完整 typed request，避免 CLI 猜测 category config 或上游 population：

```text
competitor-profile-generate --request-json ... --sku-code ...
competitor-profile-batch-generate --request-json ... [--max-new-skus ...]
competitor-profile-read --mode formal|preview --sku-code ...
competitor-profile diff --from ... --to ... --sku-code ...
competitor-profile review ...          # 本任务链不执行
competitor-profile publish ...         # 本任务链不执行
competitor-profile set-current ...     # 本任务链不执行
```

CLI 输出 JSON/text 只序列化 typed DTO；错误包含 `error_code`、安全中文 message 和 trace ID，不输出数据库 DSN、SQL、密钥或堆栈。

若增加 API endpoint，必须先有 request/response schema、preview 显式开关、scope 鉴权和 export boundary test。

## 13. 性能设计

G02 证明 broad manifest 可接近全品类，因此按最坏情况设计：

- TV pair 上限按 `377×376=141,752` 规划；
- AC pair 上限按 `155×154=23,870` 规划；
- 七类关系最大约 1,159,354 行；
- category bundle 批量加载后在内存建索引，禁止 target×candidate N+1；
- pair/relationship 纯函数分块处理，稳定顺序 bulk insert；
- profile progress 只读取 SKU/status/hash 轻量投影，不 hydrate 大 JSON；
- pairs/relation API 强制分页，单页默认 100、最大 500；
- 评论原文和重证据不进入 category bundle，按 QA evidence ref 延迟读取；
- 性能超限时显式 failed/degraded，不通过截断候选改变业务集合。

G13 用 TV 最大 broad target、AC 最大 broad target和全量 dry-run 做查询数、内存、时延门禁；具体数值基线由实测冻结，不在 G04 无证据承诺固定 P95。

## 14. 错误处理

| 错误 | 处理 |
| --- | --- |
| source authority 缺失/冲突 | version 或 SKU blocked；不 fallback latest |
| category/taxonomy/source scope 串线 | hard block + review queue |
| 可选上游缺失 | 关闭对应问题，profile partial |
| 单 pair 数据异常 | pair review/blocked；保留 manifest |
| 单 SKU 程序异常 | rollback 该 SKU，batch 继续，version failed_count+1 |
| readback hash mismatch | rollback/blocked，不标记 generated |
| 并发生成同版本 | non-blocking lock 失败并安全返回 |
| published child 写入 | immutable error |
| publish 非 review/quality 不合格 | publish not allowed |
| current CAS 不一致 | current switch conflict；旧 current 不变 |
| formal reader 无 current | profile_unavailable；不临时重算 |

日志包含 project/category/profile version/target SKU/trace ID，不记录密钥、原始评论全文或数据库凭据。

## 15. 文件与实现预算

建议新增运行文件：

1. `competitor_profile_schemas.py`；
2. `competitor_profile_persistence_schemas.py`；
3. `competitor_profile_config.py`；
4. `competitor_profile_repositories.py`；
5. `competitor_profile_input_provider.py`；
6. `competitor_profile_recall.py`；
7. `competitor_profile_pair_features.py`；
8. `competitor_profile_relations.py`；
9. `competitor_profile_selection.py`；
10. `competitor_profile_materializer.py`；
11. `competitor_profile_lifecycle.py`；
12. `competitor_profile_reader.py`。

每个文件保持单一职责。G05—G21 按 goal 逐步创建，不提前放空壳；共用 hash、pagination、base repository、release audit 模式复用现有实现，不复制 sellpoint-value 大服务。

## 16. 测试设计入口

每个公开函数至少覆盖：正常、unknown、conflict、跨品类、顺序反转和错误路径。

- schema：enum、scope、七关系完整、selected 0—3、runtime boundary；
- migration：upgrade/downgrade、unique/check/index/FK；
- repository：draft write、immutable review/published、separate publish/current、CAS；
- input：exact authority、TV multi-batch、AC single-batch、M03B 串线阻断；
- recall：全入口、无固定 limit、dedupe、empty；
- relation：G03 A01—A20；
- selection：0/1/2/3、主题去重、不强补、stable tie break；
- lifecycle：idempotency、resume、failure isolation、hash readback；
- reader：formal/preview、version lock、no fallback；
- consumer：agent/card/two reports/QA/sellpoint use same version；
- export：factory-only keys blocked。

测试不得调用外部 LLM。目标新增代码覆盖率不低于 80%，关系、lifecycle、repository 和 reader 关键模块目标不低于 90%。

## 17. G04 验收条款

- DD01：五层数据模型覆盖 version/profile/pair/relation/selection；
- DD02：storage batch 与 serving scope 分离；
- DD03：exact source authority 和 TV/AC 隔离可实现；
- DD04：配置版本参与 input fingerprint；
- DD05：G03 全部 enum 和状态可 typed 表达；
- DD06：七个 relation assessment 强制完整；
- DD07：unknown/null 不转 false/0；
- DD08：candidate/reference membership 不复制 pair；
- DD09：0—3 selections 有 DB 和 schema 约束；
- DD10：SKU ready-no-priority 与 insufficient 分开；
- DD11：五张表唯一、check、FK 和索引明确；
- DD12：draft replace、review freeze、published immutable；
- DD13：publish 与 set_current 拆成两个事务；
- DD14：current switch 有 scope lock 和 CAS，失败不动旧 current；
- DD15：batch 按 SKU 失败隔离、可续跑、readback hash；
- DD16：formal/preview reader 分离且无临时 fallback；
- DD17：consumer context 锁定同一 profile version ID；正式智能体及各展示面切换留在 G24 验收，不在 G22 改线上路由；
- DD18：用户卖点价值只能消费关系/reference，不改变身份；
- DD19：按最坏 pair/relations 数量设计且无 N+1；
- DD20：错误、日志、runtime export boundary 和测试入口完整。
