# G04 采购理由、用户实际价值与卖点组合进度

- Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`
- Goal 状态：`completed`
- 定时器：`catforge-v4-g04-10`
- 前置 G03 artifact commit：`b903c2a`
- 前置 G03 closure commit：`7f8baf5`
- 允许修改：V4 schemas、`claim_value_pm_v4_service.py`、G04 tests/fixture/回执
- 禁止事项：repository/DB 写入、反事实、选择贡献、WTP、PM renderer、CLI/路由、205

## 当前门禁

| 门禁 | 状态 |
| --- | --- |
| 复核 M12D 标准采购理由/价值主题 taxonomy | completed |
| 复核 V2 直接/场景/泛化/负向评论归因模式 | completed |
| G02 Bundle/Link typed contracts 精确对齐 | completed |
| reason -> realized value 标准映射 | completed |
| realized value -> capability bundle | completed |
| 直接用户证据与系统推导证据分离 | completed |
| 同句去重、同源同参合并、共线组合 | completed |
| value/link/fact/independent 状态机 | completed |
| 65E7Q/缺失/冲突 fixture tests | completed |
| V2 回归与边界扫描 | completed |

## 硬边界

1. M12D 是已发布采购理由假设，不改写成用户购买前明确表达；
2. M05C 只回答购买后实际体验，不补写传播心智或预期；
3. “画质很好”只支持画质组合，不能分别证明亮度、分区、MiniLED 和芯片；
4. “系统流畅”不能证明 AI 画质；
5. 评论数量不生成价值金额或卖点权重；
6. 无用户体验时 capability 可 confirmed，但 value_status 必须保持 not_observed；
7. G04 输出不是配置、定价或工作清单。

## 实现结果

1. 新增 `BundleMember`、`SellpointBundle`、`ReasonValueBundleLink`，字段和 required 集合与 G02 frozen contract 精确一致；
2. 直接复用 M12D TV 标准采购理由和价值主题 taxonomy，不新造采购理由；
3. 直接复用 V2 `TV_VALUE_UNITS` 与评论归因函数，不复制直接/场景/泛化/负向正则；
4. 补充大屏沉浸与空间审美两个 V4 value unit，只用于填补 V2 registry 未覆盖的已发布 TV taxonomy；
5. 主键固定为 `battlefield_code + purchase_reason_code`，多价值主题在同一采购理由内合并，不产生重复主表行；
6. M12D `weak_expression` 不提升为 G04 relation；
7. 产品事实 `fact_status`、用户结果 `user_result_support`、价值 `value_status` 和关系 `link_status` 分开保存；
8. 同一句评论按 V2 source key/sequence 去重，relation source refs 再次稳定去重；
9. 多成员组合标记 collinearity group，G04 一律不声明成员可独立量化；
10. 一个主题只观察到部分子体验时为 `partial`，全部相关子体验观察到才为 `established`；
11. 无评论时 capability 可 confirmed，但 value_status 为 `not_observed`；
12. M03B/M04C/M05C 版本冲突只阻断 relation，不抹掉已经观察到的用户体验状态。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| G04 linkage tests | 12 passed |
| G03 + G04 + V2 sellpoint 定向回归 | 59 passed |
| G04 service coverage | 96% |
| G04 runtime schema vs G02 contract | exact match |
| Ruff | passed |
| py_compile | passed |
| 65E7Q published anchor replay | weak anchors excluded；无 M05C fixture 时全部 not_observed；未发明用户价值 |
| forbidden output scan | 无 WTP、价格建议、反事实或工作清单逻辑 |

## 已知边界

- G01 的脱敏 65E7Q fixture 未冻结原始 M05C comment atoms，因此固定回放只能验证“不发明购后价值”；真实评论结果留待 G09 205 影子回放；
- business tier 只读取当前 context 已有确定性档位，无法识别时保持 `unknown`；
- G04 只标记组合共线和独立资格，不做跨 SKU 共线统计，后者属于 G05。

## 下一步

G04 已完成，允许进入 G05。G05 只构建 base-value、same-value、stretch 三类候选和可比性/隔离等级，不计算 WTP。
