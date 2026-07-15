# G29 竞品画像 V1.1 Typed Schema 合同

状态：completed

日期：2026-07-15

## 1. 本 Goal 的边界

G29 只冻结竞品画像 V1.1 的领域对象、条件必填、兼容映射、类型、分数和预算合同。

本 Goal：

- 不创建 migration；
- 不修改 entities、repository、reader 或竞品算法；
- 不读取或写入数据库；
- 不访问 205 写路径；
- 不生成画像；
- 不发送飞书消息，不创建卡片、报告或文档；
- 不做 review、publish 或 current 切换。

## 2. 画像的权威数据结构

V1.1 的正式业务分析对象由以下 typed models 组成：

1. `VersionSkuAnalysisSnapshot`
   - 版本、project、category、release scope 和 snapshot ref；
   - SKU identity、product form 和独立 market snapshot；
   - 参数、卖点、战场、任务、客群、用户价值和采购理由的 typed fact items；
   - M12C claim value、claim contribution 和 M12D purchase reason snapshot，内部 claim、attribution、SKU-level value、anchor、pressure 均为领域模型，不再是 `list[JsonObject]`；
   - 旧链逐叶输入进入带 entity、presence、source/target path、原始 occurrence、稳定数组位置、顺序和 value hash 的 `NormalizedSourceFact`；重复值不去重，空值标记的原文也不丢；
   - module availability、lineage、evidence、limitation 和 hash。
2. `DimensionAnalysisResult`
   - available/partial/unknown/conflict；
   - 双方、共同、仅本品、仅竞品条目；
   - raw score、available weight、normalized score、weighted contribution；
   - 计算过程、机器结论、review overlay、证据和 hash。
3. `ValueAnchorAnalysisResult`
   - 价值锚点双方集合、共同/强弱/表达状态；
   - 购买压力比较和 match details；
   - 0—15 分原始量纲及 0—1 归一；
   - method/config version、结论、证据和 hash。
4. `ReplacementPressureAnalysisResult`
   - 主/辅替代压力、计算组成、受影响采购理由和业务影响；
   - 0—10 分原始量纲及 0—1 归一；
   - method/config version、结论、证据和 hash。
5. `PairAnalysisSnapshot`
   - target/candidate snapshot refs；
   - scope、recall、购买池、七类维度、价值锚点、替代压力、购买压力和量价验证；
   - 多角色、主角色、六维分数、七类 relation assessment、八类问题级结论和 overall conclusion；
   - review、lineage、evidence、limitation、fingerprint 和 result hash。
6. `SkuCompetitionAnalysisSummary`
   - 全候选统计、维度可用度、结论强度、重点竞品顺序、角色 buckets；
   - 优势、可替代价值、配置差异、量价压力、未知项和 review items；
   - DTO/adapter 强制按完整 pair 重验七维 availability counts、overall strength counts、role buckets、unknown dimensions 和 finding candidate refs。
7. `CompetitorProfileAnalysisDTO` / `CompetitorProfileAdapterContract`
   - 一个版本内的 target/candidate shared snapshots、pair index、完整 pair 分析和 selections；
   - adapter 只接收已经计算完成的 typed 数据和已保存顺序；`build_from_authoritative_projection` 是唯一 receipt 构造入口，所有大小写/snake/camel 变体的 legacy/raw compatibility key 均按路径拒绝；`legacy_candidate_count` 只能在 summary 准确路径以非 bool 整数出现；
   - adapter 对自由 JSON 容器采用 fail-closed：非空内容必须先提升为领域模型，否则拒绝；允许保留的 JsonValue 只能是标量、标量列表或空对象。对外序列化只输出显式 typed consumer fields，自由容器、兼容字段即使在持久化模型中有空默认值也不会进入运行时结果；
   - DTO 和 adapter 均保存 stable fact index 与 evidence index；索引自身不算事实，非 unknown 结论必须先引用画像正文中真实嵌入的 fact，再由 fact index 解析到 evidence；fact ID 全局唯一，正文 fact 的 code/source path/evidence 必须与 index 逐项相等，同 ID 重复或内容错配硬失败；
   - adapter candidate 显式携带购买池、七维比较、价值锚点、替代/购买压力、量价验证、主辅角色、七类关系、八类问题、复核项和限制，不把旧输入交给智能体重算；
   - DTO 校验 version、project、category、release scope、snapshot refs、pair/index hash、selection score、coverage、结论强度、角色和 summary 完全一致；
   - adapter 使用带确定性 hash 的 source receipt 锁定原 DTO 的 version、profile hash、target/summary hash、全部 candidate snapshot hash、全部 candidate pair hash，以及完整运行时投影 hash；修改任意候选字段但保留旧 receipt 必须失败，并复用 Pair 的六维、关系、问题一致性校验；serializer 在每次输出前重新执行 fail-closed 边界、receipt 自身 hash 和当前 projection hash，构造后原地修改嵌套对象也不能绕过。

