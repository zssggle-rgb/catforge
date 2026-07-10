# AC 匹数价格池 v0.2 全链路执行与验收

## 1. 执行范围

- 目标：将 AC 市场池改为“安装形态/匹数段 × 价格带”，3匹与3匹以上柜机统一为 `floor_hp_3`。
- 链路：M07 -> M09C/M10C/M11C -> M11D -> M12C -> M12D -> 竞品智能体。
- 边界：未重跑 TV，未重跑 M03B/M04C/M05C，未在竞品智能体中生成 M12D，未发布飞书文档。
- 205 批次：`m00_20260624000202_1150a669`，AC SKU 155 个。

## 2. 版本

| 模块 | 本次版本 |
| --- | --- |
| M07 主画像 | `m07_market_profile_v1` |
| M07 AC 价格带 | `m07_ac_hp_price_band_v2` |
| M07 AC 市场池 | `m07_ac_hp_price_pool_v2` |
| M09C | `m09c_ac_user_task_profile_v0.2` |
| M10C | `m10c_ac_target_group_profile_v0.2` |
| M11C | `m11c_ac_value_battlefield_profile_v0.2` |
| M11D | `m11d_semantic_market_allocation_v0.1`，算法未改，强制重算 |
| M12C | `m12c_claim_value_quantification_v0.1`，算法未改，全量重算 |
| M12D profile | `m12d_ac_purchase_reason_profile_v0_2` |

TV 继续使用 `m07_price_band_v1 / m07_pool_v1`，本次 AC 版本升级不要求 TV 跟随重跑。

## 3. 执行结果

| 模块 | 结果 |
| --- | --- |
| M07 | 775 个画像（155 SKU × 5 窗口），全部使用 AC v2 价格带规则 |
| M09C | 144 个 v0.2 用户任务画像；11 个缺 M05C 的 SKU 按规则排除 |
| M10C | 144 个 v0.2 目标客群画像；11 个缺 M05C 的 SKU 按规则排除 |
| M11C | 144 个 v0.2 价值战场画像；11 个缺 M05C 的 SKU 按规则排除 |
| M11D | 66 个维度汇总，2994 条 allocation，2994 条 contribution |
| M12C | 884 个可比池，6345 条 SKU×卖点量化，2497 条 SKU 归因，508 条维度汇总 |
| M12D | 155 个 profile，1879 个 anchor，0 失败；v0.2 已发布为 AC current |

M12D 仍属于降级发布：135 个 SKU 低置信，135 个 SKU 缺核心成交理由，155 个 SKU 均需复核。下游必须使用 `published_degraded / degraded_pair_scoring`，不得输出无条件强替代结论。

## 4. M07 市场池验收

| SKU | 市场池 | 同池 SKU 数 | 价格分位 |
| --- | --- | ---: | ---: |
| 美的 `AC00038063` | 3匹及以上柜机 × 高价带 | 8 | 97.37% |
| 格力 `AC00030362` | 3匹及以上柜机 × 高价带 | 8 | 86.84% |
| 格力 `AC00030929` | 3匹及以上柜机 × 中高价带 | 8 | 73.68% |

- 新结果不再生成 `floor_hp_3_plus`。
- `floor_hp_3` 五个价格带各有 7-8 个 SKU。
- `wall_hp_1_5` 五个价格带各有 15-16 个 SKU，不再使用 77 个 SKU 的单一大池。

## 5. 竞品智能体验收

目标 SKU：美的 `AC00038063 / KFR-88LW/N8KS1-1U`。

| 排名 | 竞品 | 购买池关系 |
| --- | --- | --- |
| 1 | 格力 `AC00030362 / KFR-72LW/(72527)FNHAB-B1` | 3匹及以上柜机 × 高价带，与本品同池 |
| 2 | 格力 `AC00030929 / KFR-72LW/(72587)FNHAD-B1` | 3匹及以上柜机 × 中高价带，与本品邻价带不同池 |
| 3 | 格力 `AC00037563 / KFR-72LW/NHMA1BG` | 3匹及以上柜机 × 高价带，与本品同池 |

报告已消费 `m12d_ac_purchase_reason_profile_v0_2`。本品 M12D 状态为 `published_degraded`、置信度 0.30，因此锚点与替代压力输出为待复核，没有生成无依据的强结论。

报告消费修复后，主战场不再显示“本轮未计算/未分配”：3匹及以上柜机高端舒适健康战场空间 146,074 台、周均 6,086 台、覆盖 11 个 SKU；本品分配 8,862 台、周均 369 台、权重 64%。

## 6. 测试与产物

- 版本、M07、M09C、M10C、M11C、M12D 集中回归：65 passed。
- M11D、竞品 CLI、飞书报告渲染回归：107 passed。
- AC M11D 报告消费修复后 `test_catforge_analyst_cli.py`：83 passed。
- `compileall`、`git diff --check`：通过。

产物：

- [AC00038063 竞品分析报告](ac_market_pool_v02/AC00038063_competitor_report_v02.md)
- [M12D v0.2 小批量验证](ac_market_pool_v02/M12D_AC_V02_small_batch_validation_report.md)
- [M12D v0.2 全量生成](ac_market_pool_v02/M12D_AC_V02_full_batch_generation_report.md)
- [M12D v0.2 发布契约](ac_market_pool_v02/M12D_AC_V02_published_contract_report.md)

本次未 stage、未 commit。
