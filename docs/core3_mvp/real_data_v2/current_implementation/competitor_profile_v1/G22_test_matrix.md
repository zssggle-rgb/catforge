# G22 本地综合测试矩阵

状态：竞品画像专项通过；Core3 全量回归存在 7 个非本任务基线失败

日期：2026-07-14

## 1. 结论

竞品画像 G01—G21 的 typed schema、迁移、repository、生命周期、输入、候选、资格、pair 特征、购买池、价值替代、量价压力、七类关系、重点选择、主画像、质量评估、diff、生成回读、formal/preview reader 和单版本消费合同均已在本地通过。未连接 205，未写远程数据库，未部署，未生成远程画像，未执行 review/publish/set-current/deprecate。

## 2. 测试矩阵

| 检查 | 命令/入口 | 结果 |
| --- | --- | --- |
| 竞品画像专项 | `pytest -q tests/core3_real_data/test_competitor_profile_*.py` | 270 项通过 |
| 最大候选与全链性能 | `pytest -q tests/core3_real_data/test_competitor_profile_candidate_performance.py --durations=5` | 12 项通过；377/512 候选层 14.04s；377 pair + 2,639 relations 全链 10.74s；AC 155 为 3.19s |
| 覆盖率 | `coverage run --branch -m pytest -q tests/core3_real_data --ignore=...candidate_performance.py -k competitor_profile` | 通过；竞品画像服务层 statement 92.2%，branch-combined 88% |
| 关键模块 statement coverage | coverage 数据换算 | relation 94.8%；lifecycle 90.4%；repository 91.4%；reader 100% |
| CLI 写门禁/typed request/read | `test_competitor_profile_cli.py` | 通过；未显式 `--enable-profile-write` 时在打开 DB session 前拒绝 |
| 迁移 | `test_competitor_profile_migration.py`、`alembic heads` | 通过；0046 为唯一 head；有数据时 downgrade 明确拒绝 |
| 静态质量 | `ruff check ...competitor_profile_*.py ...` | 通过 |
| 编译 | `python -m compileall -q ...` | 通过 |
| JSON 合同 | `python -m json.tool COMPETITOR_PROFILE_V1_schema_contract.json` | 通过 |
| whitespace | `git diff --check -- <task paths>` | 通过 |
| 无外部 LLM | 源码扫描和模块内边界测试 | 通过；仅保留 forbidden-key 防泄露校验 |
| 无固定业务数量上限 | 源码扫描、377/512 候选测试 | 通过；仅有 repository 分页 1000，不截断业务集合 |
| 无 N+1 读取 | G09 provider select 计数、generation snapshot 计数 | provider 固定 11 次 SELECT；目标组装不加查询；生成服务每 SKU 一次 category snapshot、一次 target input |
| TV/AC 隔离 | typed scope、AC 155、TV/AC 参数化测试 | 通过 |
| unknown/null | optional module、缺失形态、缺失量价、证据冲突测试 | 通过；missing 不转 false |
| 0—3 重点竞品 | selection 测试 | 通过；允许 0，不强补，不按候选总分机械 TopN |
| runtime boundary | schema forbidden-key tests | 通过；业务 DTO 无 hash/snake_case/prompt/Gold Set |
| 旧链保护 | `git diff --name-only` 对 M12/M13/M14 | 无改动 |

## 3. Core3 全量回归

`pytest -q tests/core3_real_data` 完成到 100%，出现以下 7 个失败：

1. `test_catforge_insight_cli.py::test_query_tv_param_taxonomy_exposes_standard_params_and_raw_mapping`：测试期待 taxonomy v0.1，当前代码为 v0.2；
2. `test_catforge_insight_cli.py::test_tier_coverage_and_natural_language_route_to_matching_skus`：既有 taxonomy/fixture 覆盖差异；
3. `test_core3_real_data_constants.py::test_module_order_matches_sop_sequence`：当前模块顺序已有 M12C，旧断言仍期待 M12；
4. `test_core3_real_data_constants.py::test_module_dag_edges_only_reference_known_modules`：既有 DAG/模块列表不一致；
5. `test_local_validation_fixture_pipeline.py::test_local_validation_fixture_runs_through_m00_to_m08`：旧 comment fixture 计数差异；
6. `test_m01_no_business_outputs.py::test_m01_fixture_acceptance_keeps_cleaning_boundary_for_85e7q`：旧 comment sentence 计数差异；
7. `test_m02_no_business_outputs.py::test_m02_85e7q_fixture_does_not_fabricate_promo_evidence_when_claim_source_missing`：旧 comment fixture 计数差异。

上述失败对应的 constants、insight CLI、清洗/证据代码和测试文件均不在本任务 diff 中，且竞品画像专项及现有 `test_catforge_analyst_cli.py` 未出现失败。G22 不越权修改这些旧模块或 fixture；它们作为仓库基线问题记录，不归因于本 RC，也不从结果中隐藏。

## 4. 覆盖率说明

性能测试在 coverage instrumentation 下会放大 wall time，因此覆盖率命令明确排除定时性能文件；性能文件以无 instrumentation 的独立命令验收。服务层总 statement coverage 为 `(6688-520)/6688 = 92.2%`，冻结设计要求的关键模块均不低于 90% statement coverage。
