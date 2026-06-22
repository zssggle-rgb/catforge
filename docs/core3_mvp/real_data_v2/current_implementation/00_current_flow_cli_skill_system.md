# Current Flow, CLI, Skill, and Agent System

Last updated: 2026-06-22

This document is the current operating source of truth for CatForge real-data processing and XiaoAo analysis routing. It exists because the project now has several generations of code and skills. When instructions conflict, use this document first, then verify the current branch and the 205 deployment.

## 1. One Correct Layered Flow

The current analysis path is five layers:

```text
Raw uploaded tables
  -> Data preparation layer
  -> Fact/profile generation layer
  -> Read-only insight layer
  -> Business analyst layer
  -> External agent surfaces
```

### 1.1 Raw Uploaded Tables

The raw tables are the source of observable market data:

- `week_sales_data`
- `attribute_data`
- `selling_points_data`
- `comment_data`

Rules:

- Raw tables are not business-analysis inputs directly.
- Do not answer business questions from raw tables unless debugging data ingestion.
- New raw data must first pass the data preparation layer.

### 1.2 Data Preparation Layer

Purpose: turn raw uploaded rows into clean, traceable, analysis-ready evidence.

Internal stages:

- M00: source batch and raw-row registration.
- M01: cleaning, preliminary quality checks, comment filtering, and clean fact rows.
- M02: evidence atom and evidence link preparation.

Correct CLI:

```bash
python -m app.cli.catforge_data prepare-new-data
```

Correct skill:

```text
catforge-data
```

User-facing language:

- "新数据来了，先处理一下"
- "把这批数据预处理一下"
- "先清洗一下新数据"
- "把数据准备好可以分析"
- "看看某个 SKU 的清理情况"

Important boundary:

- This layer does not run comment semantic extraction.
- This layer does not run parameter, claim, market, task, target-group, battlefield, competitor, or opportunity analysis.
- This layer should run in SKU chunks on 205 to avoid CPU and memory pressure.

### 1.3 Fact/Profile Generation Layer

Purpose: generate structured product, comment, market, and semantic profiles from prepared evidence.

Correct CLI:

```bash
python -m app.cli.catforge_pipeline ...
```

Correct skill:

```text
catforge-pipeline
```

Current commands:

| User intent | CLI command |
| --- | --- |
| Generate SKU parameter fact profiles | `run-param-profile` |
| Generate SKU claim fact profiles | `run-claim-profile` |
| Generate SKU market profiles and comparable pools | `run-market-profile` |
| Generate SKU comment fact profiles | `run-comment-profile` or `run-comment-profile-batch` |
| Generate SKU user-task profiles | `run-user-task` |
| Generate SKU target-group profiles | `run-target-group` |
| Generate SKU value-battlefield profiles | `run-value-battlefield` |
| Generate semantic market graph and sales allocation | `run-semantic-market-graph` |

Natural-language entry:

```bash
python -m app.cli.catforge_pipeline ask "重新生成彩电价值战场画像" --force-rebuild --format json
```

Boundary:

- `catforge_pipeline` is a write/execution CLI.
- It should not answer read-only business questions.
- It should not be used for the raw-to-clean M00/M01/M02 preparation step. That belongs to `catforge_data`.

### 1.4 Read-Only Insight Layer

Purpose: query existing facts, profiles, taxonomies, coverage, graph, and allocation outputs.

Correct CLI:

```bash
python -m app.cli.catforge_insight ...
```

Correct skill:

```text
catforge-insight
```

User-facing language:

- "查某个 SKU 的参数画像"
- "查彩电标准参数"
- "查某个档位覆盖哪些 SKU"
- "查某个 SKU 的卖点画像"
- "查某个 SKU 的评论事实画像"
- "查某个 SKU 的用户任务/目标客群/价值战场"
- "查某个价值战场有多少销量"
- "查某个 SKU 的销量分配"

Boundary:

- `catforge_insight` is read-only.
- It must not rebuild profiles or mutate tables.
- It is the preferred source for factual lookups before business interpretation.

### 1.5 Business Analyst Layer

Purpose: answer business questions in professional market-analysis language.

Correct CLI:

```bash
python -m app.cli.catforge_analyst ...
```

Correct OpenClaw skill:

```text
xiaoao-home-appliance-market-analysis
```

Correct OpenClaw agent:

```text
xiaoao-home-appliance-market-analyst
```

User-facing brand:

```text
小奥家电市场分析专家
```

