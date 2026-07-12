# M12D 购买理由成立度与购买阻力分层开发任务

日期：`2026-07-11`

## 1. 总目标

完成 TV/AC 购买理由成立度、购买阻力、产品价值主张和用户承接分层改造，并让竞品智能体按 SKU、按维度消费，不再用普通负面删除购买理由或用版本覆盖率统一降级全部 SKU。

## 2. 总体规则

1. 每个任务使用独立 goal，只完成一个模块闭环。
2. 共享逻辑必须在同一 goal 内同时审计和验证 TV/AC。
3. 不跨任务提前实现后续模块。
4. 不把 M12D 生产逻辑写进竞品智能体。
5. 每个任务记录 TV/AC 影响集合、允许迁移和至少 20 个未影响回归 SKU。
6. 不降低到 7 分以下，不加入 SKU/品牌白名单。
7. 代码提交、migration 和部署按任务门槛直接执行；正式全量重跑和切换 current/published 仍需明确发布批准。

## 3. 任务总览

| 序号 | 任务 | 状态 | 内容 | 前置 |
| ---: | --- | --- | --- | --- |
| 1 | M12D-RP-G01 | completed | TV/AC 双品类基线、证据分层审计和 Gold/反例样本 | 无 |
| 2 | M12D-RP-G02 | completed | Typed contract、schema、migration 和兼容读取 | G01 |
| 3 | M12D-RP-G03 | completed | 购买阻力独立计算和负面证据作用域 | G02 |
| 4 | M12D-RP-G04 | completed | 产品价值主张、用户承接和 9/8/7 成立门槛 | G03 |
| 5 | M12D-RP-G05 | completed | 锚点角色、SKU 状态、版本质量和按 SKU 消费 | G04 |
| 6 | M12D-RP-G06 | completed | TV/AC 全量 shadow、业务抽检和发布门槛复算 | G05 |
| 7 | M12D-RP-G07 | completed | 竞品智能体消费、Top 3 和报告业务语言回归 | G06 |
| 8 | M12D-RP-G08 | completed | 跨品类集成验收、QF15 回填和上线前结论 | G07 |
| 9 | M12D-RP-G09 | completed | 提交并部署代码/migration 到 205 | G08 |
| 10 | M12D-RP-G10 | pending | 205 全量重跑、分品类发布和线上验收 | G09；需用户批准 |

## 4. 任务明细

### M12D-RP-G01 双品类基线与验收样本

- 只读重算 TV/AC 当前发布和 QF15 draft 口径。
- 分别统计普通评论冲突、负面占主导、M12C 负向、产品价值主张、用户承接和评论错维度。
- TV 复核 QF15A 139 个无核心 SKU，并将旧 `37/29/29` 作为待验证基准；不得为对齐旧估计调整全量审计结果。
- AC 按本品类 taxonomy 生成同类分布，不使用 TV 数字作目标。
- 建立正例、局部负面、负面占主导、事实证伪、proposition_only 和跨维度错配样本。
- 产物：双品类 JSON/CSV/Markdown 基线和验收 fixture。
- 验收：只读表不变；样本证据可追溯；至少 20 个未影响 SKU/品类。

### M12D-RP-G02 Typed Contract 和兼容层

- 新增成立状态、用户承接、核心资格、压力等级、压力标签和比较限制 schema。
- 设计并实现兼容 migration；历史版本读取为 unassessed，不猜测新语义。
- 新增正例、非法枚举、缺字段兼容和 export boundary 测试。
- 不实现具体压力和成立算法。

### M12D-RP-G03 购买阻力独立计算

- 将 M05C 普通冲突、混合评价、负面占主导和 M12C 负向映射为锚点级压力。
- 普通负面不修改成立分；事实证伪和证据错配保留阻断能力。
- 市场样本不足只形成比较限制，不删除用户/事实已成立理由。
- TV/AC 分别验证同锚点作用域，未引用 claim/comment 不扩散。
- 输出压力分布、迁移和原始证据样例。

### M12D-RP-G04 产品价值主张与用户购买理由

- 实现 proposition_only、user_supported、market_supported、user_validated。
- 评论域必须命中当前锚点的同维度正向事实。
- 实现 9 分标准、8 分无核心兜底和 7 分理由专属兜底；低于 7 分禁止核心。
- TV 固化大屏、价格、画质、游戏边界；AC 固化独立理由边界。
- 家庭操作和家装适配只有产品事实时保持 proposition_only。

