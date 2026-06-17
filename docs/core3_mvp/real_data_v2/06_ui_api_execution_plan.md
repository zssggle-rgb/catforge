# 06 页面、API、任务编排与实施验收

## 1. 页面目标

页面给海信业务高层看，不是给工程师看。

页面应展示：

- 本次分析用了哪些真实数据。
- 目标型号目前主要在哪些价值战场竞争。
- 系统如何从全量型号收敛到候选池。
- 核心三竞品分别是谁。
- 每个竞品为什么成立。
- 哪些数据不足会影响判断。

页面不展示：

- 英文枚举。
- UUID。
- 数据库字段名。
- `source_type`、`task_code`、`battlefield_code`。
- “AI 正在分析”之类过程性空话。
- 大段方法论说明。

## 2. 页面结构

### 2.1 数据基础

业务语言：

```text
本次分析基于 35 个彩电型号、23 周量价数据、84 类参数字段、6.2 万条评论和 65 条结构化卖点。
数据最近更新时间：2026-06-11。
```

质量提醒：

```text
部分型号缺少结构化卖点，系统会用参数和评论补充判断；相关卖点结论已降低置信度。
```

### 2.2 目标型号定位

展示：

- 型号、品牌、尺寸、价格带。
- 近 23 周销量/销额。
- 渠道重心。
- 核心参数。
- 主要正向评论。
- 数据完整度。

### 2.3 主战场推导

按业务推导展示：

```text
第一步：产品硬实力
  屏幕尺寸、亮度、刷新率、分区、接口等。

第二步：用户感知
  评论中画质、流畅、服务、价格等反馈。

第三步：市场验证
  价格带、销量、渠道、趋势。

第四步：战场判断
  主战场、次要战场、机会战场。
```

每个战场展示：

- 战场名称。
- 关系：主要/次要/机会/证据不足。
- 语义支撑。
- 市场支撑。
- 缺失证据。

### 2.4 候选池收敛

不要只展示结果，要展示收敛过程：

```text
全量 35 个型号
  -> 34 个可比候选
  -> 18 个尺寸可比
  -> 9 个价格或任务可比
  -> 5 个战场重合
  -> 3 个核心竞品
```

每一步显示业务条件，不显示 SQL 或内部 gate。

### 2.5 三竞品结论

三张卡：

- 正面对打竞品。
- 价格/销量挤压竞品。
- 高端标杆/潜在下探竞品。

每张卡先显示一句业务结论：

```text
它和目标型号抢同一批大屏观影升级用户，是最直接的正面对打竞品。
```

再显示证据：

- 尺寸和价格。
- 主战场。
- 参数对比。
- 卖点对比。
- 评论关注点。
- 销量/销额。
- 渠道重合。

### 2.6 证据详情

给业务高层的证据不应是原始表格字段，而是可读证据：

```text
参数证据：85 英寸、144Hz、高亮度、Mini LED。
市场证据：近 23 周销售额处于同尺寸高位。
评论证据：用户正向反馈集中在画质清晰和大屏体验。
```

可折叠展示原始来源，供内部核查。

## 3. API 设计

接口仍可使用英文路径，前端展示必须中文化。

### 3.1 数据状态

```text
GET /api/mvp/core3/projects/{project_id}/real-data/status
```

返回：

- 原始表行数。
- 清洗表行数。
- 已抽取事实数。
- 已生成 SKU 画像数。
- 最近批次。
- 数据质量摘要。

### 3.2 启动任务链

```text
POST /api/mvp/core3/projects/{project_id}/real-data/jobs
```

请求：

```json
{
  "mode": "incremental",
  "target_stage": "core3_report",
  "target_model": "85E7Q",
  "force_recompute": false
}
```

`target_stage` 可选：

- `cleaning`
- `semantic_extraction`
- `asset_candidates`
- `sku_profiles`
- `tasks_battlefields`
- `competitor_results`
- `core3_report`

### 3.3 查询任务

```text
GET /api/mvp/core3/projects/{project_id}/real-data/jobs/{job_id}
```

返回每个阶段：

- 状态。
- 输入行数。
- 输出行数。
- 影响 SKU 数。
- 质量问题数。
- 错误信息。

### 3.4 数据基础页面

```text
GET /api/mvp/core3/projects/{project_id}/real-data/foundation
```

返回面向页面的中文业务字段：

- 型号覆盖。
- 参数覆盖。
- 卖点覆盖。
- 评论覆盖。
- 周销覆盖。
- 质量提示。

### 3.5 单 SKU 推导报告

