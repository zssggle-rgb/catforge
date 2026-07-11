# G03 V4 只读 context、authority 与 lineage gate 进度

- Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`
- Goal 状态：`ready_to_close`
- 定时器：`catforge-v4-g03-10`
- 前置 G02 artifact commit：`f62b68f`
- 前置 G02 closure commit：`261457e`
- 允许修改：`claim_value_pm_v4_schemas.py`、`analyst_repository.py` 的 G03 只读入口、G03 测试/fixture/回执
- 禁止事项：价值关系、反事实角色/可比性、选择贡献、WTP、业务渲染、路由启用、数据库/205 写入

## 当前门禁

| 门禁 | 状态 |
| --- | --- |
| 复核至少 3 类现有 schema/repository/read-contract 模式 | completed |
| V4 context typed schema | completed |
| configured authority manifest | completed |
| published/current 双时间 lineage gate | completed |
| target/candidate snapshot 批量只读适配 | completed |
| M12C 仅中间事实、M14/fallback 仅来源事实 | completed |
| deterministic input/snapshot hash | completed |
| schema/repository/65E7Q fixture tests | completed |
| query count 与无写路径门禁 | completed |
| V2 回归 | completed_with_unrelated_m12d_baseline_failure |

## 已冻结约束

1. `is_current=true` 不能代替 configured rule version；
2. 同一 rule version 在 serving scope 内出现多个不可裁决 current 记录时必须 blocked；
3. 已发布 M12D 与当前验证事实分开保存，不能静默混读；
4. M12D source refs 缺少可比字段时状态为 unresolved，不猜测 aligned；
5. M12C 只输出 pool/tier 中间事实，不读取或映射旧分摊金额；
6. G03 的任何 DTO 都不是产品经理结论。

## 实现结果

1. `claim_value_pm_v4_schemas.py` 实现 G02 冻结的 10 个 G03 typed contracts，字段集合和 required 集合均由自动断言与 `G02_schema_contract.json` 完全对齐；
2. `sellpoint_value_v4_context()` 复用现有目标解析和 published M12D reader，按模块批量读取 configured rule/taxonomy/current；
3. M03B-M11C 每模块一条批量查询，M11D allocation/summary、M12C quant/pool、评论 atoms、周量价均为集合查询；
4. 单候选和三候选的空库查询数相同且均不超过 20，证明候选数量不触发 N+1；
5. serving scope 按显式顺序择优，同一优先批次出现多条相同 key 时不自动择一；
6. published M12D 和 current validation 分面保存，版本或批次不一致局部产生 `version_lineage_conflict`；
7. M14 缺失时 fallback 保留 `competitor_set_fallback`，不得标成 M14；
8. M12C 只选择 pool/tier/evidence 列，数值档位从冻结的 quality flags 读取，旧金额列未被 select 或序列化；
9. inventory 固定为 `unavailable`，promotion 只使用 M07 的 suspect flag；
10. input/snapshot hash 使用 canonical JSON，映射顺序不影响 hash，数据变化会改变 hash。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| G03 schema/context tests | 18 passed |
| G03 + V2 sellpoint service/answer | 47 passed |
| G03 schema coverage | 96% |
| G02 runtime field/required contract diff | exact match |
| Ruff（G03 新文件） | passed |
| Ruff（analyst repository，忽略既有 F821/F841） | passed |
| py_compile | passed |
| SQL write verbs in context integration | 0 |
| candidate N+1 | 1 候选与 3 候选 query count 相同，均 <=20 |

## 已知非 G03 基线失败

当前工作区另一个未提交任务已在 `purchase_reason_profile_repositories.py` 新增 M12D 发布质量门禁，但两个既有测试 fixture 仍以 `release_quality_status=unassessed` 发布，导致：

- `test_repository_reader_only_reads_published_m12d` 失败；
- `test_ac_competitor_set_consumes_published_m12d_without_tv_fallback` 失败。

G03 未修改上述 repository、schema 或测试，也不绕过质量门禁。V2 卖点 service/answer 的 29 项定向回归全部通过。
