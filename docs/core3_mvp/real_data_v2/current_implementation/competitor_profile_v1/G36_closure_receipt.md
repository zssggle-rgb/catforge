# G36 竞品画像 V1.1 Materializer/Generation 关闭回执

状态：completed

日期：2026-07-16

## 1. Goal

在不连接或写入业务数据库、不访问 205、不修改 G37 Adapter、G38 智能体、旧 M12/M13/M14、V1 草稿或旧 V1 默认行为、不执行 review/publish/current 的前提下，将 G32 共享 SKU snapshot、G33 PairAnalysisAssembly、G34 PairGateEvaluation 和 G35 CompetitorSelectionResult 无损组装为完整 V1.1 draft DTO，并提供单 SKU、batch、幂等、失败隔离、checkpoint/resume 和 G31 Repository 持久化适配。

## 2. 纯 Materializer 边界

- 新增 `CompetitorProfileV11Materializer`，入口只接受已完成计算的 G32—G35 typed 输出；
- materializer 不持有 provider、repository、DB session、calculator、gate evaluator 或 selector；
- 测试对 `PairAnalysisCalculator.calculate`、`PairGateEvaluator.evaluate` 和 `CompetitorProfileV11Selector.select` 设置 fail-fast spy，materializer 调用数均为 0；
- 逐项重验 G32 snapshot ref/result hash、G33 assembly hash、G34 scope/gate hash、G35 pair decision/priority/top-level hash 和 project/category/version/release/target/candidate/snapshot authority；
- target/candidate 只保存 snapshot ref，DTO 中复用版本内共享 snapshot；pair 内不复制完整 SKU snapshot JSON。

## 3. 无损 Pair、选择和 Summary

- 每个 analyzable pair 保存完整六维、价值锚点、替代压力、购买压力、市场验证、七类关系、八类产品问题、dimension gate、review overlay、证据、限制和完整 G33 过程 envelope；
- 每个 pair 保存 G35 `selection_assessment`，无论是否进入重点名单均保留 eligibility、选择名次、未入选原因、市场强度、legacy rank/role 和 pair selection hash；
- hard-excluded self pair 以共享 target snapshot 保存，不伪造任何分析、得分、关系或问题结论；
- SKU summary 保存全候选数、analyzable/excluded 分解、维度 availability、结论强度、角色桶、问题级 findings、review/limitations 和 `retained|added|dropped` 旧 Top3 diff；
- priority selection 显式绑定最终 pair hash 和 G35 pair selection hash；候选全集与 full pair index 完全一致，不截断未选候选。

## 4. 零六维市场候选边界

- G35 已支持仅有市场量价结论的候选进入重点选择；G36 保持 pair `ranking_score=null`、`available_weight=0`，selection `selection_score=0`，不把未知六维伪造成零分；
- 修正 G31 compact integrity 校验：pair header 继续保存 null 分数，selection row 保存 0；Reader 按这一明确边界核对，不再错误要求二者数值相等；
- Repository pair 行保存 G35 的真实未入选原因，不再统一降级成 `not_priority_selected`；
- 对上述 null/0 边界增加独立 compact readback 单元测试。

## 5. Fact/Evidence 闭包

- 为 G34 dimension result 生成 typed derived fact，使关系、问题和总结果的 supporting fact refs 均能解析到正式 fact index；
- 同一稳定 fact ID 在共享快照不同结构中的合法复用按 identity 合并；同 ID 不同 code/source path 仍 fail closed；
- fact index 合并同一事实的全部 evidence keys，evidence index 按规范化 EvidenceRef 去重和 hash；
- summary finding 只引用其 supporting dimension facts 对应的证据，不再挂整条 pair 的宽泛证据集合。

## 6. Generation 与持久化

- 新增单 SKU `generate_draft`：相同 typed DTO 返回 reused，不同结果要求新 profile version，禁止原地覆盖；
- 新增 batch：按 SKU 确定顺序执行，单 SKU 异常隔离，其他 SKU 继续生成；
- checkpoint 保存 completed result hash、work-item input fingerprint、failure code 和最后 SKU；resume 只有在输入指纹和已保存 result hash 同时一致时才跳过；输入已变化时重新校验并按 immutable 规则失败，不会误复用旧结果；
- 提供 in-memory store 供确定性测试，以及带 commit/rollback 的 G31 Repository store adapter；不包含 publish/current/review 状态切换；
- batch/checkpoint/result 均有稳定 hash，重跑输入顺序不改变画像结果。

## 7. 65E7Q、TV/AC 与边界验收

- 使用目标 SKU `TV00029112 / 海信 65E7Q` 的 20 候选等价 fixture 跑通完整 G32—G36 链；candidate snapshots、pair analyses 和 full pair index 均为 20，差集 0，priority 不超过 3；
- TV 与 AC 分别通过完整 materialization；
- market-only、self-pair hard exclusion、单 SKU idempotency、不同结果不覆盖、单 SKU 失败隔离、checkpoint/resume、变化输入不误 skip、Repository commit/rollback 均通过；
- materializer 对篡改后的 G32 snapshot 和 G35 decision hash 均 fail closed。

## 8. 测试与独立复核

- G36 专项测试：12 passed；
- V1.1 schema、Repository、snapshot、pair、gate、selection 与 G36 受影响回归：157 passed；
- G36 materializer/generation coverage：435 statements、36 missing、92%；
- Ruff、Python compile、whitespace check：passed；
- 独立复核发现并修复：checkpoint 只按旧 result hash 跳过导致同版本变化输入可能被误复用；Repository compact 校验错误要求 market-only pair null 分数等于 selection 0；materializer 未重验 G32 snapshot hash；summary finding 证据范围过宽；
- 终审无未关闭问题：P0=0、P1=0、P2=0。

## 9. 写入与运行边界

- 业务数据库读取或写入：0；
- 205 访问、部署或 migration：0；
- V1.1 draft 实际生成或持久化：0；仅使用 test fixture、mock 与 in-memory store；
- G37 Adapter、G38 智能体修改：0；
- 旧 M12/M13/M14、V1 草稿或旧 V1 默认行为修改：0；
- review/publish/current/deprecated 状态切换：0；
- 外部 LLM、网络分析调用、飞书消息/卡片/报告/文档：0；
- git stage/commit：0；
- 用户其他未跟踪文件未暂存、未删除、未覆盖。

## 10. 本 Goal 文件

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_v1_1_materializer.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_v1_1_generation.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_v1_1_schemas.py` 的 G36 typed persistence 兼容扩展；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_v1_1_selection.py` 的只校验不重算 hash 入口；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_v1_1_repositories.py` 的 null-score compact/readback 和未入选原因兼容修复；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_v1_1_materializer_generation.py`；
- 本关闭回执与串行 Goal 调度状态。

## 11. 下一 Goal

G37：实现 `CompetitorProfileAgentAdapter` 和 `render_competitor_answer_from_profile()` 纯展示入口，只把已保存的 V1.1 DTO 映射成现有竞品分析业务结构；不得访问 DB session、AtomicHandlers、原始上游 provider 或任何 calculator/gate/selector，不得重新打分、定角色、排序或选择。
