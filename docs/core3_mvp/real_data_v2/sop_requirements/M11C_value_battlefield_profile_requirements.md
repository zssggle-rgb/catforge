# M11C 价值战场画像与图谱 SOP 需求

## 0. 定位

M11C 是新语义能力层的“价值战场画像与图谱”模块，基于已确认的品类价值战场预设，为每个 SKU 判断其主/辅/机会价值战场，并生成批次级价值战场图谱，支持查看每个价值战场覆盖哪些 SKU。

M11C 不沿用旧 M11 的战场 seed 和旧 M07 四档市场带。新模块统一使用 M03B 参数事实画像中的 TV 五档尺寸口径：

| 尺寸档 | 规则 |
| --- | --- |
| `small_32_45` | `screen_size_inch <= 45` |
| `medium_46_59` | `46 <= screen_size_inch <= 59` |
| `large_60_69` | `60 <= screen_size_inch <= 69` |
| `xlarge_70_85` | `70 <= screen_size_inch <= 85` |
| `giant_98_plus` | `screen_size_inch >= 98` |

价格带不是原始量价表字段。M11C 必须在五档尺寸内重新计算尺寸内价格位置，再用于价值战场匹配。旧 M07 的 `screen_size_class` 可作为历史参考，但不得作为 M11C 的主分组口径。

M11C 的业务定义：

```text
价值战场 = 尺寸价格竞争池 + 用户任务 + 目标客群 + 产品价值锚点 + 用户评论验证
```

它回答：

```text
这个 SKU 在哪个尺寸价格池里被比较，面向哪些用户任务和客群，靠什么产品价值参与竞争，用户是否认可。
```

## 1. 模块边界

### 1.1 必须解决

1. 加载已发布的品类价值战场 taxonomy。
2. 对每个 SKU 计算 SKU × 价值战场的匹配关系。
3. 区分主战场、辅战场、机会战场、厂家主打战场、用户观察战场、拖后腿战场和排除战场。
4. 输出每个战场的参数、卖点、评论、用户任务、目标客群、市场尺寸价格证据。
5. 对负向评论保留用户需求含义，不把负向评论直接排除，而是识别为未满足需求或拖后腿因素。
6. 生成价值战场图谱，支持查看每个价值战场覆盖哪些 SKU、主战场 SKU、辅战场 SKU、机会 SKU 和拖后腿 SKU。
7. 提供 CLI 执行和查询能力，并能被 Claude Code skill 用自然语言驱动。

### 1.2 不解决

| 不做事项 | 原因 |
| --- | --- |
| 不生成用户任务 taxonomy | 用户任务应由 M09C 或人工发布任务预设负责 |
| 不生成目标客群 taxonomy | 目标客群应由 M10C 或人工发布客群预设负责 |
| 不直接判断核心竞品 | 竞品召回和评分由后续竞品分析层负责 |
| 不把服务履约作为产品价值战场 | 服务、物流、安装、售后只能作为服务语境或风险 |
| 不强制每个 SKU 都有主战场 | 评论不足或证据分散时可以没有高置信主战场 |
| 不调用 LLM 运行时动态创建战场 | M11C 基于已发布预设确定性执行 |
| 不读取原始四张表直接做业务判断 | 必须消费上游事实层和语义层产物 |

## 2. 输入

### 2.1 必须输入

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| 价值战场 taxonomy | 人工/LLM 辅助生成并发布的品类资产 | 战场定义、准入规则、证据规则、状态封顶规则 |
| SKU 参数事实画像 | M03B | 尺寸五档、画质、刷新率、亮度、控光、智能、外观、能效等产品能力 |
| SKU 卖点事实画像 | M04C | 标准卖点、参数支撑状态、卖点维度位置 |
| SKU 评论事实画像 | M05C | 用户声音、用途、人群、价格价值、品牌力、竞品、正负向体验 |
| SKU 量价事实 | M07 或新市场事实模块 | 尺寸内价格带、销量/销额位置、价格/英寸、市场验证 |

M11C 可以读取 M07 的价格、销量、销额、周期等指标，但必须按 M03B 五档尺寸口径重新派生 M11C 自用的 `size_tier` 和 `price_band_in_size_tier`。

