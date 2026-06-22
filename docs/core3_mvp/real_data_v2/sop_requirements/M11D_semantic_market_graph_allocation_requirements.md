# M11D 新版语义市场图谱与销量分配 SOP 需求

## 0. 定位

M11D 是新版语义能力层的“市场图谱与销量分配结果层”。

M09C、M10C、M11C 已经分别回答：

- 某个 SKU 有哪些用户任务关系。
- 某个 SKU 有哪些目标客群关系。
- 某个 SKU 有哪些价值战场关系。

M11D 要进一步回答：

- 从用户任务、目标客群、价值战场三个视角看，市场图谱是什么。
- 每个任务、客群、战场覆盖哪些 SKU，覆盖多少销量和销额。
- 一个 SKU 同时落入多个任务、客群、战场时，它的销量和销额如何做解释性切分。
- 哪些 SKU 因证据不足不能参与切分，未分配市场量有多少。

M11D 不重新生成用户任务、目标客群或价值战场，不调用 LLM，不直接读取原始四张表做业务判断。

详细技术方案见：

- [M11D 新版语义市场图谱与销量分配详细设计](../sop_detailed_design/M11D_semantic_market_graph_allocation_design.md)

## 1. 业务目标

M11D 的业务目标是把“单 SKU 语义画像”升级成“可用于市场分析的结构化图谱和市场空间结果”。

它必须支撑后续小奥家电市场分析专家回答：

1. 某个价值战场市场空间有多大，里面有哪些 SKU。
2. 某个用户任务覆盖哪些 SKU，哪些 SKU 贡献最大。
3. 某个目标客群下有哪些品牌和型号。
4. 某个 SKU 的销量估算由哪些任务、客群、战场解释，各占多少。
5. 某个 SKU 进入多个战场时，每个战场承接了多少销量和销额。
6. 某个 SKU 有没有未覆盖、未满足或拖后腿的市场机会。
7. 某个 SKU 和竞品为什么在同一个市场空间中竞争。

M11D 的输出是估算解释，不是真实消费者购买归因。

## 2. 模块边界

### 2.1 必须解决

1. 生成用户任务市场图谱。
2. 生成目标客群市场图谱。
3. 生成价值战场市场图谱。
4. 生成 SKU 在用户任务中的销量/销额解释分配。
5. 生成 SKU 在目标客群中的销量/销额解释分配。
6. 生成 SKU 在价值战场中的销量/销额解释分配。
7. 输出每个任务、客群、战场的市场规模、SKU 构成、品牌构成、尺寸价格构成和 Top SKU 贡献。
8. 输出每个 SKU 的 allocation confidence、basis、market_window 和 evidence。
9. 对未能参与分配的 SKU 输出诊断，不得隐藏在假维度里。
10. 提供后续 CLI/Skill 可查询的稳定结果表或快照。

### 2.2 不解决

| 不做事项 | 原因 |
| --- | --- |
| 不重新生成任务、客群、战场 taxonomy | 由 M09C/M10C/M11C 上游负责 |
| 不重新判断 SKU 主任务、主客群、主战场 | M11D 只消费上游 current 结果 |
| 不做卖点维度独立销量切分 | 卖点作为任务/客群/战场成立的证据，后续由分析 CLI 判断溢价卖点 |
| 不做核心竞品选择 | 竞品判断属于后续 `catforge_analyst` 复合分析 |
| 不做经营策略建议 | M11D 输出事实和市场结构，策略建议由小奥/分析 CLI 生成 |
| 不调用 LLM | M11D 是批处理结果层，必须确定性、可复跑 |
| 不把服务履约作为产品维度 | 服务、物流、安装、售后不得进入产品任务/客群/战场销量分配 |

## 3. 输入

### 3.1 必须输入

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| SKU 评论事实画像 | M05C | 限定默认分析 SKU 集，提供用户真实声音基础 |
| SKU 用户任务画像和分数 | M09C | 生成用户任务图谱和任务销量分配 |
| SKU 目标客群画像和分数 | M10C | 生成目标客群图谱和客群销量分配 |
| SKU 价值战场画像和分数 | M11C | 生成价值战场图谱和战场销量分配 |
| SKU 市场量价事实 | M07/M01 | 提供销量、销额、价格、active week、市场窗口 |
| SKU 参数事实画像 | M03B | 校验五档尺寸口径和尺寸价格带一致性 |

### 3.2 禁止输入

| 禁止输入 | 原因 |
| --- | --- |
| 原始评论表 | 评论必须先经过 M01/M02/M05C 清洗和事实化 |
| 原始卖点表 | 卖点事实必须来自 M04C |
| 原始参数表 | 参数事实必须来自 M03B |
| 原始量价表 | 市场事实必须来自 M07/M01 清洗结果 |
| 旧 M09/M10/M11/M11.6/M11.7 结果 | 旧 code 和新版语义资产不一致 |