## 3. unknown、review 和 hard exclusion

### 3.1 unknown 不是 0/false/empty

`TypedFactValue` 明确区分：

- `known`：有非 null 值，允许值本身为 `false`、`0`、`[]` 或 `{}`；
- `explicit_null`：旧源明确返回 null；
- `missing`：源路径不存在，必须带 unknown reason；
- `conflict`：至少两个冲突值，不选取伪真值。

unknown/conflict 维度：

- available weight 为 0；
- raw/normalized score 为 null；
- weighted contribution 为 0；
- conclusion strength 和 direction 必须为 unknown；
- 必须说明 limitation。

价值锚点或替代压力上游不可用时，原始 15 分/10 分字段必须为 null、level 为 `unknown`、available weight 为 0、结论为 unknown；禁止用 0 分冒充“已计算但很弱”。

### 3.2 review 独立叠加

`review_required/review_items` 不改变 `scope_status`。战场冲突、M12D review、taxonomy unknown 或 lineage 缺失在 identity 已知时仍可保持 analyzable，由具体维度记录 unknown/conflict/review。

### 3.3 只接受五类 hard exclusion

- `self_pair`；
- `project_mismatch`；
- `category_mismatch`；
- `candidate_outside_manifest`；
- `identity_decode_failed`。

自配对必须保存为 `excluded + self_pair`，不能在 schema 层悄悄消失。hard-excluded pair 不允许携带伪造的维度、得分或竞争角色。

### 3.4 问题级最低证据

八类问题不是独立填写的文案槽位，而是由 pair 的实际可用维度决定：

- `configuration_follow` 除参数和卖点差异外，必须至少具备价值锚点、用户任务或量价市场关联中的一个；
- required dimensions 或 any-of evidence group 不满足时，问题必须为 unknown/unanswerable；全部最低证据满足时不得反向写成 unknown；
- `key_competitor_selection` 不再以购买池自证，只有至少一个其他产品决策问题可回答时才成立，其结论强度等于已成立问题中的最高强度；
- relation missing/conflict/status 和 question missing/answerable/strength 均从同一份实际 dimension availability 交叉验证，adapter 也执行同一校验。

## 4. 分数量纲和排序公式

六个主体维度和权重冻结为：

| 维度 | 权重 |
| --- | ---: |
| 购买池 | 20% |
| 价值战场 | 25% |
| 用户任务 | 15% |
| 目标客群 | 15% |
| 价值锚点 | 15% |
| 替代压力 | 10% |

计算合同：

```text
weighted_contribution_i = raw_score_i * configured_weight_i
raw_total = sum(weighted_contribution_i)
available_weight = sum(available dimension weights)
normalized_total = raw_total / available_weight
coverage = available_weight
ranking_score = normalized_total
```

重点选择先按对应问题的结论强度排序，再比较 `ranking_score`。`coverage` 不乘入主体得分，也不设最低门槛；它通过问题结论强度反映证据完整性，并在同分时作为可用权重参与排序。因此低覆盖 pair 可以保留并回答已有证据支持的问题，但不能只靠少量已知维度的归一分越过结论更完整的 pair。`coverage_minimum_gate=None`，没有显性或隐性最低覆盖门槛。市场量价只用于验证和同分排序。

