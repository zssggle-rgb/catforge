# M12D TV/AC 系统质量修复开发任务链

## 1. 任务粒度

本任务链按“一个模块一次完整闭环”拆分，不再把同一模块里的每个 flag、每个函数分别建任务。

模块任务必须在同一个 goal 内完成：

1. 复核该模块全部不合常理的标记。
2. 修复标记产生、严重度或传播范围。
3. 增加正例、反例和边界测试。
4. 只重跑该模块的 draft/影子结果。
5. 输出修复前后分布和未受影响 SKU 对比。
6. 达到模块门槛后才进入下一模块。

M12D 本身横跨输入质量、锚点评分、画像决策和发布控制，因此拆成四个任务；竞品智能体仍只负责消费，不生产 M12D。

所有共享模块任务必须同时覆盖 `TV` 和 `AC`：同一个 goal 内分别审计两个品类、使用各自 taxonomy 修复、分别测试、分别重跑并分别出报告。不得先修 TV、最后才把 AC 当非回归样本；也不得把 TV 的尺寸、价格、购买理由或发布统计口径直接复用到 AC。

## 2. 依据与基线

| 类型 | 文件 |
| --- | --- |
| 系统审计 | `docs/core3_mvp/real_data_v2/current_implementation/M12D_TV_system_quality_audit_20260711.md` |
| 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M12D_sku_purchase_reason_profile_requirements.md` |
| 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_sku_purchase_reason_profile_design.md` |
| AC 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M12D_AC_sku_purchase_reason_profile_requirements.md` |
| AC 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M12D_AC_sku_purchase_reason_profile_design.md` |
| AC 既有任务记录 | `docs/core3_mvp/real_data_v2/development/M12D_AC_development_tasks.md` |
| 调度 | `docs/core3_mvp/real_data_v2/development/M12D_TV_AC_QUALITY_FIX_goal_dispatch.md` |

205 已确认 TV 基线：

- `project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`
- `category_code=TV`
- M12D batch：`m00_20260623014631_c8630747`
- 377 SKU
- 0 `ready`、359 `ready_degraded`、18 `weak_expression_only`
- 377/377 `review_required`
- 影子可行性：约 332 `ready`、33 `ready_limited`、12 `weak_expression_only`

AC 基线必须由 M12D-QF-01 在修改代码前从 205 重新采集，包括 SKU 总数、M03B/M04C/M05C/M07/M09C/M10C/M11C/M12C/M12D 状态、flag 覆盖和发布版本；不得沿用旧报告中的数量作为当前事实。

M12D-QF-01 已采集 AC 当前基线：155 SKU，50 `ready_degraded`、98 `review_required`、7 `weak_expression_only`，155/155 需复核，M03B 冲突 29，缺少核心锚点 135。完整分布以 QF-01 基线产物为准。

## 3. 模块问题归并

| 模块 | 需要一起修复的不合常理问题 | 已确认 TV 影响 | TV/AC 处理 | 任务 |
| --- | --- | ---: | --- | --- |
| M03B | 原始值与派生标准值语义一致却按字符串冲突；只保存冲突计数，不保存冲突参数和值 | 377/377 conflict | TV 检查尺寸段；AC 检查匹数、能力、安装方式、能效等原始/派生等价值；分别规范化和重跑 | M12D-QF-02 |
| M04C | 当前已有 M03B 仍保留历史 `m03b_param_profile_missing`；单条 `claim_text_unmatched` 降级整画像 | 328 行 partial | 两品类按各自 serving scope 重算依赖并按 claim 隔离 | M12D-QF-03 |
| M05C | 服务评论正确排除却算异常；历史参数/卖点缺失污染当前状态；局部评论矛盾扩散到所有锚点 | 308 partial、29 missing | 两品类分别使用产品事实评论 taxonomy，服务/安装边界按品类配置 | M12D-QF-04 |
| M07 | `<52w`、online-only、新品短历史和连续零销量被误当质量问题；TV 输入混有 AC SKU；分块会改变候选池 | 377/377 范围 flag，13 个 latest gap；TV 批次混入 155 个 AC SKU | 完整市场日历补零，品类双重隔离，目标分块但候选全集不变 | M12D-QF-05 |
| M09C | 任一次要任务需复核就让整个用户任务画像需复核 | 348/348 partial | TV/AC 各自主任务 taxonomy，采用相同关系级传播原则 | M12D-QF-06 |
| M10C | 任一次要客群需复核就让整个目标客群画像需复核 | 348/348 partial | TV/AC 各自主客群 taxonomy，采用相同关系级传播原则 | M12D-QF-07 |
| M11C | 机会/次要战场的局部问题扩散到整个价值战场画像 | 189 partial | TV/AC 各自价值战场，不跨品类复用战场 code | M12D-QF-08 |
| M12C | 阈值说明被当异常；单 SKU 比较组影响整 SKU；任一卖点行有 flag 就降级全部卖点价值 | 271 partial、88 missing | 两品类分别按 claim/anchor 聚合，量化阈值按品类配置 | M12D-QF-09 |
| M12D 输入质量 | 通用 `_profile_status` 任意 flag 即 partial；`_combine_statuses` 用最坏值传播；历史缺失不按当前 serving scope 重算 | 377 SKU | 共享三轴质量结构，adapter 和 flag 映射按品类隔离 | M12D-QF-10 |
| M12D 锚点评分 | `missing_or_partial_inputs` 对全部锚点统一 -1 分和 -0.1 置信度；真实问题没有锚点作用域；M12C 缺失一刀切 | 377 SKU | 共享作用域机制，TV/AC 使用各自购买理由和支付门槛 | M12D-QF-11 |
| M12D 画像决策 | partial 输入数量重复扣画像置信度；任意 partial 即 review；`ready_degraded` 含义混杂；修复后核心锚点可能过多 | 377 SKU | 状态语义共享，锚点族去重和排序按品类 taxonomy | M12D-QF-12 |
| M12D 发布 | 100% review 的版本仍能 current published；同一系统问题被拆成大量人工复核 | 当前发布版本 | TV/AC 分别计算门槛，任一品类失败不能被另一品类平均值掩盖 | M12D-QF-13 |
| 竞品消费 | `published_degraded` 直接改变候选角色槽位和 Top 3 | 当前线上 | TV/AC 都只消费本品类通过门槛的 M12D 版本 | M12D-QF-16 |

原审计中的 29 类问题全部保留为各模块任务内的检查项，不再拆成 29 个 goal。

## 4. 每个模块的保护门槛

每个 M12D-QF-02 至 M12D-QF-13 任务都必须执行：

1. **影响集合**：列出该模块预计变化的 flag、行、关系、锚点和 SKU 数。
2. **未影响集合**：TV、AC 各至少选 20 个未命中问题的 SKU，比对业务字段；如果某品类全量命中，则各抽 20 个验证非目标字段不变。
3. **允许迁移**：任务开始前声明允许哪些状态或角色迁移，出现未声明迁移即停止。
4. **不降门槛**：不得降低 `strong >= 9`、两个强证据域、场景门槛和弱表达封顶。
5. **不硬编码**：不得添加品牌、型号或 SKU 白名单来提高正常率。
6. **缺失不补造**：missing 保持 unknown，不得补成 false 或正向证据。
7. **系统异常守卫**：在 TV 或 AC 任一品类中，同一新增 blocking 问题覆盖超过 20%，停止任务并回到规则审计。
8. **模块重跑**：分别生成 TV 和 AC 的该模块 draft/影子版本，不提前发布 current，不顺带重跑后续模块。
9. **模块报告**：TV、AC 分开输出修复前后状态分布、flag 分布、受影响/未影响 SKU 和异常清单。
10. **品类隔离**：共享代码必须验证 TV/AC 边界，不在品类间复用 taxonomy、阈值、市场池或购买理由。

## 5. 任务总览