Typical business questions:

- "某个 SKU 的竞品有哪些"
- "为什么 A 比 B 卖得好"
- "哪些卖点是溢价卖点"
- "哪些卖点支撑用户选择"
- "怎么扩大销量"
- "有没有机会进入更多价值战场"
- "某个价值战场空间有多大"
- "目标客户是什么"
- "用户画像是什么"

Boundary:

- XiaoAo must not expose CLI names, module codes, database tables, JSON, batch IDs, or stack traces unless the user asks for implementation detail.
- XiaoAo should call `catforge_analyst`, `catforge_insight`, or `catforge_pipeline` as needed for business answers and generated-profile operations. For raw-data preparation requests, use `catforge_data` and report execution status rather than a business conclusion.
- XiaoAo should not invent market facts from general knowledge.

## 2. Correct CLI Responsibilities

| CLI | Responsibility | Writes data | Typical caller | Current branch state |
| --- | --- | --- | --- | --- |
| `catforge_data` | Raw-to-clean preparation: M00 + M01 + M02 | Yes | Claude Code / OpenClaw for new data preparation | Implemented on `hotfix/data-preprocess-20260618`, missing from current branch and 205 as of 2026-06-22 |
| `catforge_pipeline` | Generate/rebuild fact and semantic profiles | Yes | Claude Code / OpenClaw for reruns and rebuilds | Present in current branch |
| `catforge_insight` | Query generated profiles, taxonomies, coverage, and graph outputs | No | Claude Code / OpenClaw for factual lookup | Present in current branch |
| `catforge_analyst` | Business analyst atoms, SOPs, and natural-language business answers | No for normal questions | XiaoAo | Present in current branch |

## 3. Correct Skill Responsibilities

| Skill | Runtime | Should trigger when | Should not trigger when |
| --- | --- | --- | --- |
| `catforge-data` | Claude Code; also should be exposed to OpenClaw as a pipeline/tool instruction | User asks to preprocess/clean/prepare new raw data or inspect cleaning quality | User asks for competitor, opportunity, target customer, or generated profile lookup |
| `catforge-pipeline` | Claude Code | User asks to rerun/rebuild/generate profiles or semantic market graph | User asks only to query existing outputs or asks for business advice |
| `catforge-insight` | Claude Code | User asks to check existing facts, profiles, taxonomies, coverage, graph, or allocation | User asks to execute new processing or business strategy |
| `xiaoao-home-appliance-market-analysis` | OpenClaw | User asks business questions or natural-language analysis questions | Raw implementation debugging, unless the user asks how the system works |

## 4. Natural-Language Routing Rules

### 4.1 New Data and Cleaning

Route to:

```bash
python -m app.cli.catforge_data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --sku-batch-size 50 --evidence-sku-batch-size 1 --format json
```

If an existing batch should be prepared:

```bash
python -m app.cli.catforge_data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --register-source-batch none --batch-id latest --sku-batch-size 50 --evidence-sku-batch-size 1 --format json
```

For a smoke test:

```bash
python -m app.cli.catforge_data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --register-source-batch none --batch-id latest --limit-skus 5 --sku-batch-size 2 --evidence-sku-batch-size 1 --format json
```

Do not route these requests to `catforge_pipeline`.

### 4.2 Profile Rebuilds

Route to:

```bash
python -m app.cli.catforge_pipeline ask "<natural-language rebuild request>" --batch-id latest --product-category tv --force-rebuild --format json
```

Examples:

- "重新生成彩电参数画像"
- "重新生成彩电卖点事实画像"
- "重新生成彩电评论事实画像"
- "重新生成彩电用户任务画像"
- "重新生成彩电目标客群画像"
- "重新生成彩电价值战场画像"
- "重新生成彩电语义市场图谱和销量分配"

### 4.3 Read-Only Fact Lookup

Route to:

```bash
python -m app.cli.catforge_insight ask "<natural-language lookup>" --batch-id latest --product-category tv --format json
```

Examples:

- "查海信 65E7Q 的参数画像"
- "查彩电标准卖点"
- "查某个价值战场有哪些 SKU"
- "查某个 SKU 的销量分配"

### 4.4 Business Analysis

Route to:

```bash
python -m app.cli.catforge_analyst ask "<business question>" --batch-id latest --product-category tv --format json
```

Examples:

- "海信 65E7Q 的竞品有哪些"
- "分析第一款为什么选它"
- "哪些卖点是溢价卖点"
- "怎么扩大销量"
- "能抢多大的市场空间"

