# TV/AC 数据对齐 Goal 调度设计

日期：2026-07-08

本设计用于把 205 上 TV 和 AC 的数据处理结果对齐到“小奥/智能体”实际消费的最新链路。执行约束是：不重跑 M00-M02，只消费现有清洗表和 evidence atom；所有后续任务按 goal 模式分步推进；每 10 分钟 heartbeat 唤醒一次当前线程继续执行。

## 1. 当前消费链路

智能体当前消费的主链路不是旧展示页链路，而是：

```text
M03B 参数事实画像
  -> M04C 卖点事实画像
  -> M05C 评论事实画像
  -> M07 市场画像
  -> M09C 用户任务画像
  -> M10C 目标客群画像
  -> M11C 价值战场画像
  -> M11D 语义市场图谱与销量分配
  -> M12C 卖点价值量化与贡献归因
  -> catforge_analyst / 小奥
```

验收不能只看某个 Mxx 表有行数，要确认 `product_category`、`category_code`、`batch_id`、`rule_version`、`is_current` 和智能体读取逻辑一致。

## 2. 不重跑 M00-M02 的处理原则

不重跑 M00-M02 表示：

1. 不重新注册 source batch。
2. 不重新清洗 raw 表。
3. 不重新生成 evidence atom。
4. 下游只能基于现有 `core3_clean_*` 和 `core3_evidence_atom` current/active 数据补齐。

这会带来一个关键设计要求：TV 的输入数据已经分布在多个已存在 batch，不能简单用 `--batch-id latest` 代表完整 TV。后续必须建立一个明确的 serving scope 或 serving batch 口径，让 `catforge_analyst latest` 能读到完整业务底座。

## 3. 已确认的当前状态

本计划记录的最新对齐状态：

| 品类 | raw 销售/参数 | raw 卖点 | raw 评论 | M02 销售/参数 | M02 卖点 | M02 评论 | 当前主要缺口 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| TV | 377 | 328 | 360 | 377 | 328 | 348 | M03B/M04C/M05C/M07 已按当前规则对齐；M09C/M10C/M11C 已按 348 comment-ready 语义可消费口径对齐，29 个无评论 SKU 标记为 semantic-ineligible；M11D graph SKU 348；M12C current quantification SKU 289 |
| AC | 155 | 155 | 147 | 155 | 155 | 144 | M03B-M05C/M07 已按当前口径对齐；M09C/M10C/M11C 已按 144 comment-ready 语义可消费口径对齐，11 个无评论 SKU 标记为 semantic-ineligible；M11D `fact_complete_with_comment` graph SKU 140，`all_semantic_profiles` graph SKU 144；M12C claim value SKU 140 |

AC 的用户任务、目标客群、价值战场标准已经存在，并且已有输出：

- M09C：`m09c_ac_user_task_taxonomy_v0.1` / `m09c_ac_user_task_profile_v0.1`
- M10C：`m10c_ac_target_group_taxonomy_v0.1` / `m10c_ac_target_group_profile_v0.1`
- M11C：`m11c_ac_value_battlefield_taxonomy_v0.1` / `m11c_ac_value_battlefield_profile_v0.1`

但 2026-07-08 复核显示，AC 不能只按“表里有 155 行”验收。当前 `category_code=AC` / `batch_id=m00_20260624000202_1150a669`：

| 模块 | profile 行覆盖 | 有主 code 的 SKU | 主 code 缺口 |
| --- | ---: | ---: | ---: |
| M09C 用户任务 | 155 | 143 | 12 |
| M10C 目标客群 | 155 | 141 | 14 |
| M11C 价值战场 | 155 | 128 | 27 |

这意味着 AC 的 SKU 画像“记录”已生成，但并非每个 SKU 都有可直接供智能体消费的主用户任务、主目标客群、主价值战场。后续必须补一个 AC 画像完整性任务，不能直接进入 M11D/M12C。

AC G10 已补齐 M12C 的 product-category 适配：

- M12C repository 已按 `product_category` 选择 AC M03B/M04C/M05C/M09C/M10C/M11C/M11D rule version。
- `catforge_pipeline.PRODUCT_CATEGORY_CONFIGS["AC"]` 中 `claim_value_quantification_rule_version` 已打开。
- M12C 输出仍沿用通用 `m12c_claim_value_quantification_v0.1`，但运行摘要写入 `input_rule_versions`，用于证明 AC 结果没有静默套用 TV 上游规则。

## 3.1 执行闭环修订：最小可决策闭环

