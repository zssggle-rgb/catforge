# G06 执行记录：TV M11D/M12C 全量生成

时间：2026-07-08

## 本轮口径

本轮只处理 TV，不进入 AC 阶段；不重跑 M00-M02，不直接从 raw 表形成业务结论。

G06 目标是让 TV 当前智能体消费链路具备：

- M11D 语义市场图谱与销量分配。
- M12C 卖点价值量化与贡献归因。
- `catforge_analyst` 能按 `latest + product_category=tv` 读取。

## 代码修复

修改文件：

- `apps/api-server/app/services/core3_real_data/semantic_market_graph_service.py`
- `apps/api-server/app/services/core3_real_data/m12c_claim_value_quantification_service.py`
- `apps/api-server/tests/core3_real_data/test_m11d_semantic_market_graph_allocation.py`
- `apps/api-server/tests/core3_real_data/test_m12c_param_value_parsing.py`

关键修复：

1. M11D 读取 M05C 时按当前 market SKU scope 跨 current 评论批次读取，避免 6/23 评论增量被同 batch 过滤掉。
2. M12C 读取 M05C 时按 current serving 评论事实读取。
3. M12C 读取 M04C 时按当前 market SKU scope 跨 current 卖点批次读取，避免旧 TV market batch 因同 batch 没有 M04C 而被误判为无卖点。
4. M12C battlefield 上下文 fallback：
   - 仍要求 SKU 已进入 M11D contribution，避免把完全无图谱贡献的 SKU 混入。
   - 当 M11C profile `primary_battlefield_code` 为空时，使用 M11C score 中 `primary_battlefield` / `secondary_battlefield` / `opportunity_battlefield` 且 `market_gate_status != mismatch` 的战场上下文。
   - `opportunity_battlefield` 以 opportunity 低权重进入量化，不伪装成主价值战场。
5. M12C 写入增加字符串长度保护，避免异常参数结构写入 `claim_name` 造成 varchar 截断。
6. M12C 全量重跑时修正 stale current retire scope，避免旧 current 行残留。

本地验证：

```bash
python -m pytest apps/api-server/tests/core3_real_data/test_m11d_semantic_market_graph_allocation.py -q --tb=short
```

结果：6 passed。

```bash
python -m pytest apps/api-server/tests/core3_real_data/test_m12c_param_value_parsing.py -q --tb=short
```

结果：14 passed。

## 205 冒烟

热更新 API 容器：

```bash
docker cp /tmp/m12c_claim_value_quantification_service.py catforge-api-1:/app/app/services/core3_real_data/m12c_claim_value_quantification_service.py
```

import smoke：`m12c_score_fallback_hot_update_ok`。

事务回滚 smoke：

| 场景 | batch | SKU | 结果 |
| --- | --- | --- | --- |
| 旧批次跨批次 M04C 读取 | `m00_20260613004311_d548f6dc` | `TV00026886` | `input_count=1`，`comparable_sku_count=25`，rollback OK |
| 主批次 M11C score battlefield fallback | `m00_20260619084551_857df63b` | `TV00027354` | `input_count=1`，`comparable_sku_count=270`，`sku_claim_value_count=11`，rollback OK |

## 205 全量写入

M11D 已按两个 TV market batch 生成：

| batch | M11D graph SKU | allocation SKU | dimension summary | 说明 |
| --- | ---: | ---: | ---: | --- |
| `m00_20260613004311_d548f6dc` | 75 | 74 | 35 | 9 个无 M05C 评论 SKU 不进入业务图谱 |
| `m00_20260619084551_857df63b` | 273 | 270 | 35 | 20 个无 M05C 评论 SKU 不进入业务图谱 |
| 合计 | 348 | 344 | 35 | graph SKU 覆盖 348 comment-ready SKU |

M12C 全量生成命令：

```bash
python -m app.cli.catforge_pipeline run-claim-value-quantification \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id m00_20260613004311_d548f6dc \
  --product-category tv \
  --analysis-population claim_value_ready_with_comment \
  --market-window full_observed_window \
  --format json
```

旧批次结果：

- `input_count=25`
- `comparable_sku_count=25`
- current quantification SKU：23
- `sku_claim_value_count=392`
- `sku_attribution_count=128`
- `review_issue_count=582`

```bash
python -m app.cli.catforge_pipeline run-claim-value-quantification \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id m00_20260619084551_857df63b \
  --product-category tv \
  --analysis-population claim_value_ready_with_comment \
  --market-window full_observed_window \
  --format json
```

主批次结果：

- `input_count=270`
- `comparable_sku_count=270`
- current quantification SKU：266
- `sku_claim_value_count=11992`
- `sku_attribution_count=3079`
- `review_issue_count=1885`
- 用户关注的 11 个 `primary_battlefield_code` 为空 SKU 已全部有 M12C current 行。

## 最终覆盖

| 指标 | 结果 |
| --- | ---: |
| TV M11D graph SKU | 348 |
| TV M11D allocation SKU | 344 |
| TV M12C comparable SKU | 295 |
| TV M12C current quantification SKU | 289 |
| TV M12C current quantification rows | 12384 |

M12C 还有 6 个 comparable SKU 没有形成量化行：

- 旧批次：`TV00026886`、`TV00027442`
- 主批次：`TV00027774`、`TV00028200`、`TV00028472`、`TV00029167`

这 6 个不是上游读取缺失；它们有市场、评论、M04C、语义上下文，但当前 M12C 角色/可比池规则没有形成可量化 claim row，保留为 M12C 规则解释缺口。

## Analyst 验收

`catforge_analyst` 按 `latest + product_category=tv` 验收：

| 能力 | 结果 |
| --- | --- |
| `battlefield-space` | `status=ok`，`summary_count=1`，`items=1` |
| `sku-claim-value --sku-code TV00027354` | `status=ok`，`sku_level_claim_values=9`，`claim_values=3`，`attributions=2` |
| `claim-contribution --sku-code TV00027354` | `status=ok`，`attribution_count=2` |

结束时 205 API 容器无 `catforge_pipeline` / `run-claim-value-quantification` / `run-semantic-market-graph` 残留进程。

## 结论

G06 已完成。TV 当前 M11D 覆盖 348 个 comment-ready SKU；M12C 当前可消费量化 SKU 为 289，用户关注的 11 个 M11C profile primary 为空 SKU 已通过 M11C score fallback 纳入 M12C。下一子任务按计划进入 G07：AC M05C 尾差审计。
