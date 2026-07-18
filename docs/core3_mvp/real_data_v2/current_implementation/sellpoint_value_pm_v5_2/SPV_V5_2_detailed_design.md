# 用户卖点价值画像 V5.2 详细设计

状态：SPV52-G01 已冻结

日期：2026-07-18

## 1. 设计总览

```text
M04C source claim facts ─────┐
M03B parameter facts ────────┤
V5.1 user value / market ────┼─> LayeredSellpointMapper
competitor profile facts ────┘
                                  │
                                  ├─ source sellpoint facts
                                  ├─ sellpoint ↔ parameter links
                                  ├─ sellpoint ↔ user value links
                                  ├─ sellpoint assessments
                                  ├─ parameter assessments
                                  └─ competitor sellpoint findings
                                  │
                                  ▼
                      V5.2 immutable draft/profile
                                  │
                                  ▼
                    report / card / QA read-only views
```

核心变化是取消 `capability/parameter/value theme -> product sellpoint` 的反向生成，改为：

```text
M04C product sellpoint -> supporting parameters -> user value -> market result
```

## 2. 复用与新增边界

复用：

- V5.1 候选池、用户价值、量价、投入判断、版本状态机和四张持久化表；
- M04C 卖点事实、M03B 参数事实和正式竞品画像；
- V5.1 repository、immutable draft、preview reader 和正式消费边界；
- 现有 TV/AC category isolation、evidence ref、fingerprint 和 result hash。

新增：

- V5.2 typed schema；
- M04C 原始卖点只读 adapter；
- 卖点—参数—用户价值—内部主题映射器；
- 卖点评估与参数评估；
- 分层完整性校验；
- V5.2 报告、卡片和 QA 投影。

禁止：

- 修改已发布 V5.1 行；
- 在 report renderer 中读取上游；
- 在 report renderer 中生成产品卖点；
- 用参数或 value theme 兜底 `product_sellpoint`。

## 3. Typed Schema

### 3.1 原始卖点

```python
class SourceSellpointFact(BaseModel):
    source_claim_key: str
    claim_fact_id: str
    raw_claim_text: str
    clean_claim_text: str | None
    exact_quote_cn: str | None
    normalized_claim_code: str
    normalized_claim_name_cn: str
    claim_dimension: str
    claim_kind: str
    param_support_status: str
    supporting_param_codes: list[str]
    evidence_refs: list[SellpointValueEvidenceRef]
```

校验：

- `exact_quote_cn` 非空时必须是 `raw_claim_text` 的连续子串；
- `claim_fact_id/source_claim_key/raw_claim_text/claim_code` 不得为空；
- evidence 必须包含 M04C 记录引用；
- 同一 `claim_fact_id` 的来源字段不可冲突。

### 3.2 分层链接

```python
class SellpointParameterLink(BaseModel):
    sellpoint_fact_id: str
    parameter_code: str
    parameter_name_cn: str
    normalized_value: str | None
    support_role: Literal["primary", "supporting", "generic"]
    evidence_refs: list[SellpointValueEvidenceRef]

class SellpointUserValueLink(BaseModel):
    sellpoint_fact_id: str
    value_bundle_code: str
    user_value_cn: str
    perceived_status: str
    internal_value_theme_codes: list[str]
    evidence_refs: list[SellpointValueEvidenceRef]
```

`internal_value_theme_codes` 永远不提供产品卖点显示值。

### 3.3 卖点评估

```python
SellpointClassification = Literal[
    "core_sellpoint",
    "basic_sellpoint",
    "user_unrecognized_sellpoint",
    "pending_sellpoint",
]

class ProductSellpointAssessment(BaseModel):
    source_claim_key: str
    normalized_claim_code: str
    source_sellpoint_fact_ids: list[str]
    classification: SellpointClassification
    parameter_codes: list[str]
    value_bundle_codes: list[str]
    user_value_summaries_cn: list[str]
    market_result_refs: list[str]
    business_reason_cn: str
    product_action_cn: str
    confidence: Decimal | None
    evidence_refs: list[SellpointValueEvidenceRef]
```

