# 竞品画像 V1 G13 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_candidate_performance_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_candidate_performance.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_candidate_performance.py`。

## 2. 研究过的现有模式

实现前对照了三类已有批量与性能模式：

1. `test_competitor_profile_input_provider.py`：复用 SQLAlchemy `before_cursor_execute` 对 SELECT 计数，正式验证 G09 category bundle 为固定 11 次 SELECT、target bundle 从内存组装且新增查询为 0；
2. `test_sellpoint_value_profile_candidates.py`：复用 0/1/多/1000 候选无业务数量上限、固定 query count 与 `perf_counter` wall-time 门禁的模式；
3. `test_claim_value_pm_v4_context.py`：复用单候选与多候选 query count 必须相同、只读 SQL verb 门禁，避免候选规模增长产生 N+1。

## 3. 已实现的性能合同

- `CandidatePerformanceConfig` 冻结 15,000 ms wall-time、512 MiB peak memory、最多 11 次 provider SELECT 和分页大小 1/17/64/256；
- 修改上述阈值或分页套件必须使用新的 config version，不能冒用 V1；
- 配置不存在 `max_candidates`、`top_n` 或任何业务候选数量上限；
- `CandidatePerformanceBenchmark.measure` 对完整 G12 两遍重放测量 wall time 与 `tracemalloc` peak memory，返回完整 pipeline 与 typed metrics；
- 性能、查询或候选守恒超限时 metrics 明确标记 `failed` 和原因，完整 pipeline 结果仍保留，不通过裁剪候选伪装通过；
- `enforce` 对 failed metrics 抛出 `CandidatePerformanceLimitError`，异常携带完整 metrics；
- suite report 稳定保存全部 passed/failed case，不隐藏失败样例。

## 4. Metrics 与追溯

每个 case 保存：

- project/category/target/config version；
- authoritative SKU、期望候选、recall/eligibility 候选数；
- source record、recall fact、八问题 assessment、唯一 evidence ref 数；
- page size/page count、provider SELECT count；
- wall time、peak memory、状态和失败原因；
- recall、eligibility、determinism result hash；
- metrics 自身 input fingerprint/result hash。

## 5. 当前规模与高于当前规模基线

同一台本地环境、默认性能配置下的复核基线：

| Case | 候选 | 语义覆盖 | Wall time | Peak memory | Source records | Recall facts | Questions | Pages | 状态 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| TV current | 377 | 完整 | 6,721.271 ms | 59.116 MiB | 3,780 | 2,687 | 3,016 | 60 | passed |
| TV above current | 512 | sparse | 4,476.938 ms | 41.041 MiB | 1,034 | 1,088 | 4,096 | 14 | passed |
| AC current | 155 | 完整 | 2,415.455 ms | 24.254 MiB | 1,560 | 1,105 | 1,240 | 30 | passed |

这些数字是当前开发机的回归基线，不是业务阈值推导；阈值只用于显式性能失败，不改变候选集合。

## 6. 无 N+1 与分页等价

- 实际 G09 SQLite 集成复核：category bundle 11 次 SELECT，target bundle 新增 0 次；metrics 保存 `provider_select_count=11`；
- G10 recall、G11 eligibility、G12 canonicalize/replay 均不持有 session/repository/query 依赖；
- page size 1、17、64、256 产生不同 page count，但 recall、eligibility 和 determinism business hash 完全一致；
- 0、1、155、377、512 候选均完整保存；512 高于当前 TV 377 规模，未触发任何业务 cap；
- 完整语义与 sparse 语义均只影响事实量和状态，不影响候选守恒。

## 7. 验证

- G13 performance/schema tests：11 passed；
- G05—G13 schema/migration/repository/lifecycle/input/recall/eligibility/determinism/performance：124 passed；
- G13 service + schema coverage：93%；
- TV 0/1/155/377/512、AC 155：通过；
- 高于当前规模 512 候选无截断：通过；
- 四种分页大小 business hash 等价：通过；
- actual G09 fixed 11 SELECT、target 0 SELECT：通过；
- exact duplicate canonicalization：通过；
- wall/query overrun 显式 failed 且候选仍完整：通过；
- suite report 保留 failed case、typed count/status 反例：通过；
- 服务源码无 SQLAlchemy、repository、query 或外部 LLM 依赖：通过；
- Ruff、format check：通过。

## 8. 状态变化

- 本地数据库只用于 pytest SQLite 临时库的只读 query-count 集成测试；测试结束后销毁；
- 205 连接/数据库写入/migration：无；
- 画像生成、review/publish/current/deprecated：均未执行；
- pair 特征、购买池、语义替代、量价压力、七类正式关系和重点竞品选择：均未实现；
- 部署：无；
- Git 暂存/提交：无。

## 9. 下一 Goal

允许创建 G14，只实现 target×candidate pair 基础特征 DTO 与 builder，覆盖参数、卖点、用户语义、市场量价、source availability 和 unknown；不得实现购买池结论、证据族强弱、七类关系、总分、重点选择、画像持久化、205 写入、部署或 Git 提交。