## 4. 默认分析 SKU 集

M11D 默认 SKU 集为：

```text
fact_complete_with_comment
= current M05C 评论事实画像
  ∩ current M09C 用户任务画像
  ∩ current M10C 目标客群画像
  ∩ current M11C 价值战场画像
  ∩ current 市场量价事实
```

原因：

1. 用户任务、目标客群、价值战场优先由真实用户声音支撑。
2. 没有评论事实的 SKU 可以进入参数/卖点/市场事实分析，但不应默认进入用户语义市场图谱。
3. 后续如需分析新品、低评论 SKU，可显式选择 `all_semantic_profiles`。

M11D 必须在结果中写明：

- `analysis_population`
- `population_sku_count`
- `included_sku_count`
- `excluded_sku_count`
- 排除原因统计

## 5. 三类图谱要求

### 5.1 用户任务图谱

用户任务图谱必须回答：

1. 每个用户任务覆盖哪些 SKU。
2. 哪些 SKU 是主任务关系。
3. 哪些 SKU 是辅任务关系。
4. 哪些 SKU 只是评论观察到需求。
5. 哪些 SKU 有负向评论或拖后腿任务。
6. 每个任务承接多少估算销量、销额和周均销量。
7. 每个任务下品牌、尺寸、价格带如何分布。

### 5.2 目标客群图谱

目标客群图谱必须回答：

1. 每个目标客群覆盖哪些 SKU。
2. 哪些 SKU 是主客群关系。
3. 哪些 SKU 是辅客群关系。
4. 哪些 SKU 有评论直接观察到的人群或购买动机。
5. 哪些 SKU 有未满足客群需求。
6. 每个客群承接多少估算销量、销额和周均销量。
7. 每个客群下品牌、尺寸、价格带如何分布。

### 5.3 价值战场图谱

价值战场图谱必须回答：

1. 每个价值战场覆盖哪些 SKU。
2. 哪些 SKU 是主战场关系。
3. 哪些 SKU 是辅战场关系。
4. 哪些 SKU 是机会战场关系。
5. 哪些 SKU 是品牌宣称但用户评论不足。
6. 哪些 SKU 是用户观察到需求但产品支撑不足。
7. 哪些 SKU 是拖后腿战场。
8. 每个战场承接多少估算销量、销额和周均销量。
9. 每个战场下品牌、尺寸、价格带如何分布。

## 6. 销量分配要求

### 6.1 分配视角

M11D 必须分别计算三套 allocation：

| dimension_type | 含义 |
| --- | --- |
| `user_task` | 同一 SKU 的销量如何被多个用户任务解释 |
| `target_group` | 同一 SKU 的销量如何被多个目标客群解释 |
| `battlefield` | 同一 SKU 的销量如何被多个价值战场解释 |

三套 allocation 是三套解释视角，不能相互相加。

示例：

```text
某 SKU 销量 1000 台。
用户任务视角可以分配为：影院沉浸 600，性价比购买 400。
目标客群视角可以分配为：主流家庭 700，大屏换新 300。
价值战场视角可以分配为：大屏家庭影院 650，大屏换新性价比 350。
这不是 3000 台销量，而是同一 1000 台销量的三套解释。
```

### 6.2 分配闭合

对已经进入 allocation 的 SKU，必须满足：

```text
sum(allocation_weight where sku=S and dimension_type=D) = 1
sum(allocated_sales_volume where sku=S and dimension_type=D) = sku_sales_volume_total
sum(allocated_sales_amount where sku=S and dimension_type=D) = sku_sales_amount_total
```

误差不超过 `0.0001`。

### 6.3 不能强行分配

如果某 SKU 在某个维度类型没有足够证据：

- 不得生成 `unknown` 假维度。
- 不得把销量平均分配给弱关系。
- 不得默认选最高弱分关系。
- 必须输出未分配诊断。

未分配诊断至少包括：

| 字段 | 含义 |
| --- | --- |
| `sku_code` | SKU |
| `dimension_type` | 哪类维度无法分配 |
| `unallocated_sales_volume` | 未分配销量 |
| `unallocated_sales_amount` | 未分配销额 |
| `reason_code` | 原因 |
| `reason_cn` | 中文解释 |
| `recommended_action_cn` | 建议 |

## 7. 市场窗口要求

M11D 所有销量和销额必须带 `market_window`。

首版默认：

| market_window | 说明 |
| --- | --- |
| `full_observed_window` | 使用当前 M07 市场画像中的全观测窗口 |

后续预留：

