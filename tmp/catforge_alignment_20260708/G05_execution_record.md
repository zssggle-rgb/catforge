# G05 执行记录：TV M09C/M10C/M11C 对齐

时间：2026-07-08

## 本轮口径

本轮不重跑 M00-M02，不删除历史 source batch，不物理合并 TV 多 batch。TV serving market/param scope 仍为 377 SKU，但 M09C/M10C/M11C 只对有当前 M05C 评论事实画像的 SKU 生成语义画像。

无 M05C 评论事实画像的 SKU 处理为：

- 不生成用户任务、目标客群、价值战场画像。
- 如旧结果存在，取消 current。
- 在模块 summary 中记录 `comment_missing_exclusion_reason=missing_m05c_comment_fact_profile_semantic_ineligible`。

## 代码与本地验证

修改文件：

- `apps/api-server/app/services/core3_real_data/m09c_user_task_service.py`
- `apps/api-server/app/services/core3_real_data/m10c_target_group_service.py`
- `apps/api-server/app/services/core3_real_data/m11c_value_battlefield_service.py`
- `apps/api-server/tests/core3_real_data/test_m09c_user_task_profile.py`
- `apps/api-server/tests/core3_real_data/test_m10c_target_group_profile.py`
- `apps/api-server/tests/core3_real_data/test_m11c_value_battlefield_profile.py`

本地验证：

```bash
python -m pytest \
  apps/api-server/tests/core3_real_data/test_m09c_user_task_profile.py \
  apps/api-server/tests/core3_real_data/test_m10c_target_group_profile.py \
  apps/api-server/tests/core3_real_data/test_m11c_value_battlefield_profile.py \
  -q --tb=short
```

结果：17 passed。

```bash
python -m pytest apps/api-server/tests/core3_real_data/test_catforge_analyst_cli.py \
  -q --tb=short -k "latest or serving_scope or scope"
```

结果：4 passed。

## 205 执行前只读检查

205 API 容器：`catforge-api-1`，import smoke 通过。

执行前确认无残留进程：

```bash
ps -eo pid,etime,cmd | egrep 'catforge_pipeline|run-user-task|run-target-group|run-value-battlefield|run-value-battlefield-graph' | grep -v egrep
```

无输出。

执行前 TV 覆盖：

| market batch | M03B SKU | same-batch M05C | any-current M05C | only-other-batch M05C | missing M05C |
| --- | ---: | ---: | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 84 | 75 | 75 | 0 | 9 |
| `m00_20260619084551_857df63b` | 293 | 183 | 273 | 90 | 20 |

执行前 M09C/M10C/M11C current 均为 377，包含了 29 个无评论 SKU，需要重跑取消 current。

## 205 小范围冒烟

跨批次评论 SKU：

- SKU：`TV00026064`
- 市场 batch：`m00_20260619084551_857df63b`
- 评论来源：`m00_20260623014631_c8630747`

命令：

```bash
python -m app.cli.catforge_pipeline run-user-task --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id m00_20260619084551_857df63b --product-category tv --sku-code TV00026064 --force-rebuild --format json
python -m app.cli.catforge_pipeline run-target-group --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id m00_20260619084551_857df63b --product-category tv --sku-code TV00026064 --force-rebuild --format json
python -m app.cli.catforge_pipeline run-value-battlefield --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id m00_20260619084551_857df63b --product-category tv --sku-code TV00026064 --graph-mode skip --force-rebuild --format json
```

结果：M09C/M10C/M11C 均 `success`，`comment_missing_excluded_sku_count=0`。

无评论 SKU：

- SKU：`TV00009549`
- batch：`m00_20260613004311_d548f6dc`

结果：M09C/M10C/M11C 均 `warning`，`input_count=0`，`profile_count=0`，`comment_missing_excluded_sku_count=1`，回读 current 均为 false。

## 205 全量重跑

旧 TV 批次：

```bash
python -m app.cli.catforge_pipeline run-user-task --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id m00_20260613004311_d548f6dc --product-category tv --force-rebuild --format json
python -m app.cli.catforge_pipeline run-target-group --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id m00_20260613004311_d548f6dc --product-category tv --force-rebuild --format json
python -m app.cli.catforge_pipeline run-value-battlefield --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id m00_20260613004311_d548f6dc --product-category tv --force-rebuild --format json
```

结果：M09C/M10C/M11C 均生成 75 个当前画像，排除 9 个无评论 SKU。

6/19 TV 主批次：

```bash
python -m app.cli.catforge_pipeline run-user-task --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id m00_20260619084551_857df63b --product-category tv --force-rebuild --format json
python -m app.cli.catforge_pipeline run-target-group --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id m00_20260619084551_857df63b --product-category tv --force-rebuild --format json
python -m app.cli.catforge_pipeline run-value-battlefield --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id m00_20260619084551_857df63b --product-category tv --force-rebuild --format json
```

结果：M09C/M10C/M11C 均生成 273 个当前画像，排除 20 个无评论 SKU。

## 最终验收

| 模块 | 旧批次 current | 6/19 主批次 current | total current | validation gap |
| --- | ---: | ---: | ---: | ---: |
| M09C | 75 | 273 | 348 | 0 |
| M10C | 75 | 273 | 348 | 0 |
| M11C | 75 | 273 | 348 | 0 |

哨兵 SKU 回读：

| SKU | 含义 | M09C current | M10C current | M11C current |
| --- | --- | --- | --- | --- |
| `TV00026064` | 6/19 市场 + 6/23 评论增量 | true | true | true |
| `TV00009549` | 无当前 M05C 评论事实画像 | false | false | false |

结论：G05 已完成。TV 当前智能体可消费的 M09C/M10C/M11C 画像范围为 348 个 comment-ready SKU；29 个无评论 SKU 不进入语义画像，避免后续智能体消费噪音。

下一子任务：G06，TV M11D/M12C 按 348 comment-ready 业务口径生成语义市场图谱与卖点价值量化。
