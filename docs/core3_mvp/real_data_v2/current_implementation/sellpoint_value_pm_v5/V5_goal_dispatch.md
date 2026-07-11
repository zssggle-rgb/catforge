# 用户卖点价值分析 V5 串行 Goal 与 10 分钟定时器调度

状态：G00 执行中

授权：用户已明确批准需求落盘、开发、提交和 205 重跑验证

## 1. 统一调度合同

任何时刻只允许一个 active Goal。每个 Goal：

1. 使用 `create_goal` 创建独立目标，不设置 token budget；
2. 创建独立 10 分钟 heartbeat 定时器；
3. 只推进当前 Goal，不偷做下一 Goal；
4. 维护 `Gxx_progress.md`；
5. 使用精确文件列表 stage 和独立 commit；
6. 生成 `Gxx_artifact_manifest.json` 与 `Gxx_closure_receipt.md`；
7. 删除当前定时器后才 `update_goal(complete)`；
8. 前置门禁通过后创建下一 Goal 和新定时器；
9. 同一阻塞连续三次且无法继续时才标记 blocked；
10. 用户停止时立即停止当前执行和定时器。

当前工作区存在大量 M12D 质量修复和其他未提交改动。全链禁止 `git add .`、`git reset --hard`、`git clean`，禁止覆盖无关文件。每次开始、关闭记录 `git status --short`。

## 2. 任务链

| Goal | 唯一目标 | 主要产物 | 关闭门禁 |
| --- | --- | --- | --- |
| V5-G00 | 冻结修改需求、设计、验收和调度 | 本目录 4 份合同 + 回执 | 文档一致、独立提交、不改运行代码 |
| V5-G01 | 真实数据覆盖基准和 Gold Set | 覆盖矩阵、cohort、65E7Q 快照、hash | 205 只读复核，每种方法有可用/降级样本 |
| V5-G02 | 冻结 typed schema、方法配置和测试计划 | schema、算法合同、追溯、性能计划 | 方法/工程/PM 审查无 P0/P1 |
| V5-G03 | 实现多层反事实 resolver | direct/pool/ladder/tier/realization/own-curve | 覆盖率、确定性、无 M14 fallback 可用 |
| V5-G04 | 实现市场合成基线和高低绩效组合 | synthetic control、archetype、诊断 | 平衡/placebo/稳定性/合成数据通过 |
| V5-G05 | 实现战场组合优化 | existing strengthening、excluded expansion | entered/excluded 正确，挤占边界完整 |
| V5-G06 | 实现价格、销量、分配、WTP 和净新增分账 | realization DTO、严格门禁、cannibalization | 不越级、不伪金额、M11D 不作增量 |
| V5-G07 | 实现 PM 输出和显式入口 | JSON/短答/Markdown/飞书/卡片/CLI | 三分钟可读、跨载体一致、flag off |
| V5-G08 | 综合验收、提交 RC、205 重跑和回滚 | 测试审查、RC、205 报告、回滚回执 | 真实 cohort 双跑、V2/V4 回归、健康只读 |

默认路由切换不属于本链。保留 `V5-G10` 名称给未来单独授权的 canary，不自动创建。

## 3. V5-G00

允许：仅新增 `sellpoint_value_pm_v5/` 文档。

禁止：运行代码、数据库写入、205 修改。
验收：需求、设计、验收、调度互相一致；记录只读可行性快照；独立提交和关闭回执。

## 4. V5-G01

目标：把 G00 探索数字变成可重放证据。

必须完成：

- requirement -> source/table/field/version/quality 矩阵；
- 377 TV SKU 多层反事实覆盖统计；
- direct、budget、brand ladder、param tier、same-claim realization、own curve、synthetic donor coverage；
- battlefield entered/excluded/reachable 分布；
- 合成基线和高低绩效所需字段缺失审计；
- 65E7Q 脱敏快照；
- Gold Set cohort manifest/hash；
- 只读 205 命令、结果和时间戳。

只读，不写运行代码和 205。

## 5. V5-G02

目标：在实现前冻结：

- Pydantic schema/enums；
- counterfactual selection config；
- synthetic balance/placebo/stability config；
- performance residual/archetype config；
- battlefield portfolio state machine；
- price/volume/allocation/net increment contracts；
- highlight and PM DTO rules；
- unit/integration/fixture/performance/query plan；
- requirement traceability。

若真实数据不支持某方法，必须删减/降级需求并留痕，不通过实现技巧填造。

## 6. V5-G03

目标：实现统一 resolver，来源召回与角色判定分离。

关键门禁：

- M14 为空时仍可构造多数 SKU 的 fallback；
- unknown 不当作无卖点/base；
- 同输入候选顺序和 hash 稳定；
- 65E7Q 至少返回多个可解释方法层；
- 不生成市场合成增量或 PM 文案。

## 7. V5-G04

目标：实现透明市场合成和高/低绩效原型。

关键门禁：

- 合成数据能恢复已知方向，失衡/无重叠/placebo 失败正确阻断；
- donor 权重、有效样本、balance 和敏感性可审计；
- residual 采用 out-of-fold 或时间隔离，避免在样本内制造亮点；
- 组合富集不升级为单项因果；
- 不修改战场或上游画像。

## 8. V5-G05

目标：实现 battlefield portfolio optimizer。

关键门禁：

- main/secondary/opportunity/user-observed 全部归 existing；
- expansion 仅接收 excluded；
- communication/capability/market/priority/cap 路径确定性；
- 市场空间、当前分配、观察性潜力和挤占分离；
- 65E7Q 护眼类角色上限案例正确。

## 9. V5-G06

目标：实现五笔互不混淆的量化合同：

1. 用户价值/相对强度；
2. 整机价格承接；
3. 销量/份额承接；
4. M11D 当前战场分配；
5. 观察性 gross、cannibalization、net 和严格组合价格区间。

门禁失败必须 null，不允许 0 或固定建议替代。

## 10. V5-G07

目标：实现唯一 PM DTO 和所有载体。

必须包含：

- 决策摘要；
- 用户价值账；
- 市场合成基线和高/低绩效组合；
- 已有战场增强 vs 新战场拓展；
- 证据边界；
- 分析依据与用户选择对比双链接。

默认 flag off，无 flag 在 DB 查询前拒绝；自然语言默认路由保持 V2。

## 11. V5-G08

分两段但属于一个完整 Goal：

### 本地门禁

- 全量相关测试、覆盖、compile/lint/diff check；
- Gold Set 重放和 fixture hash；
- 性能、内存、query count；
- 方法、工程、PM 语言独立审查；
- 无 P0/P1 后形成不可变 RC。

### 205 默认关闭验收

- 精确部署 RC，保存 checksum 和 rollback package；
- health/ready；
- 65E7Q 与所有 cohort 双跑；
- JSON/短答/Markdown/飞书/卡片回读；
- 并发、资源、SQL/DB 只读；
- V2/V4 线上回归；
- 回滚演练。

失败立即回滚，不进入默认路由。

## 12. 当前调度状态

- active Goal：V5-G00；
- heartbeat：`catforge-v5-g00-10`；
- 周期：10 分钟；
- 当前允许路径：本目录；
- 下一 Goal：V5-G01，仅在 G00 commit、timer 删除、Goal complete 后创建。
