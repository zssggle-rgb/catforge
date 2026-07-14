# 竞品画像 V1 G11 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_candidate_eligibility_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_candidate_eligibility.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_candidate_eligibility.py`。

## 2. 研究过的现有模式

实现前对照了三类已有资格与可用性模式：

1. `competitor_profile_schemas.py`：复用 `CandidateStatus`、八类 `QuestionCode`、七类 `ReferencePurpose`、五个独立证据族和七类关系枚举；明确最终 `QuestionEligibility` 依赖已完成的关系结果，因此 G11 新增的是 pre-relation provisional DTO，不冒充最终可回答性；
2. `sellpoint_value_profile_candidate_service.py`：复用候选状态分区、review/blocked 隔离和确定性输出经验；拒绝沿用其对旧 M12/M13/M14 availability/status 的依赖；
3. `COMPETITOR_PROFILE_V1_method_contract.md` 与 `COMPETITOR_PROFILE_V1_detailed_design.md`：按八个产品经理问题保存缺口，按七类 reference purpose 保存分析用途；遵守 unknown 不等于不存在、reference 不等于竞品、关系评估必须在 G18 完成的阶段边界。

## 3. 已实现的三层分离

- `relation_evaluation_member=true` 只表示该候选具有进入 G18 正式关系评估的输入条件；
- `reference_member=true` 只表示该 SKU 可承担一种或多种分析参照用途；
- `competitor_member` 在 G11 固定为 `false`，不得在七类关系评估前声称正式竞品关系成立；
- 同一 SKU 可以同时进入关系评估集合和 reference 集合，但两个 membership 与用途分字段保存；
- 不满足关系评估条件但有明确参照用途的候选保存为 `reference_only`；只有召回事实、尚不足以评估或参照的候选保存为 `recalled_only`；
- lineage 冲突保存为 `blocked`，上游 review/processing 异常保存为 `review_required`，二者均不能驱动关系或 reference 结论。

## 4. 资格与 reference 规则

- 资格只消费 G09 exact-authority category/target bundle 与 G10 完整 recall manifest，不访问数据库；
- 同购买池/同品牌梯度还必须有语义证据；升降档还必须有已知量价、形态兼容和非纯客群语义；场景与同价值入口必须有多个独立语义证据族；
- 单一同尺寸、同预算、同品牌、同任务、同战场或共享锚点不会被写成正式竞品，G11 也不会生成 relation passed/failed；
- reference 映射覆盖：明确缺少该价值的市场基线、高绩效价值组合、低绩效价值组合、参数档位、相邻价值战场、同价值兑现和量价 archetype；
- “没有该价值”的市场基线必须有 target claim 与 candidate 明确 absence role 对应；候选 M12C 缺失时保持 unknown，不把缺失推断成没有；
- 高低绩效价值组合使用 G10 锁定的市场表现比阈值；参数档位只比较双方均已知且值不同的参数；量价 archetype 要求双方价格和周均量均已知。

## 5. 八个产品经理问题的 provisional 状态

每个候选完整保存以下八个问题：购买选择、量价压力、价值替代、配置跟随、同品牌产品线角色、场景方案、价格梯度防守和重点竞品选择。

每个问题保存：

- `provisional_eligible`、`provisional_limited` 或 `unavailable`；
- 待评估的关系类型；
- 所需与已具备的证据族；
- 缺失输入和原因代码；
- `can_drive_business_conclusion=false`。

重点竞品选择在 G11 最高只能是 `provisional_limited`，并明确缺少 `completed_relation_assessments`；只有 G18 完成关系、G19 完成选择后才能形成正式结果。

## 6. 确定性与追溯

- exact authority scope、target、category/target fingerprint 和 recall manifest 不一致时 fail closed；
- 每条 recall fact 的 target/candidate evidence ref 均回查 G09 内存 bundle，ref 不存在、SKU 归属错误、证据集合不一致或显式 lineage conflict 时阻断；
- 输入、候选、八个问题和完整 eligibility manifest 均生成稳定 fingerprint/hash；
- 候选按 SKU、枚举/原因/证据按稳定顺序保存，全部 recalled candidate 一对一守恒，无截断、无丢弃、无重复。

## 7. 验证

- G11 eligibility/schema tests：10 passed；
- G05—G11 schema/migration/repository/lifecycle/input/recall/eligibility：103 passed；
- G11 service + schema coverage：92%；
- 样例 4 个 recalled candidate 全部守恒：3 个可进入正式关系评估、4 个具有 reference 用途，其中 1 个为纯 reference；正式 `competitor_member` 全部为 false；
- 七类 ReferencePurpose 全覆盖：通过；
- 八个问题全覆盖且均不能提前驱动业务结论：通过；
- 单一同品牌/同预算、单一共同任务不升级：通过；
- TV/AC 形态规则、unknown、review_required、lineage blocked、空 manifest：通过；
- 输入语义 list 顺序反转后 manifest 与候选 result hash 不变：通过；
- classifier 源码无 SQLAlchemy、repository 或 query 依赖：通过；
- Ruff、`git diff --check` 和编译检查：通过。

## 8. 状态变化

- 本地业务数据库写入：无；
- 205 连接/数据库写入/migration：无；
- 画像生成、review/publish/current/deprecated：均未执行；
- 七类正式关系 passed/limited/failed、pair 特征、量价计算、总分排序和重点竞品选择：均未实现；
- 部署：无；
- Git 暂存/提交：无。

## 9. 下一 Goal

允许创建 G12，只实现 G10 recall 与 G11 eligibility 产物的顺序无关规范化、去重、幂等 hash 和重复输入防护；不得实现 G14 pair 特征、G15—G18 关系判断、G19 重点选择、画像持久化、205 写入、部署或 Git 提交。