| 顺序 | 任务 | 状态 | 闭环范围 | 前置 |
| ---: | --- | --- | --- | --- |
| 0 | M12D-QF-00 | completed | 审计与模块级计划冻结 | 无 |
| 1 | M12D-QF-01 | completed | 公共质量契约、状态契约和影子基线 | M12D-QF-00 |
| 2 | M12D-QF-02 | completed | M03B 修复、测试、模块重跑 | M12D-QF-01 |
| 3 | M12D-QF-03 | completed | M04C 修复、测试、模块重跑 | M12D-QF-02 |
| 4 | M12D-QF-04 | completed | M05C 修复、测试、模块重跑 | M12D-QF-03 |
| 5 | M12D-QF-05 | completed | M07 修复、测试、模块重跑 | M12D-QF-01 |
| 6 | M12D-QF-06 | completed | M09C 修复、测试、模块重跑 | M12D-QF-01 |
| 7 | M12D-QF-07 | completed | M10C 修复、测试、模块重跑 | M12D-QF-01 |
| 8 | M12D-QF-08 | completed | M11C 修复、测试、模块重跑 | M12D-QF-01 |
| 9 | M12D-QF-09 | completed | M12C 修复、测试、模块重跑 | M12D-QF-01 |
| 10 | M12D-QF-10 | completed | M12D 输入质量和作用域传播 | M12D-QF-02 至 M12D-QF-09 |
| 11 | M12D-QF-11 | completed | M12D 锚点级评分和惩罚 | M12D-QF-10 |
| 12 | M12D-QF-12 | completed | M12D 画像置信度、状态、复核和核心锚点收敛 | M12D-QF-11 |
| 13 | M12D-QF-13 | completed | M12D 发布质量门槛和系统异常守卫 | M12D-QF-12 |
| 14 | M12D-QF-14 | completed | 重点 SKU 影子验证 | M12D-QF-13 |
| 15 | M12D-QF-15 | completed | TV/AC 全链路 draft 重跑和验收；旧 blocked 口径由 RP-G06/G08 新口径取代 | M12D-QF-14 |
| 15A | M12D-QF-15A | completed | TV 139 个无核心 SKU 证据缺口和门槛反事实审计 | M12D-QF-15 blocked 后单独批准审计 |
| 16 | M12D-QF-16 | completed | TV/AC 竞品智能体消费和 Top 3 回归；由 RP-G07 承接 | M12D-QF-15 |
| 17 | M12D-QF-17 | completed | 跨品类隔离和共享链路总回归；由 RP-G08 承接 | M12D-QF-16 |
| 18 | M12D-QF-18 | completed | 提交并部署代码到 205 | M12D-QF-17 |
| 19 | M12D-QF-19 | pending | 205 全量重跑、发布切换和上线验收 | M12D-QF-18；需发布门槛通过 |

## 6. 任务明细

### M12D-QF-00 审计与模块级计划冻结

- 完成系统审计，确认不是 377 个 SKU 分别异常。
- 将原 29 类问题归并为模块级闭环任务。
- 当前只修改计划文档，不修改生产逻辑。

### M12D-QF-01 公共契约和影子基线

状态：completed。

- 建立 `availability/usability/severity/scope/affected_anchor_codes` typed contract。
- 增加 `ready_limited` 和 `release_quality_status=ready/limited/blocked` 兼容契约。
- 建立 TV/AC 只读影子对比工具，固定两个品类当前状态、锚点、置信度和问题覆盖基线。
- 从 205 实时采集 AC 基线，不沿用旧任务记录中的数量。
- 验收：契约变更不改写历史结果；两个品类影子工具重复运行结果一致且不写 current/published。

完成记录：