最小评估单元为 `source_claim_key + normalized_claim_code`。同一原始文案映射多个标准卖点时分别评估，报告再按 `source_claim_key` 分组。

### 3.4 参数评估

```python
ParameterClassification = Literal[
    "differentiating_parameter",
    "basic_parameter",
    "parameter_gap",
    "non_key_parameter_difference",
    "pending_parameter",
]

class ProductParameterAssessment(BaseModel):
    parameter_code: str
    parameter_name_cn: str
    normalized_value: str | None
    classification: ParameterClassification
    linked_sellpoint_fact_ids: list[str]
    business_reason_cn: str
    confidence: Decimal | None
    evidence_refs: list[SellpointValueEvidenceRef]
```

## 4. M04C 原始卖点 Adapter

新增只读 adapter，按 V5.2 生成请求锁定：

- project；
- category；
- source batch；
- target SKU；
- current M04C profile/hash。

读取 profile 和 claim facts，规范化为 `SourceSellpointFact`：

- 同一原始文案命中多个 claim code 时保留多个标准事实；
- 同一 `source_claim_key + claim_code` 重复行按证据合并；
- `supported` 优先于 `partially_supported/param_unknown`，但不能删除冲突；
- service fulfillment 不进入产品体验卖点分类，仍保留在来源审计；
- 不调用外部 LLM。

正式 V5.2 生成发现 M04C 缺失时：

- 不伪造产品卖点；
- 保存 `source_sellpoint_state=no_source_sellpoint`；
- 继续生成参数账、用户价值账和市场结果；
- SKU 可为 partial，不因卖点缺失成为 invalid。

## 5. 分层映射

### 5.1 卖点到参数

优先使用 M04C 已保存的：

- `primary_supporting_param_codes`；
- `supporting_param_codes`；
- `generic_support_param_codes`；
- `param_support_status`。

只允许映射 M03B 中存在的参数代码。missing 保持 unknown，不转成 absent。

### 5.2 卖点到用户价值

使用标准 claim code、claim dimension 和现有 value bundle 的 claim anchors 建立确定性映射。规则必须：

- category scoped；
- versioned；
- 可测试；
- 不读取显示文案做开放式语义生成；
- 找不到映射时保持 pending，不使用 value theme 名称替代卖点。

### 5.3 用户价值到市场结果

复用 V5.1 已保存的直接量价、市场原型和严格增强结果。市场结果挂到用户价值链接，不宣称单一卖点实验因果。

## 6. 分类算法

### 6.1 卖点分类

```text
无合法 source sellpoint fact
  -> 不创建 ProductSellpointAssessment

有来源但事实/价值证据不足或冲突
  -> pending_sellpoint

产品事实成立 + 用户价值未观察/负向
  -> user_unrecognized_sellpoint

主要支撑参数 confirmed table stake
且无具体领先档位的独立价值证据
  -> basic_sellpoint

产品事实成立 + 用户价值正向/部分正向
且存在直接市场或相对兑现支撑
  -> core_sellpoint
```

若同一卖点同时满足 basic 和 core：

- 泛能力部分进入 basic；
- 有独立证据的具体领先档位进入 differentiating parameter；
- 卖点只有在其整体用户价值和市场支撑成立时进入 core；
- 规则冲突时 pending，不使用优先级掩盖冲突。

### 6.2 参数分类

```text
confirmed table stake
  -> basic_parameter

本品具备具体领先档位 + 连接核心卖点和用户价值
  -> differentiating_parameter

本品缺失/较弱 + 对照价值或量价显示受压
  -> parameter_gap

本品缺失 + 当前价值和量价未显示受损
  -> non_key_parameter_difference

其余
  -> pending_parameter
```

参数分类不能直接生成卖点机会。

### 6.3 竞品卖点机会

只有同时满足以下条件才生成：

1. 竞品有可追溯原始卖点；
2. 本品没有对应标准卖点或用户价值；
3. 竞品的用户价值/量价表现存在正向证据；
4. 本品在该价值上存在相对弱势。

