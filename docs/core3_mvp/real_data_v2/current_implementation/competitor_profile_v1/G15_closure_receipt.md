# 竞品画像 V1 G15 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_purchase_pool_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_purchase_pool.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_purchase_pool.py`。

## 2. 研究过的现有模式

实现前对照了四类既有模式：

1. G03 方法合同 §5.1—§6：购买池四门槛、P0/P1/P2/P3/unknown 定义、通用价值与门槛功能过滤；
2. G04 detailed design §5.4 与基础 `PurchasePoolAssessment`/`GateResult`：沿用每个 gate 的 known/pass/reason/evidence 和 unknown 不等于 false；
3. `competitor_profile_candidate_recall._shared_semantics`：沿用主战场、当前战场、机会战场和共同任务按稳定 code 对齐的方式，但不沿用召回即关系成立；
4. `claim_value_pm_v5_service._target_battlefield_memberships`：沿用 primary/secondary/opportunity/user_observed/drag 角色归一和角色优先级概念，拖累只接受上游明确角色。

## 3. 已实现的购买池合同

每个 G14 pair 严格评估四个必要门槛：

1. 品类与产品形态兼容；
2. 尺寸/能力段对目标任务可替代；
3. 预算对用户可达；
4. 至少一项用户任务或区分性价值场景重合。

输出规则：

- P0：同形态、同尺寸/能力段、同预算、共享核心任务，并共享已被 taxonomy 与覆盖率共同支持的区分性当前价值；
- P1：同形态、同尺寸/能力段、同/相邻预算、共享核心任务，但双方当前价值路线明确不同；
- P2：形态或尺寸/能力段不同，但共享核心场景任务且预算可达；
- P3：数据已知但只足以做市场参照，不允许写成用户会二选一；
- unknown：任一必要 gate 未知，gate 的 `passed=None`，不写 false。

## 4. 主/辅/机会/拖累语义

- 每个 battlefield code 分别保存 target/candidate 的 primary、secondary、opportunity、user_observed、drag 角色；
- 输出共享主战场、共享当前战场、当前与机会相邻、共享机会、单边角色和角色冲突；
- taxonomy 标记 generic/table-stake 或 serving scope 覆盖率达到阈值的价值只能 supporting；
- taxonomy 声明区分性但覆盖率缺失时仍只 supporting，不能反推为区分性；
- 只有区分性且形成正向当前/相邻重合的 code 才支持购买池价值门槛；
- 双方都只是 opportunity 不支持 P0；
- drag 只来自 M11D 或带明确 battlefield context 的 M12C 上游角色；缺失、对方更强或单边无值均不会生成拖累；
- 同一 code 同时出现正向与 drag 角色时标记 review_required，不自动裁决。

## 5. 品类和量价边界

- TV 产品形态在同品类内兼容，尺寸/尺寸段单独判断；
- AC 先判断挂机/柜机等形态，再判断能力段；跨形态只有共享核心场景任务时可进入 P2；
- 同预算与相邻预算阈值由品类 config version 管理；边界值按包含处理；
- 双方价格必须为已知正数，零价或缺失价使预算 gate=unknown；
- 本 Goal 不读取销量表现、不判断量价压力、不计算 WTP 或因果销量。

## 6. 追溯与确定性

- 输入只允许 G14 `PairFeatureBundle` 与显式版本化品类配置；
- pair、battlefield code、battlefield summary、purchase pool 和 bundle 均保存 input fingerprint/result hash；
- taxonomy、覆盖率、阈值、config version 或受保护 pair fact 变化都会改变结果 hash；
- 输入顺序变化不改变业务 hash；
- 每个 G14 candidate 一对一保留，无数据库查询和候选截断；
- pair 证据只保留 M03B/M07/M09C/M11C/M11D/M12C 中实际支持形态、尺寸/能力、预算、任务和战场判断的 exact refs；
- 非 G15 模块的 review 状态不污染购买池置信度。

## 7. 验证

- G15 schema/service tests：15 passed；
- G05—G15 schema/migration/repository/lifecycle/input/recall/eligibility/determinism/performance/pair feature/purchase pool：151 passed；
- G15 service + schema coverage：89%；
- P0/P1/P2/P3/unknown：通过；
- TV/AC、同形态/跨形态、同段/跨段：通过；
- 同预算/相邻预算边界、零价：通过；
- 主/辅/机会/拖累、角色冲突：通过；
- generic/table-stake、高覆盖率、覆盖率未知：通过；
- sparse/missing、review/lineage、候选守恒：通过；
- 输入顺序、config/fact hash 变化：通过；
- 无数据库、repository、SQLAlchemy、外部 LLM 和正式关系依赖：通过；
- Ruff、format check、compileall：通过。

本地事实烟测：4 个 TV candidate 分别得到 P0、P3、P1、unknown；候选数与 G14 完全一致。

## 8. 状态变化

- 本地数据库写入：无；
- 205 连接、数据库写入和 migration：无；
- 画像 materialize、review/publish/current/deprecated：均未执行；
- G16 采购理由/用户价值替代、G17 量价压力、G18 正式关系、G19 重点选择：均未实现；
- 部署：无；
- Git 暂存/提交：无。

## 9. 下一 Goal

允许创建 G16，只基于 G14 pair facts、G15 purchase pool 和锁定 M12C/M12D 事实实现采购理由与用户价值替代判断；不得临时生成采购理由，不得实现量价压力、七类正式竞品关系、重点选择、画像持久化、205 写入、部署或 Git 提交。
