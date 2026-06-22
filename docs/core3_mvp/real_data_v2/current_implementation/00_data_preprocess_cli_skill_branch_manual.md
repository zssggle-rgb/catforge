# 数据预处理 CLI 与 Claude Code Skill 分支开发手册

本文档记录数据预处理能力的当前实现，内容最初来自 `hotfix/data-preprocess-20260618`，现已整合到当前开发分支，作为后续对外开放、外部 agent 调用、运维执行和问题排查的参考手册。

本文件是分支级总手册，重点说明 CLI、Claude Code skill、部署验证和外部调用方式。M00、M01、M02 的当前实现细节以同目录下的模块文档为准：

- [M00 原始数据登记当前实现说明](01_m00_source_registry_implementation.md)
- [M01 清洗与质量过滤当前实现说明](02_m01_cleaning_quality_implementation.md)
- [M02 Evidence 原子层当前实现说明](03_m02_evidence_atom_implementation.md)

本文档面向三类读者：

- 业务使用者：知道“预处理新数据”“看看某个 SKU 清理情况”等业务命令，但不需要知道 M00/M01/M02。
- Agent/自动化调用方：需要用自然语言或程序调用 CLI，并稳定解析 JSON 结果。
- 工程/运维人员：需要理解本分支改了哪些模块、如何部署、如何验证、如何避免 205 负载风险。

## 1. 分支范围

当前整合分支：`new/m00-safe-import-hotfix`

原始开发分支：`hotfix/data-preprocess-20260618`

基线主分支：`origin/main` 的 `396607f docs: add Core3 real-data analysis flow explainer`

本分支主要提交：

```text
1196940 feat: add preliminary CatForge data cleaning CLI
0e4dc0e docs: add Claude Code project guidance
1ade086 chore: add Claude skill plugin author
3be8e1d fix: install Claude Code skill component
74214bf fix: sync 205 data preprocess hotfix
bc1ba3c fix: make m01 cleaning chunk-safe
e88a7e9 fix: allow standalone data cli cleaning
b573f64 fix: default data preprocess to m00 m01
dd3b5d6 fix: make data cli status inspection reliable
054b285 feat: add sku-level preprocessing inspection cli
d8707d7 hotfix: make data preparation include M02 evidence
b731f89 hotfix: filter low value comments in M02 SQL
bfdfb90 hotfix: chunk M02 inactive evidence updates
```

本分支的业务目标：

```text
让“新数据进来后先准备好可分析数据”成为一个可被 CLI 和 Claude Code skill 共同驱动的原子能力。

默认执行边界：
原始数据登记 M00
  -> 初步清洗与质量过滤 M01
  -> 分析证据准备 M02

不默认进入 M05 或更后面的评论语义、画像、竞品分析阶段。
```

## 2. 新增和修改文件总览

### 2.1 CLI 与 Agent 指令

- `.claude/skills/catforge-data/.claude-plugin/plugin.json`
- `.claude/skills/catforge-data/SKILL.md`
- `.claude/skills/catforge-data/skills/catforge-data/SKILL.md`
- `CLAUDE.md`
- `apps/api-server/app/cli/__init__.py`
- `apps/api-server/app/cli/catforge_data.py`

### 2.2 M00/M01/M02 服务层

- `apps/api-server/app/services/core3_real_data/source_registry_service.py`
- `apps/api-server/app/services/core3_real_data/source_registry_repositories.py`
- `apps/api-server/app/services/core3_real_data/cleaning_quality_service.py`
- `apps/api-server/app/services/core3_real_data/cleaning_repositories.py`
- `apps/api-server/app/services/core3_real_data/cleaning_runner.py`
- `apps/api-server/app/services/core3_real_data/evidence_atom_service.py`
- `apps/api-server/app/services/core3_real_data/evidence_atom_repositories.py`

### 2.3 API、配置与部署

- `apps/api-server/app/api/core3_real_data.py`
- `apps/api-server/app/core/config.py`
- `apps/api-server/app/main.py`
- `apps/api-server/app/schemas/core3_real_data.py`
- `apps/api-server/app/services/core3_real_data/api_repositories.py`
- `apps/api-server/app/services/core3_real_data/api_response_guardrail.py`
- `apps/api-server/app/services/core3_real_data/evidence_report_service.py`
- `apps/factory-web/Dockerfile`
- `apps/factory-web/nginx.conf`
- `docker-compose.cloud.yml`

