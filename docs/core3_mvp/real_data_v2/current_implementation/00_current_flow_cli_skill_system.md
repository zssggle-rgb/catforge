# 当前正确流程、CLI、Skill 与智能体系统

最后更新：2026-06-24

本文是 CatForge 真实数据处理链路和“小奥家电市场分析专家”路由的当前口径。由于项目已经经历多轮补丁、模块重构和 Skill/Agent 调整，后续执行、排错和对外说明都以本文为准；如果本文和旧 Mxx 文档冲突，先按本文执行，再回到当前分支和 205 部署环境验证。

本文重点不是列 CLI，而是明确一条新的、可执行的分析路径：新原始数据进入后，先清洗和证据化，再生成事实画像，再生成语义画像和市场图谱，最后让小奥基于最新结果回答业务问题。

## 1. 当前新流程总览

当前链路分为六层：

```text
原始上传数据
  -> 数据准备层
  -> SKU 事实画像层
  -> 评论事实与语义画像层
  -> 语义市场图谱层
  -> 卖点价值量化层
  -> 专业市场分析层
  -> 外部智能体入口
```

每层职责如下：

| 层级 | 目的 | 当前主要产物 | 主要执行入口 |
| --- | --- | --- | --- |
| 原始上传数据 | 保存外部上传的可观测市场数据 | 原始量价、参数、卖点、评论 | 不直接用于业务分析 |
| 数据准备层 | 把原始数据清洗成可追溯、可分析的证据 | 清洗表、质量问题、评论句子、证据原子 | `catforge-data` |
| SKU 事实画像层 | 描述每个 SKU 的客观事实 | 参数画像、卖点事实画像、市场画像 | `catforge-pipeline` |
| 评论事实与语义画像层 | 从真实评论和事实资产生成用户语义判断 | 评论事实画像、用户任务、目标客群、价值战场 | `catforge-pipeline` |
| 语义市场图谱层 | 从任务、客群、战场维度看市场空间和销量分配 | 用户任务图谱、目标客群图谱、价值战场图谱、销量分配 | `catforge-pipeline` / `catforge-insight` |
| 卖点价值量化层 | 估算卖点在可比池中的价格、销量、销额贡献 | 卖点价值池、卖点量化、SKU 卖点贡献、机会缺口 | `catforge-pipeline` / `catforge-analyst` |
| 专业市场分析层 | 回答竞品、销量差异、溢价卖点、机会空间等业务问题 | 结构化分析包和业务回答 | `catforge-analyst` / 小奥 |
| 外部智能体入口 | 让用户用自然语言驱动执行或查询 | Claude Code 执行、OpenClaw 小奥问答 | Claude Code / OpenClaw |

## 2. 原始上传数据

当前原始数据来自四张上传表：

- `week_sales_data`：SKU 周度量价。
- `attribute_data`：SKU 原始参数。
- `selling_points_data`：SKU 原始卖点。
- `comment_data`：SKU 原始评论。

规则：

- 原始表只作为数据源，不直接作为业务分析输入。
- 不允许小奥直接从原始表回答“竞品是谁”“为什么卖得好”“目标客户是谁”等业务问题。
- 新增原始数据后，必须先进入数据准备层。
- 原始表里的缺失值、空值、`-`、未知值不能直接按“否”理解，除非某个品类标准参数已经明确规定“缺失即无该特性”。

## 3. 数据准备层：新数据先清洗、过滤和证据化

数据准备层对应当前 M00/M01/M02 的合并执行能力，用户不需要知道这些模块名。

### 3.1 处理目标

数据准备层要完成：

1. 给本次新增或重跑数据建立可追溯批次。
2. 清洗 SKU、周度量价、参数、卖点、评论。
3. 快速过滤空评论、低质评论、无产品信息评论。
4. 识别服务履约类评论，例如客服、物流、安装、售后、退换货、维修等。
5. 服务履约类评论只保留质量统计，不进入后续产品评论事实分析。
6. 把有效评论切成句子，生成后续可引用的证据原子。
7. 生成质量问题和覆盖情况摘要，供执行者判断是否可以继续下游画像。

