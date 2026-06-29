# CatForge 小奥家电市场分析工作台发布层详细设计

## 1. 设计目标

本文承接 [CatForge 小奥家电市场分析工作台发布层需求](../sop_requirements/CATFORGE_BASE_WORKBENCH_publish_requirements.md)，定义把 CatForge 分析结果发布到飞书多维表格的工程方案。

设计目标：

1. 建立独立发布层，不改动 M00-M12C 的计算逻辑。
2. 把核心业务结果同步到五张多维表格表：分析批次、SKU 总览、价值战场图谱、竞品关系、用户卖点价值。
3. 同步过程幂等、可重试、可按 scope 分开执行。
4. 多维表格字段使用业务语言，默认视图不暴露内部字段。
5. CLI 与 Skill 分工清楚：CLI 做发布，Skill 只做自然语言路由。
6. 单元测试不依赖真实飞书 API，真实飞书调用只在集成测试或 205 验收中执行。

## 2. 总体架构

```text
PostgreSQL / CatForge 分析结果
  -> PublishExtractors
  -> BaseRecordMapper
  -> BaseSchemaManager
  -> BaseWorkbenchPublisher
  -> Feishu Base / 小奥家电市场分析工作台
  -> 小奥 Skill / 飞书链接 / 业务视图
```

模块职责：

| 模块 | 职责 |
| --- | --- |
| `catforge_publish` CLI | 参数解析、scope 调度、dry-run、同步状态输出。 |
| `PublishExtractors` | 从 PostgreSQL 读取已生成的业务结果，不读取原始大表生成新结论。 |
| `BaseRecordMapper` | 把内部结果映射为多维表格业务字段。 |
| `BaseSchemaManager` | 创建/校验 Base、表、字段和视图。 |
| `BaseWorkbenchPublisher` | 按 scope 执行分批 upsert、重试和同步状态记录。 |
| `BaseSyncStateRepository` | 记录工作台 token、表 ID、字段 ID、最近同步状态。 |
| `LarkBaseClient` | 封装 `lark-cli base` 或后续 OpenAPI 调用，便于测试 mock。 |
| 小奥 Skill | 把自然语言转换为 `catforge_publish` 命令，不直接操作字段。 |

## 3. 目录建议

建议新增：

```text
app/cli/catforge_publish.py
app/services/publish/
  __init__.py
  base_client.py
  base_schema.py
  base_publisher.py
  extractors.py
  mappers.py
  sync_state.py
  schemas.py
tests/services/publish/
  test_base_mappers.py
  test_base_schema.py
  test_base_publisher.py
tests/cli/
  test_catforge_publish_cli.py
```

若当前项目已有 CLI 注册风格，应按现有方式接入，不额外引入新框架。

## 4. 配置设计

### 4.1 环境变量

| 变量 | 说明 |
| --- | --- |
| `CATFORGE_BASE_WORKBENCH_TOKEN` | 已创建工作台的 Base token。为空时 `base init` 可创建，`sync` 应失败并提示配置。 |
| `CATFORGE_BASE_WORKBENCH_TABLE_MAP` | JSON 字符串，记录业务表到 table_id 的映射。 |
| `CATFORGE_BASE_WORKBENCH_AS` | `user` 或 `bot`，控制飞书 CLI 身份。 |
| `CATFORGE_FEISHU_CLI_BIN` | 飞书 CLI 路径，默认 `lark-cli`。 |
| `CATFORGE_BASE_SYNC_CHUNK_SIZE` | 写入批大小，默认 100，最大 200。 |

### 4.2 配置文件

建议增加可选配置文件：

```text
config/publish/base_workbench.yaml
```

示例：

```yaml
workbench:
  name: 小奥家电市场分析工作台
  category_code: TV
  base_token_env: CATFORGE_BASE_WORKBENCH_TOKEN
  actor: bot
sync:
  chunk_size: 100
  retry:
    max_attempts: 3
    retryable_codes:
      - 1254291
tables:
  analysis_batch:
    display_name: 分析批次表
  sku_overview:
    display_name: SKU总览表
  battlefield_map:
    display_name: 价值战场图谱表
  competitor_relation:
    display_name: 竞品关系表
  claim_value:
    display_name: 用户卖点价值表
```