后续执行里的“每轮只做一个子任务”指的是一次只推进一个 Gxx 模块，不是把一个 Gxx 拆成很小的 SKU chunk 后反复停止验收。

新的闭环口径如下：

1. 一个 heartbeat/goal turn 只选择一个 Gxx，但可以在该 Gxx 内连续跑批，直到到达可判断边界。
2. “最小闭环”定义为“最小可决策闭环”：能判断该 Gxx 已完成、需要进入异常队列、需要改代码/配置、需要用户决策，或存在安全风险。
3. 不再对每个很小 SKU chunk 做完整验收；小批只做轻量进度检查，完整覆盖验收放在模块边界或连续失败阈值处。
4. LLM 类任务先做一次 smoke，后续默认使用批量和受控并发，不通过把 `llm_batch_size` 降到 1/3/5 来“降负载”。
5. 主链路和异常链路分开：主链路能继续时继续推进；失败 SKU 进入 retry/review/exclusion 清单，不能静默消失。
6. 允许某个 Gxx 在 10 分钟后继续运行同一个模块；10 分钟是调度节奏，不是自动停止条件。

当前 M05C 默认执行参数：

```bash
--llm-batch-size 20 --llm-parallelism 3 --max-sentences-per-sku 80
```

批量补跑时用 SKU worker 控制总并发，默认从 `--parallelism 2` 起步。只有新路径上线、异常复现、远端安全排查时，才使用很小的单 SKU smoke。

## 4. 子任务拆分

### G01：冻结 serving 输入口径

状态：已完成。执行记录见 `tmp/catforge_alignment_20260708/G01_execution_record.md`。

目标：形成 TV/AC 本次对齐的输入 SKU 清单，不改 M00-M02。

操作：

1. 查询 TV 和 AC 在 raw、clean active、M02 evidence current 下的 SKU 覆盖。
2. 输出三类清单：
   - `market_param_skus`
   - `claim_skus`
   - `comment_skus`
3. 明确 TV 多 batch 输入如何被下游统一消费。

验收：

- TV 输入清单应覆盖：market/param 377，claim 328，comment evidence 348。
- AC 输入清单应覆盖：market/param/claim 155，comment evidence 144。
- 文档或临时 JSON 明确保存在 `tmp/`，后续任务可复用。

### G02：TV serving scope 设计与实现

状态：已完成。执行记录见 `tmp/catforge_alignment_20260708/G02_execution_record.md`。

目标：让 TV 下游和 `catforge_analyst latest` 能消费完整 TV 数据，而不是只读某个增量 batch。

建议方案优先级：

1. 优先实现显式 serving batch/scope 映射，例如 `tv_current_20260708`。
2. 如果实现成本过高，先实现下游 runner 的 batch list 输入或复用 current-by-sku 视图。
3. 禁止直接把 6 月 23 评论增量 batch 当完整 TV latest。

验收：

- `catforge_analyst` resolve latest 时能落到完整 TV serving 口径。
- 不影响 AC `category_code=AC` 读取。
- 有单元测试覆盖 latest batch 解析和 product category 过滤。

### G03：TV M03B/M04C/M07 对齐

状态：已完成。执行记录见 `tmp/catforge_alignment_20260708/G03_execution_record.md`。

目标：TV 事实画像层与当前规则版本一致。

操作：

1. 补齐 TV 当前规则 M03B，覆盖 377 SKU。
2. 确认 M04C 当前卖点事实覆盖 328 SKU。
3. 确认或重跑 M07 当前市场画像，覆盖 377 SKU。

验收：

- M03B `m03b_tv_param_profile_v0.1`：377 SKU。
- M04C `m04c_tv_claim_fact_profile_v0.1`：328 SKU。
- M07 `m07_market_profile_v1`：377 SKU。
- 任一缺口有具体 SKU 和原因。

### G04：TV M05C 评论事实补齐

状态：已完成。进度记录见 `tmp/catforge_alignment_20260708/G04_progress_record.md`。

目标：在已从 183 推进到 236 的基础上，继续把 TV 评论事实补到接近 M02 可用评论证据上限 348。

完成结果：

- 旧 TV 批次 `m00_20260613004311_d548f6dc`：75/75 已完成。
- 6/19 主批次 `m00_20260619084551_857df63b`：183/183 已完成。
- 6/23 评论增量批次 `m00_20260623014631_c8630747`：90/90 已完成。
- 当前 TV M05C serving unique：348/348。
- 三段 M05C coverage 已按当前规则重建完成。
- LLM timeout 根因已修复，默认使用 `--llm-batch-size 20 --llm-parallelism 3 --max-sentences-per-sku 80`，不要再通过把 batch 拆到 1/3/5 来降负载。