### 3.2 当前口径

- 同一周只有一个平台有数据是正常情况，说明该 SKU 可能只在一个平台销售或是某平台特供。
- 前段缺周通常解释为新品或较晚进入样本。
- 后段缺周通常解释为退市、下架或离开样本。
- 中间缺周才是软质量预警，需要在报告中说明。
- 彩电部分属性缺失可以不作为阻断项。
- 服务履约类评论不进入产品事实、用户任务、目标客群、价值战场判断。

### 3.3 执行入口

205 上 Claude Code 应优先使用宿主机包装器：

```bash
catforge-data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --sku-batch-size 50 --evidence-sku-batch-size 1 --format json
```

如果已经有批次，只想重跑当前批次的数据准备：

```bash
catforge-data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --register-source-batch none --batch-id latest --sku-batch-size 50 --evidence-sku-batch-size 1 --format json
```

检查清洗质量：

```bash
catforge-data inspect-data-quality --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id latest --format json
```

小批量冒烟：

```bash
catforge-data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --register-source-batch none --batch-id latest --limit-skus 5 --sku-batch-size 2 --evidence-sku-batch-size 1 --format json
```

## 4. SKU 事实画像层

事实画像层描述“这个 SKU 客观上是什么样”。这层不直接给最终战略结论，而是为后面的用户任务、目标客群、价值战场和竞品分析提供证据基础。

### 4.1 参数事实画像

参数画像来自清洗后的原始参数和品类标准参数体系。

当前口径：

- TV 使用已确认的彩电标准参数体系。
- AC 已有空调标准参数体系，但后续卖点、评论、任务、客群、战场 taxonomy 是否完整要按当前实现确认。
- 标准参数体系不应压制原始字段信息；原始字段能表达的事实要尽量映射进标准参数。
- 参数画像不仅记录参数值，也记录参数所属维度、档位、在同尺寸或同价位池里的位置。

执行：

```bash
catforge-pipeline run-param-profile --product-category tv --batch-id latest --force-rebuild --format json
```

### 4.2 卖点事实画像

卖点画像来自清洗后的卖点表和品类标准卖点体系。

当前口径：

- 卖点首先看是否有参数支撑。
- 有参数支撑的卖点才更接近事实卖点。
- 卖点是否是溢价卖点，要看它是否支撑主用户任务、主目标客群和主/辅价值战场，并且是否被评论正向验证。
- 仅有厂家宣传、无参数或评论支撑的卖点，只能作为品牌主张或机会点，不能直接当成用户选择理由。

执行：

```bash
catforge-pipeline run-claim-profile --product-category tv --batch-id latest --input-source auto --force-rebuild --format json
```

### 4.3 市场画像

市场画像来自清洗后的周度量价。

当前口径：

- 所有后续分析统一使用 M03B 参数事实画像中的五档尺寸口径：
  - `small_32_45`
  - `medium_46_59`
  - `large_60_69`
  - `xlarge_70_85`
  - `giant_98_plus`
- 价格带不是原始量价表字段，而是在同一尺寸档内按价格分位派生：
  - 低价位
  - 中低价位
  - 中价位
  - 中高价位
  - 高价位
- 市场验证用重叠在售周的周均销量和周均销售额。
- 累计销量只能作为展示背景，不能作为判断谁更强的主依据。

执行：

```bash
catforge-pipeline run-market-profile --batch-id latest --sku-chunk-size 50 --format json
```

## 5. 评论事实与语义画像层

这层把事实数据转换成用户语言和市场语义：用户在什么场景下买、谁在买、在哪个价值战场竞争。

### 5.1 评论事实画像

评论事实画像从数据准备层保留下来的有效评论句子中生成。