## 5. Correct End-to-End Execution After New Raw Data

When new raw rows arrive and the goal is to make them usable by XiaoAo:

1. Run data preparation.

```bash
python -m app.cli.catforge_data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --sku-batch-size 50 --evidence-sku-batch-size 1 --format json
```

2. Inspect preparation quality.

```bash
python -m app.cli.catforge_data inspect-data-quality --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id latest --format json
```

3. Rebuild affected fact/profile layers.

Recommended full TV order:

```text
catforge_pipeline run-param-profile
catforge_pipeline run-claim-profile
catforge_pipeline run-market-profile
catforge_pipeline run-comment-profile-batch
catforge_pipeline run-user-task
catforge_pipeline run-target-group
catforge_pipeline run-value-battlefield
catforge_pipeline run-semantic-market-graph
```

4. Validate read-only outputs with `catforge_insight`.

5. Let XiaoAo answer business questions with `catforge_analyst`.

## 6. 205 Current State and Required Consolidation

As of 2026-06-22:

- Current working branch: `new/m00-safe-import-hotfix`.
- Current 205 repository also lacks `apps/api-server/app/cli/catforge_data.py`.
- `python -m app.cli.catforge_data --help` fails on 205 with `No module named app.cli.catforge_data`.
- The implemented `catforge_data` CLI and `catforge-data` skill are on `hotfix/data-preprocess-20260618` and `new/data-preprocess-20260618`.
- `catforge_pipeline`, `catforge_insight`, `catforge_analyst`, and XiaoAo OpenClaw skill/agent are present in the current branch.

Required consolidation before saying "new data can be cleaned by natural language":

1. Merge or cherry-pick `catforge_data.py`, `catforge-data` skill, tests, and current-implementation docs from `hotfix/data-preprocess-20260618`.
2. Update `catforge-pipeline` skill so generic "data preparation" does not steal raw-data cleaning requests.
3. Update XiaoAo/OpenClaw instructions so "清洗新数据/先处理一下/准备好分析" routes to `catforge_data`, not `catforge_pipeline`.
4. Deploy to 205 and install the `catforge-data` skill for Claude Code/OpenClaw.
5. Smoke test:

```bash
python -m app.cli.catforge_data prepare-new-data --register-source-batch none --batch-id latest --limit-skus 5 --sku-batch-size 2 --evidence-sku-batch-size 1 --format json
python -m app.cli.catforge_data inspect-data-quality --batch-id latest --format json
```

## 7. Output and User Reply Rules

For data preparation results, report:

- Batch id.
- Processed SKU count and chunk count.
- Clean row counts.
- Evidence preparation status.
- Low-value comment count/rate.
- Service-fulfillment comment count/rate, explicitly saying these are blocked from downstream product/comment sentence analysis.
- Review-required quality issues.

For profile rebuild results, report:

- Which profile layer was rebuilt.
- SKU/profile/output counts.
- Warnings and limitations.
- Whether downstream layers need rerun.

For read-only insight, report:

- The fact or profile requested.
- Coverage and evidence limitations.
- No strategic conclusion unless the user asked for analysis.

For XiaoAo business answers, report:

- Conclusion first.
- Top 2-3 business findings.
- Evidence in business language: size/price pool, value battlefield, user task, target group, parameter/claim overlap, comment support, and overlapping-week sales.
- Do not expose internal module names or CLI names.

## 8. Do Not Mix These Concepts

Do not mix:

- Raw-data preparation and semantic profile rebuild.
- Read-only insight and write/rebuild commands.
- Business analysis and technical command logs.
- Old M05/M06/M07 historical wording and current M05C/M09C/M10C/M11C/M11D profile/graph workflow.
- Cumulative sales and overlapping-week market validation. Cumulative sales may be display context, not the main win/loss basis.

## 9. Branch Source of Truth

Known branch split:

```text
hotfix/data-preprocess-20260618
  contains catforge_data CLI, catforge-data Skill, and M00/M01/M02 data-preparation docs.

new/m00-safe-import-hotfix
  contains current XiaoAo, catforge_analyst, catforge_insight, catforge_pipeline, and semantic-market graph work.
```

The next engineering step is to consolidate these branches so the runtime has both:

```text
M00/M01/M02 preparation CLI
  + profile generation CLI
  + read-only insight CLI
  + XiaoAo business analyst CLI/Skill/Agent
```