- 契约：新增 `M12DInputQuality`、`M12DInputQualityIssue`、`ready_limited`、`release_quality_status`、`input_quality_json` 和兼容 migration `0043`。
- 只读工具：`scripts/m12d_qf01_capture_tv_ac_quality_baseline.py`。
- 产物：
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF01_tv_ac_quality_baseline.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF01_tv_ac_quality_baseline_report.md`
- 基线指纹：`ce96cd3542aa571f93dce47350c54f07c11a7a9b765e76fdf254bfaa84fa8605`，205 连续两次只读采集一致。
- TV：377 画像、3,299 锚点、377/377 需复核、M03B 377 冲突。
- AC：155 画像、1,879 锚点、155/155 需复核、M03B 29 冲突。
- 测试：125 passed；compileall 通过；`git diff --check` 通过。
- 数据写入：无；未执行 migration，未修改 current/published。
- 下一任务：M12D-QF-02 M03B 完整修复与 TV/AC 分别重跑。

### M12D-QF-02 M03B 完整修复与重跑

状态：completed。

- TV 修复 `screen_size_segment` 原始值与派生值的 canonical 区间比较；AC 同时审计并修复匹数、制冷量、安装方式、能效等原始/派生字段的等价比较。
- 保存真实冲突的 param code、候选值、来源、selected value 和作用范围。
- TV 测试 32/43/55/65/75/85/98/100 英寸边界；AC 测试挂机/柜机、1/1.5/2/3/3+ 匹和能力边界；两个品类都注入真实矛盾反例。
- 分别重跑 TV 和 AC 的 M03B draft，不重跑 M04C 以后模块。
- 验收：TV 当前 377 个尺寸段伪冲突归零；AC 等价编码伪冲突归零；两个品类真实冲突仍可识别，非冲突参数和档位不变。

完成记录：

- 根因：TV 将原始尺寸区间与 canonical 档位按字符串比较；AC 29 个冲突全部来自把 `系列` 名称与 `三大品牌系列` 编码合并为 `product_series`。
- 修复：分段参数按数值是否落入声明区间比较；AC 拆分 `product_series`/`brand_series_code`，补齐 `5500-6499W` 制冷量档；真实冲突保存候选、来源、selected value、比较基准和作用维度。
- 版本：TV `tv_param_taxonomy_manual_v0.2` / `m03b_tv_parser_v0.2` / `m03b_tv_param_profile_v0.2`；AC 使用对应 `v0.2` 独立版本。
- 205 draft：TV 377 条，冲突 SKU `377 -> 0`；AC 155 条，冲突 SKU `29 -> 0`。旧 v0.1 保留，未切换 current/published。
- 回归：TV/AC business profile、参数完整度和 dimension tier 均 0 个未声明变化；AC 136 个 SKU 因新增独立系列编码，known param count 合法 `+1`，19 个空编码 SKU 不变。
- 测试：93 passed；覆盖 TV 32/43/55/65/75/85/98/100 英寸，AC 挂机/柜机、1/1.5/2/3/3+ 匹、制冷量连续边界和双品类真实矛盾。
- 越界守卫：M04C、M05C、M07、M09C、M10C、M11C、M12C、M12D 表的行数和最大更新时间前后一致。
- 产物：
  - `scripts/m12d_qf02_run_m03b_tv_ac_draft.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF02_tv_ac_m03b_draft.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF02_tv_ac_m03b_draft_report.md`
- 未 stage/commit，未部署运行服务代码；只通过隔离 one-off 容器写入 M03B v0.2 draft。
- 下一任务：M12D-QF-03 M04C 完整修复与 TV/AC 分别重跑。

### M12D-QF-03 M04C 完整修复与重跑

状态：completed。

- 当前 serving scope 重新判断 M03B 是否存在，旧 `m03b_param_profile_missing` 仅保留为 lineage。
- `claim_text_unmatched` 改为 claim/row 级 coverage warning，不再降级整个卖点画像。
- 保持已匹配 claim 的事实、置信度和参数支撑不变。
- 分别使用 TV/AC 的新 M03B draft 重跑各自 M04C draft，卖点 taxonomy 保持品类隔离。
- 验收：两个品类当前 M03B 存在时不再报缺失；unmatched claim 不能加事实分，但不影响其他 claim。

完成记录：

- 根因：TV M04C 按 M04C 源 batch 精确读取 M03B，未消费当前 serving scope 内已存在的 M03B；同时把行级 `claim_text_unmatched` 和单条事实的参数支撑问题扩散为画像级降级。
- 修复：M03B 同 batch 优先、品类 serving scope 回退，并记录来源 batch/规则/hash；未匹配卖点改为 `claim_summary_json.coverage_warnings` 行级告警；参数支撑问题保留在 claim fact；只有真实缺少 M03B 才保留画像级问题。
- 版本：TV `m04c_tv_claim_fact_profile_v0.2`，AC `m04c_ac_claim_fact_profile_v0.2`；两个品类继续使用各自 `*_claim_taxonomy_manual_v0.1`，未修改 taxonomy。
- 205 draft：TV 328 个画像、7,993 条事实，画像级问题 `328 m03b missing + 293 unmatched -> 0`，735 条未匹配文本保留为 293 个 SKU 的行级覆盖告警；AC 155 个画像、3,931 条事实，画像级问题 `121 unmatched -> 0`，237 条未匹配文本保留为 121 个 SKU 的行级覆盖告警。
- 参数支撑：TV 恢复使用有效 M03B 后为 396 不适用、1,064 未知、1,850 部分支撑、4,683 支撑；AC 为 914 不适用、1,070 未知、519 部分支撑、1,428 支撑，状态与修改前完全一致。
- 回归：两个品类事实无增删、claim code 无变化、claimed position 无变化；AC 参数支撑核心字段 0 变化。TV 有 993 条历史 `claim_kind` 与当前仓库 taxonomy 定义不一致，确认为 205 与仓库预存漂移，本任务未修改 taxonomy，已单独记录而未掩盖。
- 测试：74 passed；覆盖跨 batch M03B、真实缺失、未匹配行告警、事实级参数支撑及 M05C/M11C/M12C/M12D 受影响契约；编译检查和 `git diff --check` 通过。
- 越界守卫：M05C、M07、M09C、M10C、M11C、M12C、M12D 表的行数和最大更新时间前后一致；旧 M04C v0.1 保留，未切换 current/published。
- 产物：
  - `scripts/m12d_qf03_run_m04c_tv_ac_draft.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF03_tv_ac_m04c_draft.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF03_tv_ac_m04c_draft_report.md`
- 未 stage/commit，未部署运行服务代码；只通过隔离 one-off 容器写入 TV/AC M04C v0.2 draft。
- 下一任务：M12D-QF-04 M05C 完整修复与 TV/AC 分别重跑。

### M12D-QF-04 M05C 完整修复与重跑

状态：completed。

- `service_fulfillment_comment_excluded` 改为 info，仍严格排除服务/安装评论。
- 当前 scope 重算 `claim_fact_profile_missing` 和 `param_profile_missing`。
- 评论矛盾关联 claim、param、comment topic 和 affected anchor，只影响相关锚点。
- 分别使用 TV/AC 的新 M03B/M04C draft 重跑 M05C draft；产品事实评论和服务履约边界按各品类配置。
- 验收：两个品类服务过滤不降级；历史缺失不污染当前状态；无关锚点不受评论矛盾影响。

完成记录：

- 根因：M05C 按评论 batch 精确读取 M03B/M04C，并以是否存在 `fact_claim_flag=true` 的卖点事实代替 M04C profile 存在性；同时将正确服务排除和任一局部评论矛盾扩散为 SKU 画像级 flag 和模块级 warning。
- 修复：M03B/M04C 同 batch 优先、同品类 serving scope 回退；M04C 依赖按 profile 存在性判断；服务排除写入 fact 级 info；矛盾保留在具体 fact/review issue，记录 comment topic、参数、卖点、锚点映射状态和 `related_anchor_only` 传播策略，不再降级整 SKU。
- 版本：TV `m05c_tv_comment_fact_profile_v0.2`，AC `m05c_ac_comment_fact_profile_v0.2`；继续使用各自 `*_comment_fact_taxonomy_manual_v0.1`，未修改 taxonomy。
- 205 draft：TV 348 个画像、43,750 条事实，画像 flags 从 `90 param missing + 165 claim missing + 266 service + 172 contradiction` 收敛为 49 个真实 M04C profile 缺失；AC 144 个画像、68,109 条事实，画像 flags 清零。
- 事实保真：TV/AC 共 111,859 条事实无增删，评论主题、子主题、极性、原文、证据均 0 变化；服务事实 TV 3,169、AC 6,670 条完整保留并继续严格排除。
- 局部矛盾：TV 恢复当前 M04C 关联后，矛盾事实 `1,181 -> 1,400`、涉及 SKU `172 -> 233`；AC 保持 1,066 条、120 个 SKU。全部生成一一对应的局部 review issue，不构成新增 blocking，也不扩散到无关锚点。
- 上游来源：TV 348/348 使用 M03B v0.2，其中 75 个来自 6/13 batch、273 个来自 6/19 batch；299/348 使用 6/23 M04C v0.2，49 个真实缺失。AC 144/144 同时使用本品类 6/24 M03B/M04C v0.2。
- 测试：M05C 11 passed；M05C/M09C/M10C/M11C/M12C/M12D/pipeline 受影响套件共 78 passed；编译检查和 `git diff --check` 通过。
- 越界守卫：M07、M09C、M10C、M11C、M12C、M12D 表的行数和最大更新时间前后一致；旧 M05C v0.1 保留，未切换 current/published。
- 产物：
  - `scripts/m12d_qf04_run_m05c_tv_ac_draft.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF04_tv_ac_m05c_draft.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF04_tv_ac_m05c_draft_report.md`
- 未 stage/commit，未部署运行服务代码；只通过隔离 one-off 容器写入 TV/AC M05C v0.2 draft。
- 下一任务：M12D-QF-05 M07 完整修复与 TV/AC 分别重跑。

### M12D-QF-05 M07 完整修复与重跑

状态：completed。

- `observed_window_less_than_52w` 和 `online_only_channel` 改为范围 info。
- 周表无记录按销量、销额为 0 处理；新品上市时长、距最近成交周数均为市场事实，不判数据质量问题。
- 趋势按完整市场日历补零计算；基期销量或成交价为 0 时对应变化率不可计算，但不触发质量告警。
- 不改变销量、销额、均价的原始计算；仅撤销错误质量标记造成的市场置信度扣分。
- 分别使用 TV/AC 的价格池、销量口径和样本门槛重跑 M07 draft。
- 验收：TV 377 个、AC 155 个 SKU 均按完整市场时间轴判定 sufficient；范围说明不再造成 partial；销量为 0、无成交价和新品上市不得解释为数据缺失。

完成记录：

- 根因：M07 把“没有周行”解释为缺数，并用 SKU 首末成交周压缩窗口；`latest_week_gap`、`<52w`、online-only 和历史派生 flag 进入质量扣分。TV 第二市场批次还混入 155 条 `AC...` SKU，旧分块实现又把候选池限制在当前块，导致价格分位和池成员依赖运行分块。
- 修复：按品类全局日历计算五个窗口，缺行补销量/销额 0；新品时长和距最近成交周只保留为市场事实；全局最新周无成交时 `price_latest=null`，不回填历史成交价；范围信息写结构化 info，不进入 flag/review/confidence。
- 品类与分块：TV/AC 同时按 `category_code` 与 SKU 前缀隔离；目标 SKU 以 75 条分块，候选画像始终使用同批次本品类全集。TV 清除 155 条 AC 输入对品类分位的污染；AC 价格带和市场池保持 `m07_ac_hp_price_band_v2 / m07_ac_hp_price_pool_v2`。
- 版本：主画像 `m07_market_profile_v2`；TV 保持 `m07_price_band_v1 / m07_pool_v1`，AC 保持 `m07_ac_hp_price_band_v2 / m07_ac_hp_price_pool_v2`；只写 draft，未切换 current/published。
- 同输入影子：TV/AC 自身销量、销额、加权均价、价格极值、规格和 market pool key 均 0 变化。TV 有 36 条 `price_latest` 改为当前周无成交不可计算，13 个错误 latest-gap 置信度扣分撤销；TV 分位和 2,710 个池成员清单变化均来自剔除 AC 污染。AC 比较字段、置信度和池成员均 0 变化。
- 205 draft：TV 1,885 个画像、7,789 个信号、10,599 个池、1,088,980 个池成员，full window 377/377 sufficient；AC 775 个画像、3,351 个信号、4,485 个池、316,666 个池成员，full window 155/155 sufficient。两个品类跨品类池候选均为 0。
- 质量分布：TV/AC 的 `<52w` 与 online-only 全部转为 info；full profile 仅保留真实池样本 flag。TV 13 个 latest gap、历史 trend/baseline flag 均不再作为质量问题；所有 full profile `review_required=0`。
- 测试：M07/pipeline 单元与分块候选测试 27 passed；M07-M12D 受影响回归套件共 103 passed；编译检查通过。
- 越界守卫：M09C、M10C、M11C、M12C、M12D 表行数与最大更新时间前后一致；旧 M07 v1/current 保留，未发布 v2。
- 产物：
  - `scripts/m12d_qf05_run_m07_tv_ac_draft.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF05_tv_ac_m07_draft.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF05_tv_ac_m07_draft_report.md`
- 未 stage/commit，未部署运行服务代码；通过隔离 one-off 容器写入 TV/AC M07 v2 draft。
- 下一任务：M12D-QF-06 M09C 完整修复与 TV/AC 分别重跑。

### M12D-QF-06 M09C 完整修复与重跑

状态：completed。

- 主任务是否成立、primary relation status 和主任务置信度决定画像可用性。
- 次要任务复核保留为 relation 级问题，不拖累整个 SKU。
- 不修改 TV/AC 各自任务 taxonomy、主次任务 code 和关系分数。
- 分别重跑 TV/AC M09C draft。
- 验收：两个品类高置信主任务成立时 auto-pass；无主任务或主任务冲突仍受限。

完成记录：

- 根因：旧 `_profile_payload` 使用“无主任务或任一 SKU x 任务关系需复核”作为画像复核条件，导致服务信号已排除、未知参数映射、次要/潜在/观察任务证据提醒扩散到整张 SKU 画像；画像复核原因又只记录无主任务原因，无法解释大面积复核。
- 修复：新增主任务画像质量决策。仅无主任务、主关系状态异常、主关系置信度 `<0.80`、尺寸价格冲突或达到 `0.45` 阻断阈值的主任务反证限制画像；关系级提醒继续完整保留，但不跨作用域传播。
- 量价语义：沿用 M07 完整市场时间轴；没有销量行表示销量为 0，新上市观测周数短是生命周期事实，M09C 不设置“至少 8 周”门槛，也不将其解释为数据质量问题。
- 版本：模块 `m09c-user-task-profile-0.2.0`；TV rule `m09c_tv_user_task_profile_v0.3`，AC rule `m09c_ac_user_task_profile_v0.3`；两品类 taxonomy 均保持各自 `v0.1`，未交叉复用。
- 205 draft：TV 348 个画像、4,176 条关系分数，`review_required 348 -> 11`、`auto_pass 0 -> 337`；11 个均为无主任务。AC 144 个画像、1,728 条关系分数，`review_required 142 -> 1`、`auto_pass 2 -> 143`；1 个为无主任务。
- 影响集合：同输入旧聚合策略下，TV 337 个、AC 141 个高置信主任务画像从“关系问题扩散复核”迁移为 auto-pass；AC 原有 2 个 auto-pass 保持不变。未出现旧 auto-pass 被升级为复核。
- 受限集合：TV 11 个、AC 1 个无主任务画像继续 review；两个品类高置信且无阻断冲突但仍 review 的数量均为 0。
- 关系证据保真：TV 4,028 条、AC 1,692 条 relation 级复核行完整保留。质量策略单独对任务 code、主次关系、关系状态、六项分数、综合分和证据 ID 的修改数为 0；每品类均记录 20 个业务字段回归样本，覆盖总量 TV 348、AC 144。
- 上游允许迁移：v0.3 草稿消费 QF-02 至 QF-05 草稿输入，因此 TV 当前 v0.2 与草稿间 271 个画像、4,037 条关系业务字段发生上游证据驱动变化；AC 画像主次任务 0 变化，1,728 条关系证据/分数字段变化。该差异与 QF-06 质量聚合影响分开记录，不归因于本任务评分改造。
- 测试：M09C 定向测试 8 passed，覆盖高置信主任务、无主任务、低置信、阻断冲突和策略切换前后关系分数保真；`ruff check`、Python 编译检查通过。
- 越界守卫：M10C、M11C、M12C、M12D TV/AC 行数前后一致；205 运行容器源码在 one-off 草稿完成后恢复原版本；未切换 current/published。
- 产物：
  - `scripts/m12d_qf06_run_m09c_tv_ac_draft.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF06_tv_ac_m09c_draft.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF06_tv_ac_m09c_draft_report.md`
- 未 stage/commit，未部署运行服务代码；只写入 TV/AC M09C v0.3 draft。
- 下一任务：M12D-QF-07 M10C 完整修复与 TV/AC 分别重跑。

### M12D-QF-07 M10C 完整修复与重跑

状态：completed。

- 按 M09C 同一原则处理主客群和次要客群。
- 不修改 TV/AC 各自客群 taxonomy 和关系分数。
- 分别重跑 TV/AC M10C draft。
- 验收：两个品类次要客群问题不扩散；真实主客群歧义仍需复核。

完成记录：

- 根因：旧 M10C 画像将“无主客群或任一 SKU x 客群关系需复核”作为整画像复核条件，导致服务信号已排除、未知参数、次要/观察/潜在/未满足客群提醒扩散到 SKU；画像原因又只记录无主客群，无法解释大面积复核。
- 修复：画像可用性仅由主客群存在、主关系状态、主关系置信度、尺寸价格冲突和真实主候选歧义决定。关系级问题继续完整保留，不参与画像聚合。
- 置信门槛：M10C 按 6 个证据域计算置信度，自动通过门槛为 `0.8333`，即至少 5/6 证据域成立；未机械照搬 M09C 的 `0.8`。
- 歧义规则：只有综合分、评论动机分、任务支撑分、卖点对齐分四项主候选排序键全部相同时才标记 `primary_target_group_ambiguous`。只看综合分接近或分差小不构成歧义，不降低门槛或硬编码 SKU 消除真实并列。
- 量价语义：无销量行表示销量为 0，新上市观测周数短是生命周期事实；M10C 不使用固定 8 周门槛，也不据此降低画像质量。
- 版本：模块 `m10c-target-group-profile-0.2.0`；TV rule `m10c_tv_target_group_profile_v0.3`，AC rule `m10c_ac_target_group_profile_v0.3`；两品类继续使用各自 target-group taxonomy v0.1。
- 205 draft：TV 348 个画像、3,480 条关系分数，`review_required 348 -> 104`、`auto_pass 0 -> 244`；AC 144 个画像、1,440 条关系分数，`review_required 144 -> 12`、`auto_pass 0 -> 132`。
- 影响集合：同输入旧聚合策略下，TV 244 个、AC 132 个高置信且无歧义主客群画像从关系扩散复核迁移为 auto-pass；未出现旧 auto-pass 被升级为复核。
- 受限集合：TV 48 个无主客群、56 个完整排序键并列；AC 3 个无主客群、9 个完整排序键并列。两个品类高置信、无歧义主客群仍 review 的数量均为 0。
- 歧义审计：TV 最大并列组合为 `TG_VALUE_MAXIMIZER` 对 `TG_SMART_CONNECTED_USER` 26 个，其次为大屏升级对性价比 12 个；AC 最大组合为家庭长用节能对客厅大空间 6 个。单一新增 blocking 类型均未超过 20%，且均有具体候选组合和 SKU 清单。
- 关系证据保真：TV 3,332 条、AC 1,413 条 relation 级复核行完整保留。质量策略单独对客群 code、主次关系、关系状态、七项分数、综合分和证据 ID 的修改数为 0；每品类记录 20 个业务字段回归样本，覆盖 TV 348、AC 144 个画像。
- 上游允许迁移：v0.3 草稿消费 QF-02 至 QF-05 草稿输入，因此 TV 当前 v0.2 与草稿间 271 个画像、3,346 条关系业务字段变化；AC 画像主次客群 0 变化，1,440 条关系证据/分数字段变化。该差异与 QF-07 质量聚合影响分开记录。
- 测试：M10C 定向测试 6 passed，覆盖高置信主客群、无主客群、低置信、完整排序键并列和策略切换前后关系分数保真；`ruff check`、Python 编译检查和 `git diff --check` 通过。
- 越界守卫：M11C、M12C、M12D TV/AC 行数前后一致；205 运行容器源码恢复原版本；未切换 current/published。
- 产物：
  - `scripts/m12d_qf07_run_m10c_tv_ac_draft.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF07_tv_ac_m10c_draft.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF07_tv_ac_m10c_draft_report.md`
- 未 stage/commit，未部署运行服务代码；只写入 TV/AC M10C v0.3 draft。
- 下一任务：M12D-QF-08 M11C 完整修复与 TV/AC 分别重跑。

### M12D-QF-08 M11C 完整修复与重跑

状态：completed。

- 主战场决定画像可用性，辅助/机会/拖后腿战场按 relation/anchor 传播。
- 不修改 TV/AC 各自价值战场 taxonomy、销量分配和主辅排序。
- 分别重跑 TV/AC M11C draft。
- 验收：两个品类局部战场问题不降整个画像；相关拖后腿战场仍能形成锚点风险。

完成记录：

- 根因：旧 M11C 画像把“无主战场或任一战场关系需复核”作为整画像复核条件，导致用户观察、机会和拖后腿战场的局部问题扩散到 SKU；画像复核原因只记录无主战场，不能解释其余 partial。
- 修复：画像可用性仅由主战场存在、主关系状态、主战场置信度、本品类市场门槛和不可消解主候选并列决定。辅战场、机会、用户观察和拖后腿战场只按 relation/anchor 传播。
- 置信门槛：M11C 按 5 个证据域计算，自动通过门槛为 `0.80`，即至少 4/5 证据域成立；TV 当前主战场置信度为 0.8/1.0，AC 为 1.0。
- 歧义规则：先执行既有购买理由强度兜底，再比较原始战场排序；只有两阶段完整排序键全部相同才标记 `primary_battlefield_ambiguous`。205 当前 TV/AC 均为 0 个不可消解并列，不把综合分近似误判为歧义。
- 拖后腿作用域：拖后腿战场关系、代码列表、图谱和后续锚点风险完整保留，但不降低整画像。TV 16 条拖后腿关系、12 个相关画像保留，其中 8 个画像 auto-pass；AC 10 条、5 个画像全部 auto-pass。
- 量价语义：无销量行表示销量为 0，新上市观测周数短是生命周期事实；M11C 不使用固定 8 周门槛，也不据此降低画像质量。
- 版本：模块 `m11c-value-battlefield-profile-0.2.0`；TV rule `m11c_tv_value_battlefield_profile_v0.4`、taxonomy 保持 v0.2；AC rule `m11c_ac_value_battlefield_profile_v0.3`、taxonomy 保持 v0.1。
- 205 draft：TV 348 个画像、4,524 条战场分数、2 个图谱草稿，`review_required 189 -> 56`、`auto_pass 159 -> 292`；AC 144 个画像、1,584 条分数、1 个图谱草稿，`review_required 34 -> 2`、`auto_pass 110 -> 142`。
- 影响集合：同输入旧聚合策略下，TV 280 个、AC 32 个有合法主战场但被局部关系拖累的画像迁移为 auto-pass；未出现旧 auto-pass 升级为复核。
- 受限集合：TV 56 个、AC 2 个无主战场画像继续 review；两个品类合法高置信主战场仍 review 和不可消解主战场并列均为 0。
- 关系证据保真：TV 969 条、AC 43 条 relation 级复核行完整保留，其中拖后腿关系 16/10 条。质量策略单独对 taxonomy、主辅/机会/拖后腿 code、关系状态、六项分数、综合分、value effect、销量分配和证据的修改数为 0；每品类记录 20 个业务字段回归样本。
- 上游允许迁移：v0.4/v0.3 草稿消费 QF-02 至 QF-05 草稿输入，因此 TV 当前 v0.3 与草稿间 190 个画像、4,379 条战场业务字段变化；AC 画像主辅战场 0 变化，1,584 条关系证据/分数字段变化。该差异与 QF-08 质量聚合影响分开记录。
- 测试：M11C 定向测试 14 passed，覆盖 AC 市场门槛、主战场近分兜底、非主关系与拖后腿作用域、无主/低置信/真实并列以及策略切换前后分数保真；`ruff check`、Python 编译检查和 `git diff --check` 通过。
- 越界守卫：M12C、M12D TV/AC 行数前后一致；205 运行容器源码恢复原版本；未切换 current/published。
- 产物：
  - `scripts/m12d_qf08_run_m11c_tv_ac_draft.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF08_tv_ac_m11c_draft.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF08_tv_ac_m11c_draft_report.md`
- 未 stage/commit，未部署运行服务代码；只写入 TV/AC M11C draft。
- 下一任务：M12D-QF-09 M12C 完整修复与 TV/AC 分别重跑。

### M12D-QF-09 M12C 完整修复与重跑

- `l4_threshold_only`、`relaxed_pool_not_amount_quantifiable`、`l4_threshold_only_no_amount` 只限制金额量化，不否定卖点价值存在。
- `single_sku_comparison_group` 只限制对应 claim 的相对量化。
- SKU 状态只聚合当前锚点引用的卖点行，不相关行不得加分或扣分。
- 分别按 TV/AC claim taxonomy 和量化池重跑 M12C draft；TV 当前 88 个无 M12C SKU 保持 missing，AC 缺失数以 QF-01 基线为准。
- 验收：两个品类阈值说明不再让整 SKU partial；不得因此生成虚假金额、溢价或 WTP。

状态：completed。

完成记录：

- 根因：M12C 将“卖点价值可判断”“相对比较充分”“可量化金额”压进同一 `quality_flags_json`；M12D 通用状态函数又把任意行 flag 扩散成整 SKU `partial`。205 当前 TV 289 个有 M12C 的 SKU 中 271 个因此 partial；AC 140/140 因此 partial。
- 修复：每条 `claim × battlefield × pool` 输出 `quality_assessment`，分离 `value_judgement_status`、`relative_comparison_status` 和 `amount_quantification_status`；新增 `assess_m12c_claim_value_quality(..., referenced_claim_codes=...)`，只聚合当前锚点引用的 claim。
- 作用域：L4、放宽池及组样本不足只限制当前 claim/context 的金额量化；`single_sku_comparison_group` 只限制当前 claim 的相对比较解释；评论负向继续作为业务风险，不成为画像数据质量异常。
- 金额守卫：`amount_quantification_status != ready` 时，卖点贡献占比、解释性溢价、周销量贡献和周销额贡献全部强制为 0；TV/AC 草稿违规行均为 0。
- 复核传播：样本问题保留为 `claim_context_pool` warning，payload 标明 `amount_quantification_only`、`profile_blocking=false` 和 affected claim；模块运行不再生成全局 warning/review issue。
- 版本：模块 `m12c-claim-value-quantification-0.2.0`；TV `m12c_tv_claim_value_quantification_v0.2`；AC `m12c_ac_claim_value_quantification_v0.2`。TV/AC 分别读取各自 M03B/M04C/M05C/M11C/M11D/M07 版本和市场池。
- 205 draft：TV 21,315 条卖点量化行、284 个 SKU，284 个价值判断可用；AC 6,345 条、140 个 SKU，140 个价值判断可用。三轴质量覆盖分别为 21,315/21,315 和 6,345/6,345。
- 覆盖迁移：TV 旧覆盖减少 11 个、新增 6 个，净 `289 -> 284`，新增缺失 2.9%，低于 5pp 守卫；11 个减少 SKU 均具备参数、卖点、评论和 M11C 行，但 QF-08 草稿仅剩 `excluded/user_observed_battlefield`，没有可进入 M12C 的主/辅/机会战场，未补造战场。AC 覆盖保持 140，缺失保持 15。
- 状态迁移：按新作用域在同一草稿上投影，TV 284 个、AC 140 个 flag-only partial 均转为价值判断可用；真实 M12C 缺失仍为 TV 93、AC 15，不补成 0 价值。
- 上游影响隔离：当前 v0.1 与草稿间 TV 18,867 条、AC 1,655 条业务字段变化来自 QF-02 至 QF-08 草稿输入和价值战场覆盖迁移，已与本任务质量策略分开记录；本任务未降低卖点强度、样本或金额门槛。
- 测试：M12C 定向测试 21 passed；扩大到 CatForge pipeline 与 M12D context fixture 后共 51 passed，覆盖 TV/AC 版本隔离、引用 claim 过滤、L4/放宽池金额限制、单 SKU 比较组作用域、不可量化金额强制归零和既有读取兼容；`ruff check`、Python 编译和 `git diff --check` 通过。
- 越界守卫：M12D profile/anchor 表行数和最大更新时间前后一致；205 运行容器源码已恢复原版本并逐文件校验；未切换 current/published。
- 产物：
  - `scripts/m12d_qf09_run_m12c_tv_ac_draft.py`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF09_tv_ac_m12c_draft.json`
  - `docs/core3_mvp/real_data_v2/current_implementation/M12D_QF09_tv_ac_m12c_draft_report.md`
