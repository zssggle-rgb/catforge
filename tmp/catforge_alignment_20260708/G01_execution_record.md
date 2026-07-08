# G01 执行记录：serving 输入口径冻结

时间：2026-07-08

## 约束

- 不重跑 M00-M02。
- 只消费 205 上现有 `core3_clean_*` active 数据和 `core3_evidence_atom` current 数据。
- 本轮没有写 205 数据，只做只读查询和本地清单落盘。

## 生成物

目录：`tmp/catforge_alignment_20260708/`

- `g01_serving_input_scope.json`：完整覆盖摘要、M02 batch map、下游当前覆盖和 serving SKU 清单。
- `TV_market_param_skus.txt`：377 行。
- `TV_claim_skus.txt`：328 行。
- `TV_comment_skus.txt`：348 行。
- `AC_market_param_skus.txt`：155 行。
- `AC_claim_skus.txt`：155 行。
- `AC_comment_skus.txt`：144 行。

## 覆盖摘要

| 品类 | raw market | raw param | raw claim | raw comment | clean market | clean param | clean claim | clean comment | M02 market | M02 param | M02 claim | M02 comment |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TV | 377 | 377 | 328 | 360 | 377 | 377 | 328 | 357 | 377 | 377 | 328 | 348 |
| AC | 155 | 155 | 155 | 147 | 155 | 155 | 155 | 146 | 155 | 155 | 155 | 144 |

## Serving 输入清单

| 品类 | market_param_skus | claim_skus | comment_skus |
| --- | ---: | ---: | ---: |
| TV | 377 | 328 | 348 |
| AC | 155 | 155 | 144 |

## M02 batch 事实

TV 的 M02 evidence 分布在多个 batch，不能直接用单一 `latest` 表达完整 TV：

- `m00_20260613004311_d548f6dc`：TV 老全量，market/param 84，claim 35，comment 75。
- `m00_20260619084551_857df63b`：TV 新全量，market/param/claim 293，comment 183。
- `m00_20260623014631_c8630747`：TV 评论增量，comment 90。

AC 有当前 `category_code=AC` 全量口径：

- `m00_20260624000202_1150a669`：AC market/param/claim 155，comment 144。
- `m00_20260623020057_41b43cb5`：AC 评论批次，comment 144；已被 6 月 24 AC batch 复用。

注意：历史上 `category_code=TV` 的 `m00_20260619084551_857df63b` 里也含 AC 前缀 evidence。后续 AC 任务必须使用 `category_code=AC` + `product_category=AC` 的当前结果，避免混读。

## 当前下游缺口

TV：

- M03B 当前 TV 规则只覆盖 293，另有 84 个停在旧 `m03_param_v1`。
- M04C 当前 TV 规则覆盖 328。
- M05C 覆盖 183，距离 M02 comment 348 差 165。
- M07 当前规则有 84 + 293 两段，缺一个统一 serving 口径。
- M09C/M10C/M11C 当前规则均覆盖 293。
- M11D `fact_complete_with_comment` 覆盖 183。
- M12C 覆盖 182。

AC：

- M03B/M04C/M07/M09C/M10C/M11C 当前 AC 规则均覆盖 155。
- M05C 覆盖 144，raw comment 147 与 clean comment 146 的尾差待 G07 审计。
- M11D/M12C 尚未形成 AC 可消费结果，需 G08/G09 做 AC 规则适配。

## G01 验收

已通过：

- TV 输入清单：market/param 377，claim 328，comment evidence 348。
- AC 输入清单：market/param/claim 155，comment evidence 144。
- 清单已落盘到 `tmp/catforge_alignment_20260708/`。

## 下一步

进入 G02：设计并实现 TV serving scope，让下游 runner 和 `catforge_analyst latest` 能读完整 TV serving 口径，而不是误读单个 6 月 23 评论增量 batch。