操作：

1. 执行前做只读检查：当前 M02 comment evidence、M05C current coverage、残留进程。
2. 先补 6/23 评论增量批次剩余 SKU，再补旧 TV 批次剩余 SKU。
3. 默认使用批量 runner，而不是手工逐 SKU 循环：

```bash
python -m app.cli.catforge_pipeline run-comment-profile-batch \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id m00_20260623014631_c8630747 \
  --product-category tv \
  --llm-mode required \
  --llm-batch-size 20 \
  --llm-parallelism 3 \
  --max-sentences-per-sku 80 \
  --parallelism 2 \
  --limit 10 \
  --skip-final-coverage \
  --format json
```

4. 每个批量命令后只做轻量进度检查和残留进程检查；不要因为还没到 348 就完整重验所有下游。
5. 对仍失败或被跳过的 SKU 输出原因：无有效评论句、低价值、服务履约、LLM 失败、超时、上游画像缺失等。
6. 到达 G04 边界时执行 coverage rebuild 和完整覆盖验收。

验收：

- 主链路验收：TV M05C `m05c_tv_comment_fact_profile_v0.1` 补齐到接近 348，或剩余 SKU 全部进入带原因的 retry/review/exclusion 清单。
- 最终验收：TV M05C 接近 M02 comment evidence 上限 348；raw 360 与 M02 348 之间的 12 个差异有原因。
- M05C 缺口列表为空；如非空，必须有可接受排除原因，且 G05 能显式降级为 `comment_profile_pending`、`comment_missing` 或 `review`，不能静默缺行。

### G05：TV M09C/M10C/M11C 对齐

状态：已完成。执行记录见 `tmp/catforge_alignment_20260708/G05_execution_record.md`。

目标：TV 用户任务、目标客群、价值战场覆盖完整 TV serving 语义可消费 SKU。

口径修订：

1. TV market/param serving scope 仍为 377 SKU，不删除、不物理合并历史 batch。
2. M09C/M10C/M11C 只对有 M05C 当前评论事实画像的 SKU 生成语义画像。
3. 无 M05C 评论事实画像的 SKU 不生成用户任务、目标客群、价值战场，旧 current 结果取消当前态，并写入 `comment_missing_exclusion_reason=missing_m05c_comment_fact_profile_semantic_ineligible`。
4. 智能体读取时只消费 `category_code + product_category + rule_version + is_current + serving scope` 下的当前结果，不直接按裸 `batch_id` 推断完整业务结论。

操作顺序：

```text
M09C -> M10C -> M11C
```

执行口径：

1. 每个模块单独闭环：M09C 全量生成并验收后再进 M10C，M10C 全量生成并验收后再进 M11C。
2. 不按很小 SKU chunk 做完整验收；模块内只做进度检查，模块边界做覆盖和缺口原因验收。
3. M05C 未完成或进入异常清单的 SKU，必须被 M09C/M10C/M11C 显式排除或降级，不能静默混入业务画像。
4. 如果规则缺口导致大面积 unknown/review，先修 taxonomy/rule/fallback，再重跑对应模块。

验收：

- TV serving market/param：377 SKU。
- TV M05C 当前评论事实画像：348 SKU。
- M09C `m09c_tv_user_task_profile_v0.2` 当前画像：348 SKU，29 个无评论 SKU 无 current 画像。
- M10C `m10c_tv_target_group_profile_v0.2` 当前画像：348 SKU，29 个无评论 SKU 无 current 画像。
- M11C `m11c_tv_value_battlefield_profile_v0.3` 当前画像：348 SKU，29 个无评论 SKU 无 current 画像。
- 跨批次评论 SKU 必须可生成画像，例如 6/19 市场批次 SKU `TV00026064` 消费 6/23 评论增量后 M09C/M10C/M11C current 均为 true。
- 真无评论 SKU 必须不生成语义画像，例如旧批次 SKU `TV00009549` 的 M09C/M10C/M11C current 均为 false。

### G06：TV M11D/M12C 全量生成

状态：已完成。执行记录见 `tmp/catforge_alignment_20260708/G06_execution_record.md`。

目标：TV 形成智能体可消费的完整语义市场图谱和卖点价值量化。

完成结果：