- 未 stage/commit，未部署运行服务代码；只写入 TV/AC M12C v0.2 draft。
- 下一任务：M12D-QF-10 M12D 输入质量和作用域传播。

### M12D-QF-10 M12D 输入质量和作用域传播

- 接入各模块质量 adapter，删除通用“任意 flag 即 partial”的解释。
- 用 row/relation/anchor/profile/release 作用域替代 `_combine_statuses` 最坏值传播。
- 当前 serving scope 重算输入是否存在，历史 missing 只作 lineage。
- TV/AC 分别接入各自 adapter/flag mapping，重跑 context/candidate shadow，不修改评分公式。
- 验收：两个品类未引用 warning 的锚点业务字段不变；profile blocking 仍能阻断画像。
- 状态：`completed`。实现 `m12d_input_quality_scope_v0.2` 和模块专用 `M12DInputQualityAdapter`，ContextBuilder/profile record 已携带 typed `input_quality_json`；本任务未修改锚点评分、角色、置信度、画像决策或发布控制。
- TV 影响集合：377 个 serving SKU。兼容状态中 M03B `conflict -> ready` 377、M04C `partial -> ready` 328、M05C `partial -> ready` 308、M07 `partial -> ready` 377、语义画像 `partial -> ready` 348；真实缺失仍为 M04C 49、M05C 29、语义画像 29、M11D 33、M12C 93。QF 上游草稿使 289 个 SKU 候选摘要变化，质量策略本身导致 0 个候选业务字段变化。
- AC 影响集合：155 个 serving SKU。兼容状态中 M03B `conflict -> ready` 29、M04C `partial -> ready` 121、M05C `partial -> ready` 141、M07 `partial -> ready` 155、语义画像 `partial -> ready` 144、M12C `partial -> ready` 140；真实缺失仍为 M05C/语义/M11D 11、M12C 15。QF 上游草稿使 37 个 SKU 候选摘要变化，质量策略本身导致 0 个候选业务字段变化。
- 允许迁移：历史 flag-only conflict/partial 转为 ready；row/relation/anchor 问题转存 typed issue；M12C 按本品类 taxonomy 引用 claim 重算后允许 present/missing 迁移。未允许：missing 补成 false/0、TV/AC taxonomy 串用、质量策略改候选业务字段、写 profile/anchor/version current。
- 问题分布：TV info 2,156、warning 1,216，AC info 1,468、warning 717，全部为 row/anchor scope；两个品类均无 blocking 覆盖。profile blocking 与真实 missing 的阻断语义由单元测试覆盖。
- 未影响回归：TV/AC 各记录前 20 个 serving SKU 的旧/新/移除质量 DTO 候选摘要；40 个样本中质量策略业务摘要全部不变。
- 测试：QF-10、M12D、CLI 和竞品读取兼容回归 47 passed，Ruff、Python 编译通过；205 全量 context/candidate shadow 通过，三张 M12D 持久化表行数和最大更新时间前后一致。
- 产物：`apps/api-server/app/services/core3_real_data/purchase_reason_input_quality.py`、`scripts/m12d_qf10_run_tv_ac_context_candidate_shadow.py`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF10_tv_ac_context_candidate_shadow.json`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF10_tv_ac_context_candidate_shadow_report.md`。
- 205 临时覆盖源码已恢复并逐文件校验，`/healthz` 与 `/readyz` 正常；未 stage/commit，未部署，未写 current/published。
- 下一任务：M12D-QF-11 M12D 锚点级评分和惩罚。

