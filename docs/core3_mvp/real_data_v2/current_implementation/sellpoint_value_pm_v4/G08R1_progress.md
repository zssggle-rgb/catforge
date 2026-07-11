# G08R1 核心合同修复与重新验收进度

- Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`
- Goal 状态：`in_progress`
- 定时器：`catforge-v4-g08r1-10`
- 前置 G08 artifact commit：`b54418e`
- 前置 G08 closure commit：`2a985f8`
- 允许修改：G02 repair addendum、V4 repository/schema/service/answer、V4 tests、G08R1 回执
- 禁止事项：数据库/205 连接或写入、部署、默认路由切换、G09 RC、消费 M12C 旧金额、把 M11D allocation 当购买归因

## 当前门禁

| 门禁 | 状态 |
| --- | --- |
| Repair contract 与测试矩阵 | completed |
| Lineage/hash deterministic repair | completed |
| Candidate recall/snapshot/per-role repair | completed |
| Market-cell bounded trim 与 M11D sample weight | completed |
| Q5 config v2 + deterministic cluster bootstrap | completed |
| Pure negative / mixed / data conflict 分离 | completed |
| Frozen cohort/hash 真回放 | completed |
| 309+ 回归、覆盖率、性能和三审 | in_progress |

## 停止条件

1. 任何修复需要消费 M12C 旧金额或把 M11D allocation 解释成真实选择归因时停止；
2. bootstrap 不能在相同输入下确定性复现时 Q5 保持不可用；
3. typed contract 修改不能向 V2 泄漏；
4. 相关回归、性能或 PM 语义任一未通过时 G09 继续禁止；
5. 不触碰工作区现有无关 M12D 质量修复。

## 当前结果

- Repair contract 和测试矩阵已冻结；
- 同版本/同批次必须同时匹配 source hash，缺 hash 为 unresolved，不同 hash 为局部 conflict；
- authority evidence refs 在 hash 前确定性排序；
- M14/fallback recall cap 提升到 30，按 declared role 轮转选择最多 12 个 snapshot；
- 完成实际角色和可比性判断后，每个 computed role 最多保留 3 个；
- 新增 same-version hash drift、authority order、rank-4 role coverage、per-role cap 回归；
- 定向 schema/context/counterfactual：33 passed；
- repository 全文件仍有 7 个 V4 前 Ruff 基线问题，新增 V4 diff 未引入新 lint 问题。
- weekly query 现在 DB 侧最多读取 2,001 行；超限时丢弃可能不完整的边界 group，再按最新完整周/平台/渠道 group 保留 <=2,000 行；
- 超限写入 M07 authority warning，PM limitation 明示裁剪，Q5 金额 blocked，但描述性 choice 可保留；
- pair 的真实 target/candidate 销量和 share 不变，observation weight 使用总销量乘 target/candidate allocation 的保守最小解释权重；缺失权重显式记录 limitation；
- 新增完整 group 裁剪、truncation 阻断金额和 allocation sample-weight 边界测试；context/counterfactual/quantification/answer 56 passed。
- ValueStatus 已改为 established/partial/negative/mixed/not_observed；lineage/data conflict 继续由 LineageGate/LinkStatus 表达；
- pure negative 输出“用户实际获得的是负向体验”，positive+negative 输出“不同用户或场景体验分化”，两者均不能进入 Q1+ 或金额；
- pure negative、mixed 和 data conflict 跨报告语义测试通过；schema/linkage/quantification/answer 55 passed。
- Q5 method config 已升级到 v2；每个 pair 运行 200 次确定性 week-cluster bootstrap，并与 leave-one-week-out 形成联合 crossing 稳定性门禁；
- 多 pair 计算质量权重和 weighted median center，金额区间由 pair point、LOO、bootstrap P10/P90 组成联合保守包络；
- available WTP schema 强制要求两个 stable bootstrap pair、完整 sensitivity keys，且区间必须包含 weighted center；v1 结果不能冒充 v2；
- bootstrap seed 只来自 input hash、relation hash、candidate SKU 和 config version，同输入完整结果相同；bootstrap 不稳时金额为空；
- 市场空间主表新增尺寸档、观察窗口和实际平台覆盖；schema/service 过时阶段说明已修正；
- G08R1 schema contract addendum 已落盘；V4 全量 87 passed，新增/修改 V4 文件 Ruff passed。
- 新增 frozen cohort 专属测试，先用 G01 artifact manifest 校验整个 cohort manifest SHA-256，再逐条消费实际 SKU、尺寸、战场、参数档位、时间周数和版本字段；
- C01 candidate-only、C02 same-value-only、C03 bundle-only、C04 single-week、C05 version conflict 均按 frozen payload 回放；不再用只核对 ID 后另造无关样例冒充回放；
- pending SessionLocal entity 在 V4 查询后仍保持 unflushed，SQL 仍只有 SELECT/PRAGMA，read-only 运行边界有显式回归；
- frozen cohort + counterfactual + quantification 39 passed；context 12 passed。
- 相关回归分组完整退出：V4+V2 122、analyst CLI 88、M11C/M11D/M12C 43、M12D/reader 71，合计 324 passed；
- V4 92 tests，schema/service/answer coverage 93%；10,000 rows peak 25.413MB，Q5 report P95 0.016519s，65E7Q-like P95 0.000490s，Markdown P95 0.000076s；
- G02-G08 artifact commit hash 全匹配；G01 发现历史 pointer 指向 core commit、但 progress hash 来自 closure commit，已把 artifact_commit 纠正为四项均匹配的 `6c3525c`；
- PM 主表现显示“尺寸档、观察窗口、实际平台；市场空间”，并去除“已感知/已观察到”的重复表达。
