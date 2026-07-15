# G29 竞品画像 V1.1 Typed Schema 关闭回执

状态：completed

日期：2026-07-15

## 1. Goal

在不创建 migration、不修改 entities/repository/reader/竞品算法、不写数据库、不访问 205 写路径、不发布飞书的前提下，把 G28 的完整兼容基线落入竞品画像 V1.1 Typed Schema，冻结 SKU、Pair、多维分析、结论、排序、证据、Adapter 和性能/存储合同。

## 2. 完成的正式合同

本轮新增并冻结：

- `VersionSkuAnalysisSnapshot`：版本化 SKU identity、product form、market、typed facts、M12C/M12D 领域快照、module availability、evidence 和 hash；
- `DimensionAnalysisResult`、`ValueAnchorAnalysisResult`、`ReplacementPressureAnalysisResult`：维度状态、原始量纲、归一、weighted contribution、计算过程、机器结论和 review overlay；
- `PairAnalysisSnapshot`：完整购买池、七维比较、价值锚点、替代/购买压力、量价验证、六维得分、七类关系、八类问题和 overall conclusion；
- `SkuCompetitionAnalysisSummary`：全候选统计、角色、重点顺序、优势/替代/配置/量价结论，并与完整 Pair 精确交叉验证；
- `CompetitorProfileAnalysisDTO`：version/scope/snapshot/pair/index/selection/fact/evidence 内容闭环；
- `CompetitorProfileAdapterContract`：只消费已计算结果，锁定 target/candidate snapshot、pair、summary 和完整 runtime projection，不重新分析或排序；
- TV/AC 性能与存储预算、六维权重、基础功能 prevalence、unknown/null/empty、hard exclusion 和 deterministic ranking 合同。

## 3. G28 兼容映射与无损性

`G29_legacy_typed_mapping_contract.json.gz` 覆盖：

- 13,756 条观察路径；
- 12,841 条值/null 路径；
- 915 条空数组/空对象路径；
- 3,684 个 alias canonicalization groups；
- 6,493 条可执行 `observed_leaf_to_typed_source_fact`；
- 7,244 条 canonical reference；
- unmapped 0，known-to-unknown 0。

每次旧观测保存稳定 `occurrence_key`、数组索引顺序、原始值、typed value 和 raw occurrence hash。重复值不去重；65E7Q fixture 中 `TV00028909` 指定证据路径原始出现 3 次，投影仍为 3 次且位置一致。Schema 会从 raw occurrence 重算 known/explicit-null/missing 与 typed value，canonical JSON 比较严格区分 `true` 和 `1`。

合同 hash：

`e930470fb80fe90e41f3f67c47a4c7dac97b7fcffbcb080af1d129c8d8ddfe3a`

确定性 gzip SHA-256：

`cd835c115dd6dbbeaad4951b00f136a93c3d6f406c122f212325eb7f9b91cd72`

连续两次重新生成的合同 hash 和 gzip SHA 均一致。

## 4. M12C/M12D 领域字段

四份真实 TV/AC、complete/partial fixture 已逐条执行 claim value、claim contribution、purchase reason projection。以下结果不再依赖 `raw_details`：

- 卖点业务类型及中文定义；
- 用户价值标签与含义；
- typed 市场位置；
- typed SKU 超额表现解释；
- 可解释价格、销量和销额；
- attribution 的品牌、型号、价格带和尺寸档；
- SKU-level claim source 中文标签。

所有 claim、attribution、positive/drag/opportunity、SKU-level value、anchor 和 pressure 条目数与原 fixture 一致；非空业务字段逐项等价。

## 5. Fact、Evidence 与 Summary 闭环

- 正文 `fact_id` 全局唯一；
- fact index 的 key、fact code、source path 与正文事实精确相等；
- fact evidence 必须唯一解析到 evidence index，evidence keys 必须精确相等；
- 同 ID 重复、同 ID 不同内容、错 code、错 path、错 evidence、index-only fact 均硬失败；
- summary 的 candidate count、七维 availability counts、overall strength counts、role buckets、unknown dimensions 和 finding candidate refs 均由保存的 Pair/Adapter candidate 重验；
- selection score、available weight、结论强度、角色、pair hash 和 priority order 必须与保存 Pair 一致。

## 6. Adapter 运行时边界

Adapter 使用 fail-closed consumer projection：

- legacy/raw key 统一大小写并消除 snake/camel 差异后识别；
- `legacy_candidate_count` 只允许出现在 summary 准确路径，且必须为非 bool 整数；
- 任意自由 JSON 容器非空即拒绝，需先提升为领域模型；
- JsonValue 只允许标量、标量列表或空对象；
- serializer 不输出 compatibility 或自由 JSON 容器；
- serializer 每次输出前重跑 runtime boundary、receipt hash 和当前 projection hash；
- 合法构造后修改候选名称、raw occurrence 或 typed value，也无法携带旧 receipt 输出。

已覆盖 `system_instruction`、`golden_dataset`、`cross_category_migration_tool`、`Legacy_Payload`、`legacyPayload`、错误路径/错误类型 `legacy_candidate_count` 和 post-build mutation 绕过。

G32/G37/G38 若需要向智能体提供新的非空自由 JSON，必须先扩展 typed consumer model；不得重新放宽 Adapter。

## 7. 验证与评审

- G29 schema tests：25 passed；
- V1 base + G28 baseline + G29 合并回归：63 passed；
- G29 schema coverage：89%；
- 四份 G28 fixture 完整 compatibility roundtrip：passed；
- 6,493/6,493 observed leaf executable projection：passed；
- M12C/M12D typed domain projection 和逐字段等价：passed；
- raw occurrence 顺序、重复值、raw→typed 严格转换：passed；
- Adapter path whitelist、factory/raw 泄漏、receipt/projection 篡改和 post-build mutation：passed；
- Ruff：passed；
- Python compileall：passed；
- `git diff --check`：passed；
- 独立方法复核：P0=0、P1=0、P2=0，可关闭；
- 独立工程复核：P0=0、P1=0、P2=0，可关闭。

## 8. 写入边界

- migration/entities/repository/reader 修改：0；
- 竞品算法修改：0；
- 数据库写入：0；
- 205 访问或写入：0；
- 飞书消息、卡片、报告或文档：0；
- review/publish/current 切换：0；
- git stage/commit：0；
- 用户已有卖点价值文件和其他未跟踪文件未修改。

## 9. 下一 Goal

G30：实现 V1.1 migration 与 entities，原样落地 G29 已冻结的版本、scope、snapshot、Pair、summary、selection、fact/evidence 和 conditional completeness 合同。G30 尚未创建，必须由下一次调度在确认无 active Goal 后创建。