## 5. 表结构设计

### 5.1 字段类型原则

| 业务内容 | Base 字段类型建议 |
| --- | --- |
| 名称、摘要、编码 | 文本 |
| 金额、销量、得分、数量 | 数字 |
| 状态、角色、价格带、尺寸档 | 单选 |
| 多个战场、多个卖点、多个品牌 | 多选或文本摘要，一期优先文本摘要 |
| 报告链接 | URL |
| 同步时间 | 日期时间 |
| 备注 | 长文本 |

一期优先使用稳定字段类型，避免过早使用复杂 lookup、公式和自动化。

### 5.2 分析批次表

业务表名：`分析批次表`

唯一键：`batch_id + category_code`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | 文本 | 分析批次 ID。 |
| `category_code` | 单选 | 品类编码，例如 TV。 |
| `product_category` | 文本 | 业务品类名，例如 彩电。 |
| `data_window` | 文本 | 数据窗口，例如 26W01-26W24。 |
| `source_batch_id` | 文本 | 来源导入批次。 |
| `sku_count` | 数字 | 当前批次可分析 SKU 数。 |
| `comment_sku_count` | 数字 | 有评论事实 SKU 数。 |
| `sku_overview_count` | 数字 | 已发布 SKU 总览行数。 |
| `competitor_relation_count` | 数字 | 已发布竞品关系行数。 |
| `claim_value_count` | 数字 | 已发布用户卖点价值行数。 |
| `sync_status` | 单选 | `未同步`、`同步中`、`成功`、`失败`。 |
| `synced_at` | 日期时间 | 最近同步时间。 |
| `note_cn` | 长文本 | 业务备注或失败摘要。 |

### 5.3 SKU 总览表

业务表名：`SKU总览表`

唯一键：`batch_id + category_code + sku_code`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | 文本 | 分析批次 ID。 |
| `category_code` | 单选 | 品类编码。 |
| `sku_code` | 文本 | SKU 编码。 |
| `brand_name` | 文本 | 品牌。 |
| `model_name` | 文本 | 型号。 |
| `screen_size_inch` | 数字 | 屏幕尺寸。 |
| `size_tier` | 单选 | M03B 五档尺寸口径。 |
| `price_band` | 单选 | 尺寸内价格带。 |
| `weighted_price` | 数字 | 加权均价。 |
| `avg_weekly_sales_volume` | 数字 | 周均销量，取整数展示。 |
| `avg_weekly_sales_amount` | 数字 | 周均销售额。 |
| `primary_battlefield` | 文本 | 主价值战场。 |
| `primary_user_task` | 文本 | 主用户任务。 |
| `primary_target_group` | 文本 | 主目标客群。 |
| `top_claims_cn` | 长文本 | 重点卖点摘要。 |
| `competitor_report_url` | URL | 竞品分析报告。 |
| `claim_value_report_url` | URL | 用户卖点价值报告。 |
| `updated_at` | 日期时间 | 更新时间。 |

### 5.4 价值战场图谱表

业务表名：`价值战场图谱表`

唯一键：`batch_id + category_code + battlefield_code`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | 文本 | 分析批次 ID。 |
| `category_code` | 单选 | 品类编码。 |
| `battlefield_code` | 文本 | 战场编码，默认视图隐藏。 |
| `battlefield_name` | 文本 | 战场名称。 |
| `size_tiers` | 文本 | 覆盖尺寸档。 |
| `price_bands` | 文本 | 覆盖价格带。 |
| `covered_sku_count` | 数字 | 覆盖 SKU 数。 |
| `allocated_sales_volume` | 数字 | 分配周均销量，取整数展示。 |
| `allocated_sales_amount` | 数字 | 分配周均销售额。 |
| `leading_brands_cn` | 长文本 | 主要品牌。 |
| `representative_skus_cn` | 长文本 | 代表 SKU。 |
| `business_summary_cn` | 长文本 | 战场业务摘要。 |
| `updated_at` | 日期时间 | 更新时间。 |

### 5.5 竞品关系表

业务表名：`竞品关系表`

