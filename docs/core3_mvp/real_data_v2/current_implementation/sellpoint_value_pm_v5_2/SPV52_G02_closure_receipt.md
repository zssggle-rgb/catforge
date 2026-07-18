# SPV52-G02 Typed Schema 与 M04C 原始卖点 Reader 回执

状态：completed

日期：2026-07-18

## 1. 实现内容

新增：

- V5.2 schema、rule、method 版本常量；
- `SourceSellpointFact` 与 M04C lineage；
- 卖点—参数、卖点—用户价值 typed link；
- 卖点四分类与参数五分类 typed assessment；
- `LayerIntegritySummary`；
- `SqlAlchemyM04CSourceSellpointRepository`；
- `M04CSourceSellpointReader`。

## 2. 已冻结行为

- Reader 按 project、category、batch、SKU、正式 M04C taxonomy/rule 读取；
- 原始卖点保存 raw/clean claim、标准 claim、参数支撑、证据和 confidence；
- `exact_quote_cn` 必须是原始卖点的连续子串；
- 同一 `source_claim_key + claim_code` 确定性去重并合并证据；
- 不同原文或标准名称冲突时抛出 integrity error；
- M04C profile/fact 缺失时诚实返回 `no_source_sellpoint`；
- 无外部 LLM、无卖点生成、无数据库写入。

## 3. 专项验证

- `test_sellpoint_value_profile_v5_2_claim_reader.py`：8 passed；
- touched files `ruff check`：passed；
- `git diff --check`：passed。

按效率约束未运行完整 SPV/竞品画像回归、覆盖率或性能评审；这些集中在 G06。

## 4. 未执行

- 未改报告、卡片或问答；
- 未接入 materializer/repository；
- 未部署 205；
- 未生成画像；
- 未 review、publish 或切 current。

下一 Goal：SPV52-G03 分层映射、卖点分类、参数分类和完整性校验。
