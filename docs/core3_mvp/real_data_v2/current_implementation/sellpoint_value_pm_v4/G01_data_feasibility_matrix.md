# G01 用户卖点价值 V4 数据可行性与 205 只读审计

审计时间：2026-07-11 18:32-18:55 CST

环境：`deploy@123.56.42.205` / `catforge_dev`

方式：SSH 进入健康 API 容器，通过 SQLAlchemy 开启只读事务并执行 `SELECT`；未写数据库、未修改 205 文件、未调用发布能力。

## 1. 结论

现有数据可以支撑 V4 的主体业务结构：

> 价值战场及市场空间 -> SKU 采购理由假设 -> 用户购后实际体验 -> 支撑卖点组合 -> 基础/同价值/上探对照 -> 当前市场兑现层级

但不能把“有可比池”直接等同于“卖点 WTP 可识别”。当前应分三层处理：

- 可稳定输出：价值战场、采购理由假设、用户实际体验、卖点组合、SKU 在战场中的量价表现；
- 条件输出：相对体验、同价选择关联、整机相对价格承接；
- 严格门禁后才输出：卖点组合市场隐含 WTP。65E7Q 当前不满足该门禁。

## 2. requirement -> source -> field -> version -> quality 矩阵

| 需求字段 | 权威来源与字段 | 2026-07-11 可读版本 | 覆盖/质量 | V4 使用边界 |
| --- | --- | --- | --- | --- |
| 主/辅/机会/拖累战场 | M11C `core3_sku_value_battlefield_profile`：`primary_battlefield_code`、三组 battlefield JSON | `m11c_tv_value_battlefield_profile_v0.4` / taxonomy v0.2 | 348 SKU；6/19 273、6/13 75 | 可直接读；必须按 rule version 解析，不得只看 `is_current` |
| 战场市场空间 | M11D `core3_semantic_market_dimension_summary`：销量、销额、份额、窗口 | `m11d_semantic_market_allocation_v0.1` | 344 SKU 的 allocation；生成于 7/8 | 是解释性分配，不是真实购买归因；与 M11C v0.4 存在时间差 |
| SKU 战场贡献 | M11D allocation：`allocation_weight`、allocated sales、confidence | 同上 | 65E7Q 主战场 allocation 可读 | 只作战场口径权重，不当作卖点选择贡献 |
| 采购理由/价值锚点 | M12D profile + anchor：role、evidence strength、confidence | 已发布 `m12d_tv_purchase_reason_profile_v0_1_draft` | 377 SKU；0 ready、359 ready_degraded、18 weak-only；100% review required | 只能作为已发布采购理由假设；当前版本引用旧上游，不得与新上游静默拼接 |
| 参数事实和档位 | M03B `param_values_json`、core groups、conflict、profile hash | `m03b_tv_param_profile_v0.2` | 377 SKU；6/19 293、6/13 84；最新 conflict_count 全部为 0 | 可读产品事实；缺失仍为 unknown |
| 卖点事实 | M04C claim/fact codes、profile hash | `m04c_tv_claim_fact_profile_v0.2` | 328 SKU | 表达和事实必须分开；无行不能补成 false |
| 用户实际体验 | M05C 评论事实、正负向、支持/反驳 codes、evidence refs | `m05c_tv_comment_fact_profile_v0.2` | 348 SKU | 只代表购后体验；不推断购买前传播心智 |
| 周×平台量价 | M01 clean weekly：week、platform、sales、price、clean hash | `m01_clean_v1` | 65E7Q 24 周、2 平台、48 行 | 可建共同市场单元；不得外推观测范围 |
| SKU 市场画像 | M07 full/latest/4w/8w/12w：price、volume、volatility、pool percentile | `m07_market_profile_v2` | 377 SKU × 5 窗口 | 可用于量价表现和样本门禁 |
| 任务与客群 | M09C/M10C profile | M09C v0.3 / M10C v0.3 | 各 348 SKU | 用于场景/人群语义；缺 29 SKU 降级 |
| 竞品角色 | M14 selection run；缺失时既有 competitor-set fallback | M14 `core3_mvp_real_data_v2_m14_v1` | 仅旧批次 84 target；65E7Q 无 M14 run | 必须保留 `M14` 与 `fallback` 两种 provenance |
| M12C 可比池/参数档位 | context pool：with/without/unknown、numeric param tier、pool hash | `m12c_tv_claim_value_quantification_v0.2` | 284 SKU；65E7Q 亮度/控光/高刷均有池 | 仅复用池和档位；旧分摊金额不进入 V4 WTP |
| 促销 | raw `promotion_flag`；M07 `promotion_suspect_flag` | raw + M07 v2 | raw TV 仅 5 行；M07 派生疑似 149/377 | 真实促销控制不可用；疑似标记只能排除/降级 |
| 库存 | 无 | 无 | information_schema 未找到 inventory/stock 字段 | 不得声称已控制库存；WTP 模型必须记录该限制 |
| 异常价格 | clean weekly `price_check_status/delta` | m01 clean v1 | 18,694 行均为 `ok` | 可排除校验异常；不能替代促销/库存控制 |

## 3. 权威版本解析结论

`is_current=true` 不是跨规则版本的唯一 current。以 M11C 65E7Q 为例，v0.1、v0.2、v0.3、v0.4 都保留 current 行。V4 必须采用以下顺序：

1. 优先读取显式发布版本（M12D）；
2. 其他模块按配置的允许 rule version 精确过滤；
3. 在同 rule version 内按 serving scope、batch 和 created_at 解析；
4. source refs 与实际选中版本不一致时返回 `version_lineage_conflict`；
5. 禁止 `is_current=true + 最新 created_at` 跨版本混读。