- M11D 业务图谱 graph SKU：348。
- M11D allocation SKU：344。
- M12C comparable SKU：295。
- M12C current quantification SKU：289。
- 用户关注的 11 个 M11C profile `primary_battlefield_code` 为空 SKU 已通过 M11C score fallback 纳入 M12C。
- 6 个 comparable SKU 无量化行，原因是当前 M12C 角色/可比池规则没有形成可量化 claim row，已在 G06 记录中列出。

操作：

1. M11D 使用 `fact_complete_with_comment` 业务口径。
2. 可附加 `all_semantic_profiles` 诊断口径，用于解释未进业务图谱 SKU。
3. M12C 使用 `claim_value_ready_with_comment`。
4. 如果 G04 仍有异常 SKU，M11D/M12C 要输出可解释的排除诊断，不把异常吞掉。
5. M11D 和 M12C 各自按一次完整 population 生成并验收，不按很小 SKU chunk 作为完成边界。

验收：

- TV M11D 业务图谱覆盖 348 SKU。
- TV M12C 覆盖 289 个有 current quantification 行的 SKU；295 个 SKU 进入 comparable，6 个无量化行的 SKU 有原因清单。
- `catforge_analyst battlefield-space`、`sku-claim-value`、`claim-contribution` 能读取结果。
- 业务图谱缺口和卖点价值缺口都能追溯到上游证据、异常清单或可接受排除原因。

### G07：AC M05C 尾差审计

状态：已完成。执行记录见 `tmp/catforge_alignment_20260708/G07_execution_record.md`。

目标：解释或修复 AC raw 评论 147 与 M05C 144 的差异。

完成结果：

- AC M02 current comment evidence SKU：144。
- AC M05C current `m05c_ac_comment_fact_profile_v0.1` SKU：144。
- M02 current comment evidence 缺 M05C SKU：0。
- raw/clean 147 到 M05C 144 的差异来自上游清洗和 M02 证据资格，不是 M05C 漏跑：
  - `AC00036291`：clean comment 仅有 skipped row，无 active comment、无 sentence、无 M02 comment evidence。
  - `AC00039044`：active comment 全为低价值默认/空评价，无 sentence、无 M02 comment evidence。
  - `AC00039082`：active comment 全为低价值默认/空评价，无 sentence、无 M02 comment evidence。
- G07 未写 205 数据，未重跑 M00-M02，也无需补跑 M05C。

操作：

1. 查 3 个缺口 SKU 的 clean/M02/M05C 状态。
2. 若有有效 M02 评论句但无 M05C，补跑。
3. 若无有效产品评论，记录排除原因。

验收：

- AC M05C 达到 144+，缺口原因明确。
- AC 后续 M11D 使用的业务 population 可解释。

### G08：AC M09C/M10C/M11C 画像完整性补齐

状态：已完成。执行记录见 `tmp/catforge_alignment_20260708/G08_execution_record.md`。

目标：让 AC 每个 SKU 都具备智能体可消费的用户任务、目标客群、价值战场画像，或者给出明确的 unknown/review 降级原因，不能只看 profile 行数。

完成结果：

- AC semantic 输入口径已从 155 个市场/参数 SKU 收敛到 144 个 M05C comment-ready SKU。
- 11 个无 M05C 评论事实画像 SKU 已从 M09C/M10C/M11C current 画像中排除，排除原因为 `missing_m05c_comment_fact_profile_semantic_ineligible`。
- M09C current profile：144，主用户任务：143，剩余 1 个 review reason。
- M10C current profile：144，主目标客群：141，剩余 3 个 review reason。
- M11C current profile：144，主价值战场：142，剩余 2 个 review reason。
- M11C 修复 AC `adjacent` 稀疏可比池下的主战场规则；高置信 adjacent opportunity 可升主战场，TV 规则不变。
- 下游 G09 `fact_complete_with_comment` 当前预期为 140 个三类主画像齐全 SKU；`all_semantic_profiles` 诊断口径为 144 个 comment-ready SKU。

操作：

1. 拉取缺主 code 的 SKU 清单和各自 M03B/M04C/M05C/M07 上游可用性。
2. 判断缺口原因：评论缺失、参数缺失、卖点缺失、价格带未知、规则未覆盖、只生成了 review/unknown。
3. 先按原因分组形成一次性修复方案，不按单个 SKU 手工补洞。
4. 如果上游数据足够但规则未覆盖，修正 AC taxonomy/rule 或 runner fallback 后按模块重跑 M09C/M10C/M11C。
5. 如果上游数据不足，写入可消费的 unknown/review reason，保证智能体能解释而不是静默空值。
6. M09C、M10C、M11C 分别以模块边界验收；小批只用于 smoke 或异常复现。

