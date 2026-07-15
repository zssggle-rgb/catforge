# G33 竞品画像 V1.1 Pair Analysis 关闭回执

状态：completed

日期：2026-07-16

## 1. Goal

在不连接或写入业务数据库、不访问 205、不生成 profile/relation/selection、不修改 G34—G38、旧 M12/M13/M14 或 V1 草稿、不执行 review/publish/current 的前提下，实现完整 `PairAnalysisCalculator` 与 `PairAnalysisAssembler`：Calculator 对 G32 共享 SKU 快照和冻结候选事实完成成熟多维比较；Assembler 只无损组装已经算完的 typed 结果、证据闭包、lineage 和确定性 hash。

## 2. Calculator 与 Assembler 边界

- `PairAnalysisCalculator` 是 G33 唯一计算入口，校验 target/candidate snapshot、候选召回事实和 pair 输入是否属于同一 project/category/version/scope/hash 链；
- Calculator 生成购买池、七类维度比较、价值锚点、替代压力、购买压力、市场量价验证和旧链评分依据；
- `PairAnalysisAssembler` 不调用任何计算器，不从旧 V1 展示摘要、compatibility subtree 或 `raw_details` 反推结论，只复制 typed calculation 中已经完成的字段；
- Assembler 入场时重新闭合 `calculation_result_hash`，任一中间结果被篡改都会 fail closed；
- 静态测试禁止 Assembler/本模块引用 Repository、SQLAlchemy、外部 LLM、网络、G34 关系门槛、G35 角色排序或 G36 materializer。

## 3. 成熟计算合同与版本冻结

- 价值锚点：显式调用成熟 `ValueAnchorMatcher`，完整保存 15 分制得分、逐锚点匹配过程、目标/候选建立状态、共同与单边锚点、弱表达和未兑现证据；
- 替代压力：显式调用成熟 `ReplacementPressureClassifier`，完整保存 10 分制主压力、辅助压力、组成项、等级、市场信号和限制；
- 购买压力：显式调用成熟 `PurchasePressureComparator`，逐项保存双方采购理由、共同价值锚点、方向、证据和边界；
- 三个成熟模块均新增并导出稳定的 method/config version；G33 result hash 同时绑定这些版本，版本变化会产生不同结果 hash；
- M12D 下游消费复用正式 `derive_consumption_capabilities` 合同；上游声明的 comparison mode 只能收窄能力，不能被 G33 擅自放宽。

## 4. 多维事实、过程和结论

- 无损保存 `aligned_features`、完整 purchase reason assessments、value assessments、参数/卖点/战场/任务/客群双方事实及差异；
- 量价同时保存总体周均、共同窗口/平台诊断、双方量价、gap、ratio、boundary 和原始计算过程；不要求共同周度或共同平台存在才保留总体量价事实；
- 市场样本 limited/review 时，只允许方向性市场结论并把替代压力市场信号降为 weak；市场未知时不制造市场信号；
- 一侧模块缺失时该维度为 unknown，不填假 0；双方仍有部分事实时只降为 partial；冲突保留为 conflict，并继续保留其他可用维度；
- TV 与 AC 分别覆盖 complete、partial、missing、conflict，不发生 TV/AC 产品形态串线。

## 5. 旧链评分依据

- 上游提供 `LegacyScoreBasis` 时，`competitor_score`、semantic overlap、parameter/claim overlap、sales closeness 和原始 payload 逐字段原样保存；
- 上游没有旧链 basis 时，G33 仅生成确定性兼容审计值，并明确写入 `basis_source=v1_1_compatibility_reconstructed`；该值不冒充旧链原值，后续 G36 接入真实旧链 basis 时可明确区分和替换；
- `recall_rank` 始终由冻结候选事实保留；G33 不生成 G35 的角色、综合排序或重点竞品选择。

## 6. Evidence、Lineage 与确定性

- 同一证据引用合并时无损取 evidence/source file/raw row ID 并集；版本或 confidence 冲突立即失败，不允许后写覆盖前写；
- 顶层 evidence refs、各维度 evidence refs 和 source lineage refs 必须形成完整闭包；缺失引用或孤立引用均失败；
- 相同输入连续计算的 input fingerprint、calculation result hash 和 assembly result hash 一致；输入、成熟计算器版本或中间结果变化会改变对应 hash；
- 20 次 TV 和 AC 重复运行均只有 1 个唯一 hash：TV 平均 18.628 ms、最大 71.971 ms、JSON 504,129 bytes；AC 平均 19.095 ms、最大 77.087 ms、JSON 530,254 bytes；这是单 pair G33 基准，完整 profile 的预算验收仍按调度集中在 G39。

## 7. 测试与独立复核

- G33 专项测试：22 passed；覆盖 TV/AC complete/partial/missing/conflict、未评估锚点、声明能力上限、有限/未知市场、证据闭包、证据合并冲突、身份/hash guard、旧 basis 原样保留和确定性；
- 成熟锚点、pair feature、量价、购买池、G33、Repository、Schema、G32、价值替代、购买压力和替代压力受影响回归：161 passed；
- G33 核心模块覆盖率：710 statements、51 missing、93%；
- Ruff、Python compile、`git diff --check`：passed；
- 独立复核中发现并修复：未评估锚点误入购买压力、有限市场信号过强、重复证据覆盖、购买压力结论矛盾、上游能力被放宽、Assembler 未重验 calculation hash；
- 终审无未关闭问题：P0=0、P1=0、P2=0。

## 8. 写入与运行边界

- 业务数据库读取或写入：0；
- 205 访问、部署或 migration：0；
- profile/relation/selection/重点竞品生成：0；
- G34—G38 代码修改：0；
- 旧 M12/M13/M14 或 V1 草稿修改：0；
- review/publish/current/deprecated 状态切换：0；
- 外部 LLM、网络分析调用、飞书消息/卡片/报告/文档：0；
- git stage/commit：0；
- 用户其他未跟踪文件未暂存、未删除、未覆盖。

## 9. 本 Goal 文件

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_v1_1_pair_analysis.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_v1_1_schemas.py`（购买压力 typed 合同补齐）；
- `apps/api-server/app/services/core3_real_data/analyst/anchor_substitutability.py`；
- `apps/api-server/app/services/core3_real_data/analyst/replacement_pressure.py`；
- `apps/api-server/app/services/core3_real_data/analyst/purchase_pressure_comparison.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_v1_1_pair_analysis.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_v1_1_schemas.py`（fixture 合同补齐）；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_v1_1_repository.py`（fixture 合同补齐）；
- 本关闭回执与串行 Goal 调度状态。

## 10. 下一 Goal

G34：重构候选和关系门槛。只允许五类 hard scope error 全局排除，把 scope、dimension availability、conclusion strength 和 review overlay 四轴分离；局部缺失、authority/review/taxonomy/lineage/conflict 不得再让候选从其他可比较维度消失。