当前已发布 M12D 的 65E7Q source refs 明确引用：M03B v0.1、M04C v0.1、M12C v0.1。当前最新事实层分别是 M03B v0.2、M04C v0.2、M12C v0.2。因此 G02/G03 必须把“同一分析使用一套可追溯版本”作为硬闸门。

## 4. 65E7Q 真实市场与战场快照

- SKU：`TV00029112`，海信 65E7Q；
- M11C v0.4 主战场：`BF_PREMIUM_PICTURE_UPGRADE`；辅战场：智能互联、游戏体育流畅；
- M07 v2 全窗口：24 周、2 平台、48 行，销量 6,023，销额 35,833,186.49，均价 5,949.39，价格范围 4,764.89-7,055.83；
- M11D 主战场：战场估计销量 155,240.77、估计销额 1,259,550,167.29；65E7Q allocation weight 0.438110、解释性分配销量 2,638.74；
- M12D 已发布采购理由：画质配置解释加价、同尺寸画质越级获得感、贵得值的体验升级、影音用户愿为画质升级付费；
- M03B v0.2 画质/游戏核心事实：MiniLED、亮度 5200、控光分区 1920、刷新率 300、RAM 4、存储 64；最新 `conflict_count=0`；
- 既有竞品 fallback：基础价值 65E5Q、同价值 L65MC-SP、上探 K-65XR50。65E7Q 没有 M14 selection run。

M11D 的战场空间和 allocation 是按语义权重分配的市场解释，不代表“有 43.8% 用户因该战场购买”，也不能直接转成卖点金额。

## 5. M12C 中间事实可用，但不能直接成为 WTP

65E7Q 在 65 寸高端画质战场存在真实可比池：

| 能力 | pool SKU | with | without | unknown | 当前可用结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| HDR/高亮档位 | 8 | 3 | 2 | 3 | 可以构造亮度档位候选；unknown 较多，不能直接估金额 |
| 分区控光档位 | 8 | 4 | 4 | 0 | 具备 with/without；仍需控制品牌、其他配置和共同周×平台 |
| 高刷新率档位 | 8 | 1 | 7 | 0 | with 只有 1 个，易与目标 SKU 身份共线 |
| 色彩档位 | 8 | 5 | 3 | 0 | 有档位差；需证明能独立变化 |

这些池的 `sample_status=sufficient` 只表示旧 M12C 的池规则通过，不等于 V4 的因果/需求模型识别门槛通过。

## 6. 五类真实 cohort 与量化上限

| cohort | 真实样本/窗口 | 识别判断 | 当前最高允许层级 |
| --- | --- | --- | --- |
| 可识别候选 | 75E5Q vs 75E5Q-PRO：同品牌、同尺寸、同主战场、刷新/RAM/存储相同，画质亮度/分区形成业务档位差，双方均有多周价格变化 | 具备高可比候选，不代表已通过模型；还需共同周×平台、品牌系列固定效应、价格方向和敏感性门禁 | G01 只确认可进入“相对体验/选择模型候选”；WTP 待 G06 |
| 只有同价值竞品 | 65E7Q vs L65MC-SP：同尺寸、同战场、亮度 5200、分区 1920 vs 1792、刷新 300 vs 330、RAM/存储相同 | 只能说明同价值方案间整机选择和价格承接，无法定义“没有该价值”的反事实 | 市场选择关联/整机价格承接；不输出卖点增量 WTP |
| 完全共线 | 65E7Q 65 寸高端画质 cohort：MiniLED、高亮、分区、高刷等能力随整机方案共同变化 | 可以把能力合并为“高端画质+游戏流畅组合”，不能拆 MiniLED、亮度、分区、高刷单项金额 | 组合/整机层；单项 WTP 不可识别 |
| 无时间价格变化 | 65E7Q `latest_week` 窗口：单周、2 平台、2 行 | 有截面价格和销量，但没有时间价格响应；不能建价格曲线 | 当周量价位置；不输出价格敏感度或 WTP |
| 版本事实冲突 | 65E7Q 已发布 M12D 记为 param conflict，最新 M03B v0.2 conflict_count=0；M12D source refs 为 v0.1 | 必须阻断混合版本的受影响结论，不能择一自证 | 只展示冲突和各自版本事实；不输出 WTP |

## 7. 65E7Q 当前量化上限

205 只读运行 `sellpoint-value-pm` 的现状为：

- 数据门显示 ready；
- 只有 1 个强直接价格对照（L65MC-SP）；
- 同价条件选择份额 0.613，同价优势 +11.3pp；
- 方法等级为单一竞品同价销量承接观察；
- 当前价格情景除基准点外全部因样本不足置空；
- 选择保持价差为空；
- 所有单卖点均提示无法隔离到价值组合。

因此 V4 对 65E7Q 的当前上限是：

> 用户价值成立 + 整机同价选择关联；不得输出亮度、控光、MiniLED、高刷或“高端画质组合”的市场隐含 WTP。

## 8. 进入 G02 的约束

1. 设计 `version_lineage_conflict`，禁止发布 M12D 与最新上游静默混读；
2. counterfactual provenance 必须区分 M14、fallback、same-family candidate 和 model-selected candidate；
3. 促销只能用疑似标记降级，库存明确为 unavailable；
4. 量化层级必须独立于价值是否成立；
5. 只有同价值竞品时封顶为选择关联/整机承接；
6. 单周窗口、完全共线和价格系数异常时 WTP 必须为空；
7. 任何 M12C 旧金额均不进入 V4 WTP 真值。

## 9. 只读与健康证据

- `healthz={"status":"ok"}`；
- `readyz={"status":"ready","database":"ok"}`；
- 数据库查询全部在 `SET TRANSACTION READ ONLY` 后执行；
- 未执行 INSERT/UPDATE/DELETE、迁移、上游重跑、报告发布或部署。
