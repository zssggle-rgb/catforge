# G03 执行记录：TV M03B/M04C/M07 对齐

时间：2026-07-08

## 本轮目标

不重跑 M00-M02，只补齐 TV 当前智能体消费链路中事实画像层的缺口：

- M03B 当前 TV 参数事实画像规则覆盖 377 个 market/param SKU。
- M04C 当前 TV 卖点事实画像规则覆盖 328 个 claim SKU。
- M07 当前 TV 市场画像规则覆盖 377 个 market SKU。

## 补跑前缺口

205 只读盘点：

| 项 | 结果 |
| --- | ---: |
| 旧 TV 批次 `param_raw` SKU | 84 |
| 新 TV 批次 `param_raw` SKU | 293 |
| 旧 TV 批次已有 M03 旧规则 `m03_param_v1` | 84 |
| 旧 TV 批次缺当前 M03B `m03b_tv_param_profile_v0.1` | 84 |
| M04C 当前规则 serving unique | 328 |
| M07 当前规则 serving unique | 377 |

缺当前 M03B 的旧批次样例：

`TV00009549`, `TV00023850`, `TV00026886`, `TV00026941`, `TV00027302`, `TV00027353`, `TV00027442`, `TV00027443`, `TV00027463`, `TV00027475`

## 执行动作

在 205 API 容器中执行：

```bash
python -m app.cli.catforge_pipeline run-param-profile \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id m00_20260613004311_d548f6dc \
  --product-category tv \
  --format json
```

该命令只调用 M03BRunner，读取既有 M02 `param_raw` evidence，不重新注册 source batch，不重新清洗 raw 表，不重新生成 evidence atom。

## 执行结果

M03B runner 返回：

| 字段 | 值 |
| --- | --- |
| status | `warning` |
| module_status | `warning` |
| batch_id | `m00_20260613004311_d548f6dc` |
| rule_version | `m03b_tv_param_profile_v0.1` |
| input_count | 6900 |
| sku_profile_count | 84 |
| output_count | 4868 |
| changed_input_count | 4868 |
| warning | `m03b_param_value_conflicts_need_review` |

warning 原因是 84 个 SKU 内存在参数值冲突待复核；本轮仍成功生成 84 个 SKU 参数事实画像。

## 验收结果

205 只读 SQL 验收：

| 模块 | batch_id | 当前规则 SKU 数 |
| --- | --- | ---: |
| M03B | `m00_20260613004311_d548f6dc` | 84 |
| M03B | `m00_20260619084551_857df63b` | 293 |
| M04C | `m00_20260619084551_857df63b` | 293 |
| M04C | `m00_20260623014631_c8630747` | 328 |
| M07 | `m00_20260613004311_d548f6dc` | 84 |
| M07 | `m00_20260619084551_857df63b` | 293 |

Serving unique 覆盖：

| 模块 | 当前规则 serving unique | 输入缺口 |
| --- | ---: | ---: |
| M03B | 377 | 0 vs M02 `param_raw` |
| M04C | 328 | 0 vs M02 claim evidence |
| M07 | 377 | 0 vs clean market active |

M07 额外校验：

- clean market active unique：377。
- M07 missing vs clean market active：0。
- M07 extra vs clean market active：0。

## G03 验收

已通过：

- TV M03B 当前规则覆盖 377 个 SKU。
- TV M04C 当前规则覆盖 328 个 SKU。
- TV M07 当前规则覆盖 377 个 SKU。
- 本轮未重跑 M00-M02。

## 下一步

进入 G04：TV M05C 评论事实补齐。当前 M05C 只覆盖 183，目标是接近 M02 comment evidence 348，并解释 raw 360 / clean 357 / M02 348 / M05C 目标之间的差异。