唯一键：`batch_id + category_code + target_sku_code + competitor_sku_code`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | 文本 | 分析批次 ID。 |
| `category_code` | 单选 | 品类编码。 |
| `target_sku_code` | 文本 | 目标 SKU。 |
| `target_brand` | 文本 | 目标品牌。 |
| `target_model` | 文本 | 目标型号。 |
| `competitor_sku_code` | 文本 | 竞品 SKU。 |
| `competitor_brand` | 文本 | 竞品品牌。 |
| `competitor_model` | 文本 | 竞品型号。 |
| `rank` | 数字 | 排名。 |
| `competitor_role_cn` | 单选 | 首选直接竞品、强直接竞品、价格贴身竞品、下探分流竞品等。 |
| `same_purchase_pool_score` | 数字 | 同一购买池得分。 |
| `battlefield_overlap_score` | 数字 | 价值战场重合得分。 |
| `user_task_overlap_score` | 数字 | 用户任务重合得分。 |
| `target_group_overlap_score` | 数字 | 目标客群重合得分。 |
| `value_anchor_overlap_score` | 数字 | 价值锚点替代得分。 |
| `replacement_pressure_cn` | 长文本 | 替代压力说明。 |
| `avg_weekly_sales_volume` | 数字 | 竞品周均销量，取整数展示。 |
| `report_url` | URL | 详细竞品报告。 |
| `reasoning_cn` | 长文本 | 入选原因。 |
| `updated_at` | 日期时间 | 更新时间。 |

### 5.6 用户卖点价值表

业务表名：`用户卖点价值表`

唯一键：`batch_id + category_code + sku_code + claim_code + claim_role_cn`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | 文本 | 分析批次 ID。 |
| `category_code` | 单选 | 品类编码。 |
| `sku_code` | 文本 | SKU 编码。 |
| `brand_name` | 文本 | 品牌。 |
| `model_name` | 文本 | 型号。 |
| `claim_code` | 文本 | 卖点编码，默认视图隐藏。 |
| `claim_name` | 文本 | 卖点名称。 |
| `claim_role_cn` | 单选 | 高溢价、份额转化、客户获得价值、人无我有、门槛、待激活、竞品拦截等。 |
| `explainable_price_value` | 数字 | 可解释金额。不可量化则为空。 |
| `explainable_weekly_sales` | 数字 | 可解释周均销量。不可量化则为空。 |
| `main_battlefields_cn` | 长文本 | 主要成立战场。 |
| `parameter_evidence_cn` | 长文本 | 参数证据。 |
| `comment_evidence_cn` | 长文本 | 评论证据。 |
| `market_validation_cn` | 长文本 | 市场验证。 |
| `action_suggestion_cn` | 长文本 | 行动建议。 |
| `report_url` | URL | 用户卖点价值详细报告。 |
| `confidence_cn` | 单选 | 高、中、低、待复核。 |
| `updated_at` | 日期时间 | 更新时间。 |

## 6. 同步流程

### 6.1 初始化

命令：

```bash
python -m app.cli.catforge_publish base init --category tv --base-name "小奥家电市场分析工作台"
```

流程：

1. 检查飞书 CLI 可用性和身份。
2. 若配置已有 Base token，读取现有 Base。
3. 若无 Base token，根据参数创建 Base。
4. 创建或校验五张表。
5. 创建或校验字段。
6. 创建基础视图。
7. 写入或输出 table map。

### 6.2 单 scope 同步

命令：

```bash
python -m app.cli.catforge_publish base sync --scope claim-value --category tv --batch-id latest
```

流程：

1. 解析 `batch-id=latest` 为当前最新完整分析批次。
2. 校验目标 Base 和表结构。
3. 从 PostgreSQL 提取该 scope 的发布 payload。
4. 映射为 Base cell values。
5. 用唯一键读取已有记录索引。
6. 拆分为 create 和 update。
7. 按批次写入，单批不超过 200 行。
8. 更新分析批次表的同步状态和行数。
9. 输出同步摘要和 Base 链接。

### 6.3 全量同步

命令：

```bash
python -m app.cli.catforge_publish base sync-all --category tv --batch-id latest
```

执行顺序：

1. 分析批次表
2. SKU 总览表
3. 价值战场图谱表
4. 竞品关系表
5. 用户卖点价值表
6. 分析批次表二次更新最终状态

