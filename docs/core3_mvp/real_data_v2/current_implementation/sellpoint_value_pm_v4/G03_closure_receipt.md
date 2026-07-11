# G03 关闭回执：V4 只读 context 与权威版本闸门

## Objective

实现用户卖点价值分析 V4 的目标解析复用、只读上游 context adapters、configured authority manifest、published/current 双时间 lineage gate、typed schemas、source/evidence refs、deterministic hash、缺失/冲突/多 current 降级和批量查询预算；不生成用户价值、反事实、选择贡献或 WTP，不修改数据库或 205，不启用路由。

## 前置输入

- G02 核心设计 commit：`f62b68f`；
- G02 closure commit：`261457e`；
- G03 Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`；
- G03 timer：`catforge-v4-g03-10`。

## 实际产物

- `claim_value_pm_v4_schemas.py`；
- `AnalystRepository.sellpoint_value_v4_context()` 及 G03 只读批量适配器；
- `test_claim_value_pm_v4_schemas.py`；
- `test_claim_value_pm_v4_context.py`；
- `G03_progress.md`；
- 本关闭回执；
- `G03_artifact_manifest.json`。

未修改数据库 schema、迁移、205 文件、上游 runner、V2 路由、自然语言路由或飞书发布。

## 关键实现

1. 复用现有 `resolve_sku()` 支持 SKU 与唯一型号入口；
2. M03B/M04C/M05C/M07/M09C/M10C/M11C 使用 configured rule 和 taxonomy 批量读取；
3. M11D allocation/summary、M12C quant/pool、M05C atoms 和 M07 weekly rows 使用集合查询，不逐候选读取；
4. published M12D 只走 frozen downstream reader，不调用 runner；
5. M14 无当前合格结果时只接受显式 fallback，并保留 `competitor_set_fallback`；
6. serving scope 按顺序择优，同一优先批次多 current 不自动择一；
7. source authority、published/current lineage、局部 issue 和 blocked reason 分开保存；
8. M12C 仅选择 pool/tier/evidence 字段，旧价差和贡献金额列不进入 context；
9. inventory 明确 `unavailable`，promotion 仅为 suspect flag；
10. target/candidate snapshot 与 input hash 均确定性生成。

## 合同门禁

运行时 10 个 G03 model 的字段集合和 required 集合均与 `G02_schema_contract.json` 自动比对一致。候选来源写在 `SkuEvidenceSnapshot.facts.candidate_source`，没有擅自增加顶层 wrapper。

## 测试结果

| 验证 | 结果 |
| --- | --- |
| G03 schema/context | 18 passed |
| G03 + V2 sellpoint service/answer | 47 passed |
| G03 schema coverage | 96% |
| G02 runtime contract exact diff | passed |
| Ruff | passed |
| py_compile | passed |
| `git diff --check` | passed |
| SQL write verbs | 0 |
| query budget | 单候选/三候选相同，均 <=20 |
| 65E7Q frozen lineage replay | stale conflict |

## 已知非本任务基线失败

工作区其他未提交任务在 `purchase_reason_profile_repositories.py` 增加了 M12D 发布质量门禁，但两个旧测试 fixture 仍以 `release_quality_status=unassessed` 发布，因此：

- `test_repository_reader_only_reads_published_m12d` 失败；
- `test_ac_competitor_set_consumes_published_m12d_without_tv_fallback` 失败。

G03 未修改或绕过这些文件。失败堆栈均终止于 `M12DReleaseQualityNotPublishableError`，与 V4 context 无调用关系。

## Commit

- G03 核心实现：`b903c2a`；
- 本关闭回执、manifest 和完成状态：本文件所在的独立 closure commit。

## 下一 Goal 准入

`G04 allowed`。G04 只允许实现采购理由 -> 用户实际价值 -> 卖点组合关系、证据去重和值状态；不得提前构建反事实、选择贡献或 WTP。