固定同分顺序：

1. market validation strength；
2. available weight；
3. recall rank；
4. candidate SKU code。

## 5. 基础功能 prevalence

参数/卖点条目同时保存：

- 原始差异；
- supported/contradicted/unsupported/unknown；
- prevalence numerator、denominator、ratio、source 和 scope hash；
- `foundational|differentiating|unknown`。

首版规则冻结为：

- known count 小于 5：unknown；
- known count 至少 5 且 prevalence 大于等于 80%：foundational；
- known count 至少 5 且 prevalence 小于 80%：differentiating。

scope 必须同时锁定 category、price band、product form 和 size relation。基础功能仍保存双方原始事实，但不能贡献差异得分、重点排序理由或产品建议。

## 6. G28 旧字段兼容合同

`G29_legacy_typed_mapping_contract.json.gz` 由本地确定性脚本生成：

- G28 inventory hash：`34be0aa0fdf42437ec3a5d96bf5325e30164a2aa25dd09ee5eb7a3dc71639381`；
- 真实 fixture：4 份，覆盖 TV/AC、published-ready/published-degraded；
- 观察路径：13,756；
- 普通值/null 路径：12,841；
- 空数组/空对象路径：915；
- alias canonicalization groups：3,684；
- unmapped：0；
- known-to-unknown：不允许；
- 当前 contract hash：`e930470fb80fe90e41f3f67c47a4c7dac97b7fcffbcb080af1d129c8d8ddfe3a`；
- 确定性 gzip SHA-256：`cd835c115dd6dbbeaad4951b00f136a93c3d6f406c122f212325eb7f9b91cd72`。

每个观察路径都保存 source atom、旧 target leaf、兼容保存路径、normalized target path/model/field、可执行 transform code、观察/接受类型、出现次数、null/empty policy 和 roundtrip policy。合同 hash 由完整规范化 JSON（排除 hash 字段自身）计算，篡改任一字段会校验失败。

### 6.1 兼容副本不等于 V1.1 分析权威

旧 atom 中有大量深层 M12C/M12D 和旧 pair payload。为保证升级可审计：

- 旧值按逐叶类型合同保留；
- 旧 `top_competitors` 和角色 bucket 的重复完整 pair payload 不重复存储；
- top list 只转为 selection rank + candidate/pair ref；
- role bucket 只转为 role + candidate SKU refs；
- 其余兼容 subtree 标记 `normalization_required=true`；
- 兼容 subtree 标记 `authoritative_for_v11_analysis=false`，不能直接进入 V1.1 scorer、selection 或 adapter；
- 只有标准化后的 V1.1 typed fields 标记为 analytical authority。

字段分配模式已经显式冻结：13 条 direct assignment，1 条 batch scalar 转 singleton list，5 条角色 bucket 转 SKU refs，6,493 条 `observed_leaf_to_typed_source_fact`，7,244 条重复视图只保留 canonical reference。合计 6,512 条 canonical 路径均有 normalized analytical destination；重复视图指向 canonical 结果，不产生第二份事实。

旧 compatibility subtree 仍为非权威审计副本，但每一条 canonical legacy leaf 现在同时具有独立的 normalized target 和可执行 transform，不再以 `normalization_required=true` 代替映射本身。四份 fixture 实际执行 6,493 条逐叶 typed projection，TV/AC、complete/partial 的观察路径并集为 6,493/6,493；`false`、`0`、空数组、空对象、explicit null 和缺失标记分别按 presence 合同保存。每次观测另存 `occurrence_key + ordinal + raw_value + typed_value`，`occurrence_count`、顺序和 raw occurrence hash 由 schema 交叉校验；schema 还会按冻结规则从 raw value 重算 known/explicit-null/missing 与 typed value，不能同时篡改两个 typed 副本。同一路径出现三次相同文本仍保存三条，不再因 canonical JSON 相同而合并。

