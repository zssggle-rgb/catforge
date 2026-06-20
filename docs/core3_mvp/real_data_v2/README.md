# 真实数据版 Core3 MVP v2 设计包

本设计包是在重新研读产品级 PRD、产品详细设计、Goal1/Goal2/Goal3 文档、Core3 MVP 文档和参考 Word 后形成的 v2 设计。

v2 的核心修正：

- 不再把清洗、预分析、画像生成理解为一个大脚本。
- 不直接从 4 张上传原始表跳到竞品报告。
- 原始表、清洗表、语义抽取表、资产候选表、SKU 画像表、竞品结果表分层持久化。
- 预制知识只作为完整的彩电业务本体和识别框架；SKU 结论必须由真实数据激活。
- 后续原始表增量增加时，执行同一条任务链，只重算受影响 SKU 和受影响资产候选。

## 阅读顺序

### 设计与方法论

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

### 当前实现

当前已经落地的实现说明单独放在 [current_implementation](current_implementation/README.md)，用于和前面的设计稿、历史开发说明分开。

当前实现文档包括：

1. [数据预处理 CLI 与 Claude Code Skill 分支开发手册](current_implementation/00_data_preprocess_cli_skill_branch_manual.md)
2. [M00 原始数据登记当前实现说明](current_implementation/01_m00_source_registry_implementation.md)
3. [M01 清洗与质量过滤当前实现说明](current_implementation/02_m01_cleaning_quality_implementation.md)
4. [M02 Evidence 原子层当前实现说明](current_implementation/03_m02_evidence_atom_implementation.md)

## 与旧设计的关系

- `docs/core3_mvp/00_*` 到 `12_*` 仍是 Core3 MVP 的基础设计。
- `docs/core3_mvp/13_real_data_ingestion_preanalysis_design.md` 是第一版真实数据接入设计，概念有效但分层不够细。
- 本目录是后续讨论和实现真实样例数据接入的主设计依据。
- `current_implementation/` 记录当前分支已经实现、可执行、可验证的模块行为；排查线上和 205 行为时优先看这里。
- 后续模块详细设计按 `00a_competitor_sop_module_plan.md` 一个一个生成，先讨论确认，再进入下一模块。
- 后续模块完成实现后，也要在 `current_implementation/` 中新增对应实现文档，避免设计稿和实现稿混用。

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