当前口径：

- 评论事实画像使用 LLM。
- 必须拉入标准参数和标准卖点，用来判断评论是否支持某些参数或卖点。
- 每个 SKU 要输出评论事实，也要输出跨 SKU 的维度统计。
- 评论中的人群、用途、尺寸、价格、竞品提及、品牌信任/复购，都属于评论事实维度。
- 服务履约类评论不进入产品评论事实画像。

推荐执行方式：

先小批量冒烟：

```bash
catforge-pipeline run-comment-profile-batch --product-category tv --batch-id latest --llm-mode required --parallelism 4 --limit 5 --max-sentences-per-sku 500 --format json
```

再全量执行：

```bash
catforge-pipeline run-comment-profile-batch --product-category tv --batch-id latest --llm-mode required --parallelism 8 --max-sentences-per-sku 500 --format json
```

如果 205 负载稳定，可以提高到 12 或 16；如果出现 API 超时、内存压力或错误，降回 8 或 4。

### 5.2 用户任务画像

用户任务是用户主观使用或购买目的，不是厂家宣传语。

当前口径：

- 评论中的真实用途、真实人群和真实体验表达优先。
- 卖点代表厂家想打什么。
- 参数代表产品有没有能力支撑。
- 评论负向集中不是排除任务，而是说明用户有需求但产品没做好，对应卖点可能是拖后腿。
- 允许某个 SKU 没有主用户任务，但必须给出原因。

执行：

```bash
catforge-pipeline run-user-task --product-category tv --batch-id latest --force-rebuild --format json
```

### 5.3 目标客群画像

目标客群基于评论人群、已成立用户任务、尺寸价格适配、卖点表达和参数能力共同推导。

当前口径：

- 评论里直接出现的人群或购买动机优先级最高。
- 没有人群词但用户任务强，也可推导客群。
- 卖点只能说明厂家想服务谁，不能单独证明真实客群。
- 参数只能说明产品是否适合某类客群，不能单独证明谁在买。
- 品牌信任和复购是购买心理增强因素，不单独成为客群。
- 服务履约、物流安装、售后不作为产品客群。

执行：

```bash
catforge-pipeline run-target-group --product-category tv --batch-id latest --force-rebuild --format json
```

### 5.4 价值战场画像

价值战场用于回答“这个 SKU 在什么市场池里竞争，以及它靠什么价值被选择”。

当前定义：

```text
价值战场 = 尺寸价格竞争池 + 用户任务 + 目标客群 + 产品价值锚点 + 用户评论验证
```

当前口径：

- 战场必须先过五档尺寸和尺寸内价格带门槛。
- 评论强但参数/卖点弱，可以是用户观察到的需求或拖后腿因素，不能直接判为溢价。
- 卖点强但评论弱，只能是品牌主张或机会点。
- 服务履约不得进入产品价值战场。
- 一个 SKU 最多 1 个主战场、最多 2 个辅战场，可有多个机会战场或拖后腿战场。

执行：

```bash
catforge-pipeline run-value-battlefield --product-category tv --batch-id latest --force-rebuild --format json
```

## 6. 语义市场图谱层

语义市场图谱把 SKU 级画像上卷到市场维度，回答“每个任务、客群、战场包含哪些 SKU、贡献多少销量、一个 SKU 的销量如何分配到多个语义维度”。

当前产物：

- 用户任务市场图谱。
- 目标客群市场图谱。
- 价值战场市场图谱。
- SKU 在任务、客群、战场之间的销量分配。

当前口径：

- 默认只让事实完整且有评论事实的 SKU 进入业务图谱。
- 一个 SKU 可以进入多个用户任务、目标客群或价值战场。
- 销量分配是解释性分配，不是因果归因。
- 分配依据来自主/辅/机会/拖后腿等关系、评分和市场画像。

执行：