四份 G28 真实 fixture 还实际执行 M12C/M12D 领域 projection：所有 claim values、claim contribution attributions、positive/drag/opportunity claims、SKU-level claim values、purchase reason anchors 和 purchase pressure reasons 均成功进入 typed record，条目数与原始 fixture 一致。`business_claim_type`、`business_value_label`、`business_value_meaning_cn`、typed `market_position`、typed `sku_excess_explanation`、可解释价差和可解释销量差均已提升为正式 typed 字段，并对每条真实记录逐字段核对；`ClaimAttributionRecord` 的品牌/型号/价格带/尺寸档和 SKU-level claim source 中文标签也已提升。智能体无需读取 `raw_details` 才能获得“基础门槛/用户价值/量价解释”等业务结果。完整 pair 只保存一次，Top 列表只保存 rank + pair ref，角色 buckets 只保存去重 SKU refs，batch ID 转为单元素 typed list。该 projection 冻结 G32/G33/G36 必须复用的变换合同，但不在 G29 生成数据库画像。

G32/G33 必须从 frozen upstream snapshot 产生标准化 typed fields；不能把旧展示摘要或 compatibility subtree 冒充新分析结果。保留旧 subtree 只解决无损回读和新旧差异审计。

## 7. 性能和存储预算

| 品类 | 最大候选 | 生成 p95 | 峰值内存 | 单 SKU draft 上限 |
| --- | ---: | ---: | ---: | ---: |
| TV | 377 | 60 s | 1,200 MiB | 512 MiB |
| AC | 155 | 30 s | 600 MiB | 256 MiB |

共同预算：

- compact readback 不高于 2 秒；
- provider SELECT 不高于 11 次；
- 每增加一个 target 的额外 provider SELECT 为 0；
- SKU snapshot 必须版本内共享；
- pair 不复制完整 SKU payload；
- 不允许以性能为由截断候选或删除分析维度。

G28 在 205 只读观察到 TV 359、AC 151，均低于冻结上限。预算是 G39/G41 的失败门禁，不是提前裁剪数据的理由。

## 8. G30—G38 的强制交接条件

1. G30 migration/entities 必须原样实现 schema version、snapshot ref、scope、conditional completeness 和 hash 列；
2. G31 repository/reader 必须完整回读 shared snapshots、pair analysis、selection 和 evidence index；
3. G32 必须填充 normalized SKU typed facts，不能只写 compatibility subtree；
4. G33 必须调用成熟锚点/替代/购买压力计算器，填充 15/10 分原始量纲、过程、method/config version 和机器结论；
5. G34 只能使用五类 hard exclusion；其他缺失按维度继续；
6. G35 使用本合同的“问题结论强度 → normalized score → 固定同分项”顺序；coverage 只影响结论强度和同分，不得成为门槛；
7. G37/G38 只消费 `normalized_authoritative_for_v11_analysis` 的 typed 结果，不消费旧 compatibility subtree，不重新计算；adapter 映射错字段时必须由共享一致性合同硬失败。

## 9. 当前验证

- G29 schema tests：25 passed；
- G29 schema 覆盖率：89%；
- G29 + G28 baseline + V1 base schema 合并回归：63 passed；
- 四份真实 G28 fixture 完整 roundtrip：passed；
- 四份真实 G28 fixture 的 6,493 条逐叶 typed source-fact projection、重复 occurrence 无损保存与 M12C/M12D 业务字段逐项等价：passed；
- 13,756 路径 compatibility + normalized destination、显式 transform、alias、authority 和 hash 验证：passed；
- pair/adapter 六维得分与源分析、问题最低证据、关系/问题状态与维度可用性、summary 聚合、compact index、selection、正文 fact/code/path/evidence 内容闭环、重复 fact ID、raw→typed 篡改、Adapter 路径白名单/case-camel 绕过/自由 JSON 泄漏、投影篡改和构造后 mutation→serialization 负例：passed；
- Ruff：passed；
- Python compile：passed；
- `git diff --check`：passed；
- 数据库/205/飞书写入：0。

独立方法和工程评审结果将在关闭回执中记录。
