# V5-G08 真数验收后的需求与详细设计修订

## 1. 修订原因

G08 在 205 真数和飞书真实页面中发现，本地 fixture 未覆盖四类问题：完整反事实证据使 JSON 膨胀、阻断报告仍召回亮点、非 battlefield 语义维度进入战场表、同一战场与用户价值组合重复成行。以下修订已经进入最终 RC。

## 2. 产品需求修订

1. `analysis_state=blocked` 时亮点必须为空，并用业务语言说明阻断来源；不得保留“仅用户兑现”或“仅市场承接”亮点。
2. 用户价值账的唯一行键是“价值战场 × 规范化能力组合”，不同采购理由映射到相同组合时合并，不按采购理由重复列行。
3. 战场全集固定使用 13 个 TV battlefield taxonomy；task、target group 和其他语义维度不能进入战场组合。
4. 全部 excluded 战场都进入资格判断；产品经理主表只展示 eligible、recalled 和 deferred unknown，明确 rejected 留在 DTO 审计，避免无效长表。
5. 完整 evidence ID 不进入 PM DTO。PM DTO 保存集合 hash、结果 hash 和受控候选摘要；详细 evidence 通过“查看分析依据”下钻。
6. 只允许加载 3 个完整候选证据快照；这是内存门禁，不等于市场只有 3 个候选。更宽市场池只可作为召回事实，不能绕过弱价值档位和共同市场门槛生成合成差异。

## 3. 工程设计修订

- `report_ref` 代替 answer 内重复整份 report；顶层 result 保留唯一完整报告；
- CounterfactualCandidate、SellpointBundle 和 ValueAccountRow 在 PM DTO 中清空重复 source refs，审计保留 hash；
- `_is_battlefield_semantic` 同时要求 `dimension_type=battlefield` 与 `BF_` 编码；
- `_dedupe_value_account_rows` 以 battlefield code 和 capability code 集合去重；
- TV adapter 从冻结 taxonomy 初始化 13 个战场，不依赖候选快照是否恰好覆盖；
- renderer 不展示 `ExpansionStage=rejected`，但 report DTO 保留完整 13 战场判断；
- `V5_FALLBACK_SNAPSHOT_LIMIT=3`，205 单次 tracemalloc 峰值 75.429 MB；
- 默认关闭仍在 CLI 建立数据库会话之前和 orchestrator 加载上下文之前执行。

## 4. 真实数据结论边界

当前 18 个冻结 SKU 全部存在发布线谱冲突，因此本轮亮点数、严格组合金额、观察性合成销量差、净新增和 eligible 新战场均为 0。这不是功能失败，而是最终功能正确回答了“当前证据不能支持什么”。在 M03B/M04C/M05C/M07/M11D 与发布画像重新对齐、弱价值档位可识别之前，V5 必须保持显式调用和默认关闭。