### 2.4 测试

- `apps/api-server/tests/core3_real_data/test_catforge_data_cli.py`
- `apps/api-server/tests/core3_real_data/test_m00_source_registry_runner.py`
- `apps/api-server/tests/core3_real_data/test_m01_cleaning_api.py`
- `apps/api-server/tests/core3_real_data/test_m01_cleaning_coverage_quality.py`
- `apps/api-server/tests/core3_real_data/test_m01_cleaning_domain_cleaners.py`
- `apps/api-server/tests/core3_real_data/test_m01_cleaning_repositories.py`
- `apps/api-server/tests/core3_real_data/test_m01_cleaning_runner.py`
- `apps/api-server/tests/core3_real_data/test_m01_no_business_outputs.py`
- `apps/api-server/tests/core3_real_data/test_m02_evidence_repositories.py`
- `apps/api-server/tests/core3_real_data/test_m02_evidence_runner.py`
- `apps/api-server/tests/core3_real_data/test_m02_no_business_outputs.py`
- `apps/api-server/tests/core3_real_data/test_business_api_lightweight_queries.py`
- `apps/api-server/tests/core3_real_data/test_m15_evidence_map_compaction.py`
- `apps/api-server/tests/core3_real_data/test_acceptance_local_validation.py`

## 3. 业务口径

### 3.1 用户不需要知道 M00/M01/M02

对业务用户，推荐使用如下表达：

- “先把新数据预处理一下”
- “把这批数据准备好分析”
- “看一下这批数据清洗质量”
- “看一下某个 SKU 的清理情况”

Agent 可以在内部把这些自然语言映射到 CLI 命令，但面向用户汇报时不要求用户理解模块编号。

### 3.2 预处理的完成标准

“数据准备好可以分析”在本分支中定义为：

1. 原始表变更被登记成 source batch。
2. M01 已生成清洗后的结构化事实表与质量信息。
3. M01 已快速过滤低质评论、空评论、默认好评、服务履约类评论。
4. M02 已把可消费清洗事实转成 evidence atom 和 evidence link。
5. 不进入 M05 及后续评论语义、画像、竞品分析阶段。

### 3.3 服务履约评论处理口径

服务履约类评论包括客服、物流、安装、售后、退换货、维修等内容。

处理原则：

- 在 M01 阶段识别为服务履约类非产品评论，并从产品评论候选中拦截。
- 保留在预处理统计中，便于后续评估“有多少评论其实是服务类”。
- 不进入评论句子、M02 产品证据、M05 评论语义分析。
- 不单独新增 `service_fulfillment_comment` 质量类型，避免把服务履约误写成产品质量事实。

### 3.4 量价周度覆盖解释口径

M01 中对周度量价覆盖做解释时遵循：

- 同一周只有一个平台有数据是正常情况，通常解释为该 SKU 只在一个平台售卖或某平台特供。
- 起始缺周不直接判定为漏数，可解释为新品、晚进入样本或本批次首次可见。
- 末尾缺周不直接判定为漏数，可解释为退市、离开样本或后续无销售记录。
- 首尾之间的中间断档才作为软性质量提醒。
- 缺失是未知，不把空值、`-`、null 当成 false。

### 3.5 彩电属性缺失口径

彩电属性在原始表中天然可能存在缺项。M01 会统计 unknown/missing，但不把所有属性缺失直接视为阻断问题。对外汇报时应区分：

- 原始表没有提供该属性。
- 提供了但值为空、`-` 或不可解析。
- 与其他表存在冲突。

## 4. CLI 总览

入口模块：

```bash
python -m app.cli.catforge_data
```

服务端 205 推荐在 API 容器内执行：

```bash
docker compose -f docker-compose.cloud.yml --env-file .env exec -T api \
  python -m app.cli.catforge_data <command> ...
```

支持命令：

```text
prepare-new-data       登记源批次、运行 M01 清洗、运行 M02 证据准备
inspect-data-quality   查看当前批次整体清洗质量
inspect-sku-quality    查看单个 SKU 清洗质量
```

公共参数：

```text
--project-id       项目 ID，默认读取 CATFORGE_PROJECT_ID，未设置时为 core3_mvp
--category-code    品类代码，默认读取 CATFORGE_CATEGORY_CODE，未设置时为 TV
--format           输出格式，json 或 text，默认 json
```

