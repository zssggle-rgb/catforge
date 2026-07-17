# 用户卖点价值画像 V5.1 详细设计

状态：SPV51-G01 已冻结

日期：2026-07-17

## 1. 设计总览

```text
current published competitor agent snapshot v2
                 │
                 ▼
CompetitorProfileSourceAdapter ──> competitor manifest / pair facts / Top3 labels
                 │
market + parameter + battlefield references
                 │
                 ▼
QuestionEligibilityEngine
  ├─ value realization
  ├─ price-volume comparison
  ├─ parameter/config comparison
  ├─ investment conversion
  ├─ table-stake assessment
  └─ optional strict WTP/synthetic tiers
                 │
                 ▼
LocalConclusionAssembler
  question -> value item -> SKU -> version integrity
                 │
                 ▼
V5.1 repository / immutable draft / report + QA readers
```

关键变化是取消“候选整体资格 → 投入整体复核 → 价值整体复核 → SKU 整体阻断”的串联门槛，改为问题级可用性和局部状态聚合。

## 2. 复用与改造边界

复用：

- V5 现有 4 张持久化表、repository、draft 不可变、版本状态机和报告/问答读画像路径；
- V5 用户价值、投入分类、市场原型、合成对照和严格 WTP 计算器；
- 竞品画像 agent snapshot v2 的 repository、typed schema 和 current published 状态机；
- 现有 TV/AC category isolation、hash、lineage 和 evidence contract。

改造：

- 候选输入由旧 M12/M13/M14 adapter 替换为竞品画像 adapter；
- candidate eligibility 改为 question eligibility；
- materializer 状态聚合、confidence、review propagation 和 lifecycle quality；
- 直接量价层成为可独立报告的正式结果；
- 严格方法从主门槛降为 optional enhancement；
- 必要时通过 migration 增加来源版本与结论状态列/JSON contract。

不改造：竞品画像生成、Top 3、报告视觉设计、上游画像。

## 3. 竞品画像读取合同

新增 `SellpointValueCompetitorProfileAdapter`：

```python
class SellpointValueCompetitorSource(BaseModel):
    source: Literal["competitor_profile_agent_snapshot_v2"]
    access_mode: Literal["formal", "preview"]
    competitor_profile_version_id: str
    profile_version: str
    category_code: Literal["TV", "AC"]
    target_sku_code: str
    source_result_hash: str
    candidates: list[SellpointValueCompetitorCandidate]
    priority_order: list[str]
```

formal：只允许 repository 返回 current published agent snapshot v2；不接受显式 version id。

preview：必须显式给 version id 和 release scope；只允许一个非 current draft 或 current published 版本。

候选映射：

- `source_rank`、`selected_rank`、`role/role_cn`、`business_score` 原样保存；
- `purchase_pool`、`weighted_overlap`、`value_anchor`、`replacement_pressure`、`market_validation` 等作为问题级事实；
- 缺某字段时标记该字段 unavailable，不把 candidate 状态整体改为 review；
- `priority_order` 只写 `is_priority`/priority rank，不参与过滤。

正式生成发现竞品画像不可用、版本错类目或 hash 失败时生成失败，不回退旧候选。

## 4. 问题级可用性

新增统一结构：

```python
class QuestionEvidenceStatus(str, Enum):
    CONCLUSION_AVAILABLE = "conclusion_available"
    PARTIAL_CONCLUSION = "partial_conclusion"
    NO_CONCLUSION = "no_conclusion"
    INVALID = "invalid"

class QuestionCandidateUse(BaseModel):
    candidate_sku_code: str
    source_type: Literal["competitor", "market_reference"]
    selected: bool
    usable_dimensions: list[str]
    unavailable_dimensions: list[str]
    selection_reasons: list[str]
    rejection_reasons: list[str]

class QuestionConclusion(BaseModel):
    question_code: str
    status: QuestionEvidenceStatus
    strength: Literal["group", "small_group", "single", "directional", "none"]
    candidate_uses: list[QuestionCandidateUse]
    facts: dict[str, Any]
    result: dict[str, Any]
    limitations: list[str]
    review_required: bool = False
    review_reasons: list[str] = []
```

规则：

- invalid 仅用于 schema/scope/hash/自相矛盾；
- no_conclusion 不触发 review；
- 一个 candidate 可参与量价但不参与价值兑现，或相反；
- candidate 级 review 只在该问题使用了受冲突影响的直接字段时叠加；
- unknown 不按 0、false 或负向处理。

## 5. 门槛配置

建议新增 `sellpoint_value_profile_v5_1.yaml`：

```yaml
direct_market_gap:
  min_comparators: 1
  small_group_max: 4
  require_common_weeks: false
  require_common_platforms: false
  allow_weekly_average: true
value_realization:
  min_shared_anchors: 1
  allow_single_comparator: true
parameter_group:
  min_distinct_values: 2
  min_skus_per_value: 1
  require_ordinal_tier: false
table_stake:
  min_known: 5
  prevalence_threshold: 0.80
  insufficient_sample_status: not_assessed
strict_market_implied_wtp:
  required_for_profile: false
  required_for_release: false
synthetic_control:
  required_for_profile: false
  required_for_release: false
```