### M12D-QF-11 M12D 锚点级评分

- 删除 `missing_or_partial_inputs` 的统一生成、-1 分和 -0.1 置信度。
- 为真实 issue 显式配置 affected domain、anchor penalty、confidence impact 和 role cap。
- TV/AC 各自的价格/WTP 理由严格使用本品类 M12C 或价格+评论+市场替代证据；功能理由按本品类对应证据成立。
- 分别重跑 TV/AC 锚点评分 shadow，不改变画像状态和发布逻辑。
- 验收：两个品类 info 零影响；无 affected anchor 不扣分；真实 blocking 不能成为 core。
- 状态：`completed`。新增 `M12DAnchorIssuePolicy` 和锚点级质量评估；删除锚点上的 `missing_or_partial_inputs`、全局评论负向数量和全局 M12C role/drag 传播。本任务未修改画像状态机、review、核心锚点族收敛或发布门槛。
- TV 影响集合：377 SKU、3,542 个候选锚点，候选集合保持不变；335 SKU 的 2,433 个锚点评分业务字段发生允许迁移。角色由 core 1,106/risk 696/supporting 1,198/weak 542 迁移为 core 807/risk 242/supporting 1,624/weak 869；移除 749 个全局 missing 风险。
- AC 影响集合：155 SKU、1,879 个候选锚点，候选集合保持不变；150 SKU 的 1,776 个锚点评分业务字段发生允许迁移。角色由 core 70/risk 1,493/supporting 123/weak 193 迁移为 core 535/risk 191/supporting 702/weak 451；移除 154 个全局 missing 风险。
- 允许迁移：删除无关输入的统一 -1/-0.1；同域 warning 取最大惩罚；相关评论矛盾和 M12C 负向按锚点扣分；候选相关 drag 保留 hard risk；无当前锚点 claim 映射的 M12C 域不计分；价格理由按本品类 M12C 或评论+价格市场替代门槛封顶。未允许：改候选集合、跨品类 claim/reason、info 扣分、blocking 成为 core、改 source refs/支持摘要/input fingerprint。
- scoped issue 应用：TV 评论矛盾 998、M09C/M10C/M11C 主关系限制 71/707/390、M12C 相关负向 440、市场池类 73；AC 评论矛盾 462、主关系限制 7/115/10、M12C 相关负向 468、市场池类 192。warning 保留但不自动转 risk_drag。
- 验收守卫：两个品类新增全局 missing 风险均为 0、info 误影响均为 0、blocking 成为 core 均为 0、候选增删均为 0、非目标字段变化均为 0；TV/AC 各记录 20 个不同 SKU 的非目标字段回归样本。
- 测试：QF-11、M12D、CLI 和竞品读取兼容回归 55 passed；Ruff、Python 编译和差异格式检查通过。
- 产物：`apps/api-server/app/services/core3_real_data/purchase_reason_anchor_quality.py`、`scripts/m12d_qf11_run_tv_ac_anchor_scoring_shadow.py`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF11_tv_ac_anchor_scoring_shadow.json`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF11_tv_ac_anchor_scoring_shadow_report.md`。
- 205 仅执行两阶段只读 shadow，临时覆盖源码已恢复并逐文件校验，`/healthz` 与 `/readyz` 正常；三张 M12D 持久化表前后不变，未 stage/commit、未部署、未写 current/published。
- 下一任务：M12D-QF-12 M12D 画像置信度、状态、复核和核心锚点收敛。