若某个 scope 失败：

- 已成功的 scope 不回滚。
- 当前 scope 标记失败。
- CLI 返回非零退出码。
- 输出失败 scope 和可重试命令。

## 7. 提取器设计

### 7.1 提取原则

`PublishExtractors` 只从已生成结果中提取摘要，不重新做业务判断。

| Extractor | 数据来源 |
| --- | --- |
| `AnalysisBatchExtractor` | M00 批次、当前分析完成状态、各结果表行数。 |
| `SkuOverviewExtractor` | M03B/M07/M09C/M10C/M11C/M12C 最新结果和报告链接索引。 |
| `BattlefieldMapExtractor` | M11D 图谱结果。 |
| `CompetitorRelationExtractor` | `catforge_analyst competitor-set` 结果表或其持久化结果。 |
| `ClaimValueExtractor` | M12C 用户卖点价值结果和报告链接。 |

如果某类结果尚未持久化，应先在该模块补持久化或明确降级，不允许在发布层临时重算复杂逻辑。

### 7.2 数字格式

写入 Base 时保存数字值，不把数字格式化为中文字符串。

展示规则：

- 周均销量取整数。
- 金额保留 0-1 位小数，由视图或报告控制。
- 百分比类字段保留 1 位小数。
- 缺失值写空，不写 `暂无` 作为数字字段。

## 8. Upsert 设计

### 8.1 唯一键

每张表都生成 `unique_key`，用于 upsert。

| 表 | unique_key |
| --- | --- |
| 分析批次表 | `batch_id|category_code` |
| SKU 总览表 | `batch_id|category_code|sku_code` |
| 价值战场图谱表 | `batch_id|category_code|battlefield_code` |
| 竞品关系表 | `batch_id|category_code|target_sku_code|competitor_sku_code` |
| 用户卖点价值表 | `batch_id|category_code|sku_code|claim_code|claim_role_cn` |

建议在 Base 中保留隐藏字段 `unique_key`，便于同步定位。

### 8.2 写入策略

```text
extract records
  -> map unique_key
  -> load existing record ids by unique_key
  -> split create/update
  -> batch write <= 200
  -> retry retryable errors
  -> write sync summary
```

更新只覆盖发布字段，不删除用户在多维表格中手工新增的业务备注字段。若后续需要删除过期记录，应增加 `--prune-missing` 显式参数。

## 9. CLI 设计

### 9.1 命令

```bash
python -m app.cli.catforge_publish base init \
  --category tv \
  --base-name "小奥家电市场分析工作台"

python -m app.cli.catforge_publish base sync \
  --scope sku-overview \
  --category tv \
  --batch-id latest

python -m app.cli.catforge_publish base sync-all \
  --category tv \
  --batch-id latest

python -m app.cli.catforge_publish base status \
  --category tv

python -m app.cli.catforge_publish base open \
  --category tv
```

### 9.2 参数

| 参数 | 说明 |
| --- | --- |
| `--category` | 品类，默认 `tv`。 |
| `--batch-id` | 分析批次，支持 `latest`。 |
| `--scope` | `analysis-batch`、`sku-overview`、`battlefield-map`、`competitor-relations`、`claim-value`。 |
| `--dry-run` | 不写入，只输出行数和字段校验结果。 |
| `--limit` | 限制提取行数，用于测试。 |
| `--allow-schema-update` | 允许自动新增缺失字段。 |
| `--format` | `text` 或 `json`。 |

### 9.3 text 输出示例

```text
已同步小奥家电市场分析工作台。
品类：TV
批次：m00_20260619084551
SKU 总览：184 行
价值战场图谱：12 行
竞品关系：552 行
用户卖点价值：1286 行
工作台：https://...
```

### 9.4 JSON 输出示例

```json
{
  "status": "ok",
  "category_code": "TV",
  "batch_id": "m00_20260619084551",
  "base_url": "https://...",
  "scopes": [
    {
      "scope": "sku-overview",
      "created": 12,
      "updated": 172,
      "skipped": 0
    }
  ]
}
```

## 10. Skill 设计

### 10.1 意图路由