| market_window | 说明 |
| --- | --- |
| `recent_12w` | 最近 12 周 |
| `custom_week_range` | 指定周范围 |

M11D 不能只输出累计销量。为了避免累计销量误导比较，必须同时输出：

- `sales_volume_total`
- `sales_amount_total`
- `avg_weekly_sales_volume`
- `avg_weekly_sales_amount`
- `allocated_sales_volume`
- `allocated_sales_amount`
- `allocated_avg_weekly_sales_volume`
- `allocated_avg_weekly_sales_amount`

业务解释要求：

- “市场空间”可以使用窗口累计销量/销额。
- “谁更强、谁卖得更好”应优先使用周均销量、周均销额或后续重叠周指标。

## 8. 关系状态要求

M11D 必须保留上游 relation_status，同时输出统一的 allocation role。

| 统一角色 | 业务含义 | 分配要求 |
| --- | --- | --- |
| `primary_value` | SKU 在该维度的主关系 | 默认参与正向分配 |
| `secondary_value` | SKU 在该维度的辅关系 | 默认参与正向分配 |
| `observed_need` | 用户评论观察到需求 | 满足证据门槛时可参与需求侧分配 |
| `drag_risk` | 用户有需求但体验负向或产品支撑不足 | 不参与正向分配，进入风险图谱 |
| `brand_claim` | 厂家宣称，用户证据不足 | 不参与正向分配，进入宣称图谱 |
| `latent_capability` | 参数具备潜在能力 | 不参与正向分配，进入潜力图谱 |
| `opportunity` | 机会关系 | 不参与正向分配，进入机会图谱 |
| `excluded` | 不成立 | 不进入图谱和分配 |

## 9. 输出

### 9.1 Allocation 明细

M11D 必须输出 SKU × 维度的分配明细。

至少包括：

- 项目、品类、批次、规则版本。
- SKU、品牌、型号。
- `analysis_population`。
- `market_window`。
- `dimension_type`。
- `dimension_code`。
- `dimension_name`。
- 上游 `relation_status`。
- 统一 `allocation_role`。
- `allocation_weight`。
- 分配销量、销额、周均销量、周均销额。
- `allocation_confidence`。
- `allocation_basis`。
- `source_profile_id`。
- `source_score_id`。
- `evidence_ids`。

### 9.2 维度市场汇总

M11D 必须输出每个任务、客群、战场的市场汇总。

至少包括：

- 维度名称和定义。
- 覆盖 SKU 数。
- 进入分配 SKU 数。
- 主关系 SKU 数。
- 辅关系 SKU 数。
- 评论观察 SKU 数。
- 品牌宣称 SKU 数。
- 机会 SKU 数。
- 拖后腿/未满足 SKU 数。
- 估算销量、销额、周均销量、周均销额。
- 占已分配市场比例。
- 未分配市场量。
- 品牌分布。
- 尺寸价格分布。
- Top SKU 贡献。
- 平均置信度。
- 中文业务摘要。

### 9.3 SKU 贡献明细

M11D 必须支持从维度汇总反查 SKU 贡献。

至少包括：

- SKU 在该任务/客群/战场中的销量贡献。
- SKU 在该任务/客群/战场中的销额贡献。
- SKU 在该任务/客群/战场中的贡献占比。
- SKU 在该任务/客群/战场中的排名。
- 贡献原因说明。

### 9.4 图谱快照

M11D 必须输出图谱快照，支持后续 CLI 和 Skill 快速查询。

图谱至少包括：

- SKU 节点。
- 用户任务节点。
- 目标客群节点。
- 价值战场节点。
- SKU 到任务/客群/战场的边。
- 边上的 relation_status、allocation_role、score、allocation_weight、confidence。
- 汇总统计。
- 未分配诊断统计。

## 10. 数据质量要求

M11D 必须做以下校验：

| 校验 | 要求 |
| --- | --- |
| current 唯一 | 同一 SKU 同一模块只能有一条 current 画像 |
| batch 一致 | 不允许混用不同 batch 的 M09C/M10C/M11C/M07 |
| taxonomy 一致 | 同一运行内 taxonomy_version 不得混用 |
| 尺寸口径 | 必须使用 M03B 五档尺寸 |
| 价格带口径 | 必须使用尺寸内五档价格带 |
| 服务隔离 | 服务履约不得进入产品维度分配 |
| 权重归一 | 已分配 SKU 的同维度 allocation weight 合计为 1 |
| 销量闭合 | 已分配 SKU 的 allocated volume 与 SKU market volume 闭合 |
| 销额闭合 | 已分配 SKU 的 allocated amount 与 SKU market amount 闭合 |
| 汇总闭合 | 维度汇总必须能由 allocation 明细反算 |