退出码：

```text
0  success、warning、dry_run、not_found 等非阻断状态
2  failed 或 blocked
```

建议外部调用方始终使用 `--format json`，不要解析 text 输出。

## 5. `prepare-new-data`

### 5.1 作用

`prepare-new-data` 是本分支最核心的命令。默认目标是把新上传数据处理到“可以进入事实分析”的状态。

默认执行：

```text
M00 source batch registration
M01 cleaning and preliminary quality
M02 evidence atom preparation
```

默认不执行：

```text
M05 and later semantic/profile/competitor modules
```

### 5.2 常用命令

新数据进来后，登记源批次并处理到 M02：

```bash
docker compose -f docker-compose.cloud.yml --env-file .env exec -T api \
  python -m app.cli.catforge_data prepare-new-data \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --sku-batch-size 50 \
  --evidence-sku-batch-size 1 \
  --format json
```

已有 batch 重新准备到 M02：

```bash
docker compose -f docker-compose.cloud.yml --env-file .env exec -T api \
  python -m app.cli.catforge_data prepare-new-data \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --register-source-batch none \
  --batch-id latest \
  --sku-batch-size 50 \
  --evidence-sku-batch-size 1 \
  --format json
```

小样本冒烟：

```bash
docker compose -f docker-compose.cloud.yml --env-file .env exec -T api \
  python -m app.cli.catforge_data prepare-new-data \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --register-source-batch none \
  --batch-id latest \
  --limit-skus 5 \
  --sku-batch-size 2 \
  --evidence-sku-batch-size 1 \
  --format json
```

只看计划，不写入：

```bash
docker compose -f docker-compose.cloud.yml --env-file .env exec -T api \
  python -m app.cli.catforge_data prepare-new-data \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --dry-run \
  --format json
```

预期 dry-run 关键字段：

```json
{
  "status": "dry_run",
  "plan": {
    "will_run_modules": ["M00", "M01", "M02"],
    "will_not_run_modules": ["M05"]
  }
}
```

### 5.3 参数说明

```text
--batch-id
  默认 latest。
  当 --register-source-batch none 时，用于指定已有 source batch。

--register-source-batch
  incremental: 默认，先登记增量源批次，再执行 M01/M02。
  full: 登记全量源批次。
  none: 不登记新批次，复用 --batch-id 指定的已有批次。

--source-tables
  默认 week_sales_data,attribute_data,selling_points_data,comment_data。
  对外开放初期不建议由外部调用方改动。

--sku-code
  可重复传入，用于只处理指定 SKU。
  例如：--sku-code TV00029115 --sku-code AC00028642

--sku-batch-size
  M01 清洗按 SKU 分批的大小。
  205 上默认推荐 50。

--evidence-sku-batch-size
  M02 evidence 准备按 SKU 分批的大小。
  205 上默认推荐 1，避免大评论 SKU 占用过高内存。

--limit-skus
  冒烟测试或抽样处理用。

--include-no-change
  包含 M00 判断为 no_change 的来源行。
  默认不打开。

--allow-full-scan
  如果无法解析目标 SKU，允许 M01 不按 SKU 目标列表全量扫描。
  205 上慎用；除非明确知道数据规模和资源状态。

--dry-run
  只输出计划，不写 DB。

--run-id / --module-run-id
  调试或外部编排追踪用。
```

### 5.4 输出字段

主要 JSON 字段：

```text
command
status
batch_id
project_id
category_code
execution_label
source_registration
plan
processed_chunks
processed_evidence_chunks
m01_summary
m02_summary
message_cn
```

`status` 含义：

```text
success   执行成功，没有 warning
warning   执行成功，但存在质量提醒或低置信 evidence
failed    模块执行失败
blocked   缺少 batch、缺少目标 SKU 等前置条件不足
dry_run   只输出计划
```

`processed_chunks` 是 M01 清洗分块结果。

`processed_evidence_chunks` 是 M02 evidence 分块结果。

`m01_summary` 中重点关注：

```text
clean_counts
issue_counts
review_required
market_coverage_summary
comment_preliminary_summary
```

`m02_summary` 中重点关注：