| 用户说法 | CLI |
| --- | --- |
| “同步最新电视分析结果到工作台” | `base sync-all --category tv --batch-id latest` |
| “重新发布用户卖点价值结果” | `base sync --scope claim-value --category tv --batch-id latest` |
| “打开小奥工作台” | `base open --category tv` |
| “查看工作台同步状态” | `base status --category tv` |

### 10.2 回答约束

Skill 回答必须：

- 使用业务语言说明同步结果。
- 提供工作台链接。
- 不输出命令、stderr、堆栈、Base token、table_id、field_id。
- 如果权限不足，明确提示“当前账号或 bot 没有工作台写入权限”。
- 如果配置缺失，明确提示需要先执行初始化或配置 Base token。

## 11. 视图设计

一期视图只做筛选和排序，不做复杂仪表盘。

| 视图 | 表 | 筛选/排序 |
| --- | --- | --- |
| SKU 总览-按品牌 | SKU 总览表 | 按品牌分组，按周均销售额降序。 |
| SKU 总览-按尺寸价格带 | SKU 总览表 | 按尺寸档、价格带分组。 |
| 海信 SKU | SKU 总览表 | 品牌=海信。 |
| 价值战场空间 | 价值战场图谱表 | 按分配周均销售额降序。 |
| 高销量竞品 | 竞品关系表 | 竞品周均销量降序，排名小于等于 3。 |
| 高溢价卖点 | 用户卖点价值表 | 卖点角色=高溢价，按可解释金额降序。 |
| 待激活卖点 | 用户卖点价值表 | 卖点角色=待激活。 |
| 竞品拦截卖点 | 用户卖点价值表 | 卖点角色=竞品拦截。 |

## 12. 错误处理

| 场景 | 处理 |
| --- | --- |
| 缺少 Base token | `sync` 失败并提示先执行 `base init` 或配置 token。 |
| 表不存在 | 默认失败；带 `--allow-schema-update` 时创建。 |
| 字段不存在 | 默认失败；带 `--allow-schema-update` 时新增字段。 |
| 字段类型冲突 | 失败，不自动修改字段类型，提示人工处理。 |
| 飞书权限不足 | 失败并提示检查 bot/账号权限和 Base 协作者权限。 |
| 飞书限流 | 按配置重试，仍失败则输出失败 scope。 |
| 数据缺失 | 写空值，并在批次表备注中记录缺失 scope。 |
| 重复 unique_key | 本地提取阶段失败，提示检查上游结果。 |

## 13. 测试设计

### 13.1 单元测试

必须覆盖：

- 每张表的 mapper 字段输出。
- 每张表 unique key 生成。
- 数字字段缺失和格式处理。
- `--dry-run` 不调用写入。
- create/update 拆分逻辑。
- 字段类型冲突时失败。

### 13.2 CLI 测试

使用 fake repository 和 fake Lark client：

- `base init` 能创建五张表配置。
- `base sync --scope sku-overview --dry-run` 输出行数。
- `base sync-all` 按正确顺序调度。
- 某 scope 失败时返回非零退出码。
- `--format json` 输出结构稳定。

### 13.3 集成验收

在 205 上使用真实配置验证：

1. 初始化或复用“小奥家电市场分析工作台”。
2. 同步 TV 最新批次。
3. 检查五张表行数。
4. 重复执行同步，确认不新增重复行。
5. 打开工作台，检查业务视图和报告链接。
6. 用小奥自然语言触发同步和打开链接。

## 14. 安全与边界

- 不把数据库密码、API key、Base token 写入文档、日志或飞书表。
- 不在工作台发布原始评论全文。
- 不在工作台发布 LLM prompt、LLM response、内部规则 JSON。
- 不让业务用户通过工作台修改分析结果源数据。
- 手工备注字段与发布字段分离，后续同步不得覆盖人工备注。

## 15. 实施计划

| 阶段 | 交付 |
| --- | --- |
| P1 | 需求和详细设计文档。 |
| P2 | `catforge_publish` CLI 框架、配置读取、fake Lark client 测试。 |
| P3 | Base 初始化、表字段校验、基础视图创建。 |
| P4 | 五张表 extract/map/upsert 同步。 |
| P5 | 小奥 Skill 路由和 205 部署验收。 |
| P6 | 评估更丰富的 Base 仪表盘和多维表格协作流程。 |

