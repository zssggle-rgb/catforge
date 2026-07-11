# G08 工程质量独立评审

## 结论

`FAIL with verified blockers`。类型合同、默认关闭、只读查询路径、旧金额隔离、V2 回归、性能和覆盖率均达到已测门槛；但存在两个 P1 和五个 P2 的已验证问题，不能形成 RC。

## 审查范围

- 提交范围：`b903c2a^..095016d`，31 个文件，8,225 insertions / 1 deletion；
- 不包含当前工作区未提交的 M12D 质量修复和资料文件；
- 对照：G02 schema contract、详细设计、测试计划和需求追溯；
- 独立对抗审查：Codex read-only；结构化 pass 5 分钟超时，对抗 pass 返回 8 个候选问题，逐项由主审回读验证。

## 已验证问题

| ID | 级别 | 问题 | 影响 |
| --- | --- | --- | --- |
| E01 | P1 | 同版本/同批次 hash 改变被 lineage gate 当作 aligned | 可能在不同于已发布 M12D 的事实版本上继续输出 Q5 |
| E02 | P1 | Q5 缺少 cluster bootstrap、质量加权中心和联合保守区间 | “严格市场隐含支付区间”不满足冻结方法合同 |
| E03 | P2 | 候选在比较前总计截为 3，而不是 recall 30 / snapshot 12 / per-role 3 | 漏掉第二 base pair 或第二 model family，产生排名选择偏差 |
| E04 | P2 | M11D battlefield weight 读取后未用于样本权重 | 战场曲线实际按整机销量而非战场样本口径加权 |
| E05 | P2 | 先加载全部 weekly rows，再静默取全局排序前 2,000 行 | 可能截断周或候选、丢失后期覆盖、内存无 DB 侧上限且无降级说明 |
| E06 | P2 | configured profile query 无稳定排序，authority hash 对 list 顺序敏感 | 相同数据库内容可能产生不同 input/result hash |
| E07 | P2 | G01 五 cohort 测试没有按 frozen input manifest/hash 回放 | fixture 漂移或 C03 未执行时测试仍可通过 |
| E08 | P2 | 纯负向体验在状态机和 PM 文案中被写成“正反并存” | 产品经理得到错误的用户价值状态 |
| E09 | P3 | schema/service 顶部说明仍写 G05 不计算 choice/WTP | 与 G06/G07 实际职责矛盾，误导维护者 |

## 独立审查候选中的不成立项

- “普通 SQLAlchemy Session 会 autoflush pending write”：CatForge 运行入口使用的 `SessionLocal` 在 `app/core/database.py` 明确 `autoflush=False`；实测 pending entity 调用 V4 未出现 INSERT。因此不作为当前生产缺陷。
- 仍保留防御建议：若未来允许外部传入任意 `Session`，可增加只读 session/transaction contract，但不应把它冒充为当前已发生的写库问题。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| G03-G07 manifest hash | 23/23 matched at each artifact commit |
| V4 tests | 77 passed |
| V4 + V2 service/answer | 107 passed |
| analyst CLI | 88 passed |
| M11C/M11D/M12C/M12D | 108 passed |
| competitor purchase-reason reader | 6 passed |
| 合计已运行 | 309 passed |
| V4 schema/service/answer coverage | 93% |
| V4 新增/修改文件（不含旧 repository 基线）Ruff | passed |
| py_compile | passed |
| SQL query count | 单/多候选相同且 <= 20 |
| 10,000 synthetic rows | 0.283883s；peak 25.413MB < 256MB |
| 65E7Q-like local report P95 | 0.000325s < 1s |
| Markdown render P95 | 0.000060s < 0.5s |

## 基线隔离

全文件 Ruff 在 `analyst_repository.py` 报 7 项旧问题：一个未使用变量和六个缺失 `Mapping` import。`git blame` 均指向 V4 之前的 `79343371`，不属于本提交范围；V4 专属文件和本次修改入口单独 Ruff 全通过。本评审不吸收或修复这些旧问题。

## 工程准入决定

`G09 not allowed`。E01-E08 必须在独立修复 Goal 中修复并新增回归；E09 同步机械修正。修复后重新跑 309 项相关回归、覆盖率、性能、manifest/hash 和独立审查。