## 11. CLI 和 Skill 要求

### 11.1 Pipeline CLI

M11D 必须提供批处理执行入口。

建议命令：

```bash
python -m app.cli.catforge_pipeline run-semantic-market-graph \
  --product-category tv \
  --batch-id latest \
  --analysis-population fact_complete_with_comment \
  --market-window full_observed_window \
  --force-rebuild \
  --format json
```

必须支持：

| 参数 | 说明 |
| --- | --- |
| `--product-category` | 品类 |
| `--batch-id` | 批次，支持 `latest` |
| `--analysis-population` | 分析 SKU 集 |
| `--market-window` | 市场窗口 |
| `--dimension-type` | 可选，只跑某一类维度 |
| `--force-rebuild` | 清理 current 后重算 |
| `--format` | `json`、`text` |

### 11.2 Analyst CLI

M11D 结果必须支持后续查询。

建议命令：

```bash
python -m app.cli.catforge_insight semantic-market-map \
  --product-category tv \
  --dimension-type battlefield \
  --dimension-code BF_LARGE_SCREEN_FAMILY_CINEMA \
  --format json

python -m app.cli.catforge_insight sku-sales-allocation \
  --product-category tv \
  --sku-query "海信 65" \
  --format json
```

### 11.3 Skill 自然语言能力

Skill 必须能把以下自然语言路由到 M11D 结果查询：

- “某个价值战场有哪些 SKU？”
- “某个目标客群图谱是什么？”
- “某个用户任务覆盖哪些型号？”
- “某个 SKU 的销量分配到哪些战场？”
- “这个 SKU 在几个战场里竞争？”
- “某个战场市场空间多大？”
- “某个客群下面哪些品牌卖得好？”

## 12. 性能要求

M11D 不调用 LLM，运行时瓶颈主要是数据库读取、JSON 处理和批量写入。

必须满足：

1. 在 205 上 TV 默认 population 全量运行时，不应导致 SSH 不可访问。
2. 分块读取 score 和 profile，不一次性加载全部 JSON 到内存。
3. 批量写入结果，不逐行 commit。
4. 支持 `--dimension-type` 局部重跑。
5. 可重复运行，重跑应幂等。

## 13. 验收标准

### 13.1 基础验收

1. M11D 能在 TV 当前批次生成三类图谱。
2. M11D 能生成用户任务 allocation。
3. M11D 能生成目标客群 allocation。
4. M11D 能生成价值战场 allocation。
5. 输出结果带 `market_window`、`analysis_population`、`rule_version` 和 evidence。

### 13.2 业务验收

1. 可以查某个价值战场包含哪些 SKU。
2. 可以查某个用户任务包含哪些 SKU。
3. 可以查某个目标客群包含哪些 SKU。
4. 可以查某个 SKU 的任务、客群、战场销量分配。
5. 可以看到一个 SKU 同时进入多个战场。
6. 可以看到每个战场的市场空间、Top SKU、品牌结构、尺寸价格结构。
7. 可以看到哪些 SKU 没有被分配，以及为什么没有被分配。

### 13.3 数据验收

1. 已分配 SKU 的 allocation weight 闭合。
2. 已分配 SKU 的销量、销额闭合。
3. 维度汇总和 allocation 明细闭合。
4. 不出现旧 M07 四档尺寸作为主口径。
5. 不出现服务履约维度进入产品市场图谱。
6. 不出现旧 M09/M10/M11/M11.6/M11.7 code 混入新版结果。

### 13.4 205 验收

1. 部署到 205 后，能对 TV `fact_complete_with_comment` 全量运行。
2. 运行后 205 API 和 SSH 保持可访问。
3. 抽查一款海信 65 寸 SKU，能查到：
   - 用户任务分配。
   - 目标客群分配。
   - 价值战场分配。
   - 所属图谱中的 SKU 贡献。
4. 抽查一个价值战场，能查到：
   - 覆盖 SKU。
   - 主/辅/机会/拖后腿关系。
   - 估算销量、销额和周均销量。
   - Top SKU 贡献。

## 14. 后续依赖

M11D 完成后，才能进入以下工作：

1. `catforge_insight semantic-market-map`。
2. `catforge_insight sku-sales-allocation`。
3. 后续复合分析 CLI 中的 `battlefield-space`。
4. 竞品判断 SOP：同尺寸价格 > 同价值战场 > 同用户任务/目标客群 > 同参数/卖点 > 销量接近。
5. 小奥家电市场分析专家 Skill 和 Agent 提示词。

没有 M11D，OpenClaw 只能回答“覆盖关系”，不能稳定回答“市场空间、销量分配、战场贡献、SKU 在多个图谱中的份额”。