```text
evidence_counts
link_counts
created_atom_count
reused_atom_count
superseded_atom_count
inactive_atom_count
created_link_count
reused_link_count
inactive_link_count
partition_count
partition_summaries
```

### 5.5 外部调用建议

外部系统调用时建议：

1. 固定使用 `--format json`。
2. 使用单任务串行，不要并发多次执行同一 batch。
3. 新数据默认调用 `prepare-new-data`，不要直接调用内部 M00/M01/M02。
4. 先 `--dry-run` 获取计划，再正式执行。
5. 若是大批次，保留 stdout/stderr 日志，至少记录 `batch_id`、`processed_chunks`、`processed_evidence_chunks`。
6. 如果返回 `warning`，不代表失败，而是说明有质量问题或低置信证据需要后续解释。
7. 如果返回 `blocked` 或退出码 2，先读 `message_cn`，再检查 batch 是否存在、目标 SKU 是否解析出来。

## 6. `inspect-data-quality`

### 6.1 作用

读取已有批次的 M01 初步清洗和质量摘要，不重新处理数据。

用于回答：

- “这批数据清理得怎么样？”
- “有效评论还有多少？”
- “量价覆盖有什么问题？”
- “服务类评论过滤了多少？”
- “有哪些 SKU 样本需要看？”

### 6.2 命令

```bash
docker compose -f docker-compose.cloud.yml --env-file .env exec -T api \
  python -m app.cli.catforge_data inspect-data-quality \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id latest \
  --limit-skus 20 \
  --format json
```

### 6.3 输出字段

```text
command
status
batch_id
project_id
category_code
clean_counts
issue_counts
review_required
market_coverage_summary
comment_preliminary_summary
sample_skus
```

关键解释：

- `clean_counts`：各清洗表行数。
- `issue_counts`：质量问题数量和类型。
- `market_coverage_summary`：周度量价覆盖、单平台周、中间断档等摘要。
- `comment_preliminary_summary`：原始评论、低质评论、过滤后候选评论、服务履约评论等摘要。
- `sample_skus`：样例 SKU 的质量状态和覆盖信息。

## 7. `inspect-sku-quality`

### 7.1 作用

读取单 SKU 的 M01 清洗质量结果，不重新处理数据。

用于回答：

- “这个 SKU 清理情况怎么样？”
- “这个 SKU 评论过滤后还有多少有效内容？”
- “这个 SKU 量价周度覆盖是不是缺？”
- “这个 SKU 是否有属性、卖点、评论、质量问题？”

### 7.2 命令

```bash
docker compose -f docker-compose.cloud.yml --env-file .env exec -T api \
  python -m app.cli.catforge_data inspect-sku-quality \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id latest \
  --sku-code TV00029115 \
  --issue-limit 10 \
  --format json
```

### 7.3 输出字段

```text
command
status
found
batch_id
project_id
category_code
sku_code
sku
row_counts
market_summary
attribute_summary
claim_summary
comment_summary
quality_issue_summary
stored_coverage
message_cn
```

重点字段：

- `row_counts`：该 SKU 在清洗表中的行数。
- `market_summary`：周度范围、销售量额、平台分布、价格检查、覆盖信息。
- `attribute_summary`：属性行数、unknown 数量、质量状态。
- `claim_summary`：卖点行数、句子数、文本存在性、质量状态。
- `comment_summary`：原始评论数、低质评论数、过滤后候选评论数、服务履约评论数、句子数、评论维度数。
- `quality_issue_summary`：质量问题类型、严重级别、样例问题。

如果 `status=not_found`，说明该批次中没有这个 SKU 的 M01 清洗结果。

## 8. Claude Code Skill

### 8.1 文件位置

仓库内：

```text
.claude/skills/catforge-data/SKILL.md
.claude/skills/catforge-data/skills/catforge-data/SKILL.md
.claude/skills/catforge-data/.claude-plugin/plugin.json
```

205 已安装位置：

```text
/root/.claude/skills/catforge-data
```

### 8.2 Skill 能力边界

skill 负责把自然语言业务请求映射到数据预处理 CLI。

它应该处理：

- “先初步处理一下”
- “预处理新数据”
- “初步清洗”
- “把数据准备好分析”
- “看一下这批数据质量”
- “查一下某个 SKU 清理情况”
- “这个 SKU 评论还有多少有效内容”

它不应该默认处理：

