# 彩电核心三竞品 MVP 设计包

本目录是 `CatForge_彩电核心三竞品生成_MVP` 的可执行设计，不按“前端/后端”粗拆，而是按数据从 PostgreSQL 进入系统后逐步变成核心三竞品报告的链路拆分。

## 阅读顺序

1. [总体流程设计](00_overall_pipeline.md)
2. [数据读取与源表适配](01_data_reading.md)
3. [运行上下文、数据健康与落库骨架](02_run_context_quality.md)
4. [彩电预制知识资产目录](03a_preset_asset_catalog.md)
5. [真实数据抽取框架](03b_real_data_extraction.md)
6. [SKU 市场画像模块](03_market_profile.md)
7. [参数、卖点、评论特征模块](04_param_claim_comment_features.md)
8. [任务、客群、价值战场评分模块](05_task_group_battlefield.md)
9. [候选池与组件评分模块](06_candidate_pool_scoring.md)
10. [核心三竞品选择与证据卡模块](07_core3_selection_evidence.md)
11. [报告、页面工作流与导出模块](08_report_page_export.md)
12. [实施任务、测试与验收](09_implementation_tests.md)
13. [/goal 执行计划](10_goal_execution_plan.md)
14. [契约与 Schema 规格](11_contracts_and_schemas.md)
15. [测试夹具与期望结果设计](12_test_fixtures_expected.md)
16. [真实数据版 v2 设计包](real_data_v2/README.md)

## 核心原则

- 从读取数据开始设计，每一步都明确输入、输出、持久化表、失败处理和验收。
- 新 MVP 独立于现有 Goal3 工作台，不混入现有页面组。
- 使用现有 raw tables 和 `evidence_item`，新增 `core3_` 前缀结果表。
- 预制知识只定义可识别概念、别名、阈值和映射；SKU 结论必须从真实数据抽取和留证。
- 新发现的字段、短语、卖点和主题先进入候选资产，不自动污染正式预制知识。
- 第一版使用确定性规则，不启用 LLM。
- 缺失值是 unknown，不等于 false。
- 不足时输出原因，不硬凑三个竞品。

## 主数据流

```text
PostgreSQL raw tables / production views
  -> 数据读取与字段适配
  -> 运行上下文与数据健康检查
  -> 加载彩电预制知识资产
  -> 真实数据抽取与候选发现
  -> SKU 市场画像
  -> 参数归一、卖点激活、评论主题
  -> 用户任务、目标客群、价值战场
  -> 候选池召回与组件评分
  -> 三槽位选择 direct / pressure / benchmark_potential
  -> 证据卡、报告、页面、CSV/JSONL 导出
```

## /goal 执行入口

如果要进入 `/goal` 模式执行，优先使用：

1. [10 /goal 执行计划](10_goal_execution_plan.md)
2. [11 契约与 Schema 规格](11_contracts_and_schemas.md)
3. [12 测试夹具与期望结果设计](12_test_fixtures_expected.md)
4. [真实数据版 v2 设计包](real_data_v2/README.md)

这四部分把实现拆成 Goal A-G，并固定了文件范围、schema、测试夹具、真实数据分层和退出标准。

如果目标是接入 205 上的 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data` 真实样例表，应以 `real_data_v2/` 为主设计依据。`13_real_data_ingestion_preanalysis_design.md` 是第一版草案，已被 v2 的分层设计取代。
