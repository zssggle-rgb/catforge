# 用户卖点价值画像详细设计

状态：G01 设计冻结候选

日期：2026-07-13

需求：`V5_profile_requirements_addendum.md`

调度：`V5_profile_goal_dispatch.md`

## 1. 架构边界

新增画像层位于 CatForge 工厂内部，消费现有 M03B—M14 权威画像，不修改上游算法和发布版本。

```text
M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D/M12D
M12 candidate pool + M13 scores + M14 selected labels
                         |
                         v
       SellpointValueCandidateUniverseService
          competitor universe | reference pool
                         |
                         v
       ThresholdCapabilityClassifier
                         |
                         v
       Existing V5 value/counterfactual/market services
                         |
                         v
       SellpointValueProfileMaterializer
                         |
           draft -> validate -> review -> publish
                         |
                         v
       persisted profile DTO + candidate/item rows
                 |                       |
                 v                       v
          report renderer          profile Q&A retriever
```

关键边界：

- 候选召回、门槛分类、量价分析只在画像生成阶段执行；
- 报告和问答只读取画像；
- renderer 不直接访问 analyst repository；
- Q&A 可组合画像事实，但不重新运行反事实或切换 profile version；
- 工厂 prompt、Gold Set 和内部方法不得进入运行时导出。

## 2. 模块与建议文件

新增：

- `sellpoint_value_profile_schemas.py`：画像、候选、价值项、投入分类、问答 DTO；
- `sellpoint_value_profile_repositories.py`：版本、SKU、候选、价值项 CRUD；
- `sellpoint_value_profile_candidate_service.py`：M12/M13/M14 宇宙与 reference pool；
- `sellpoint_value_profile_thresholds.py`：门槛功能和投入分类纯函数；
- `sellpoint_value_profile_service.py`：materialize、validate、get、list、diff、batch；
- `sellpoint_value_profile_answer.py`：profile -> report 和 profile ask；
- migration `0045_core3_sellpoint_value_profile.py`；
- 对应 unit/integration/CLI/migration tests。

修改：

- `entities.py`；
- `analyst_repository.py` 或新的专用 repository；
- `atomic_handlers.py`、`analyst_service.py`、`ability_registry.py`；
- `sop_orchestrators.py`；
- `catforge_analyst.py`；
- 当前 V5 renderer 入口。

## 3. Typed domain contract

### 3.1 CandidateUniverseManifest

```text
target_sku_code
competitor_candidates[]
analysis_references[]
m12_rule_version
m13_rule_version
m14_rule_version
candidate_count_by_status
candidate_manifest_hash
limitations[]
```

`CandidateManifestItem`：

```text
candidate_sku_code / brand / model
pool_type: competitor | reference
relation_types[]
primary_relation_type
m12_recall_strength / sources
m13_component_score / role_scores
m14_selected / slot / rank
eligibility_status
eligible_questions[]
unavailable_questions[]
data_availability
market_summary
source_hashes
review_status / reasons
```

manifest 排序固定为：

```text
pool_type
eligibility_status priority
m14 selected desc
primary relation
role/component score desc
candidate_sku_code
```

输入顺序不进入 hash。

### 3.2 CapabilityInvestmentDecision

```text
capability_code / name
classification
target_fact_status / target_value
known_candidate_count
present_candidate_count
missing_candidate_count
prevalence
comparison_scope
user_feedback_status
experience_outcomes[]
price_support / volume_support
candidate_scope_ids[]
reason_cn / boundary_cn
evidence_refs[]
decision_hash
```

### 3.3 SellpointValueDecisionProfile

```text
identity + version metadata
analysis_state / freshness
target_market_summary
source_lineage
candidate_universe_summary
threshold_summary
value_items[]
question_analyses[]
investment_decisions[]
price_role
battlefield_options[]
pm_decisions
qa_index[]
limitations / evidence summary
input_fingerprint / result_hash
```

Pydantic 统一 `extra=forbid`。未知值必须为 `null + status`，不得用 0、空字符串或 false 代替。

## 4. 候选宇宙查询

### 4.1 权威查询

以 target SKU + batch 为键：

1. 查询 current `Core3CandidatePool`；
2. 批量查询对应 current `Core3CandidateComponentScore`；
3. 批量查询对应 current `Core3CandidateRoleScore`；
4. 查询 current、非 review 的 `Core3CompetitorSelectionRun/Selection` 作为标签；
5. 批量读取候选身份、M07 轻市场摘要和上游状态；
6. 组装全量 manifest。