- 直接跑 M05 或更后面的评论语义分析。
- 直接生成用户任务、目标客群、价值战场。
- 直接生成竞品分析结论。
- 未经确认并发执行多个大批次。

### 8.3 Skill 决策树

```text
用户说“新数据预处理 / 准备好分析”
  -> 调用 prepare-new-data
  -> 默认 M00 + M01 + M02
  -> --sku-batch-size 50
  -> --evidence-sku-batch-size 1

用户说“已有批次再处理 / 看 latest”
  -> 调用 prepare-new-data
  -> 加 --register-source-batch none --batch-id latest 或明确 batch_id

用户说“看这批数据质量”
  -> 调用 inspect-data-quality

用户说“看某个 SKU 清理情况”
  -> 调用 inspect-sku-quality

用户问“用户画像 / 目标客群 / 竞品”
  -> 这已经超出本 skill 默认处理边界
  -> 需要后续事实层、语义层、画像层、竞品层能力
```

### 8.4 Skill 对外汇报口径

汇报时必须使用业务语言，避免把用户拉进内部模块细节。

推荐结构：

```text
批次：
处理范围：
处理结果：
清洗行数：
证据准备状态：
量价覆盖：
评论过滤：
服务履约评论：
需要复核的问题：
下一步建议：
```

对服务履约评论的说法：

```text
客服、物流、安装、售后等服务履约评论已在清洗阶段识别并拦截，
保留在预处理统计里，但不会进入后续产品卖点和评论语义分析。
```

对单平台周的说法：

```text
同一周只有一个平台有数据不直接视为漏数，
可能表示该 SKU 只在单平台售卖或属于平台特供。
```

对新品和退市的说法：

```text
首段缺周可能是新品或晚进入样本；末段缺周可能是退市或离开样本。
只有首尾之间的中间断档才作为软性质量提醒。
```

## 9. M00 开发内容

本分支增强了 source batch 登记和增量识别能力，支撑 CLI 默认先登记源数据批次。

实现要点：

- 支持 `incremental` 和 `full` source batch。
- 默认登记 4 张原始表：
  - `week_sales_data`
  - `attribute_data`
  - `selling_points_data`
  - `comment_data`
- 记录来源行指纹、来源表、来源主键、候选 SKU。
- 识别需要重算的 impacted SKU。
- 允许后续 M01/M02 按 impacted SKU 分批执行。
- 支持已有 batch 通过 `--register-source-batch none --batch-id <id>` 复用。

注意：

- source batch 是工厂内部处理边界，不建议外部业务用户直接操作。
- 对外只暴露“登记新数据并准备分析”这类业务命令。

## 10. M01 开发内容

M01 是本分支处理大数据量风险和评论质量的核心。

### 10.1 分批处理

历史问题：一次处理 100 万级评论可能导致 205 CPU 占用高、SSH 不稳定或 API 无响应。

本分支处理方式：

- CLI 默认按 SKU 分批跑 M01。
- 默认 `--sku-batch-size 50`。
- M01 内部按 source row chunk 写入，减少一次性内存占用。
- 每个 chunk 写入后 commit，并清理 session。

### 10.2 评论低质过滤

M01 快速过滤如下评论：

- 空评论。
- 默认好评。
- 明显模板评论。
- 服务履约评论。
- 低业务信息密度评论。

过滤结果：

- 低质评论和服务履约评论仍保留在 `core3_clean_comment` 中，用于统计。
- 不生成可用于后续产品语义分析的有效评论句。
- 不进入 M02 产品证据。

### 10.3 评论句子切分

评论句子切分发生在 M01。

M01 会从有效评论文本或已有分段字段中生成 `core3_clean_comment_sentence`。

低质评论和服务履约评论不会进入句子切分结果，避免后续产品评论分析被服务类、空评论和默认好评淹没。

### 10.4 质量信息来源

质量信息不是 4 张原始表中的独立输入表。

质量信息由 M01 基于 4 张原始表和清洗规则生成，落到：

```text
core3_data_quality_issue
```

这些质量信息用于：

- 解释缺失、冲突、低质、覆盖不足等情况。
- 指示哪些 SKU 或字段需要复核。
- 为后续事实层和报告层提供“不能过度推断”的约束。

### 10.5 M01 不输出业务结论

M01 只做清洗和质量诊断，不输出：