首版 M11C 不依赖已经落地的 SKU 用户任务画像和 SKU 目标客群画像，因为新版任务/客群模块在本开发序列中位于 M11C 之后。首版通过价值战场 taxonomy 中的 `primary_task_codes`、`secondary_task_codes`、`primary_target_group_codes` 以及对应的评论/卖点/参数规则完成任务和客群含义的间接匹配。后续 M09C/M10C 落地后，可以作为增强输入加入评分，但不得改变 M11C 的尺寸价格门槛和评论优先原则。

### 2.2 禁止输入

| 禁止输入 | 原因 |
| --- | --- |
| 原始 `comment_data` | 评论事实必须来自 M05C |
| 原始 `selling_points_data` | 卖点事实必须来自 M04C |
| 原始 `attribute_data` | 参数事实必须来自 M03B |
| 原始 `week_sales_data` | 市场事实必须来自 M07 或新市场事实模块 |
| 旧 M06 下游信号 | 旧 seed 与新任务/客群/战场口径不一致 |
| 旧 M11 战场结果 | 新 M11C 需要独立生成，不继承旧结果 |

## 3. TV 首版价值战场预设

TV 首版 M11C 价值战场 taxonomy 建议为 12 个。

| battlefield_code | 名称 | 尺寸价格基础 | 主用户任务 | 主目标客群 | 核心产品价值 |
| --- | --- | --- | --- | --- | --- |
| `BF_SMALL_SCREEN_ESSENTIAL_VALUE` | 小屏刚需性价比战场 | `small_32_45 × low/mid_low` | 卧室/副屏小空间、预算内高性价比购买 | 卧室副屏/租房用户、性价比理性用户 | 低价、尺寸适配、基础画质、易用 |
| `BF_SMALL_SMART_EASY_USE` | 小屏智能易用战场 | `small_32_45 × mid/mid_high` | 长辈易用、投屏互联 | 长辈友好用户、智能互联用户 | 语音、投屏、系统、少广告 |
| `BF_MAINSTREAM_FAMILY_VALUE` | 主流家庭性价比战场 | `medium_46_59 / large_60_69 × low/mid_low/mid` | 主流客厅日常观影 | 主流家庭观影用户、性价比用户 | 价格效率、基础画质、销量口碑 |
| `BF_MAINSTREAM_LIVING_BALANCE` | 主流客厅均衡体验战场 | `medium_46_59 / large_60_69 × mid/mid_high` | 主流客厅观影、护眼长看 | 主流家庭、儿童家庭 | 画质、系统、护眼、音效均衡 |
| `BF_LARGE_SCREEN_VALUE_UPGRADE` | 大屏换新性价比战场 | `xlarge_70_85 × low/mid_low/mid` | 大屏换新升级 | 大屏换新用户、性价比用户 | 大尺寸、价格/英寸、销量验证 |
| `BF_LARGE_SCREEN_FAMILY_CINEMA` | 大屏家庭影院战场 | `xlarge_70_85 × mid/mid_high` | 影院沉浸观影 | 大屏家庭用户、主流家庭升级用户 | 大屏、HDR、音效、家庭观影评论 |
| `BF_PREMIUM_PICTURE_UPGRADE` | 高端画质升级战场 | `large_60_69 / xlarge_70_85 × mid_high/high` | 高端画质体验 | 高端影音体验用户 | MiniLED/OLED/QD、亮度、控光、色域 |
| `BF_PREMIUM_VALUE_DOWNTRADE` | 高配下探价值战场 | `xlarge_70_85 × mid/mid_high` | 高端画质体验、大屏换新 | 高端但重视性价比用户 | 高端参数成立，但价格低于同级高端 |
| `BF_GAMING_SPORTS_FLUENCY` | 游戏体育流畅战场 | 中大尺寸 × `mid` 以上 | 主机游戏、体育赛事 | 游戏体育用户 | 高刷、HDMI2.1、VRR、MEMC、低延迟 |
| `BF_EYE_CARE_FAMILY_COMFORT` | 家庭护眼舒适战场 | 小/中/大尺寸 × `mid_low` 以上 | 长时间护眼观看 | 儿童家庭、主流家庭、长辈家庭 | 护眼、低蓝光、无频闪、舒适评论 |
| `BF_SMART_CONNECTED_EXPERIENCE` | 智能互联体验战场 | 中尺寸及以上 × `mid` 以上 | 投屏互联与智能控制 | 智能互联用户、年轻家庭 | AI 语音、投屏、家电联动、摄像头 |
| `BF_GIANT_HOME_THEATER_FLAGSHIP` | 巨幕家庭影院旗舰战场 | `giant_98_plus × mid_high/high` | 巨幕影院、新家空间融合 | 巨幕家庭影院用户、新家装修/大户型用户 | 巨幕、旗舰画质、音画沉浸、贴墙空间适配 |

