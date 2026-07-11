# G08R1 工程质量复审

## 结论

`PASS`。G08 的 B01-B08 均有实现和回归证据，未发现新的 SQL write、外部 LLM、路由泄漏、旧金额消费或非确定性结果路径。

## 阻断项关闭矩阵

| G08 blocker | 修复证据 | 回归证据 |
| --- | --- | --- |
| B01 Q5 无 bootstrap/保守区间 | config v2、week-cluster bootstrap、joint gate、weighted median、interval components | stable/unstable/v1 reject tests |
| B02 同版本 hash 漂移漏过 | same-version hash compare，missing/unmatched 分流 | same version + different hash test |
| B03 M11D weight 未进入样本 | conservative battlefield sample weight，不改 sales/share | allocation complete/missing test |
| B04 候选总计过早截 3 | recall 30、snapshot 12、per computed role 3 | rank-4 role coverage/per-role cap tests |
| B05 weekly 静默前缀裁剪 | DB limit 2001、完整 group trim、M07 warning、Q5 blocked | 2001 rows/truncation test |
| B06 hash 受 list 顺序影响 | evidence refs canonical sort | reversed authority refs same hash test |
| B07 frozen cohort 假回放 | 新增 G01 artifact SHA + actual payload replay | C01-C05 dedicated tests |
| B08 pure negative 误写 mixed | ValueStatus negative/mixed，lineage 独立 | negative/mixed/data conflict renderer tests |

## 回归和质量

| 验证 | 结果 |
| --- | --- |
| V4 + V2 service/answer | 122 passed |
| analyst CLI | 88 passed |
| M11C/M11D/M12C | 43 passed |
| M12D + competitor reader | 71 passed |
| 合计 | 324 passed |
| V4 tests | 92 passed |
| V4 schema/service/answer coverage | 93% |
| py_compile | passed |
| V4 新增/修改文件 Ruff | passed |
| G01-G08 historical artifact hash | 35/35 matched |
| diff check | passed |

## 性能

| 指标 | 实测 | 门槛 |
| --- | --- | --- |
| 10,000 rows 构造 | 0.282463s | 记录项 |
| 10,000 rows peak memory | 25.413MB | <256MB |
| Q5 config v2 report P95 | 0.016519s | <1s local |
| 65E7Q-like report P95 | 0.000490s | <1s |
| Markdown P95 | 0.000076s | <0.5s |
| SQL query count | 单/多候选固定且 <=20 | <=20 |

## 边界扫描

- V4 service/schema/answer 无 INSERT/UPDATE/DELETE/commit/flush；
- `SessionLocal(autoflush=False)` 下 pending entity 在 V4 查询后仍 unflushed；
- 无外部 LLM 或网络调用；
- 无 `estimated_price_premium_abs` 等 M12C 旧金额路径；
- `causal_claim` 和 `psychological_max_price` 只能为 false；
- CLI 与 SOP 双层默认关闭，自然语言路由仍不选择 V4；
- 当前工作区无关 M12D 修改未被纳入任何 G08R1 提交。

## 已知非本任务基线

`analyst_repository.py` 全文件仍有 V4 之前的 7 个 Ruff 问题，均由旧提交 `79343371` 引入；本次修改文件的定向 Ruff、py_compile 和回归均通过，未扩大该基线。

## 工程准入

`PASS for G09 shadow validation`。本复审不等于已部署或已验证 205；G09 仍需不可变 RC、回滚包、health/ready、真实回放和 V2 线上回归。
