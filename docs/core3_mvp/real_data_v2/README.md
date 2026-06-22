# 真实数据版 Core3 MVP v2 设计包

本设计包是在重新研读产品级 PRD、产品详细设计、Goal1/Goal2/Goal3 文档、Core3 MVP 文档和参考 Word 后形成的 v2 设计。

v2 的核心修正：

- 不再把清洗、预分析、画像生成理解为一个大脚本。
- 不直接从 4 张上传原始表跳到竞品报告。
- 原始表、清洗表、语义抽取表、资产候选表、SKU 画像表、竞品结果表分层持久化。
- 预制知识只作为完整的彩电业务本体和识别框架；SKU 结论必须由真实数据激活。
- 后续原始表增量增加时，执行同一条任务链，只重算受影响 SKU 和受影响资产候选。

## 阅读顺序

1. [设计依据与总体原则](00_design_basis_and_principles.md)
2. [竞品生成方法论 SOP 模块设计计划](00a_competitor_sop_module_plan.md)
3. [从原始表到三竞品的完整流水线](01_pipeline_from_raw_to_competitor.md)
4. [持久化分层与增量数据模型](02_persistence_and_incremental_tables.md)
5. [清洗、质量诊断与规范化任务](03_cleaning_and_quality_jobs.md)
6. [分词、语义抽取与资产候选生成](04_semantic_extraction_asset_candidates.md)
7. [评论基础证据与下游独立抽取模块](04a_comment_modular_extraction.md)
8. [SKU 画像反推、任务客群战场与竞品推导](05_sku_profile_reverse_inference.md)
9. [用户任务独立模块详细设计](05a_user_task_module_design.md)
10. [页面、API、任务编排与实施验收](06_ui_api_execution_plan.md)
11. [彩电真实数据结果链路解释](07_result_chain_explainer_tv_example.md)
12. [分层分析路径指导](08_layered_analysis_path_guidance.md)
13. [当前正确流程、CLI、Skill 与 Agent 系统](current_implementation/00_current_flow_cli_skill_system.md)

## 与旧设计的关系

- `docs/core3_mvp/00_*` 到 `12_*` 仍是 Core3 MVP 的基础设计。
- `docs/core3_mvp/13_real_data_ingestion_preanalysis_design.md` 是第一版真实数据接入设计，概念有效但分层不够细。
- 本目录是后续讨论和实现真实样例数据接入的主设计依据。
- 后续模块详细设计按 `00a_competitor_sop_module_plan.md` 一个一个生成，先讨论确认，再进入下一模块。
- `08_layered_analysis_path_guidance.md` 是在 `07_result_chain_explainer_tv_example.md` 基础上重新整理的分层分析路径，用于指导后续模块保留、优化、合并和执行顺序调整。
- `current_implementation/00_current_flow_cli_skill_system.md` 是当前执行入口、CLI、Skill、OpenClaw/XiaoAo 路由的最新口径，用于避免把历史模块、当前 CLI 和 agent 能力混在一起。

## 一句话架构

```text
上传原始表
  -> 原始行登记与批次指纹
  -> 清洗规范表
  -> Evidence 原子层
  -> 参数抽取、基础卖点激活、评论基础证据
  -> 评论下游信号、卖点评论验证增强、市场画像
  -> SKU 综合信号画像
  -> 用户任务、目标客群、价值战场
  -> 战场内卖点价值分层
  -> 候选池召回、组件评分、三槽位核心竞品选择
  -> 面向业务高层的证据卡和推导式竞品报告
```