仅缺参数时保存 `parameter_gap`，不生成卖点机会。

## 7. 持久化与兼容

优先把新增 sections 放入现有 JSON payload，不增加新表和 migration。G02/G04 通过真实 repository 结构确认；只有无法完成查询完整性或版本隔离时才新增最小 migration。

版本规则：

- schema/method version 升为 V5.2；
- V5.1 current published 保持不变；
- V5.2 只创建新 immutable draft；
- V5.1 reader 不读取 V5.2；
- V5.2 reader 可明确返回旧画像缺少 layered sellpoint contract，不能现场补算；
- fingerprint 绑定 M04C/M03B/竞品画像/用户价值来源 hash。

## 8. 消费投影

删除或禁用当前 `_v5_1_product_sellpoint_cn()` 的参数拼接与 capability/value-theme fallback。

报告模型不再使用一个无来源的 `product_sellpoint_cn` 字段，改为：

```python
class StoredPmSellpointRow(BaseModel):
    raw_claim_text: str
    exact_quote_cn: str | None
    normalized_claim_name_cn: str
    classification_cn: str
    supporting_parameters_cn: list[str]
    user_values_cn: list[str]
    current_user_recognition_cn: str
    market_performance_cn: str | None
    product_action_cn: str
```

产品经理正文按以下顺序：

1. 本品原始卖点价值结论；
2. 核心卖点；
3. 基础卖点；
4. 用户未认知卖点；
5. 基础参数和其他参数判断；
6. 卖点机会与竞品参考；
7. 产品卖点修改建议。

内部 value theme 只进入审计下钻，不显示为产品卖点。

## 9. 完整性校验

新增 `LayerIntegritySummary`：

- displayed_sellpoint_count；
- sourced_sellpoint_count；
- unsourced_sellpoint_count；
- parameter_as_sellpoint_count；
- value_theme_as_sellpoint_count；
- exact_quote_mismatch_count；
- dangling_sellpoint_link_count；
- source_profile_hash_mismatch_count。

发布质量要求：

- `unsourced_sellpoint_count = 0`；
- `parameter_as_sellpoint_count = 0`；
- `value_theme_as_sellpoint_count = 0`；
- quote/link/hash mismatch 均为 0。

缺少原始卖点是数据不足，不是结构 invalid；伪造或串线才是 invalid。

## 10. 测试策略

开发 Goal 只运行：

- 当前新增 public functions 的正常、边界和异常测试；
- 直接受影响的 1—3 个回归文件；
- touched Python 文件 ruff/compile；
- 不重复运行全量回归、覆盖率、性能和三类评审。

SPV52-G06 集中执行：

- V5.2 全部专项测试；
- V5.1 正式消费兼容回归；
- competitor-profile consumption 回归；
- 最大卖点/候选 SKU 性能与 query count；
- 方法、工程和产品经理语言评审；
- 精确暂存、提交和推送。

## 11. 65E7Q 确定性断言

- 原始游戏卖点完整回读；
- “游戏影音双丝滑”来自 raw claim 连续子串；
- “游戏与运动流畅”只存在于 internal theme；
- 170Hz/300Hz/HDMI 2.1/48Gbps 只存在于参数链接；
- 不再生成“300Hz高刷”作为产品原始卖点；
- table-stake 有来源卖点与无来源参数正确分流；
- 原有 20 个竞品、Top 3、51 个参考和 4 组量价结果不回退；
- card/report/QA 同 hash、同分类、同原始文案。

## 12. 部署与回退

- G06 提交前不部署；
- G07 只部署代码并生成 65E7Q draft；
- 65E7Q 失败不创建 AC/全量草稿；
- G08 先 AC 单 SKU，再 TV/AC 全量 draft；
- V5.2 不覆盖 V5.1 current；
- 未获明确批准，不 review、publish 或切 current；
- 回退只需恢复部署代码并删除未发布 V5.2 draft，不影响 V5.1 正式消费。