不得从 M14 selection 反向限定 candidate pool。

### 4.2 状态决策

```text
M12 current absent                         -> not in competitor universe
M12 blocked                               -> blocked
M12 current + M13 missing                 -> recalled_only
M13 review_required                       -> review_required
M13 available but some question data lack -> limited
M13 available + at least one question     -> eligible
```

blocked/review/recalled_only 保存但不驱动正式 PM 结论。

### 4.3 分析参考池

reference pool 由具体方法服务生成：

- parameter reference：同类目可替代形态、参数 known、同一参数不同取值；
- performance reference：满足市场质量门禁的市场 SKU；
- battlefield reference：目标 excluded 战场中的已成立案例；
- synthetic donor：满足 donor 门禁的 SKU。

每个 reference item 保存 `reference_purpose`，不保存 competitor role。

## 5. 问题级选择

每个问题保存 `QuestionAnalysis`：

```text
question_code
business_question_cn
candidate_pool_type
eligible_candidate_ids[]
selected_candidate_ids[]
rejected_candidate_ids[] + reasons
method
facts / metrics / conclusion boundary
sample_manifest_hash
result_hash
```

计算范围：

- `current_price_support`：全部 eligible 同预算候选；
- `value_relative_advantage`：全部 eligible 同价值候选；
- `same_brand_role`：全部 eligible 同品牌梯度候选；
- `scale_conversion`：全部 eligible 降档分流及价格更低、周均销量更高候选；
- `configuration_follow`：真实替代候选中具备目标能力者；
- `parameter_conversion`：reference pool，同一参数不同有效取值；
- `battlefield_expansion`：reference pool 的 excluded 战场标杆。

报告可展示代表产品，但 `sample_count`、完整 id 清单和 hash 保持全量。

## 6. 门槛功能算法

### 6.1 输入范围

按问题使用相应竞争范围，不对全品类统一计算：

```text
category + product form + relevant size relation
+ price band / competitor role / value battlefield
```

### 6.2 三值统计

每个候选能力只允许：

- known_present；
- known_absent；
- unknown/conflict。

```text
known_count = present + absent
prevalence = present / known_count
```

unknown 不进入 known_count。保存所有计数，门槛样本不足时分类 unknown。

### 6.3 分类顺序

1. fact unknown/conflict -> unknown；
2. target present 且能力普及率过阈值 -> table_stake 候选；
3. target present、体验已形成、相对差异与量价支持 -> retain；
4. target present、投入较高但体验尚未形成或弱于竞品 -> unconverted；
5. target absent、竞品 present，但目标仍在同预算竞争中不弱 -> do_not_follow；
6. target absent、竞品 present 且目标选择/量价受损 -> missing_competitive_gap；
7. 其余 -> unknown/review。

table stake 能力的体验结果重新进入体验比较，例如 HDMI 2.1 不差异化，但游戏连接稳定可差异化。

## 7. 数据库设计

### 7.1 profile version

`core3_sellpoint_value_profile_version`：

- PK `sellpoint_value_profile_version_id`；
- project/category/batch/product_category；
- `profile_version`、schema/rule/method versions；
- draft/reviewed/published/deprecated；
- release quality、current、timestamps/operators；
- source scope、quality summary、validation summary；
- SKU 状态计数；
- input fingerprint、candidate universe fingerprint、result hash。

唯一键不包含 `is_current`，防止同 version 重复创建。current 使用受事务保护的状态切换。

### 7.2 SKU profile

`core3_sku_sellpoint_value_profile`：

- version FK + project/category/batch/SKU；
- identity/display name；
- analysis/freshness/processing/review/release status；
- confidence；
- target market、source lineage、candidate summary；
- threshold、question analyses、investment decisions；
- price role、battlefield、PM decisions、QA index；
- evidence/limitations；
- input fingerprint/result hash；
- generated_at/is_current。

唯一键：project/category/batch/profile_version/SKU/rule_version。

### 7.3 candidate row

`core3_sku_sellpoint_value_candidate`：

- profile/version/SKU FKs；
- target/candidate identities；
- pool type、relation、status；
- M12/M13/M14 摘要；
- eligible questions 和 data availability；
- market summary；
- selected questions/reasons；
- review/evidence/hash。

