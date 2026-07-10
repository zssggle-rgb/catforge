# AC-CA-G01 竞品智能体 AC M12D 消费验收

## 1. 验收范围

- 验收时间：2026-07-08。
- 目标任务：验证竞品智能体在 AC M12D-G09 发布后，只消费已发布 AC M12D 成交理由画像，不生成 M12D，不修改 AC 锚点角色。
- 验收目标 SKU：`AC00032338`，格力 `KFR-35GW/(35551)FNHAA-B1`。
- 项目/品类/批次：`d8d2245b-358b-4a64-95cc-9d7f2341bd26` / `AC` / `m00_20260624000202_1150a669`。
- M12D 版本：`m12d_ac_purchase_reason_profile_v0_1_draft`，来自 G09 published current 合约。

## 2. 实现变更

- `competitor-set` SOP 增加 M12D 只读消费：通过 `RepositoryPurchaseReasonProfileReader` 读取 published current 合约，再调用既有 `ValueAnchorMatcher` 与 `ReplacementPressureClassifier` 计算 pair 级关键价值锚点可替代性和替代压力。
- 目标 SKU 没有 published M12D 时，只记录降级和 limitation，不覆盖旧有事实维度评分，避免旧报告排序被全量 blocked。
- 目标 SKU 有 published M12D、候选 SKU 缺失/不可用时，该候选的锚点维度明确 blocked，不使用 TV fixture 或参数卖点 fallback 冒充成交理由。
- `to_legacy_value_anchor()` 补充 `pair_scoring_allowed` 和 `gate_reasons`，报告层可以展示降级原因。
- 报告层修正空列表 fallback：M12D 明确输出 `shared_anchors=[]` 时不再回退到旧参数/卖点重合结果。

## 3. 真实验收结果

产物：

- 竞品报告 Markdown：`docs/core3_mvp/real_data_v2/current_implementation/AC_CA_G01_competitor_set_AC00032338_20260708.md`
- 竞品验收摘要 JSON：`docs/core3_mvp/real_data_v2/current_implementation/AC_CA_G01_competitor_set_AC00032338_20260708_summary.json`

运行结果：

- `competitor-set` 返回 `status=ok`。
- M12D 消费状态：`consumed_with_review`。
- 目标 M12D 合约：`found=true`，`category_code=AC`，`consumption_state=published_degraded`，`downstream_action=degraded_pair_scoring`，`profile_confidence=0.5`。
- 候选读取：8/8 个候选读取到 AC M12D 合约，8/8 个竞品对触发复核门控。
- 复核原因来自 G09 质量口径：`review_required`、`profile_status_ready_degraded`、`low_profile_confidence`、`core_payment_missing`、`risk_drag_anchor_present`、`missing_or_partial_inputs` 等。

Top 3 验收摘要：

| 排名 | 竞品 SKU | 竞品 | 锚点分 | 锚点等级 | 替代压力分 | 替代压力 | 结论语义 |
| ---: | --- | --- | ---: | --- | ---: | --- | --- |
| 1 | `AC00034717` | 格力 `KFR-35GW/NHAE1BAT` | 0/15 | blocked | 3/10 | 低替代压力复核 | 保留价格贴身/事实维度判断，但不得输出强锚点替代 |
| 2 | `AC00039564` | 格力 `KFR-35GW/NHMB1BAJ` | 11/15 | medium | 5/10 | 场景心智压力 | 可说明锚点有中等替代，但必须带复核语义 |
| 3 | `AC00038399` | 格力 `KFR-35GW/NHMB1BG` | 0/15 | blocked | 3/10 | 低替代压力复核 | 保留价格贴身/事实维度判断，但不得输出强锚点替代 |

可验证的 AC 购买理由锚点示例：

- `AC00039564` 与目标共同覆盖：匹数空间匹配降低买小风险、大空间冷暖一步到位、冷暖效果解释更高价格、长期省电抵消更高价格、同价位能效/能力获得感、低价不明显牺牲核心冷暖体验、小房间/租房安装适配、远程/智能控制减少操作摩擦。
- 报告未使用 TV 锚点或 TV 话术作为 AC M12D fallback；`MiniLED`、影院沉浸观影等 TV 语义不进入本次验收结论。

## 4. 测试结果

- `apps/api-server/.venv/bin/pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py -q`：82 passed。
- `apps/api-server/.venv/bin/pytest apps/api-server/tests/core3_real_data/test_competitor_purchase_reason_profile_reader.py apps/api-server/tests/core3_real_data/test_competitor_anchor_substitutability.py apps/api-server/tests/core3_real_data/test_competitor_replacement_pressure.py apps/api-server/tests/core3_real_data/test_competitor_answer_gates.py -q`：19 passed。
- 真实 205 验收命令：
  - `python -m app.cli.catforge_analyst competitor-set --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code AC --batch-id m00_20260624000202_1150a669 --product-category ac --sku-code AC00032338 --limit 8 --top-n 3 --answer-style xiaoao --with-report markdown --format json`

## 5. 边界与剩余风险

- 本任务没有调用或引入 `PurchaseReasonProfileBatchGenerator`，没有在竞品智能体内生成 M12D。
- 本任务没有修改 M12D 生产逻辑和 AC 锚点角色。
- 当前 AC G09 发布版本整体为 degraded，业务报告必须展示复核/降级原因；如果要输出强替代结论，需要后续单独提升 AC M12D 画像质量，而不是在竞品智能体内临时修正。
- AC-CA-G01 已完成后，本 AC M12D 调度链暂无下一个 pending 任务。
