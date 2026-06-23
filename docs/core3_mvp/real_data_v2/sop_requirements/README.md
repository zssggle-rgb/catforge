# SOP 模块需求文档索引

本目录存放 CatForge 彩电核心三竞品生成的 SOP 模块需求文档。

当前阶段只定义“模块需求”，不写技术详细设计，不拆开发任务，不开发代码。

设计依据优先级：

1. `cankao/CatForge_竞品生成SOP_详细指导_v1.md`
2. `cankao/catforge_sop_md/modules/` 中对应模块
3. `cankao/CatForge_核心竞品展示页_UI设计规范_v1.md`
4. `docs/core3_mvp/real_data_v2/00a_competitor_sop_module_plan.md`
5. 前面已确认的 205 PostgreSQL 真实样例数据分析

## 真实数据基线

所有模块都必须参考：

- [00 真实样例数据基线](00_real_data_baseline.md)

## 数据分层边界

前面讨论过的“原始表、清洗表、分析抽取表分开保存”已经作为本批需求文档的核心约束。后续详细设计和开发任务拆分必须沿用这个分层：

| 层级 | 作用 | 典型表或产物 |
| --- | --- | --- |
| 原始表 | 保留上传方原始数据，不覆盖改写 | `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data` |
| 原始登记层 | 记录批次、水位、原始行、来源和行哈希 | `core3_source_batch`、`core3_source_row_registry` |
| 清洗规范层 | 生成标准 SKU、市场、参数、卖点、评论表 | `core3_clean_sku`、`core3_clean_market_weekly`、`core3_clean_attribute`、`core3_clean_claim`、`core3_clean_comment` |
| 证据原子层 | 把市场、参数、卖点、评论、质量问题统一成 evidence | `core3_evidence_atom` |
| 抽取特征层 | 生成参数、卖点、评论下游信号 | `core3_extract_param`、`core3_sku_claim_fact_profile`、`core3_sku_claim_activation`、`core3_comment_signal` |
| 画像推导层 | 生成市场画像、SKU 画像、任务、客群、战场、卖点价值分层 | `core3_sku_market_profile`、`core3_sku_signal_profile`、`core3_m09c_sku_user_task_profile`、`core3_m10c_sku_target_group_profile`、`core3_sku_value_battlefield_profile`、`core3_sku_claim_value_layer` |
| 语义市场结果层 | 生成任务、客群、战场图谱和销量/销额分配 | `core3_semantic_market_allocation`、`core3_semantic_market_dimension_summary`、`core3_semantic_market_graph_snapshot` |
| 竞品结果层 | 生成候选、评分、核心竞品、证据卡和报告 payload | `core3_candidate_pool`、`core3_candidate_component_score`、`core3_competitor_selection`、`core3_evidence_card`、`core3_target_report_payload` |

原则：下游模块只能读取上游产物，不能为了省事直接读取原始表做业务判断。

## 生成顺序

1. [M00 原始数据批次与行登记](M00_source_batch_registry_requirements.md)
2. [M01 清洗规范化与质量诊断](M01_cleaning_quality_requirements.md)
3. [M02 Evidence 原子层](M02_evidence_atom_requirements.md)
4. [M03A 品类参数语义资产生成](M03A_param_taxonomy_semantic_asset_requirements.md)
5. [M03B SKU 参数事实画像与参数档位覆盖](M03B_sku_param_profile_requirements.md)
6. [M03 参数字段画像与标准参数抽取](M03_param_extraction_requirements.md)
7. [M04C SKU 卖点事实画像与卖点位置覆盖](M04C_claim_fact_profile_requirements.md)
8. [M04a 基础卖点激活](M04a_base_claim_activation_requirements.md)
9. [M05 评论基础证据层](M05_comment_evidence_requirements.md)
10. [M06 评论下游信号抽取层](M06_comment_downstream_signal_requirements.md)
11. [M04b 评论验证增强](M04b_claim_comment_enhancement_requirements.md)
12. [M07 市场画像与可比池基线](M07_market_profile_requirements.md)
13. [M05C 评论事实画像](M05C_comment_fact_profile_requirements.md)
14. [M09C 新用户任务画像](M09C_user_task_profile_requirements.md)
15. [M10C 新目标客群画像](M10C_target_group_profile_requirements.md)
16. [M11C 新价值战场画像与图谱](M11C_value_battlefield_profile_requirements.md)
17. [M11D 新版语义市场图谱与销量分配](M11D_semantic_market_graph_allocation_requirements.md)
18. [CatForge Analyst 与小奥家电市场分析专家](CATFORGE_ANALYST_xiaoao_agent_requirements.md)
    - [CatForge Analyst 竞品问答 CLI 与小奥 Skill](CATFORGE_ANALYST_competitor_answer_requirements.md)
19. [M08 SKU 综合信号画像](M08_sku_signal_profile_requirements.md)
20. [M08.4 评论原生业务维度发现](M08_4_comment_native_dimension_discovery_requirements.md)
    - [M08.6 参数-卖点-评论分层产品锚点校准](M08_6_product_anchor_evidence_layer_requirements.md)
21. [M09 用户任务模块](M09_user_task_requirements.md)
22. [M10 目标客群模块](M10_target_group_requirements.md)
23. [M11 价值战场模块](M11_battlefield_requirements.md)
24. [M11.5 战场内卖点价值分层](M11_5_claim_value_layer_requirements.md)
25. [M12 候选池召回模块](M12_candidate_recall_requirements.md)
26. [M13 竞品组件评分模块](M13_component_scoring_requirements.md)
27. [M14 三槽位核心竞品选择](M14_core3_selection_requirements.md)
28. [M15 证据卡与高层报告](M15_evidence_report_requirements.md)
29. [M16 增量任务编排、复核和验收](M16_incremental_review_acceptance_requirements.md)

新分层链路落地后，旧 M05/M06/M08/M09/M10/M11 只作为历史兼容和对照验证；常规新链路由 M02 进入 M05C 评论事实画像，再进入 M09C 用户任务、M10C 目标客群和 M11C 价值战场。

## 共同约束

- 下游模块不得绕过上游直接读取原始表做业务判断。
- 评论粗分类只作为参考，不直接生成任务、客群、战场或竞品结论。
- 任意业务结论必须有 evidence、置信度、规则版本和样本充分性说明。
- 竞品结果只输出 0-3 个核心竞品，不输出 TopN 大列表。
- 页面面向业务领导，主屏只展示结论、证据和策略含义。