```bash
catforge-pipeline run-semantic-market-graph --product-category tv --batch-id latest --force-rebuild --format json
```

查询：

```bash
catforge-insight ask "查彩电语义市场图谱" --batch-id latest --sku-limit 100 --format json
catforge-insight ask "查彩电价值战场图谱" --batch-id latest --format json
catforge-insight ask "查 100A4F 的销量分配" --batch-id latest --format json
```

## 7. 卖点价值量化与贡献归因层

卖点价值量化层用于回答“哪些卖点在当前可比市场池中支撑定价、销量或销额表现”。它不是严格因果归因，而是基于可观测样本的解释性估算。

当前产物：

- 卖点可比池：某个标准卖点在同尺寸、同价格带、同战场/任务/客群下的有卖点组和对照组。
- 池级卖点价值指标：价格溢价、周均销量优势、周均销额优势、样本状态和置信度。
- SKU 卖点价值角色：强溢价卖点、强销量卖点、组合型增值卖点、基础门槛、用户感知不足、厂家主张、用户验证需求、高价竞品拦截、价格上探机会、拖后腿、机会缺口、样本不足。
- SKU 卖点贡献归因：一个 SKU 相对同池基准的价格、销量、销额超额表现，如何解释性分摊到若干卖点。
- 卖点维度汇总：某个卖点在价值战场、用户任务、目标客群、尺寸价格池中的覆盖和表现。

当前口径：

- 默认分析人群使用 `claim_value_ready_with_comment`，即要求有卖点事实、评论事实、市场画像和语义图谱。
- 对缺评论但有参数和卖点事实的 SKU，可降级到 `claim_value_ready`，但只能说“用户评论验证不足”。
- 卖点价值必须在可比池内判断，不能跨尺寸档、跨价格层级或跨完全不同战场直接比较。
- “值多少钱”“贡献多少销量”只能表达为“对应价格溢价估计”“对应周均销量优势估计”，不能表达为严格因果。
- 服务履约、物流安装、售后不进入产品溢价卖点。

执行：

```bash
catforge-pipeline run-claim-value-quantification --product-category tv --batch-id latest --analysis-population claim_value_ready_with_comment --market-window full_observed_window --format json
```

自然语言执行：

```bash
catforge-pipeline ask "生成彩电卖点价值量化和贡献归因结果" --product-category tv --batch-id latest --format json
```

查询和业务分析入口：

```bash
catforge-analyst sku-claim-value --query 65E7Q --product-category tv --batch-id latest --format json
catforge-analyst claim-contribution --query 65E7Q --product-category tv --batch-id latest --format json
catforge-analyst claim-value-space --query MiniLED --dimension-type battlefield --product-category tv --batch-id latest --format json
catforge-analyst claim-opportunity-gaps --query 65E7Q --candidate-sku-code TV00040001 --product-category tv --batch-id latest --format json
catforge-analyst claim-value-compare --query 65E7Q --candidate-sku-code TV00040001 --product-category tv --batch-id latest --format json
```

小奥问“哪些卖点是溢价卖点”“这款卖得好靠哪些卖点”“比竞品贵在哪里”时，应优先使用 M12C 已生成结果；如果 M12C 未生成，只能降级为事实卖点、评论支撑和语义关系的候选判断。

## 8. 小奥专业市场分析层

小奥不是数据处理程序，而是业务分析专家。它消费前面所有事实画像、语义画像和市场图谱，回答业务问题。

### 8.1 小奥能回答的问题

- 某个 SKU 的竞品有哪些。
- 为什么 A 比 B 卖得好。
- 哪些卖点支撑用户选择。
- 哪些卖点是溢价卖点。
- 某个 SKU 如何扩大销量。
- 某个 SKU 有没有机会进入更多价值战场。
- 某个价值战场空间有多大。
- 某个 SKU 的目标客户和用户画像是什么。
- 某个 SKU 在任务、客群、战场里的市场位置是什么。