### M12D-RP-G05 画像、发布质量和消费契约

- 更新角色收敛、画像置信度和 SKU 状态。
- 核心理由和压力并行输出；高压力不得无声删除理由。
- `limited` 版本内的 ready SKU 按 ready 消费；版本状态不覆盖 SKU 状态。
- proposition_only SKU 可消费事实和产品意图，但不能形成强购买理由替代结论。
- 更新 repository、reader、CLI 和 contract fixture。

### M12D-RP-G06 TV/AC 全量 Shadow

- 分品类全量只读重跑 context、candidate、establishment、pressure、profile 和 release quality。
- TV 逐项复核 QF15A 139 个 SKU；AC 复核既有重点和负向样本。
- 输出新增/删除核心理由、压力标签、proposition 分布、状态迁移和未影响回归。
- 对每个新增核心理由进行同锚点评论和理由业务边界检查。
- 未达到发布门槛时不得用白名单或跨品类平均继续。

### M12D-RP-G07 竞品智能体回归

- 只消费 G06 fixture，不生成 M12D。
- 购买理由重合度、替代压力和负面压力分别展示。
- 产品价值主张必须表达为“产品希望传达但尚未观察到用户承接”。
- TV 覆盖 65E7Q 和至少 10 个目标 SKU；AC 覆盖至少 10 个柜机/挂机重点 SKU。
- Top 3 变化必须能追溯到成立理由、压力或 SKU 级质量，不得来自版本统一降级。

### M12D-RP-G08 集成验收和 QF15 回填

- 运行 M03B-M12D、竞品 reader、CLI、报告和品类隔离回归。
- 回填 QF15 阻塞结论和 QF16 前置状态。
- 输出 TV/AC 分品类 go/no-go；一个品类通过不能覆盖另一个品类失败。
- 到此暂停并请求提交部署批准。

### M12D-RP-G09 提交部署

- 用户已授权以后同类代码提交与部署无需单独审批；任务达到测试、备份和回滚门槛后直接执行。
- 精确 stage 本任务链文件，提交、部署 migration 和代码到 205，保留回滚点。
- 不执行正式全量发布。

### M12D-RP-G10 全量重跑发布

- 仅在用户明确批准后执行。
- 205 分别重跑 TV/AC；各自达标后分别切换 current。
- 验证 API、竞品智能体、飞书报告和回滚点。

## 5. 停止条件

- 普通负面仍被用作购买理由不存在的唯一依据。
- proposition_only 被输出为用户购买理由。
- 评论错维度仍可贡献 `COMMENT_PERCEPTION`。
- TV/AC taxonomy、门槛或市场池串用。
- 已有 ready SKU 出现无法解释的大规模核心理由变化。
- 需要低于 7 分或白名单才能达到覆盖率。
- G09/G10 到达时未取得用户明确批准。

## 6. 当前指针

```text
COMPLETED: M12D-RP-G01 TV/AC 双品类基线与验收样本。
COMPLETED: M12D-RP-G02 Typed contract 和兼容层。
COMPLETED: M12D-RP-G03 购买阻力独立计算和同锚点证据作用域。
COMPLETED: M12D-RP-G04 产品价值主张、用户承接和 9/8/7 成立门槛。
COMPLETED: M12D-RP-G05 锚点角色、SKU 状态、版本质量和按 SKU 消费。
COMPLETED: M12D-RP-G06 TV/AC 全量 shadow、业务审计和发布门槛复算。
COMPLETED: M12D-RP-G07 竞品智能体消费、Top 3 和报告业务语言回归。
COMPLETED: M12D-RP-G08 跨品类集成验收、QF15/QF16 回填和上线前结论。
PAUSED: M12D-RP-G09 提交部署需要用户明确批准。
```

## 7. M12D-RP-G01 执行记录