## 4. 匹配优先级

M11C 匹配优先级为：

```text
尺寸价格门槛
-> 评论中的用户需求和体验
-> 已成立用户任务
-> 已成立目标客群
-> 标准卖点表达
-> 标准参数能力
-> 市场销量/销额验证
```

说明：

1. 价值战场必须先过尺寸价格门槛。门槛不匹配时，不得成为主战场。
2. 评论是用户真实需求证据，优先说明“用户是否在这个战场里使用和评价”。
3. 卖点是厂家表达，参数是产品能力。厂家表达和产品能力用于判断是否能把用户需求变成溢价价值。
4. 评论强但参数/卖点弱，仍可识别用户观察战场或拖后腿战场，但不能判为溢价战场。
5. 卖点强但评论弱，只能判为厂家主打战场或机会战场。
6. 参数强但评论/卖点弱，只能判为潜在机会，不作为主价值战场。
7. 服务履约评论必须隔离，不进入产品价值战场。

## 5. 输出

### 5.1 SKU 价值战场画像

每个 SKU 输出：

| 字段 | 含义 |
| --- | --- |
| `primary_battlefield_code` | 主价值战场，可空 |
| `secondary_battlefield_codes` | 辅价值战场，最多 2 个 |
| `opportunity_battlefield_codes` | 机会战场 |
| `drag_factor_battlefield_codes` | 用户需求存在但产品体验负向或支撑不足的战场 |
| `size_tier` | M03B 五档尺寸口径 |
| `price_band_in_size_tier` | M11C 在尺寸档内计算的价格带 |
| `user_voice_summary` | 评论对战场的正负向摘要 |
| `task_group_summary` | 用户任务和目标客群支撑摘要 |
| `claim_param_summary` | 卖点和参数支撑摘要 |
| `value_effect_summary` | 溢价、基础支撑、拖后腿、未满足需求等判断 |
| `review_required` | 是否需要人工复核 |

### 5.2 SKU × 价值战场分数

每个 SKU × 战场输出：

| 字段 | 含义 |
| --- | --- |
| `relation_status` | `primary_battlefield`、`secondary_battlefield`、`opportunity_battlefield`、`brand_claimed_battlefield`、`user_observed_battlefield`、`drag_factor_battlefield`、`excluded` |
| `battlefield_score` | 综合分 |
| `market_gate_status` | `matched`、`adjacent`、`mismatch`、`unknown` |
| `user_voice_score` | 评论用户声音强度 |
| `task_group_fit_score` | 用户任务和目标客群适配分 |
| `claim_alignment_score` | 标准卖点表达分 |
| `param_capability_score` | 参数能力支撑分 |
| `market_validation_score` | 销量、销额、价格位置验证分 |
| `sentiment_polarity` | `positive`、`negative`、`mixed`、`neutral`、`unknown` |
| `value_effect` | `premium_driver`、`basic_support`、`brand_claim_only`、`user_observed_need`、`drag_factor`、`unmet_need`、`not_applicable` |
| `confidence` | 置信度 |
| `evidence_ids` | 可追溯证据 |

### 5.3 价值战场图谱

批次级输出：

| 输出 | 用途 |
| --- | --- |
| 战场节点 | 战场定义、名称、规则版本、SKU 覆盖数 |
| SKU 节点 | SKU、型号、品牌、尺寸档、价格带、主/辅战场 |
| 战场-SKU 边 | 每个 SKU 在该战场的状态、分数、价值作用 |
| 战场-任务边 | 战场主要由哪些用户任务支撑 |
| 战场-客群边 | 战场主要服务哪些目标客群 |
| 战场-卖点边 | 战场核心卖点和拖后腿卖点 |
| 战场-参数边 | 战场核心参数能力 |
| 覆盖统计 | 每个战场主战场 SKU、辅战场 SKU、机会 SKU、拖后腿 SKU |

图谱必须支持回答：