验收：

- AC M09C profile 行数 144，且每个 comment-ready SKU 有 `primary_user_task_code` 或明确 unknown/review reason。
- AC M10C profile 行数 144，且每个 comment-ready SKU 有 `primary_target_group_code` 或明确 unknown/review reason。
- AC M11C profile 行数 144，且每个 comment-ready SKU 有 `primary_battlefield_code` 或明确 unknown/review reason。
- 无 M05C 评论事实画像 SKU 不生成 current 用户任务、目标客群、价值战场画像。
- 缺主 code 的 SKU 如非空，必须有业务可接受的降级原因；真正 analyst 入口读取在 G09/G11 验收。

### G09：AC M11D 适配与生成

状态：已完成。执行记录见 `tmp/catforge_alignment_20260708/G09_execution_record.md`。

目标：让 AC 进入语义市场图谱。

完成结果：

- M11D 已增加 AC input rules，按 AC M05C/M09C/M10C/M11C/M07 规则隔离读取。
- `catforge_pipeline.PRODUCT_CATEGORY_CONFIGS["AC"]["semantic_market_rule_version"]` 已打开。
- `fact_complete_with_comment` 按 G08 三类主画像齐全口径生成 140 个 SKU。
- `all_semantic_profiles` 按 comment-ready 诊断口径生成 144 个 SKU。
- `catforge_analyst semantic-dimension-space --product-category ac` 和 `battlefield-space --product-category ac` 均可读取。
- 本地 M11D 目标测试 8 passed；M09C/M10C/M11C/M11D 组合测试 27 passed。

实现点：

1. 给 M11D 增加 AC input rules：
   - M05C AC rule/taxonomy
   - M09C AC rule/taxonomy
   - M10C AC rule/taxonomy
   - M11C AC rule/taxonomy
   - M07 market rule
2. `catforge_pipeline.PRODUCT_CATEGORY_CONFIGS["AC"]` 打开 `semantic_market_rule_version`。
3. 加测试覆盖 AC input rule 过滤，避免误读 TV。

执行口径：

- 代码/配置适配、单元测试、远端 smoke、全量生成、analyst 读取检查是一个 G09 闭环。
- 不能只打开配置就标记完成；必须能生成并被 `catforge_analyst` 按 `product_category=ac` 读取。
- 如 AC G08 仍有异常 SKU，M11D 输出必须携带可解释排除或降级诊断。

验收：

- AC M11D `fact_complete_with_comment` 接近 140 SKU。
- AC M11D `all_semantic_profiles` 接近 144 SKU。
- `catforge_analyst semantic-dimension-space --product-category ac` 可读取。

### G10：AC M12C 适配与生成

状态：已完成。执行记录见 `tmp/catforge_alignment_20260708/G10_execution_record.md`。

目标：让 AC 进入卖点价值量化与贡献归因。

完成结果：

- AC M12C 可量化交集：140 SKU。
- M12C context pool：902。
- M12C pool metric：902。
- M12C SKU claim value：140 SKU / 6303 rows。
- M12C contribution attribution：140 SKU / 2491 rows。
- M12C dimension summary：514 rows。
- 405 条 review issue 均为 pool 级 `sample_insufficient`，不是 SKU 级静默失败。
- `catforge_analyst sku-claim-value --product-category ac`、`claim-value-space --product-category ac`、`claim-contribution --product-category ac` 均可读取。
- 本地 M12C product-category + param parsing 测试 17 passed；M12C + M11D 回归测试 25 passed。

实现点：

1. M12C repository 按 product_category 选择 M04C/M05C/M09C/M10C/M11C rule version。
2. 增加 AC claim-code 到 param fallback、门槛卖点、差异化卖点、场景卖点规则。
3. 本次保留通用 M12C 输出 rule version 以兼容现有 analyst/publish 过滤；AC 可追溯性通过 `product_category=AC` 和 `input_rule_versions` 固化，不静默套 TV 上游规则。
4. `catforge_pipeline.PRODUCT_CATEGORY_CONFIGS["AC"]` 打开 claim-value quantification 规则。

执行口径：

- 代码/规则适配、测试、远端 smoke、全量生成、analyst 读取检查是一个 G10 闭环。
- 不把 TV 的卖点价值规则静默套到 AC；AC claim value 规则必须有可追溯的 AC 口径。
- 如初始可量化交集小于预期，先输出缺口分层，再决定补规则还是进入 review。