### 8.2 小奥不能做的事

- 不能直接从原始表编业务结论。
- 不能绕过 CLI 或稳定服务直接临时写 SQL 形成结论。
- 不能把 CatForge、CLI、Mxx、数据库表、JSON、批次号、报错堆栈暴露给普通业务用户。
- 不能用通用常识替代当前 205 数据。
- 不能把累计销量当成销量胜负的主判断依据。

### 8.3 小奥执行入口

OpenClaw 侧：

```text
xiaoao-home-appliance-market-analysis Skill
xiaoao-home-appliance-market-analyst Agent
```

CLI 侧：

```bash
catforge-analyst ask "海信65E7Q的竞品有哪些" --product-category tv --batch-id latest --format json
```

## 9. 新数据进入后的完整执行顺序

当目标是“让小奥能使用最新上传数据回答问题”时，按下面顺序执行。

### 9.1 环境检查

```bash
cd /opt/catforge
git status --short --branch
git log -1 --oneline
docker compose -f docker-compose.cloud.yml ps api
curl -fsS http://127.0.0.1:8000/readyz
command -v catforge-data catforge-pipeline catforge-insight catforge-analyst
```

### 9.2 数据准备

```bash
catforge-data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --sku-batch-size 50 --evidence-sku-batch-size 1 --format json
```

然后检查：

```bash
catforge-data inspect-data-quality --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id latest --format json
```

### 9.3 事实画像

```bash
catforge-pipeline run-param-profile --product-category tv --batch-id latest --force-rebuild --format json
catforge-pipeline run-claim-profile --product-category tv --batch-id latest --input-source auto --force-rebuild --format json
catforge-pipeline run-market-profile --batch-id latest --sku-chunk-size 50 --format json
```

### 9.4 评论事实画像

先冒烟：

```bash
catforge-pipeline run-comment-profile-batch --product-category tv --batch-id latest --llm-mode required --parallelism 4 --limit 5 --max-sentences-per-sku 500 --format json
```

再全量：

```bash
catforge-pipeline run-comment-profile-batch --product-category tv --batch-id latest --llm-mode required --parallelism 8 --max-sentences-per-sku 500 --format json
```

### 9.5 语义画像、市场图谱和卖点价值量化

```bash
catforge-pipeline run-user-task --product-category tv --batch-id latest --force-rebuild --format json
catforge-pipeline run-target-group --product-category tv --batch-id latest --force-rebuild --format json
catforge-pipeline run-value-battlefield --product-category tv --batch-id latest --force-rebuild --format json
catforge-pipeline run-semantic-market-graph --product-category tv --batch-id latest --force-rebuild --format json
catforge-pipeline run-claim-value-quantification --product-category tv --batch-id latest --analysis-population claim_value_ready_with_comment --market-window full_observed_window --format json
```

### 9.6 最终验收

```bash
catforge-insight ask "查彩电语义市场图谱" --batch-id latest --sku-limit 20 --format json
catforge-insight ask "查彩电价值战场图谱" --batch-id latest --format json
catforge-analyst ask "海信65E7Q的竞品有哪些" --product-category tv --batch-id latest --format json
catforge-analyst ask "海信65E7Q哪些卖点是溢价卖点" --product-category tv --batch-id latest --format json
```

验收口径：

- 最新批次存在。
- 数据准备成功，且没有阻断性质量问题。
- 参数画像、卖点画像、市场画像成功。
- 评论事实画像完成，失败 SKU 或跳过 SKU 有明确说明。
- 用户任务、目标客群、价值战场成功。
- 语义市场图谱和销量分配成功。
- 卖点价值量化和贡献归因成功。
- 小奥可以基于 latest batch 回答典型业务问题。

## 10. CLI、Skill、Agent 的职责边界

CLI 和 Skill 是执行入口，不是分析流程本身。

