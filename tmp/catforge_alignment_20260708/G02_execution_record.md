# G02 执行记录：TV serving scope 设计与实现

时间：2026-07-08

## 本轮目标

让 `catforge_analyst --batch-id latest` 不再把 TV 错误压缩成单一 source batch，而是能按智能体消费口径读取 TV 当前多批次 serving 数据；同时保证 AC 继续只读 `category_code=AC` 的当前批次。

## 代码变更

- `apps/api-server/app/services/core3_real_data/analyst/analyst_repository.py`
  - 增加 `latest_serving_scope_batch_ids(product_category=...)`。
  - `latest_batch_id(product_category=...)` 优先返回 product-category scoped serving scope。
  - 单批次仍返回原 `batch_id`；多批次编码为 `serving-scope:{PRODUCT_CATEGORY}:{batch_id,...}`。
  - 仓储查询统一通过 `_batch_filter(...)` 展开 scope，单批使用 `=`，多批使用 `IN (...)`。
  - scope 发现时同时检查 M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D 当前结果，并按 `category_code` 与 SKU 前缀/product_category 隔离 TV/AC。
- `apps/api-server/app/services/core3_real_data/analyst/analyst_service.py`
  - `build_context()` 解析 `latest` 时传入 normalized `product_category`。
- `apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py`
  - 增加 TV 多批 latest 测试。
  - 增加多批重复 SKU 时新批次优先测试。
  - 增加 AC latest 隔离测试，覆盖历史 TV category 中存在 AC 前缀数据时 AC 不混读。

## 本地测试

工作目录：`/Users/sjs/catforge/apps/api-server`

```bash
python -m pytest tests/core3_real_data/test_catforge_analyst_cli.py -k "latest_uses_latest_analyst_ready_batch or latest_tv_serving_scope or latest_scope_prefers_newer_duplicate_batch_row or latest_ac_scope"
```

结果：`4 passed`

```bash
python -m pytest tests/core3_real_data/test_catforge_analyst_cli.py
```

结果：`80 passed`

## 205 只读校验

通过 205 API 容器内原始 SQL 校验当前真实数据，不使用容器旧 analyst 代码，不写数据库。

TV 当前 serving scope 批次：

1. `m00_20260623014631_c8630747`
2. `m00_20260619084551_857df63b`
3. `m00_20260613004311_d548f6dc`

TV 当前下游结果分布：

| 模块 | batch_id | SKU/summary 数 |
| --- | --- | ---: |
| M07 | `m00_20260613004311_d548f6dc` | 84 |
| M03B | `m00_20260619084551_857df63b` | 293 |
| M04C | `m00_20260619084551_857df63b` | 293 |
| M05C | `m00_20260619084551_857df63b` | 183 |
| M07 | `m00_20260619084551_857df63b` | 293 |
| M09C | `m00_20260619084551_857df63b` | 293 |
| M10C | `m00_20260619084551_857df63b` | 293 |
| M11C | `m00_20260619084551_857df63b` | 293 |
| M11D | `m00_20260619084551_857df63b` | 35 |
| M04C | `m00_20260623014631_c8630747` | 328 |

AC 当前 serving scope 批次：

1. `m00_20260624000202_1150a669`

AC 当前下游结果分布：

| 模块 | batch_id | SKU 数 |
| --- | --- | ---: |
| M03B | `m00_20260624000202_1150a669` | 155 |
| M04C | `m00_20260624000202_1150a669` | 155 |
| M05C | `m00_20260624000202_1150a669` | 144 |
| M07 | `m00_20260624000202_1150a669` | 155 |
| M09C | `m00_20260624000202_1150a669` | 155 |
| M10C | `m00_20260624000202_1150a669` | 155 |
| M11C | `m00_20260624000202_1150a669` | 155 |

## G02 验收

已通过：

- `catforge_analyst latest` 在 TV 多批次场景下形成显式 serving scope。
- 多批次中同一 SKU 存在重复行时，优先读取 serving scope 中靠前的新批次。
- 单批 AC 仍返回 `m00_20260624000202_1150a669`，不会混入历史 TV category 中的 AC 前缀数据。
- 单元测试覆盖 latest 解析、多批查询过滤、product category/category_code 隔离。

## 下一步

进入 G03：TV M03B/M04C/M07 对齐。重点是补齐 TV 当前规则 M03B 的 84 个老批次 SKU，并确认 M07 377 与 M04C 328 在 serving scope 下可读。