验收：

- 冒烟 SKU 能生成 pool metric、SKU claim value、contribution attribution。
- AC M12C 覆盖当前可量化交集 140 SKU。
- `catforge_analyst sku-claim-value --product-category ac` 可读取。

### G11：智能体验收

状态：已完成。执行记录见 `tmp/catforge_alignment_20260708/G11_execution_record.md`。

目标：证明 TV/AC 智能体入口可以基于最新对齐结果回答业务问题。

完成结果：

- TV `ask "TV00026228 的竞品有哪些"` 路由到 `competitor-set`，读取 TV batch `m00_20260619084551_857df63b`。
- TV `ask "TV00026228 哪些卖点是溢价卖点"` 路由到 `premium-claim-drivers`，读取 TV M12C/M07 等派生结果。
- AC `ask "AC00038662 的目标客群是什么"` 路由到 `sku-business-brief`，读取 AC batch `m00_20260624000202_1150a669`，并对缺失 `semantic_dimension_positions` 给出 limitation。
- AC `ask "AC00038662 哪些卖点支撑销量"` 路由到 `claim-contribution`，读取 AC M12C 归因结果。
- TV `battlefield-space --product-category tv` 返回 13 个战场，首个 `BF_LARGE_SCREEN_VALUE_UPGRADE`。
- AC `battlefield-space --product-category ac` 返回 11 个战场，首个 `BF_WALL_1_5_MAINSTREAM_VALUE`。
- 验收过程中发现 205 compose 被重建成连接本地空 Postgres；已切回 `docker-compose.cloud.yml` + `.env` 的外部 `catforge_dev`，并重新热更新运行容器代码。

遗留风险：

- `/opt/catforge` 源目录由 uid 501 持有，`deploy` 无 sudo，无法把本地提交直接固化到远端源码。当前运行容器正确；后续如重建容器，必须先通过正常部署同步本地提交。

验收命令方向：

```bash
catforge-analyst ask "<TV SKU> 的竞品有哪些" --product-category tv --format json
catforge-analyst ask "<TV SKU> 哪些卖点是溢价卖点" --product-category tv --format json
catforge-analyst ask "<AC SKU> 的目标客群是什么" --product-category ac --format json
catforge-analyst ask "<AC SKU> 哪些卖点支撑销量" --product-category ac --format json
catforge-analyst battlefield-space --product-category tv --format json
catforge-analyst battlefield-space --product-category ac --format json
```

验收标准：

- 不读取 raw 表形成业务结论。
- 不暴露 Mxx、batch、SQL 给业务回答层。
- TV/AC 不串品类。
- 缺评论或样本不足时降级说明，不把 unknown 当 false。

## 5. Heartbeat 执行协议

当前 heartbeat 自动化已按用户要求停止；如果重新启用，每次 10 分钟 heartbeat 唤醒后执行：

1. 调用 `get_goal` 确认总 goal 仍 active。
2. 读取本文件和当前 git/status。
3. 读取上一轮输出或验收记录。
4. 选择第一个未完成子任务 G01-G11。
5. 只推进这个 Gxx 的最小可决策闭环，而不是只跑一个很小 SKU chunk。
6. 不重跑 M00-M02。
7. 如果要写 205 数据，先做只读检查和小范围冒烟。
8. 在同一个 Gxx 内允许连续跑批，直到出现以下任一停止条件：
   - Gxx 达到模块验收边界。
   - 连续失败达到阈值，需要代码/配置修复。
   - 出现需要用户决策的业务口径问题。
   - 出现 205 残留进程、写入异常、品类串写等安全风险。
   - 用户明确要求停止。
9. 不因 10 分钟自然停止；10 分钟只是下一次调度节奏。
10. 每轮结束写一条简短执行记录，说明：
   - 完成了哪个子任务。
   - 执行了哪些命令。
   - 当前处于模块完成、异常队列、代码修复、用户决策还是安全停止。
   - 输出覆盖是否达到验收；如果只是中间小批，只记录增量进度，不做完整验收结论。
   - 下一个子任务是什么。

完成 G11 且所有验收通过后，调用 `update_goal(status="complete")`。

## 6. 当前首轮建议

第一轮 heartbeat 从 G01 开始，不改代码，只冻结输入口径并保存 SKU 覆盖清单。

如果 G01 已由当前人工检查覆盖，可直接进入 G02，但仍要把清单落盘，避免后续任务基于口头结论继续。