- 用户任务。
- 目标客群。
- 价值战场。
- 竞品选择。
- 业务结论。

## 11. M02 开发内容

M02 把 M01 结果转成证据原子和证据链接，是事实分析的输入层。

### 11.1 Evidence 粒度

本分支 M02 已生成的 evidence type 包括：

```text
sku_fact
market_fact
param_raw
promo_raw
promo_sentence
comment_raw
comment_sentence
comment_dimension
quality_issue
```

M02 仍然不输出：

- 用户任务。
- 目标客群。
- 价值战场。
- 竞品结论。
- 报告结论。

### 11.2 大数据安全优化

本分支修复了 3 个 M02 风险点：

1. 大量低质评论 source_row_id 不能展开成一次性 `NOT IN (...)`。
2. M02 分 SKU 处理后必须清理 repository save cache 和 SQLAlchemy session。
3. 将低质评论对应旧 evidence 标记 inactive 时，不能一次性 `source_row_id IN (11 万...)`。

实现策略：

- `MAX_SQL_EXCLUDE_SOURCE_ROW_IDS = 50000`
- 超过阈值时不展开大 `NOT IN` 参数。
- 评论主表在 SQL 层加 `low_value_flag = false`。
- 评论句子和评论维度通过父评论 `clean_comment_id` 做 SQL 侧 low-value 过滤。
- inactive evidence 按 1000 个 source_row_id 分批查询和更新。
- 每个 SKU partition 后 flush、expunge，并清 repository cache。

### 11.3 205 实测结果

批次：

```text
m00_20260619084551_857df63b
```

执行结果：

```text
SKU 总数：448
current evidence：230,534
current links：472,434
全量 M02 用时：约 40 分 25 秒
运行中 API 容器内存：大致 0.5GB，观察峰值约 562MB
执行后 API 容器回落：约 177MB
```

current evidence by type：

```text
comment_sentence   91,440
comment_raw        36,871
comment_dimension  36,871
param_raw          28,712
market_fact        15,372
quality_issue       8,550
promo_sentence      6,502
promo_raw           5,768
sku_fact              448
```

confidence：

```text
high     48,252
medium  163,782
low      18,500
```

`low` 和 `review_required` 各 18,500 条，因此 M02 整体是 `warning`，不是失败。

## 12. API 与部署开发内容

### 12.1 配置

本分支补充了容器和部署所需配置，重点是让 CLI 和 API 共用同一套环境变量。

关键环境变量：

```text
CATFORGE_DATABASE_URL
CATFORGE_PROJECT_ID
CATFORGE_CATEGORY_CODE
CATFORGE_REDIS_URL
CATFORGE_API_MEM_LIMIT
CATFORGE_API_MEMSWAP_LIMIT
```

### 12.2 Docker Compose

`docker-compose.cloud.yml` 中 API 容器设置：

```text
mem_limit: ${CATFORGE_API_MEM_LIMIT:-3g}
memswap_limit: ${CATFORGE_API_MEMSWAP_LIMIT:-3g}
```

这与本分支分批处理策略配套，避免大数据处理拖垮 205。

### 12.3 205 部署状态

205 代码工作区：

```text
/opt/catforge
```

205 当前分支：

```text
hotfix/data-preprocess-20260618
```

205 最新提交：

```text
bfdfb90
```

API 容器：

```text
catforge-api-1
```

本分支已在 205 上重建 API 镜像并重启，健康检查为 healthy。

## 13. 测试与验收

本分支关键测试：

```bash
python -m pytest \
  apps/api-server/tests/core3_real_data/test_m02_evidence_repositories.py \
  apps/api-server/tests/core3_real_data/test_m02_evidence_runner.py \
  apps/api-server/tests/core3_real_data/test_catforge_data_cli.py \
  apps/api-server/tests/core3_real_data/test_m02_evidence_mappers.py \
  apps/api-server/tests/core3_real_data/test_m02_evidence_schemas.py \
  apps/api-server/tests/core3_real_data/test_m02_no_business_outputs.py \
  -q
```

已通过：

```text
39 passed
```

重点覆盖：

- CLI 默认参数。
- CLI dry-run 计划。
- M02 不输出业务字段。
- 大 source_row_id 排除集不展开超大 SQL 参数。
- SQL 侧过滤低质评论。
- inactive evidence 按 source_row_id 分批更新。
- 低质评论不会进入 M02 语义 evidence。