| 能力 | 主要用途 | 是否写数据 | 主要使用者 |
| --- | --- | --- | --- |
| `catforge-data` | 新数据预处理、清洗、质量检查、证据准备 | 是 | Claude Code |
| `catforge-pipeline` | 生成或重跑参数、卖点、市场、评论、用户任务、目标客群、价值战场、语义市场图谱、卖点价值量化 | 是 | Claude Code |
| `catforge-insight` | 查询已经生成的事实、画像、taxonomy、覆盖、图谱、销量分配 | 否 | Claude Code / OpenClaw |
| `catforge-analyst` | 竞品、销量差异、溢价卖点、卖点贡献、机会空间等业务分析包 | 通常否 | OpenClaw / 小奥 |
| `catforge-data` Skill | 让 Claude Code 理解“新数据来了先处理一下” | 通过 CLI 写数据 | Claude Code |
| `catforge-pipeline` Skill | 让 Claude Code 理解“重新生成画像/图谱” | 通过 CLI 写数据 | Claude Code |
| `catforge-insight` Skill | 让 Claude Code 做只读事实检查 | 否 | Claude Code |
| `xiaoao-home-appliance-market-analysis` Skill | 让 OpenClaw 按业务 SOP 调用分析 CLI | 否 | OpenClaw |
| `xiaoao-home-appliance-market-analyst` Agent | 小奥家电市场分析专家角色、语气和边界 | 否 | OpenClaw |

当前分工：

- Claude Code 是数据执行主力：负责清洗、重跑、检查、补数。
- OpenClaw / 小奥是业务问答主力：负责面向业务用户回答竞品、销量、卖点、机会等问题。
- OpenClaw 不应替代 Claude Code 去跑大规模清洗和画像重建。
- Claude Code 不应替代小奥输出面向业务用户的完整市场分析话术，除非用户明确要求它调用 `catforge-analyst` 做验证。

## 11. 自然语言路由规则

### 11.1 新数据、预处理、清洗

用户说：

- “新数据来了，先处理一下。”
- “把最新上传的评论清洗一下。”
- “先把数据准备好可以分析。”
- “查一下这批数据清理情况。”

路由到：

```bash
catforge-data prepare-new-data ...
catforge-data inspect-data-quality ...
```

不要路由到 `catforge-pipeline`。

### 11.2 重新生成画像、图谱或卖点价值量化

用户说：

- “重新生成彩电参数画像。”
- “重新生成彩电卖点事实画像。”
- “重新生成彩电评论事实画像。”
- “重新生成彩电用户任务画像。”
- “重新生成彩电目标客群画像。”
- “重新生成彩电价值战场画像。”
- “重新生成彩电语义市场图谱和销量分配。”
- “生成彩电卖点价值量化和贡献归因结果。”
- “重新计算彩电溢价卖点和卖点贡献。”

路由到：

```bash
catforge-pipeline ask "<用户原话>" --batch-id latest --product-category tv --force-rebuild --format json
```

### 11.3 查询现有事实或覆盖

用户说：

- “查某个 SKU 的参数画像。”
- “查彩电标准卖点。”
- “查某个 SKU 的用户任务。”
- “查某个 SKU 的目标客群。”
- “查某个 SKU 的价值战场。”
- “查某个价值战场有哪些 SKU。”
- “查某个 SKU 的销量分配。”

路由到：

```bash
catforge-insight ask "<用户原话>" --batch-id latest --product-category tv --format json
```

### 11.4 业务分析问题

用户说：

- “海信 65E7Q 的竞品有哪些？”
- “为什么 A 比 B 卖得好？”
- “哪些卖点是溢价卖点？”
- “怎么扩大销量？”
- “能抢多大的市场空间？”

路由到：

```bash
catforge-analyst ask "<用户原话>" --batch-id latest --product-category tv --format json
```

OpenClaw 小奥对外回答时必须翻译成业务语言，不暴露 CLI 和内部模块。