```text
GET /api/mvp/core3/projects/{project_id}/real-data/sku/{model_or_sku}/derivation-report
```

返回：

- 目标型号定位。
- 主战场推导。
- 候选池收敛。
- 三竞品。
- 证据卡。
- 不足原因。

### 3.6 资产候选

```text
GET /api/mvp/core3/projects/{project_id}/real-data/asset-candidates
```

用于内部复核，不进入高层页面主流程。

## 4. 任务编排

### 4.1 同步与异步

MVP 可以本地同步执行小批量任务，但设计上必须是任务化。

推荐：

- 小样例：API 同步触发，后台任务记录状态。
- 1000 SKU：异步 job，前端轮询。

### 4.2 入口不是大脚本

允许一个 CLI：

```text
python -m app.services.core3_mvp.real_data_pipeline run --mode incremental --target-stage core3_report
```

但它内部必须调用服务：

```text
SourceScanner
QualityScanner
SalesCleaner
ParamCleaner
ClaimCleaner
CommentCleaner
FieldProfiler
TextProfiler
ParamExtractor
ClaimExtractor
CommentTopicExtractor
AssetCandidateGenerator
SkuProfileBuilder
TaskBattlefieldScorer
CompetitorSelector
ReportAssembler
```

## 5. 实施阶段

### Phase A：数据登记和清洗落表

交付：

- `core3_source_batch`
- `core3_source_row_registry`
- `core3_clean_market_fact`
- `core3_clean_param_fact`
- `core3_clean_claim_fact`
- `core3_clean_comment_fact`
- 数据质量页面。

验收：

- 原始表不改。
- 重复执行不重复写入。
- 新增一条评论能识别为增量。

### Phase B：分词、字段画像和文本画像

交付：

- `core3_param_field_profile`
- `core3_text_token`
- `core3_phrase_profile`
- 参数字段候选。
- 卖点短语候选。
- 评论主题候选。

验收：

- 能列出高覆盖参数字段和未映射字段。
- 能列出高频卖点短语和评论主题短语。

### Phase C：参数、卖点、评论主题抽取

交付：

- `core3_extract_param_value`
- `core3_extract_claim_hit`
- `core3_extract_comment_topic_hit`
- `core3_sku_claim_activation`
- `core3_sku_comment_topic_summary`

验收：

- 85E7Q 能生成参数和评论画像。
- 结构化卖点缺失时，卖点画像降级但不伪造。

### Phase D：任务、客群、战场反推

交付：

- `core3_sku_task_score`
- `core3_sku_target_group_score`
- `core3_sku_battlefield_score`

验收：

- 能解释目标 SKU 主战场是什么。
- 能解释为什么某战场不是主战场。

### Phase E：竞品候选和三竞品报告

交付：

- `core3_competitor_candidate`
- `core3_competitor_result`
- `core3_evidence_card`
- 高层报告页面。

验收：

- 三槽位按不同逻辑选择，不是综合 Top3。
- 同品牌竞品可进入结果。
- 每个竞品有业务解释和证据。

## 6. 测试策略

### 6.1 单元测试

- unknown 处理。
- 周期解析。
- 销售价格校验。
- 评论去重。
- 参数 parser。
- 卖点分句。
- 评论主题情感。
- 任务和战场公式。

### 6.2 集成测试

构造小型真实表 fixture：

- 目标 SKU 85E7Q。
- 同尺寸候选。
- 低价压力候选。
- 高端标杆候选。
- 缺卖点但有参数和评论的 SKU。

验证完整任务链从原始表到报告。

### 6.3 增量测试

1. 首次全量跑。
2. 新增一条评论。
3. 再跑 incremental。
4. 验证只更新相关 SKU 的评论、任务、战场和竞品分。

### 6.4 页面测试

- 页面不出现英文枚举和内部字段。
- 页面先给竞品结论，再展示推导。
- 页面能展示候选池收敛。
- 证据详情可折叠。

## 7. /goal 执行前置要求

进入实现前应先确认：

1. 使用 `all_current` 还是按最新 `write_time` 切批。
2. 是否允许新增上述清洗和抽取表。
3. 是否以 seed 作为 approved baseline，新发现只进候选。
4. 目标演示型号是否仍为 `85E7Q`。
5. 高层页面是否只展示报告，不展示资产候选和复核页面。

建议默认：

- 使用 `all_current`。
- 允许新增清洗、抽取、候选和画像表。
- seed 作为 approved baseline。
- 新发现进入候选，不自动影响高置信结论。
- 默认目标型号 `85E7Q`，但支持输入任意型号。