### M12D-QF-12 M12D 画像决策

- 画像置信度只聚合最多 3 个核心锚点，不再按 partial 输入数量重复扣分。
- `review_required` 只由会改变结论的 blocking 问题触发。
- 实现 ready、ready_limited、weak_expression_only、missing_input、failed 状态机。
- 核心锚点按分数、置信度、强域数量和本品类 taxonomy priority 排序，同 family 去重且最多 3 个。
- 分别重跑 TV/AC 画像 shadow。
- 验收：两个品类状态互斥完备；核心锚点 <=3；一般 warning 不进入人工复核。
- 状态：`completed`。画像状态与 `review_required` 已解耦；保留旧枚举仅用于读取历史记录，新画像只生成 `ready`、`ready_limited`、`weak_expression_only`、`missing_input`、`failed`。
- 核心收敛：按 adjusted score、anchor confidence、strong domain count、taxonomy rank 和 anchor code 稳定排序；同 family 只保留第一名，最多 3 个。TV 807 个原核心保留 501、降辅助 306；AC 535 个原核心保留 321、降辅助 214。两个品类均无核心超限或同族重复。
- 置信度：只用已选核心按 `0.60/0.25/0.15` 聚合，1/2 个核心时归一化已有权重；没有核心时 `profile_confidence=0`，最高辅助置信度单独写入 `confidence_basis_json.limited_confidence`。不再按 missing/partial 输入数量扣分。
- 复核：仅 profile/release blocking 或会改变核心角色的 anchor blocking 触发；风险锚点、普通 warning、无核心、低置信和输入缺失均不自动触发。205 当前 typed issue 无 blocking，因此 TV `203 -> 0`、AC `76 -> 0`；synthetic blocking 正反边界由单元测试覆盖。
- TV 影子：377 SKU 全部写入新决策依据；状态由 ready 178/ready_degraded 117/review 状态 64/weak 18 迁移为 ready 238/limited 94/weak 45；核心数由最多 9 个收敛为 0 个 139、1 个 67、2 个 79、3 个 92。
- AC 影子：155 SKU 全部写入新决策依据；状态由 ready 74/ready_degraded 29/review 状态 52 迁移为 ready 130/limited 23/weak 2；核心数收敛为 0 个 25、1 个 16、2 个 37、3 个 77。
- 允许迁移：画像状态、核心/辅助列表、画像置信度、决策依据和 blocking-only review；核心超限/同族重复可 `core_payment -> supporting`。未允许：候选增删、锚点评分/置信度/强度/证据/风险/source refs/input fingerprint 变化、跨品类 taxonomy、发布状态变化。
- 验收守卫：TV/AC 画像和锚点集合无增删，锚点非目标字段变化 0，非法状态 0，核心上限/同族违规 0，置信度公式违规 0，复核门槛违规 0；各记录 20 个不同 SKU 的未影响锚点字段回归样本。
- 发布门槛预检：TV ready 63.13%、ready+limited 88.06%、无核心 36.87%；AC ready 83.87%、ready+limited 98.71%、无核心 16.13%。两个品类均未完全达到 QF-13 既定门槛；这是显式风险，不在 QF-12 内放宽阈值或伪造核心，QF-13 必须如实阻断未达标品类，QF-14/QF-15 继续解释无核心/弱画像。
- 测试：M12D、质量契约、CLI 和竞品读取兼容回归 63 passed；Ruff、Python 编译和差异格式检查通过。
- 产物：`apps/api-server/app/services/core3_real_data/purchase_reason_profile_scoring.py`、`apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`、`apps/api-server/app/services/core3_real_data/purchase_reason_profile_runner.py`、`scripts/m12d_qf12_run_tv_ac_profile_decision_shadow.py`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF12_tv_ac_profile_decision_shadow.json`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF12_tv_ac_profile_decision_shadow_report.md`。
- 205 只执行两阶段只读 shadow，临时覆盖源码已恢复并逐文件校验，`/healthz` 与 `/readyz` 正常；三张 M12D 持久化表前后一致，未 stage/commit、未部署、未写 current/published。
- 下一任务：M12D-QF-13 M12D 发布控制。

### M12D-QF-13 M12D 发布控制