## 12. 输出报告口径

### 12.1 数据准备报告

报告：

- 批次号。
- 处理 SKU 数和分批情况。
- 清洗后各类行数。
- 评论过滤情况：低质评论、服务履约类评论、有效评论句子。
- 周度量价覆盖情况。
- 是否有需要人工复核的问题。
- 是否可以进入事实画像层。

### 12.2 画像重跑报告

报告：

- 重跑了哪些画像层。
- 输入 SKU 数、输出画像数、覆盖统计数。
- 警告和失败 SKU。
- 下游是否需要继续重跑。

### 12.3 图谱报告

报告：

- 用户任务、目标客群、价值战场图谱是否生成。
- 进入图谱的 SKU 数。
- 各维度覆盖 SKU 数和销量分配口径。
- 没有主任务、主客群、主战场的 SKU 数和原因。

### 12.4 卖点价值量化报告

报告：

- 分析人群、市场窗口和进入量化的 SKU 数。
- 可比池数量、池级指标数量、SKU 卖点量化数量、贡献归因数量、维度汇总数量。
- 强溢价卖点、强销量卖点、组合型增值卖点、基础门槛、用户感知不足、厂家主张、拖后腿、机会/拦截和样本不足分布。
- 明确说明这是可观测贡献估计，不是严格因果归因。

### 12.5 小奥业务回答

报告：

- 结论先行。
- 给出 2-3 个最重要判断。
- 用业务语言解释依据：尺寸价格池、价值战场、用户任务、目标客群、参数卖点重合、评论支持、重叠周销量验证。
- 不展示原始 JSON、命令、Mxx 模块名、内部 code。

## 13. 不再混用的旧概念

当前流程不再补丁式沿用旧链路来回答新问题。

不要混用：

- 原始表直接分析和清洗后事实分析。
- 旧 M05/M06 评论信号抽取和当前 M05C 评论事实画像。
- 旧 M07 尺寸口径和当前 M03B 五档尺寸口径。
- 旧 M09/M10/M11 设计和当前 M09C/M10C/M11C/M11D 语义画像及图谱。
- 执行型 CLI 和只读查询 CLI。
- 技术日志和业务回答。
- 累计销量和重叠周均销量验证。

## 14. 当前已知限制

截至 2026-06-22：

- TV 链路最完整，已覆盖参数、卖点、市场、评论、用户任务、目标客群、价值战场、语义市场图谱、卖点价值量化和小奥分析。
- AC 已有参数标准体系和参数画像能力；卖点、评论、用户任务、目标客群、价值战场 taxonomy 是否可用，需要按当前部署能力确认。
- 评论事实画像依赖 LLM，执行前必须确认 205 环境中的 LLM 配置可用。
- 大批量评论画像执行要控制并行度，先冒烟再全量。
- 如果查询返回多个候选 SKU，必须让用户二次确认；飞书入口可以做候选卡片。

## 15. 当前分支和部署口径

当前工作分支：

```text
new/m00-safe-import-hotfix
```

当前 205 部署应具备：

- `catforge-data`
- `catforge-pipeline`
- `catforge-insight`
- `catforge-analyst`
- Claude Code 的 `catforge-data`、`catforge-pipeline`、`catforge-insight` Skill
- OpenClaw 的 `xiaoao-home-appliance-market-analysis` Skill
- OpenClaw 的 `xiaoao-home-appliance-market-analyst` Agent

205 上 Claude Code 负责执行：

```text
清洗 -> 事实画像 -> 评论事实画像 -> 用户任务 -> 目标客群 -> 价值战场 -> 语义市场图谱 -> 卖点价值量化
```

205 上 OpenClaw / 小奥负责回答：

```text
竞品是谁 -> 为什么卖得好/差 -> 哪些卖点支撑选择 -> 哪些卖点是溢价卖点 -> 怎么扩大销量 -> 战场空间有多大
```