唯一键：profile + candidate SKU + pool type。

### 7.4 value item

`core3_sku_sellpoint_value_item`：

- profile/version/SKU FKs；
- battlefield、purchase reason、value bundle；
- perceived outcome/status；
- capability codes 和 investment decisions；
- question result refs；
- price/volume realization；
- evidence/boundary/hash。

唯一键：profile + battlefield + normalized bundle code。

## 8. Repository 事务

`write_draft(profile)`：

1. 校验 version 为 draft；
2. 以 version + SKU 锁定/幂等；
3. 相同 input fingerprint 返回已有结果；
4. 不同输入在同版本下拒绝原地覆盖，要求新 profile version；
5. 一个事务写 SKU、candidate、value item；
6. 单 SKU 失败回滚该 SKU；
7. 更新 version counts 使用独立聚合。

`publish_version(version)` 不属于本次执行授权，但 repository 合同和测试必须存在：

- 校验质量；
- 锁定同 category/batch current published；
- 旧 current -> false，新 version -> published/current；
- 不更新 profile payload；
- 失败整体回滚。

## 9. Materializer

单 SKU：

```text
load upstream refs
load candidate universe/reference manifests
build value links and V5 analyses
classify capabilities
assemble question analyses and five PM decisions
validate profile
write draft
read back and verify hash
```

批量：

- 获取权威 SKU 清单；
- 分页/分批；
- `resume_unfinished_only`；
- 每 SKU 独立事务；
- 聚合状态计数；
- 不因一个失败 SKU 回滚整批；
- 同时只运行一个 version job；
- checkpoint 保存最后处理 SKU 和状态，而非依赖内存。

## 10. 报告消费

`sellpoint-value-pm-v5` 新流程：

```text
explicit enable flag
resolve SKU
get current published profile
or explicit draft profile version for preview
validate schema/hash/freshness
profile -> report DTO adapter
render all carriers
```

禁止调用：候选召回、threshold classifier、counterfactual builder、market calculation。

迁移期允许保留 `sellpoint-value-pm-v5-live-preview` 作为显式内部命令，仅用于 G05/G09 对照；不得进入默认报告入口。

## 11. 深入问答

新增 profile ask contract：

```text
sku_code / profile_version / question
resolved_topic
answer_cn
business_implication_cn
fact_paths[]
candidate_ids[]
value_item_ids[]
evidence_refs[]
boundary_cn
profile_result_hash
```

topic router 使用确定性关键词/意图规则：

- retain investment；
- unconverted capability；
- do-not-follow configuration；
- current price support；
- price/volume strategy；
- specific competitor；
- candidate selection reason；
- table stake；
- profile version diff；
- battlefield/portfolio。

自然语言生成可以由上层智能体完成，但事实选择和边界必须来自 qa index。测试使用确定性 renderer。

## 12. CLI/能力边界

建议命令：

- `sellpoint-value-profile-generate`：单 SKU 或 batch draft；
- `sellpoint-value-profile-get`：回读指定/current profile；
- `sellpoint-value-profile-diff`：版本差异；
- `sellpoint-value-profile-ask`：深入问答；
- `sellpoint-value-pm-v5`：只消费 profile；
- `sellpoint-value-profile-publish`：合同存在，但本任务链不执行。

生成、预览、发布和消费 flag 分离。默认自然语言路由仍不启用 V5。

## 13. 测试设计

单元：

- candidate status/role/question eligibility；
- threshold 三值统计和六类决策；
- profile hash/determinism；
- topic router/answer boundary。

repository/migration：

- CRUD、唯一键、事务回滚；
- draft/current/published；
- migration upgrade/downgrade；
- JSON 回读 schema/hash。

集成：

- upstream -> profile -> DB -> report；
- report 路径不触发上游查询；
- profile -> ask；
- TV/AC isolation；
- V4/V5 old fixtures regression。

性能：

- 最大候选 SKU；
- query count 与候选数近似常数而非线性；
- full manifest 数量正确；
- evidence lazy load；
- batch resume。

## 14. 205 执行边界

G09 前禁止部署 migration 或写画像。

G09：只允许 65E7Q draft；记录前后 SQL、hash、报告和问答。

G10：只允许在 G09 complete 后创建全 SKU draft version；分批/resume；不 publish。

任何 published/current 切换必须在 G11 审计后另行获得用户明确授权。