所有数值只影响本方法的结论强度，不能改变竞品画像候选集合。

## 6. 量价实现

### 6.1 直接竞品/参考组量价

对每个价值项或价值组合：

1. 从正式竞品中选择共同价值、共同采购理由或相同任务场景候选；
2. 必要时补充同预算、参数组或市场原型参考；
3. 使用 M07 已保存的均价和周均销量；
4. 分别计算逐款 gap 与组加权/简单均值 gap；
5. 保存对照数、候选清单、价格 gap、销量 gap、比例、方向和证据强度。

只要有 1 个合法对照就生成 `direct_market_gap`。多产品组不能因其中一个缺量价而整体失败；只排除缺该问题直接字段的行。

### 6.2 市场原型

复用现有同预算组、卖得好/卖得差组合、参数分组、相邻战场和 synthetic donor。输出统一挂在 `market_archetype`，保存方法名称和可比边界。

### 6.3 严格 WTP

保留既有 donor、balance、common weeks/platforms、leave-one-out 等严格门槛。失败结果保存技术原因，但不进入 SKU review/release quality，也不进入默认业务报告。

## 7. 基础能力与投入分类

基础能力计算返回：

- `confirmed_table_stake`；
- `not_table_stake`；
- `not_assessed`；
- `invalid`。

`not_assessed` 不等于 unknown investment，也不触发 review。投入分类按可用证据输出：

- 已有产品事实 + 用户价值 + 市场差异，可判断 retain/unconverted/do_not_follow/missing_gap；
- 只有产品事实，可输出配置事实和该问题 no_conclusion；
- 只有基础能力样本不足，不影响其连接的用户价值；
- 内部分类未知不允许把全部 linked value items 标成 review。

## 8. 状态聚合算法

### 8.1 value item

```text
任何 question invalid                       -> invalid
至少一个 conclusion_available               -> conclusion_available
否则至少一个 partial_conclusion             -> partial_conclusion
否则                                        -> no_conclusion
```

只有该价值自身的核心证据冲突才设置 value item review。`linked_investment_review` 取消作为自动原因。

### 8.2 SKU

```text
结构/范围/hash/持久化 invalid               -> invalid
至少一个 value/action conclusion_available  -> conclusion_available
否则至少一个 partial_conclusion             -> partial_conclusion
否则                                        -> no_conclusion
```

profile confidence 不再取全部投入分类 confidence 的平均值。保存各问题 confidence distribution；SKU confidence 仅反映已输出结论的最低/中位强度，不作为发布阻断。

### 8.3 version

```text
coverage mismatch / generation failure / invalid rows > 0 -> blocked
完整性通过，存在 partial/no_conclusion/review           -> limited
完整性通过，全部 conclusion_available 且无 review       -> ready
```

版本 `limited` 可进入 review/publish，但 publish/current 仍需显式批准。

## 9. 持久化与迁移

G03 先冻结 typed schema，G04 再决定最小 migration。优先复用现有 JSON payload，只有以下查询/完整性字段才做实体列：

- source competitor profile version id/method/result hash；
- SKU conclusion status 与计数；
- version conclusion distribution 与 invalid count；
- value item conclusion status；
- direct market result availability。

约束：

- V5 旧草稿只读，不原地转换；
- V5.1 新 method/schema/rule version 写新 draft；
- downgrade 遇到 V5.1 行时明确阻断或要求先清理 V5.1 draft，不伤害 V5 历史行；
- fingerprint 绑定竞品画像 version id/result hash 和所有现有上游版本。

## 10. 报告与问答

报告/问答改造只做字段映射：

- conclusion/partial 的已成立内容进入业务答案；
- no_conclusion SKU 返回统一业务提示；
- invalid 返回系统数据异常，不生成产品结论；
- strict WTP/synthetic 不成立的区块省略；
- 不从 `review_reasons` 重新推导产品动作；
- 正式和 preview 均锁定同一 V5.1 画像 hash。

## 11. 测试策略

### 11.1 每个开发 Goal

只运行：

- 新增/修改 public function 的正常、边界、异常测试；
- 直接受影响的 1—3 个回归文件；
- touched Python 文件 ruff/compile 或对应 migration/schema check。

不在每个 Goal 重复：全量 SPV 回归、全量 competitor-profile 回归、覆盖率、性能压测、三类总评审。

### 11.2 集成 Goal

SPV51-G13 一次性完成：

- 全部 sellpoint-value + competitor-profile consumption 回归；
- migration upgrade/downgrade；
- coverage；
- 最大候选性能、无 N+1、内存边界；
- 方法、工程、业务语言和发布边界评审；
- 精确暂存与提交。

## 12. 失败与回退

- 单 SKU 生成失败只回滚该 SKU 写入，不污染同版本其他 SKU；
- 新 draft 不覆盖 V5 或 published current；
- 205 部署与生成分开；
- 65E7Q/AC 单 SKU失败时停止，不创建全量 Goal；
- 全量只生成 draft；
- 未获得用户明确批准，不 review/publish/current。
