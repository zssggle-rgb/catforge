# G05 卖点级反事实与可比性门禁进度

- Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`
- Goal 状态：`completed`
- 定时器：`catforge-v4-g05-10`
- 前置 G04 artifact commit：`7cc39fa`
- 前置 G04 closure commit：`4132077`
- 允许修改：V4 schemas/service、G05 tests/fixture/回执
- 禁止事项：repository/DB 写入、选择曲线、价格承接、WTP、renderer、CLI/路由、205

## 当前门禁

| 门禁 | 状态 |
| --- | --- |
| 复核 G01 五 cohort 和 65E7Q 候选 | completed |
| 复核现有 M14/V2 配置比较模式 | completed |
| ComparabilityAssessment 合同对齐 | completed |
| base/same/stretch 角色判定 | completed |
| M14/fallback/M12C/same-family provenance | completed |
| 战场×尺寸×周×平台共同单元 | completed |
| 价格重叠、促销疑似、库存 unavailable | completed |
| 其他 bundle 差异与 A/B/C/unusable | completed |
| full collinearity 合并 | completed |
| G01 fixture 与回归测试 | completed |

## 硬边界

1. same-value 只回答选择反事实，不证明卖点增量价值；
2. base-value 才能作为价值增量候选，但候选资格不等于 WTP 可识别；
3. stretch 只作上探事实观察；
4. M12C 只提供 pool/tier 候选线索，任何旧金额不得参与召回、评分或分级；
5. promotion 只有 suspect flag，inventory 固定 unavailable；
6. 单一差异很大的 pair、无共同周、无价格重叠或关键 unknown 不进入高等级；
7. G05 不计算选择份额、价格弹性、价格承接或 WTP。

## 实现结果

1. `ComparabilityAssessment` 与 G02 frozen contract 的字段和 required 集合精确一致；
2. 候选角色由已观察价值档位优先判定，M14/fallback/M12C/family 的 slot 只作召回声明；slot 与档位冲突时按事实角色输出并降为 C；
3. 市场共同单元固定为相同价值战场、相同尺寸前提下的 `周 × 平台`，异常价格状态、负销量和非正价格不进入共同单元；
4. 价格只判断共同单元观测区间是否重叠，不计算选择曲线、价格承接或金额；
5. A/B/C/unusable 同时检查战场、卖点事实覆盖、共同单元、价格重叠、其他 bundle 差异/unknown 和促销清洁单元；
6. inventory 固定为 `unavailable`，没有声称已控制库存；
7. base-value A 级候选最多获得“可进入 G06 Q5 总门禁”的 pair 资格，不代表已经得到 WTP；
8. same-value 明确标记 `same_value_only`，封顶 Q3/Q4；stretch 明确标记 `stretch_benchmark_only`，只保留 Q2 相对体验资格；
9. 多成员共线卖点继续沿用 G04 bundle，一条候选只生成一条 bundle assessment，不拆单项 WTP；
10. G01 五 cohort 和 65E7Q fixture 已回放；G01 未包含逐周市场 cell 时保持 unusable，不补造市场数字；
11. 未读取 M12C 旧金额，未新增 repository/DB/CLI/router/renderer，未连接 205。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| G05 counterfactual tests | 11 passed |
| G03 + G04 + G05 + V2 定向回归 | 55 passed |
| G04 + G05 service coverage | 91% |
| G05 runtime schema vs G02 contract | exact match |
| Ruff | passed |
| py_compile | passed |
| `git diff --check` | passed |
| G01 cohort replay | C01-C05 stop boundary 全部通过 |
| 65E7Q fixture replay | 三角色和 fallback provenance 保留；无逐周 cell 时不冒充可量化 |
| forbidden source scan | 无 M12C 旧金额、same-price choice、selection gap 或 PAVA |

## 下一步

G05 已完成，允许进入 G06。G06 才计算相对体验、市场选择关联、整机价格承接，并在“两条独立 A 级 base pair、跨两个 model family”等全部门禁通过时计算 matched equal-choice WTP；否则金额必须为 null。