- 实现 release quality 状态。
- TV、AC 分别计算门槛，不合并分母；共同目标为 ready>=85%、ready+limited>=95%、review<=15%、missing+failed<=5%、core missing<=15%。
- 在任一品类中同一 blocking issue 覆盖 >20% 时，生成该品类 release-level system issue 并阻断该品类发布。
- 验收：任一品类 100% info 不阻断、21% blocking 阻断；一个品类通过不能覆盖另一个品类失败；blocked 版本不能成为 strong current。
- 状态：`completed`。新增独立 `M12DReleaseQualityEvaluator`，runner 只消费 QF-12 画像并把 typed evaluation 写入版本质量摘要；本任务未修改候选、锚点评分、画像角色或状态机。
- 门槛：TV/AC 分别使用本品类 expected SKU 分母计算生成成功率 `>=98%`、ready `>=85%`、ready+limited `>=95%`、review `<=15%`、missing+failed `<=5%`、无核心 `<=15%` 和重点 SKU 通过率 `=100%`；未执行重点验证时版本最多 limited，不能伪装 ready。
- 系统异常：按 `issue_code + distinct sku_code` 聚合 typed blocking，覆盖率严格 `>20%` 才生成 release-level `systemic_blocking_issue_coverage` 并判 blocked；20% 不阻断，21% 阻断。info/warning 不进入 blocking 覆盖。
- 发布守卫：`unassessed` 和 `blocked` 一律拒绝发布；`limited` 必须显式 `allow_limited=True` 且提供非 system 审批人；所有检查在撤销旧 current 之前执行。查询端过滤历史 blocked current，确保 blocked 不能成为强消费版本。
- 下游守卫：读取契约输出真实 `release_quality_status`；ready 才是新版本强消费门槛，limited 强制 `published_degraded`，blocked 强制不可用；QF-12 `ready_limited` 明确进入降级消费。历史已发布 unassessed 版本保持原画像级消费行为，避免 QF-18 部署代码后、QF-19 新版本切换前先改变线上排序；repository 已禁止任何新 unassessed 版本发布。
- TV 影响集合：377 SKU，画像 ready 238/limited 94/weak 45，发布质量影子 `unassessed -> limited`。生成成功率 100%、review 0%、missing+failed 0% 通过；ready 63.13%、ready+limited 88.06%、无核心 36.87% 未通过。即使假设重点 SKU 100% 通过，仍有三项门槛失败。
- AC 影响集合：155 SKU，画像 ready 130/limited 23/weak 2，发布质量影子 `unassessed -> limited`。生成成功率 100%、ready+limited 98.71%、review 0%、missing+failed 0% 通过；ready 83.87%、无核心 16.13% 未通过。即使假设重点 SKU 100% 通过，仍有两项门槛失败。
- blocking 结果：205 当前 TV/AC typed issue 均无 blocking 覆盖，因此 system issue 均为 0；不为门槛失败伪造 blocking。两个品类均独立判 limited，一个品类的分布没有进入另一个品类分母。
- 允许迁移：新 draft 版本的 `release_quality_status`、版本质量摘要、门槛失败原因和 release-level system issue；未允许画像/锚点字段变化、跨品类平均、降低门槛或自动发布。TV/AC 画像指纹前后一致，各记录 20 个未影响回归样本。
- 测试：M12D 质量/画像/runner、发布 repository、下游 contract、CLI 和竞品读取/报告相关回归 168 passed；覆盖 100% info、20%/21% blocking、重点验证全过/未过/未执行、TV/AC 隔离、blocked/unassessed 拒绝、limited 人工批准和历史 unassessed 消费兼容。Ruff、Python 编译、JSON 和差异格式检查通过。
- 产物：`apps/api-server/app/services/core3_real_data/purchase_reason_release_quality.py`、`apps/api-server/app/services/core3_real_data/purchase_reason_profile_schemas.py`、`apps/api-server/app/services/core3_real_data/purchase_reason_profile_runner.py`、`apps/api-server/app/services/core3_real_data/purchase_reason_profile_repositories.py`、`apps/api-server/app/services/core3_real_data/purchase_reason_profile_contract.py`、`scripts/m12d_qf13_run_tv_ac_release_quality_shadow.py`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF13_tv_ac_release_quality_shadow.json`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF13_tv_ac_release_quality_shadow_report.md`。
- 205 只执行只读发布质量 shadow，三张 M12D 表行数和最大更新时间前后一致；临时源码已恢复并逐文件校验，`/healthz` 与 `/readyz` 正常。未 stage/commit、未部署、未切 current/published。
- 下一任务：M12D-QF-14 重点 SKU 影子验证。当前 TV/AC 均为 limited，QF-14/QF-15 必须继续解释并修复无核心/弱画像，未达到 ready 门槛前不得进入正式发布。

### M12D-QF-14 重点 SKU 影子验证

状态：completed。

- TV 验证 65E7Q、A7H PRO、Q9L PRO、A6F ULTRA、小米、华为及高低价/大小尺寸边界 SKU；AC 验证既有重点柜机/挂机及匹数、价格边界 SKU。
- 输出每个状态和锚点变化对应的修复原因。
- 不写 current，不改变线上 Top 3。
- 验收：两个品类价格价值弱表达不得误升核心，真实证据不足仍保持 limited/weak。

完成记录：

- 205 只读重算 TV 377、AC 155 个 SKU，并从真实市场画像自动选择 TV 10 个、AC 18 个重点与边界样本；TV 覆盖 65E7Q、A7H PRO、Q9L PRO、A6F ULTRA、小米、华为、均价和尺寸边界，AC 覆盖 15 个既有重点样本、挂机/柜机匹数边界和均价边界，无固定样本缺失。
- 当前发布到 QF12 影子分布：TV `359 ready_degraded + 18 weak -> 238 ready + 94 ready_limited + 45 weak`，无核心 `120 -> 139`；AC `50 ready_degraded + 98 review_required + 7 weak -> 130 ready + 23 ready_limited + 2 weak`，无核心 `135 -> 25`。结果与 QF12 快照完全一致，没有新增未声明迁移。
- QF11 到 QF12 仅发生核心收敛：TV 306、AC 214 个锚点由 `core_payment` 降为 `supporting`，原因均由核心最多 3 个或锚点族去重记录；其他角色不变。
- 价格价值门槛覆盖：TV 239、AC 46 个价格理由锚点命中弱表达或核心证据不足门槛，误升核心均为 0。65E7Q 的 `same_price_core_config_gain` 明确因价格价值核心证据不足保持 `supporting`，未进入核心成交理由。
- 无核心归因：TV 139 个均落在证据或业务门槛不足，其中 92 个涉及价格价值核心证据不足、20 个全部锚点证据弱或不足、32 个含风险拖拽；AC 25 个中 14 个涉及价格价值核心证据不足、11 个卖点价值风险角色占主导。未发现强锚点因场景门槛被系统性误杀，本任务不新增评分补丁。
- 真实证据不足保持受限：TV 45 个、AC 2 个 `weak_expression_only` 未被提级；A7H PRO、华为重点样本及 AC 匹数边界中的无核心样本按最高支持理由置信度保持 `ready_limited` 或 `weak_expression_only`。
- 影响集合：全部 TV/AC SKU 只读重算；允许变化仅为 QF11 到 QF12 的核心收敛和当前发布到影子结果的记录，不写库。两个品类分别记录 20 个非重点未影响回归样本。
- 测试：M12D 画像、质量契约和竞品消费相关回归 105 passed；Ruff、Python 编译、JSON 结构和差异格式检查通过。
- 205 守卫：三张 M12D 持久化表的行数和最大更新时间前后一致；临时源码恢复为原哈希，`/healthz` 和 `/readyz` 正常；未发布 current，未运行竞品智能体，未改变线上 Top 3。
- 产物：`scripts/m12d_qf14_validate_tv_ac_focus_boundaries.py`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF14_tv_ac_focus_boundary_shadow.json`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF14_tv_ac_focus_boundary_shadow_report.md`。
- 下一任务：M12D-QF-15 TV/AC 全链路 draft 重跑和验收。QF15 必须使用 QF02-QF13 的双品类 draft 规则链，不得把本轮当前发布上游数据的分布直接当作发布结果。

### M12D-QF-15 TV/AC 全链路 draft 重跑

状态：completed (superseded)。旧口径全链路执行一致性通过、发布质量门槛未通过的 blocked 结论保留为历史事实；经批准的 RP-G01 至 G08 将购买理由成立度、购买阻力和版本消费能力分层后，G06 双品类全量影子结果均为 ready，旧阻塞不再作为 QF16 前置。

- TV、AC 分别按 M03B -> M04C/M05C -> M07 -> M09C/M10C/M11C -> M12C -> M12D 顺序生成一致的新 draft 链路。
- 两个品类分别输出状态迁移、锚点增删、置信度变化、问题覆盖和未影响 SKU 报告。
- TV 约 332 ready、33 limited、12 weak 是影子参照；AC 参照由 QF-01 基线和各模块修复结果形成，均不是强制配额。
- 验收：两个品类分别达到发布门槛；任一品类偏离自身影子参照超过 5pp 必须解释和复审，不得直接发布。

执行记录：