- 完成时间：`2026-07-11`。
- 只读范围：TV 当前发布 `377` SKU、AC 当前发布 `155` SKU；同时按当前 QF15 本地代码重建 context、candidate 和现行评分。
- TV 基线：当前无核心 `139`；同锚点正向成立且无普通压力 `18`；成立并有普通压力 `75`；仅产品主张 `17`；负面占主导 `7`；M12C 负向 `163`；评论错维度 `258`。
- AC 基线：当前无核心 `25`；同锚点正向成立且无普通压力 `2`；成立并有普通压力 `12`；仅产品主张 `0`；负面占主导 `4`；M12C 负向 `107`；评论错维度 `143`。
- 旧 TV 估计 `37/29/29` 未通过全量同维度复核；差异来自 M12C 正负角色并存、旧评论冲突码跨维度以及产品主张/用户承接重新分层。该差异不阻塞 G02 schema，但 G03/G04 必须逐项解释，不得将旧数字作为配额。
- 允许迁移：已成立理由可新增局部负面、负面占主导或 M12C 负向标签；普通压力不得删除理由；评论错维度不得贡献成立分；proposition_only 不得升级为用户购买理由。
- 未影响回归：TV `20`、AC `20`；不变量为核心理由有无不变，已有核心不得因普通压力被删除。
- 产物：
  - `scripts/m12d_rp_g01_audit_tv_ac_baseline.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G01_tv_ac_baseline.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G01_tv_ac_baseline.csv`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G01_tv_ac_baseline_report.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G01_acceptance_fixture.json`
- 测试：专用确定性测试 `3 passed`；脚本全量验收通过；三张 M12D 表前后行数和最大更新时间一致。

## 8. M12D-RP-G02 执行记录

- 完成时间：`2026-07-11`。
- 新增共享枚举：成立状态、用户承接状态、压力等级和压力类型；TV/AC 共用字段 contract，但不共用品类理由或阈值。
- 新增 typed schema：压力标签、比较限制、成立/承接/核心资格、产品主张证据和用户承接证据。
- 新增兼容 migration：`0044_core3_m12d_reason_pressure`；profile 4 个字段、anchor 12 个字段；Alembic 保持单 head。
- 历史兼容：缺字段映射为 `unassessed/null/empty`，不猜测为 `rejected/not_observed/none/false/0`。
- downstream export 只新增业务 contract；评分明细、角色推导、指纹和 taxonomy 生成方法继续禁止输出。
- TV 影响集合：377 个 profile、3,542 个 anchor 仅获得兼容默认值；业务结论变化 0；冻结未影响 SKU 20 个。
- AC 影响集合：155 个 profile、1,879 个 anchor 仅获得兼容默认值；业务结论变化 0；冻结未影响 SKU 20 个。
- 产物：
  - `apps/api-server/alembic/versions/0044_core3_m12d_reason_pressure_contract.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_reason_pressure_contract.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G02_contract_fixture.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G02_contract_implementation_report.md`
- 测试：G02 专用 10、M12D 画像/质量 65、竞品 reader 11，合计 `86 passed`；Python 编译、diff check、JSON 和 Alembic head 检查通过。

## 9. M12D-RP-G03 执行记录

- 完成时间：`2026-07-12`。
- 独立压力：M05C 局部负面、反馈分化、负面占主导，M12C 价值承接/价格压力，市场比较限制、事实证伪和证据错配写入 G02 typed contract；不修改旧证据分、角色或画像决策。
- 评论量化：使用 M05C `dimension_summary_json.polarity_counts` 的完整维度分布；展开评论只作为原文和 evidence_id 证据，不再用前 50 条样本外推全量比例。只有维度汇总、没有子维度完整分布时输出比较限制，不伪造子维度比例。
- M12C 作用域：TV/AC 分别维护理由到 claim 的精确映射；`opportunity_gap` 不再误作当前购买阻力，未引用 claim 不扩散。全量角色摘要为每个 claim/role 保留确定性的原始行引用，解决明细前 50 条之外证据不可追溯的问题。
- TV 全量：377 SKU；339 个 SKU、1,921 个锚点命中至少一种压力；压力标签计数为局部负面 749、反馈分化 1,176、负面占主导 31、M12C 价值压力 1,159、市场不确定性 45、证据错配 230。数字是可并存的锚点标签数，不是异常 SKU 数。
- AC 全量：155 SKU；144 个 SKU、1,215 个锚点命中至少一种压力；压力标签计数为局部负面 778、反馈分化 1,062、负面占主导 15、M12C 价值压力 982、市场不确定性 104、证据错配 35。
- 不合常理复核：TV 证据错配 230 中，游戏设备适配和体育流畅各 112 个，来源是旧候选生成把评论域召回到没有游戏/动态评论的锚点；AC 主要为智能控制 11、自清洁 7、柔风人群 7。G03 只做显式错配标记且不改变旧结论，G04 必须据此禁止这些错维度评论贡献用户承接。
- 比较限制：子维度完整分布缺失 TV 1,059、AC 736；这是“不能量化该子维度正负占比”，不删除理由、不降 SKU 状态。M12C 金额不可量化和市场样本限制同样只约束相应比较表达。
- 允许迁移：仅新增 pressure 和 comparison limitation；TV/AC 的旧评分、角色、核心理由、画像状态变化均为 0。未影响回归样本 TV 20、AC 20；无压力样本 TV 20、AC 11。
- 只读证明：三张 M12D 表执行前后行数和最大更新时间一致；无来源压力标签 TV 0、AC 0；未写生产数据库。
- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_pressure.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_pressure.py`
  - `scripts/m12d_rp_g03_shadow_tv_ac_pressure.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G03_tv_ac_pressure_shadow.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G03_tv_ac_pressure_anchors.csv`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G03_tv_ac_pressure_shadow_report.md`
- 测试：G03 专项 16，G02 contract/M12D 画像/质量回归 75，合计 `91 passed`；Python 编译通过；205 TV/AC 全量只读影子验收通过。
- Git/发布：未 stage、未 commit、未 deploy、未 publish。

## 10. M12D-RP-G04 执行记录

- 完成时间：`2026-07-12`。
- 新增 `ReasonEstablishmentScorer` 和 `UserValidationClassifier`：分别计算正向成立分与 `user_validated/user_supported/market_supported/not_observed`，再输出 `established/established_limited/proposition_only/rejected`。
- 正向口径：M05C 只读取 TV/AC 各自理由对应维度的正向评论；M12C 只读取同理由 claim 的正向/中性角色。普通负面、负面占主导和 G03 M12C pressure 不扣成立分。
- 门槛：标准路径 `>=9`，基线无核心时 `>=8` 兜底，理由专属边界通过时最低 `>=7`；三条路径均要求至少两个强域、场景成立、用户/市场承接和品类理由边界。低于 7 分、proposition、事实证伪、评论错配、边界失败和弱表达角色上限均不得 core eligible。
- TV 边界：大屏影院至少 75 英寸；低价理由必须 low/mid_low；主观画质加价理由必须同尺寸 mid_high/high 且有画质正向评论；游戏/体育必须有游戏动态同维度正向评论；家庭操作和家装只有产品事实/场景时保持 proposition。
- AC 边界：价格理由必须有当前理由正向 M12C，或同锚点正向评论与市场承接同时成立；匹数/大空间可用本品类评论或市场承接；静音、柔风、新风、除湿、自清洁、安装和智能控制作为用户购买理由时必须有对应正向评论。未复用 TV 尺寸、价格或 claim 规则。
- TV 全量：377 SKU、3,542 锚点；成立 1,178、有限成立 636、产品主张 170、拒绝 1,558。139 个基线无核心 SKU 中 107 个获得至少一个新核心资格，32 个仍无核心资格；至少一个 proposition 的 SKU 为 69。
- TV 与 G01 差异：G01 正向审计为 93 个无核心 SKU 可成立，G04 多 14 个；逐个复核确认均由完整评论维度统计补回真实同锚点正向证据，最低正向计数 2，不是降分、白名单或跨维度评论。14 个 SKU 清单和业务证据见 G04 shadow report。
- TV proposition 复核：“家庭操作更省心”和“新家家装更适配”仅产品事实/场景形成 proposition 的 SKU 并集为 27，没有自动升级为用户购买理由。65E7Q 的同价位配置理由为 6 分且缺场景，大屏影院理由未过 75 英寸边界，均不可成为新核心。
- AC 全量：155 SKU、1,879 锚点；成立 888、有限成立 138、产品主张 71、拒绝 782。25 个基线无核心 SKU 中 14 个获得新核心资格、11 个仍无核心，与 G01 结果完全一致；至少一个 proposition 的 SKU 为 45。
- 影响与不变量：core eligible SKU TV 335、AC 143；这是 G04 候选资格，尚未执行 G05 的最多三条/理由族收敛。旧评分、旧角色、SKU 状态和 G03 pressure 变化均为 0；未影响回归 TV 20、AC 20。
- 反例门槛：低于 7 分核心 0、proposition 核心 0、边界失败核心 0、无证据引用核心 0、unassessed 锚点 0。评论错配 SKU 为 TV 114、AC 30，均不贡献用户承接或核心资格。
- 只读证明：205 三张 M12D 表执行前后行数和最大更新时间一致；未写生产数据库。
- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_establishment.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_purchase_reason_establishment.py`
  - `scripts/m12d_rp_g04_shadow_tv_ac_establishment.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G04_tv_ac_establishment_shadow.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G04_tv_ac_establishment_anchors.csv`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G04_tv_ac_establishment_shadow_report.md`
- 测试：G04 专项 15，G02/G03 contract、压力、画像和质量回归 91，合计 `106 passed`；Python 编译和 205 TV/AC 全量只读影子验收通过。
- Git/发布：未 stage、未 commit、未 deploy、未 publish。

## 11. M12D-RP-G05 执行记录

- 完成时间：`2026-07-12`。
- 角色决策：新成立字段已评估时，`established + core_eligible` 映射 `core_payment`，成立但未入选或未获核心资格映射 `supporting`，`proposition_only` 兼容映射 `supporting` 但标记为产品价值主张，只有事实证伪/证据错配映射 `risk_drag`；普通负面和高压力不参与角色删除。
- 核心收敛：继续执行每 SKU 最多三条和理由族去重，但排序改用用户承接层级、正向成立分和成立强域，不再使用被负面扣减的旧 adjusted score。画像置信度只读取入选成立理由；存在入选核心即为 `ready`，只有 supporting/proposition 为 `ready_limited`，只有弱表达为 `weak_expression_only`。
- 消费契约：新增 typed `capabilities`，明确 `strong/limited/facts_only/blocked` 以及事实维度、产品价值主张、已成立理由、强理由和压力是否可比较。版本 `limited` 只形成版本质量说明，不再把其内部 `ready` SKU 统一改成 `published_degraded`；版本 `blocked` 或 SKU `failed/missing_input` 才不可消费。
- Reader/CLI：目标和候选 SKU 均按 capabilities 决策；proposition-only/弱表达 SKU 不参与 M12D 购买理由 pair 评分，但候选仍可依赖参数、卖点、市场等其他维度参与 Top 3。历史 fixture 缺 capabilities 时按旧 SKU 状态和核心字段兼容推导，不猜测新成立语义。契约导出脚本增加版本质量和能力字段。
- Repository：保留发布门禁，`blocked/unassessed` 版本仍不可发布、`limited` 版本仍需人工批准；已批准发布的 `limited` 版本可被 repository 读取，具体消费强度交给 SKU capabilities，而不是在 repository 层统一降级。
- TV 影子：377 SKU；`ready 335 / ready_limited 13 / weak_expression_only 29`；消费能力 `strong 335 / limited 10 / facts_only 32`。状态或核心理由迁移 360 SKU，其中 335 个由旧 `ready_degraded` 恢复为 `ready`；入选且带高压力核心 337 条，因压力丢失核心资格 0；proposition 入核心 0；低于 7 分核心 0。
- AC 影子：155 SKU；`ready 143 / ready_limited 1 / weak_expression_only 11`；消费能力 `strong 143 / facts_only 12`。状态或核心理由迁移 148 SKU，其中旧 `review_required -> ready` 98 个、旧 `ready_degraded -> ready` 45 个；入选且带高压力核心 257 条，因压力丢失核心资格 0；proposition 入核心 0；低于 7 分核心 0。
- 迁移解释：旧画像允许超过三条核心且使用负面混合扣分，本轮按成立度和理由族重新收敛，因此 TV 核心条数减少 146 SKU、增加 134 SKU，AC 核心条数减少 20 SKU、增加 123 SKU；G06 必须对新增/删除核心逐项抽检，不把这些数字直接当发布结论。
- 回归集合：TV/AC 各冻结 20 个非目标字段回归 SKU，保持 G04 成立状态/分数/承接/核心资格、G03 压力和本品类 taxonomy 不变；状态与核心完全不迁移的 SKU 为 TV 17、AC 7，单独记录，不冒充 20 个完全不变样本。
- 205 状态：线上尚未部署 G02/G05 migration，版本质量字段读取为 `legacy_unassessed`；这是 G09 前禁止部署的预期状态，不猜测为 ready/limited。影子运行前后三张 M12D 表行数和最大更新时间一致，未写生产数据库。
- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`
  - `apps/api-server/app/services/core3_real_data/purchase_reason_profile_contract.py`
  - `apps/api-server/app/services/core3_real_data/analyst/purchase_reason_profile_reader.py`
  - `scripts/m12d_g09_publish_and_export_contract.py`
  - `scripts/m12d_rp_g05_shadow_profile_consumption.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G05_tv_ac_profile_consumption_shadow.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G05_tv_ac_profile_consumption_shadow.csv`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G05_tv_ac_profile_consumption_shadow_report.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G05_consumption_contract_fixture.json`
- 测试：M12D 画像、成立度、压力、typed contract、质量、reader 和 PM context/linkage 共 `141 passed`；智能体 CLI 的 M12D 关联用例 `1 passed`；Python compileall、ruff、diff check 和 205 双品类只读影子验收通过。
- Git/发布：未 stage、未 commit、未 deploy、未 publish。

## 12. M12D-RP-G06 执行记录

- 完成时间：`2026-07-12`。
- 全量范围：经 SSH 隧道只读连接 205，分别对当前发布范围 TV `377` SKU / `3,542` 锚点、AC `155` SKU / `1,879` 锚点完整重建 context、candidate、establishment、pressure、profile 和 release quality；未复用旧画像作为输出。
- TV 结果：`ready 335 / ready_limited 13 / weak_expression_only 29`；消费能力 `strong 335 / limited 10 / facts_only 32`；新增核心 `483` 条 / `315` SKU，删除核心 `435` 条 / `241` SKU。QF15A 139 个原无核心 SKU 全部复核，`107` 个形成核心、`32` 个仍无核心，未低于 7 分或使用白名单。
- AC 结果：`ready 143 / ready_limited 1 / weak_expression_only 11`；消费能力 `strong 143 / facts_only 12`；新增核心 `364` 条 / `123` SKU，删除核心 `103` 条 / `20` SKU。TV/AC 使用各自 taxonomy、业务边界、市场池和发布版本。
- 逐条业务审计：新增核心的成立状态、最低 7 分、core eligibility、品类业务边界、产品命题证据、用户/市场承接和同锚点评论追溯失败均为 `0`；压力来源失败 `0`，proposition 误入核心 `0`，与 G04 成立度/承接/压力漂移 `0`。
- 成立度与压力分层：TV 入选核心压力 `high 337 / medium 193 / low 31 / none 280`，AC 为 `high 257 / medium 130 / low 6 / none 31`；压力把已成立且具备核心资格的理由改判为弱表达或风险项均为 `0`。这证明高压力作为第二层标签保留，没有反向删除购买理由。
- 重点和边界：TV 10 个、AC 18 个重点 SKU 全部通过。65E7Q 的同价位配置理由仍为 6 分拒绝，大屏影院理由仍未过 75 英寸边界；两者均未进入核心。TV/AC 各 20 个未影响回归 SKU 保持 G04 成立状态、分数、承接、核心资格和压力等级不变。
- 发布质量：修正 `sku_consumable_rate` 为 `ready + ready_limited + weak_expression_only`，同时保留 `ready_rate` 衡量强消费覆盖；`ready_or_limited_rate` 仅作诊断。TV `ready_rate 0.8886 / sku_consumable_rate 1.0000 / core missing 0.1114`，AC `0.9226 / 1.0000 / 0.0774`，两品类 release quality 均为 `ready`。
- 只读证明：三张 M12D 表运行前后行数和最大更新时间完全一致；总体验收失败项 `0`，未写 current，未运行竞品智能体。
- 产物：
  - `apps/api-server/app/services/core3_real_data/purchase_reason_release_quality.py`
  - `apps/api-server/tests/core3_real_data/test_m12d_quality_contract.py`
  - `scripts/m12d_rp_g06_full_shadow_validation.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G06_tv_ac_full_shadow.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G06_tv_ac_core_migrations.csv`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G06_tv_ac_full_shadow_report.md`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G06_validated_fixture.json`
- 测试：M12D 画像、成立度、压力、typed contract、质量、reader 和 PM report 共 `126 passed`；智能体 CLI M12D 关联用例 `1 passed`；Python compileall、ruff、JSON 语法和 205 双品类全量只读影子验收通过。
- Git/发布：未 stage、未 commit、未 deploy、未 publish。

## 13. M12D-RP-G07 执行记录

- 完成时间：`2026-07-12`。
- 消费边界：竞品智能体只读取 G06 validated fixture 和 typed downstream contract；未调用 context builder、候选生成、成立度评分或压力生产逻辑，未生成/修正 M12D。
- proposition 隔离：候选锚点为 `proposition_only` 时，即使与目标核心理由同 code/同 family，也只输出“产品希望传达但尚未观察到用户承接”，购买理由覆盖、证据对等和候选优势贡献均为 0；历史 `unassessed` 契约继续按兼容角色读取。
- 候选门控：`not_found/blocked` 候选的 typed `top3_eligible=false` 已贯通到最终选择，不能再凭其他总分进入 Top 3；`facts_only` 候选仍可凭参数、卖点、市场、价值战场、用户任务和目标客群参与，购买理由贡献为 0；`limited` 可有限比较但不能升级为首选直接竞品。
- 三层业务输出：购买理由重合、竞品对本品的替代压力、双方各自已成立理由上的购买阻力分别计算和展示。购买阻力不扣成立分，`proposition_only/rejected/weak_expression` 不进入同理由阻力比较。
- 业务语言：低替代压力统一表达为“较弱/参考竞品”，删除“威胁但压力弱、证据不足却最可能影响成交”的矛盾拼接；PM 报告新增“产品希望传达但尚未观察到用户承接”“购买阻力”和“双方各自的购买阻力”，不输出内部英文 code。
- Top 3 追溯：每个候选新增 `ranking_trace`，记录目标/候选消费模式、购买理由重合分、替代压力分、两维对 100 分制的贡献和中文排序作用；版本统一降级标记固定为 false，实际门控只读 SKU capabilities。
- TV 回归：G06 fixture 覆盖 10 个目标 SKU（含海信 65E7Q）、90 个 pair；2 个 proposition 画像均按产品意图表达，误计购买理由重合 0，压力混淆 0，Top 3 追溯失败 0，PM 业务语言失败 0。
- AC 回归：G06 fixture 覆盖 18 个目标 SKU、306 个 pair；5 个 proposition 画像形成 10 个同锚点候选命中，但购买理由重合贡献均为 0；压力混淆、Top 3 追溯和 PM 业务语言失败均为 0。
- 65E7Q 回放：使用既有 205 真实候选池和 G06 validated fixture，旧 Top 3 为 `创维 65A7H PRO / TCL 65Q9L PRO / 华为 VISION智慧屏 5 PRO 65`；新 Top 3 为 `创维 65A7H PRO / TCL 65Q9L PRO / 创维 65A6F ULTRA`。第三名变化可追溯到 G06 fixture 是否覆盖和已成立理由重合；该回放只代表 G07 fixture 范围，不代表正式全量发布后候选缺少画像，G08/G10 仍需用全量版本复核。
- 产物：
  - `apps/api-server/app/services/core3_real_data/analyst/anchor_substitutability.py`
  - `apps/api-server/app/services/core3_real_data/analyst/purchase_pressure_comparison.py`
  - `apps/api-server/app/services/core3_real_data/analyst/replacement_pressure.py`
  - `apps/api-server/app/services/core3_real_data/analyst/sop_orchestrators.py`
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py`
  - `apps/api-server/app/services/core3_real_data/analyst/competitor_pm_report.py`
  - `scripts/m12d_rp_g07_validate_competitor_consumption.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G07_competitor_consumption_shadow.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G07_competitor_consumption_fixture.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G07_top3_migration_audit.csv`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G07_competitor_consumption_shadow_report.md`
- 测试：M12D 与竞品消费相关回归 `161 passed`，智能体 CLI 竞品回归 `13 passed`，合计 `174 passed`；Python compileall、ruff、JSON 语法和 G06 fixture 双品类回归通过。
- Git/发布：未 stage、未 commit、未 deploy、未 publish。

## 14. M12D-RP-G08 执行记录

- 完成时间：`2026-07-12`。
- 集成范围：M03B、M04C、M05C、M07、M09C、M10C、M11C、M12C、M12D、竞品 reader、CLI、详细报告、PM 报告和 TV/AC 类别隔离；共 `378 passed`，无功能失败。
- TV 结论：全量影子 `377` SKU，`335 ready / 13 ready_limited / 29 weak_expression_only`；ready 比例 `0.8886`，可消费比例 `1.0000`，无核心理由比例 `0.1114`；10 个重点 SKU 和 20 个未影响回归 SKU 全部通过，taxonomy 和 SKU 前缀隔离通过，结论为 `go_to_g09`。
- AC 结论：全量影子 `155` SKU，`143 ready / 1 ready_limited / 11 weak_expression_only`；ready 比例 `0.9226`，可消费比例 `1.0000`，无核心理由比例 `0.0774`；18 个重点 SKU 和 20 个未影响回归 SKU 全部通过，taxonomy 和 SKU 前缀隔离通过，结论为 `go_to_g09`。
- 竞品消费：复用 G07 收据，TV 10 个目标/90 个 pair、AC 18 个目标/306 个 pair；proposition 误计、压力混淆、Top 3 追溯失败和 PM 内部码泄漏均为 0。竞品智能体未生成或修正 M12D。
- QF 回填：QF15 在旧口径下的 blocked 事实保留，不改写为当时已通过；其混合成立度、阻力和版本消费能力的口径已由本任务链取代，新口径下 QF15 当前状态为 `completed_superseded`。QF16 由 G07 完成，QF17 由 G08 完成。
- 上线边界：TV/AC 均允许申请进入 G09 提交部署；当前仍为 `no_go_pending_g09_g10`，因为尚未提交部署，也未在 205 正式全量重跑和发布。
- 产物：
  - `scripts/m12d_rp_g08_integrated_acceptance.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G08_integrated_acceptance.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G08_integrated_acceptance_report.md`
- 验证：集成回归 `378 passed`；G07 冻结输入确定性回放与既有收据逐字段一致；G08 脚本 ruff、Python 编译和 JSON 解析通过；G06 只读守卫保持不变。
- Git/发布：未 stage、未 commit、未 deploy、未 publish；任务链停在 G09 审批门。

## 15. M12D-RP-G09 执行记录

- 完成时间：`2026-07-12`。
- 提交：`67a11d6 feat(m12d): separate purchase reasons and pressure`；migration 修复：`adeab0a fix(m12d): index JSON fields through jsonb`；均已推送到 `new/base-publish-workbench-design`。
- 提交前验证：集成回归 `378 passed`；静态清理后回归 `84 passed`；migration 修复回归 `32 passed`；ruff、compileall 和 Alembic 单 head 通过。
- 回滚点：`/var/backups/catforge/m12d-rp-g09-20260712_084936`，`180M`；包含三张 M12D 表、全库 schema、运行环境、应用源码、远端 Git patch 和运行产物；SHA256 与 `pg_restore -l` 校验通过。
- 部署过程：首次同步因远端脏工作树在构建前停止；备份并清理后，首次 migration 因 `json` GIN 缺少 operator class 事务回滚至 0042，旧服务未中断；改为 `json::jsonb` 表达式索引后重新部署成功。
- 205 结果：Git revision `adeab0a`；Alembic `0044_core3_m12d_reason_pressure`；profile 字段 `5/5`、anchor 字段 `12/12`、索引 `5/5`。
- 数据守卫：部署前后 `687 profiles / 7057 anchors / 3 versions` 和最大更新时间完全一致；未执行正式重跑，未切换 current/published。
- 兼容读取：687 个历史 profile 的成立理由/产品主张为空，7057 个历史 anchor 的成立度/购买阻力为 `unassessed`；没有猜测新语义。
- 运行验收：仓库与容器关键源码 hash 一致；新模块 import 通过；API 日志无错误；205 本机 `/healthz`、`/readyz` 通过。
- 产物：
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G09_deployment_receipt.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_RP_G09_deployment_report.md`
- 下一任务：M12D-RP-G10 正式全量重跑和发布；需要明确发布批准。