1. 某个 SKU 落在哪些价值战场。
2. 某个价值战场有哪些 SKU。
3. 某个价值战场主战场 SKU 有哪些。
4. 某个价值战场有哪些拖后腿 SKU。
5. 某个战场的主要任务、客群、卖点和参数证据是什么。

## 6. CLI 与 Skill 要求

### 6.1 Pipeline CLI

实现时必须提供执行 CLI：

```bash
python -m app.cli.catforge_pipeline run-value-battlefield --product-category tv --batch-id latest --force-rebuild --format json
```

必须支持：

| 参数 | 说明 |
| --- | --- |
| `--product-category` | 品类，首版 `tv` |
| `--batch-id` | 批次，默认支持 `latest` |
| `--sku-code` | 只跑单 SKU |
| `--battlefield-code` | 只跑指定战场，可重复 |
| `--force-rebuild` | 清理并重算当前范围 |
| `--graph-mode` | `inline`、`skip`、`rebuild-only` |
| `--format` | `json`、`text` |

自然语言入口必须识别：

- “生成彩电价值战场画像”
- “重新分析某个 SKU 的价值战场”
- “生成价值战场图谱”
- “新数据来了，把价值战场准备好”

### 6.2 Insight CLI

实现时必须提供查询 CLI：

```bash
python -m app.cli.catforge_insight sku-value-battlefield --sku-code TV00000000 --format json
```

```bash
python -m app.cli.catforge_insight value-battlefield-skus --battlefield-code BF_LARGE_SCREEN_VALUE_UPGRADE --sku-limit 100 --format json
```

```bash
python -m app.cli.catforge_insight value-battlefield-graph --product-category tv --format json
```

必须支持自然语言查询：

- “查某 SKU 的价值战场”
- “大屏换新性价比战场有哪些 SKU”
- “哪些 SKU 在高端画质升级战场拖后腿”
- “查彩电价值战场图谱”
- “查某价值战场的任务、客群、卖点、参数证据”

### 6.3 Claude Code Skill

实现 CLI 后必须同步更新：

| Skill | 要求 |
| --- | --- |
| `tools/claude/skills/catforge-pipeline/SKILL.md` | 加入价值战场生成和图谱生成的自然语言触发、稳定命令、执行后摘要规则 |
| `tools/claude/skills/catforge-insight/SKILL.md` | 加入 SKU 价值战场、战场覆盖 SKU、价值战场图谱的查询触发和稳定命令 |

在 CLI 未实现前，不得把未实现命令写入已安装 skill，避免 Claude Code 误执行。

## 7. 验收标准

1. TV 价值战场 taxonomy 覆盖 12 个预设战场。
2. 每个战场都有尺寸价格门槛、评论规则、卖点规则、参数规则、任务/客群映射。
3. 每个 SKU 能输出 0-1 个主战场、0-2 个辅战场和若干机会/拖后腿战场。
4. 评论负向集中时，不得简单排除；必须能输出 `drag_factor_battlefield` 或 `unmet_need`。
5. 卖点强但评论弱时，不得直接判主战场；应输出 `brand_claimed_battlefield` 或机会战场。
6. 参数支撑不足的卖点不得作为 `premium_driver`。
7. 服务履约、物流安装、售后体验不得进入产品价值战场。
8. 图谱能查询每个价值战场包含哪些 SKU，并区分主/辅/机会/拖后腿状态。
9. CLI 支持全量、单 SKU、单战场和图谱重建。
10. Skill 能把自然语言请求映射到 CLI 执行或查询。

## 8. 性能与安全

M11C 不需要运行时 LLM，默认确定性执行。

执行策略：

- 当前 TV 首版可一次读取目标 SKU 集合并生成 SKU × 战场分数；可用 `sku_code` 限定单 SKU 或小范围重跑。
- 每次执行只读取目标 SKU 的参数、卖点、评论和市场事实；首版通过战场 taxonomy 间接使用任务/客群规则。
- 图谱默认在 SKU 分析完成后重建一次；可用 `graph_mode=skip` 只写 SKU 画像和分数。
- 后续多品类或大规模 SKU 扩展时，再补充 chunk 执行和图谱单独重建能力。
- 不得一次加载全量评论原文；只能读取 M05C 聚合画像和必要 evidence 摘要。
- 测试不得调用外部 LLM。
- 输出必须带 `project_id`、`category_code`、`batch_id`、`taxonomy_version`、`rule_version`、`evidence_ids`、`confidence` 和 `review_status`。
