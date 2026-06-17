# 00 设计依据与总体原则

## 1. 本次重新设计读取的依据

本设计不是只看 Core3 MVP 局部文档，而是对齐 CatForge 的整体产品链路。

已读取并吸收的关键文档：

| 文档 | 对本设计的约束 |
| --- | --- |
| `cankao/品类生产工具_PRD_v0.1.docx` | CatForge 是内部品类资产生产线，不是单纯竞品页面；流程应包含数据剖析、候选生成、复核、评测、发布 |
| `cankao/品类生产工具_产品开发详细设计_v0.1.docx` | 所有后续计算基于 canonical schema 和 evidence_id，不直接依赖原始 Excel 列名；重计算应由任务流水线执行 |
| `cankao/CatForge_彩电核心三竞品生成_MVP_PRD_PostgreSQL版.docx` | MVP 聚焦“市场数据如何转化为可解释竞品判断”，输出目标 SKU 的核心三竞品和证据卡 |
| `cankao/CatForge_彩电核心三竞品生成_MVP_详细设计_PostgreSQL版.docx` | 三竞品必须按正面对打、价格/销量挤压、高端标杆/潜在下探三槽位选择，不能只取综合 Top3 |
| `docs/00_context.md` | 主链路是事实数据、参数归一、卖点映射、评论主题、任务、客群、战场、竞品规则、复核、导出 |
| `docs/02_data_contract.md` | 每条导入记录必须有 provenance；缺失是 unknown，不能当 false |
| `docs/03_asset_schema.md` | 参数、卖点、评论主题、任务、战场都是资产，有 candidate/approved/deprecated 状态 |
| `docs/05_export_boundary.md` | 工厂生成方法、聚类、Prompt、Gold Set 不进入运行态导出 |
| `docs/06_technical_architecture.md` | 应按 ingestion、profiling、param_factory、claim_factory、comment_topic_factory、task_battlefield_factory、competitor_engine 拆服务 |
| `docs/goal1/*` | 运行链路顺序：参数归一、卖点抽取、评论主题、卖点激活、任务评分、战场评分、竞品引擎 |
| `docs/goal3/*` | 资产生成要保留来源、覆盖率、样例、置信度、复核状态、版本 |
| `docs/core3_mvp/*` | Core3 MVP 的独立命名空间、三槽位、证据卡和业务报告页面边界 |

## 2. 对用户三个问题的设计回答

### 2.1 清洗、画像等不能只靠一个脚本

结论：不能设计成一个大脚本。

可以有一个统一执行入口，例如：

```text
python -m app.services.core3_mvp.real_data_pipeline run --project TV --mode incremental
```

但这个入口只负责调度，不承载业务逻辑。真实结构应是多个独立任务：

```text
source_scan
clean_sales
clean_params
clean_claims
clean_comments
profile_fields
profile_text
extract_params
extract_claims
extract_comment_topics
generate_asset_candidates
build_sku_profiles
score_tasks_groups_battlefields
build_competitor_candidates
select_core3_results
assemble_business_report
```

每个任务必须有：

- 清晰输入表。
- 清晰输出表。
- 版本号。
- row hash 或 input fingerprint。
- 可重跑策略。
- 失败后可定位的 diagnostics。

### 2.2 不能跳过分词、语义抽取和资产候选

竞品不是从“价值战场”直接写出来，而是从真实数据层层推导：

```text
原始参数、卖点、评论、量价
  -> 字段画像和文本分词
  -> 标准参数、候选参数别名
  -> 宣传卖点片段、候选标准卖点
  -> 评论主题、候选新主题
  -> 用户任务候选和得分
  -> 目标客群候选和得分
  -> 价值战场候选和得分
  -> 每个 SKU 的信号画像
  -> 每个目标 SKU 的候选竞品池
  -> 三槽位竞品和证据卡
```

页面给领导看时可以收敛表达，但后台不能跳过这些阶段。

### 2.3 原始表、清洗表、分析表必须分开

当前上传的 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data` 应视为原始输入表。

后续必须新增三类以上持久化产物：

- 清洗规范层：字段名统一、类型统一、unknown 统一、去重后的规范事实。
- 语义抽取层：分词、短语、参数抽取、卖点命中、评论主题、候选资产。
- SKU 分析层：市场画像、参数画像、卖点画像、评论画像、任务、客群、战场、竞品候选和结果。

增量数据进入原始表后，执行增量任务链即可把新增或变化行转换到后续表。

## 3. 总体设计原则

1. 原始表只读：业务任务不修改上传原始表。
2. 清洗结果落表：不能只在内存里清洗，必须可检查、可回放、可增量。
3. 语义抽取落表：分词、短语、主题、候选资产是可复用生产资产，不只是报告中间变量。
4. 资产候选与批准资产分离：候选可以来自算法，批准必须可由人工复核或 seed 版本确认。
5. SKU 结果由资产激活：SKU 的参数、卖点、任务、客群、战场必须来自真实证据和规则计算。
6. 同品牌可竞争：竞品池不按内部/外部品牌排除，海信型号可以是海信型号的竞品。
7. 缺失是 unknown：空、`-`、`未知`、null 不作为负向判断。
8. 证据必须贯穿：最终竞品理由要能回溯到原始行、清洗行、抽取行和规则版本。
9. 页面业务化：领导页面展示业务判断链，不展示 UUID、数据库字段、英文枚举、内部任务名。
10. 工厂边界不外泄：分词、聚类、Prompt、Gold Set、自动资产生成方法属于 CatForge 内部能力。

## 4. v2 与现有 Core3 MVP 的关系

现有 Core3 MVP 已有：

- `core3_pipeline_run`
- `core3_sku_market_profile`
- `core3_sku_feature_profile`
- `core3_competitor_candidate`
- `core3_competitor_result`
- `core3_evidence_card`

v2 不推翻这些结果表，但需要在它们之前补齐真实生产链路：

```text
原始输入层
  -> 清洗规范层
  -> 语义抽取层
  -> 资产候选/映射层
  -> SKU 画像层
  -> 现有 core3 结果层
```

实现时可以继续把最终报告写入现有 `core3_` 结果表，但不能再从原始表直接拼出报告。