## 14. 对外开放调用建议

### 14.1 推荐开放层级

对外开放时建议只开放业务动作，不开放内部模块动作。

推荐开放：

```text
prepare_new_data
inspect_data_quality
inspect_sku_quality
```

不推荐开放：

```text
run_m00
run_m01
run_m02
run_m05
```

### 14.2 程序调用伪代码

```python
import json
import subprocess

cmd = [
    "docker", "compose", "-f", "docker-compose.cloud.yml", "--env-file", ".env",
    "exec", "-T", "api",
    "python", "-m", "app.cli.catforge_data",
    "prepare-new-data",
    "--project-id", "d8d2245b-358b-4a64-95cc-9d7f2341bd26",
    "--category-code", "TV",
    "--sku-batch-size", "50",
    "--evidence-sku-batch-size", "1",
    "--format", "json",
]

completed = subprocess.run(cmd, cwd="/opt/catforge", text=True, capture_output=True)
payload = json.loads(completed.stdout)

if completed.returncode == 2:
    raise RuntimeError(payload.get("message_cn") or payload)

print(payload["status"], payload.get("batch_id"))
```

### 14.3 Agent 调用准则

外部 agent 应遵循：

- 先把用户自然语言归一到业务动作。
- 不要求用户说出 M00/M01/M02。
- 大批次处理前可以先 dry-run。
- 输出中必须包含 batch id。
- `warning` 要解释成质量提醒，不要误报成失败。
- 不要默认跑 M05 及后续模块。
- 205 上同一时间只跑一个大处理任务。

### 14.4 推荐用户回复模板

预处理完成：

```text
已完成数据预处理，批次为 <batch_id>。
本次已完成源数据登记、初步清洗过滤和分析证据准备，数据可以进入后续事实分析。
处理 SKU <n> 个，生成清洗记录 <n> 条，生成 current evidence <n> 条。
评论中空评论、默认好评和服务履约评论已被拦在清洗层，不进入后续产品语义分析。
目前存在 <n> 条需要复核的质量提醒，主要用于解释缺失、覆盖和低置信证据，不代表处理失败。
```

数据质量查看：

```text
批次 <batch_id> 当前清洗结果如下：
量价覆盖方面，单平台周按单渠道售卖或平台特供解释，不直接视为漏数；
首尾缺周分别按新品/退市或样本进出解释，中间断档作为软提醒。
评论方面，原始评论 <n> 条，低质评论 <n> 条，过滤后候选评论 <n> 条。
服务履约评论已保留统计但不进入后续产品分析。
```

SKU 清理情况：

```text
SKU <sku_code> 在批次 <batch_id> 中已找到清洗结果。
量价覆盖为 <summary>；属性 <n> 条，卖点 <n> 条，原始评论 <n> 条。
评论过滤后剩余候选 <n> 条，其中服务履约类 <n> 条已被拦截。
该 SKU 当前质量状态为 <quality_status>，需要复核的问题有 <n> 条。
```

## 15. 已知边界

1. 本分支只处理“预处理到可事实分析”的阶段，不负责生成最终用户画像、目标客群、价值战场和竞品结论。
2. `prepare-new-data --register-source-batch none` 会重新执行 M01 和 M02；对于已经完成 M01 的历史批次，如只需补跑 M02，当前没有对外 CLI 子命令，需要工程脚本或后续新增命令。
3. CLI 当前没有跨进程锁；外部调度系统应保证同一项目/批次不要并发运行多个大处理任务。
4. `--allow-full-scan` 可能触发大范围扫描，只应在明确知道 batch 规模和资源状态时使用。
5. 质量信息由 M01 派生，不是原始 4 表输入；后续分析阶段应把它当作约束和解释依据，而不是产品事实本身。

## 16. 后续建议

对外开放前建议补齐：

- 一个正式 API wrapper，内部调用 CLI 或服务层，但对外只暴露业务动作。
- 任务锁和任务状态查询，避免外部系统重复提交。
- 执行日志持久化，记录 batch id、触发人、参数、开始/结束时间、耗时、资源峰值。
- 只补跑 M02 的公开命令，用于 M01 已完成但 evidence 需要重建的历史批次。
- 更细的业务级返回摘要，减少外部调用方解析深层 JSON 的负担。