- 205 分品类按 `M03B -> M04C/M05C -> M07 -> M09C/M10C/M11C -> M12C -> M12D -> release quality` 完整重跑；QF02-QF09 只写各自新版 draft，M12D 和发布质量只读影子，未写 current/published。
- 模块一致性：M03B、M04C、M05C、M07、M12C 的 `after` 摘要与批准产物完全一致；M09C、M10C、M11C 仅 TV `score_business_digest` 因 M07 幂等重写刷新 evidence lineage 标识，画像数量、关系状态、分数分布和其余业务摘要一致。QF10 上下文/候选结果与批准快照完全一致，M12D 重跑前后归一化业务结果完全一致。
- M07 运行事件：全部 TV/AC draft 块提交后，旧后置验收再次整体载入约 140 万市场池成员，容器因内存不足以 `137` 退出；未重复写 draft，随后用批准影子收据执行 `validate-persisted-only` 数据库聚合紧凑校验并通过。该事件不影响 draft 完整性或业务结果。
- TV draft：377 SKU，`238 ready / 94 ready_limited / 45 weak`，无核心 139；发布质量 `limited`。未通过 ready `63.13% < 85%`、ready+limited `88.06% < 95%`、无核心 `36.87% > 15%`。达到门槛至少还需 83 个 SKU 进入 ready、27 个 SKU 进入 ready/limited，并将无核心减少 83 个。
- AC draft：155 SKU，`130 ready / 23 ready_limited / 2 weak`，无核心 25；发布质量 `limited`。未通过 ready `83.87% < 85%`、无核心 `16.13% > 15%`。达到门槛至少还需 2 个 SKU 进入 ready，并将无核心减少 2 个。
- TV 对 QF01 早期可行性投影偏差：ready `-24.93pp`、limited `+16.18pp`、weak `+8.75pp`。原因已由 QF11 锚点作用域门槛、QF12 核心族收敛和 QF14 无核心逐项归因解释；未发现系统性误杀，不能通过降低证据门槛或伪造核心消除。
- 重点/边界与价格守卫：TV 10、AC 18 个重点/边界 SKU 全部完成验证；价格价值门槛观察 TV 239、AC 46，误升核心均为 0。TV/AC 各记录 20 个非重点未影响回归样本。
- 系统守卫：两个品类均无 release-level blocking system issue；M12D profile/anchor/version 表在全链路前后不变；TV/AC taxonomy、市场池和版本隔离，无跨品类候选。
- 测试：M03B-M12D、质量契约和竞品读取相关回归 182 passed；Ruff、Python 编译、JSON 和差异格式检查通过。205 临时源码恢复为原哈希，`/readyz` 正常。
- 产物：`scripts/m12d_qf15_aggregate_tv_ac_full_chain.py`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF15_tv_ac_full_chain_draft.json`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF15_tv_ac_full_chain_draft_report.md`、QF15 pre/post focus、context 和 release-quality 技术收据。
- 阻塞条件：两个品类均未达到 QF15 冻结的发布门槛。不得进入 QF16；需要先决定补充可追溯真实证据，或单独发起发布门槛定义复审。不得以降低强证据/场景/弱表达门槛、添加 SKU/品牌白名单或跨品类平均方式解除阻塞。
- `2026-07-12` 回填：上述阻塞条件只适用于旧混合口径，不能改写为当时已通过。RP-G06 在新批准口径下全量只读重算 TV `335/13/29`、AC `143/1/11`，两个品类 release quality 均为 ready；RP-G08 集成验收通过，因此 QF15 记为 `completed (superseded)`，允许以 RP-G07/G08 收据承接 QF16/QF17。

### M12D-QF-15A TV 139 个无核心 SKU 门槛反事实审计

状态：completed。只读审计完成；未修改生产评分、数据库或 current，未解除 QF15 阻塞。

- 基线复现：TV 377 SKU，`238 ready / 94 ready_limited / 45 weak`，无核心 139；与 QF15 完全一致。
- `9.0 -> 8.5`：新增核心 0，说明不存在介于 8.5 和 9.0 的可恢复集合。
- 全局 `9.0 -> 8.0`：新增核心 47，但其中 25 个包含评论错维度、评论冲突、M12C 负向或市场样本不足，并会改变 56 个既有 ready SKU 的核心组合；该方案拒绝。
- 取消全部价格理由门槛并降至 8.0：仅新增 48，其中 27 个证据越界，并改变 57 个既有 ready SKU；该方案拒绝。
- 单独放宽客观性价比价格门槛：新增 0；价格价值门槛不是当前主要瓶颈，不建议修改。
- 原始评论对齐复核：11 个初筛锚点虽被评分器记为 `comment_perception`，但 M05C 原始事实中没有与该购买理由同维度的正向评论；例如游戏理由没有游戏/高刷评论。这些锚点不得用泛化好评替代，已从兜底集合移除。
- 有守卫的无核心专属 8 分兜底：只处理基线无核心 SKU，保留双强证据域、场景和现行价格门槛，要求评论与锚点同维度，并逐锚点排除评论冲突、M12C 负向及市场样本风险；可进入抽检 29，证据越界 0，既有 ready 核心变化 0，五个重点 TV SKU 变化 0。
- 兜底后测算：`267 ready / 67 ready_limited / 43 weak`，无核心 110；ready 70.82%、ready+limited 88.59%、无核心 29.18%，仍不满足冻结发布门槛。
- 结论：29 个属于可谨慎实施的边界集合，110 个不应继续靠统一降分或取消证据门槛处理。若实施，必须另立 QF15B 生产规则和业务抽检任务，并先修正评论证据必须按锚点对齐的生产契约；同时需单独复审版本级发布质量是否应把全部 SKU 一并降级，不能用本审计直接进入 QF16。
- 产物：`scripts/m12d_qf15a_audit_tv_no_core_thresholds.py`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF15A_tv_no_core_threshold_audit.json`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF15A_tv_no_core_threshold_audit.csv`、`docs/core3_mvp/real_data_v2/current_implementation/M12D_QF15A_tv_no_core_threshold_audit_report.md`。
- 验证：Ruff、Python 编译通过；205 `catforge_dev` 只读全量重算通过；M12D profile/anchor/version 三张表前后计数和 `max(updated_at)` 完全不变。

### M12D-QF-16 竞品消费和排序回归

状态：completed by M12D-RP-G07。

- ready 可强比较；ready_limited 只做局部展示；weak/missing 不产生强替代结论；blocked 版本不读。
- 使用 draft fixture 分别验证 TV、AC；TV 覆盖 65E7Q 和至少 10 个目标 SKU，AC 覆盖至少 10 个重点柜机/挂机 SKU 的 Top 3、角色槽位和锚点分。
- 不为恢复旧 Top 3 硬编码型号。
- 验收：两个品类每次排名变化可追溯到业务证据；竞品智能体不生成或修改 M12D。
- 执行回填：TV 10 个目标/90 pair、AC 18 个目标/306 pair；proposition 误计、压力混淆、Top 3 追溯失败和 PM 内部码泄漏均为 0。详细收据见 `M12D_RP_G07_competitor_consumption_shadow.json`。

### M12D-QF-17 跨品类隔离和共享链路总回归

状态：completed by M12D-RP-G08。

- 汇总运行 TV/AC taxonomy、M12D fixture、竞品契约和类别隔离测试。
- 校验 TV 规则不进入 AC，AC 规则不进入 TV；两个品类版本、batch、阈值和发布统计互不串用。
- 验收：TV/AC 均无未声明状态迁移，共享代码和类别隔离测试通过。
- 执行回填：M03B-M12D、竞品 reader、CLI 和报告集成回归 `378 passed`；TV/AC 各自 taxonomy、SKU 前缀、发布统计、重点样本和 20 个未影响样本隔离检查全部通过。详细收据见 `M12D_RP_G08_integrated_acceptance.json`。

### M12D-QF-18 提交并部署代码到 205

- 用户已授权以后同类代码提交与部署无需单独审批；只提交本任务链产生的文件。
- 部署代码和 migration，保留备份和回滚点。
- 此任务不执行正式全量发布。
- 验收：服务 healthy/ready，代码和 schema 版本一致。
- 执行回填：提交 `67a11d6` 和 migration 修复 `adeab0a` 已推送并部署；205 Git revision `adeab0a`，Alembic `0044_core3_m12d_reason_pressure`，服务 healthy/ready，仓库与容器源码 hash 一致。回滚点为 `/var/backups/catforge/m12d-rp-g09-20260712_084936`。
- 数据守卫：三张 M12D 表行数和最大更新时间不变，未执行正式重跑或切换 current/published。详细收据见 `M12D_RP_G09_deployment_receipt.json`。

### M12D-QF-19 205 全量重跑、发布和上线验收

- 在 205 分别按全链路顺序重跑 TV 和 AC，先生成两个品类各自 draft。
- 每个品类只有在自身质量门槛全部通过后才切换该品类 current published-ready；旧异常版本分别 deprecated。
- 验证 TV 377 SKU 分布、AC 全量分布、两个品类重点竞品结果、飞书报告和内部 code 隔离。
- 验收：TV/AC 各只有一个 current published-ready 版本；统计分别与 M12D-QF-15 一致；任一品类失败只阻断该品类切换并保留回滚点。

## 7. 单任务执行模板

```text
目标：只执行一个 M12D-QF-xx 模块闭环任务，不跨任务。

执行前：
- 读取任务链、调度、系统审计、需求和详细设计。
- 记录预计影响集合、允许迁移和至少 20 个未影响回归 SKU。

执行中：
- 修复该模块列出的全部问题。
- 增加该模块 TV/AC 正例、反例和边界测试。
- 分别重跑 TV/AC 的该模块 draft/影子结果，不顺带执行下一模块。

执行后：
- 分品类输出前后分布、受影响/未影响 SKU 和测试结果。
- 更新任务状态、产物和下一个任务。
- 不 stage/commit，除非用户明确要求。
```

## 8. 当前指针

调度已启用；当前 goal 完成后的下一个任务：

```text
HISTORICAL: M12D-QF-15 旧口径全链路执行通过，但发布质量门槛未通过；该 blocked 事实保留。
COMPLETED: RP-G06/G08 按新批准分层口径完成双品类全量影子与集成验收，QF15 记为 completed (superseded)。
COMPLETED: M12D-QF-16 由 RP-G07 完成；M12D-QF-17 由 RP-G08 完成。
COMPLETED: M12D-QF-18 / M12D-RP-G09 已提交部署，205 revision 为 adeab0a，Alembic 为 0044。
PAUSED: M12D-QF-19 / M12D-RP-G10 正式全量重跑和发布需要明确批准。
```
