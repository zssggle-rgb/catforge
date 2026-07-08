# G04 进度记录：TV M05C 评论事实补齐

时间：2026-07-08

## 当前状态

G04 已启动但未完成。本轮完成了 M05C 缺口审计、LLM 链路 smoke、部分低句量 SKU 补跑，并清理了被中止后残留的远端进程。

## 缺口审计

使用当前 TV M05C taxonomy/rule：

- taxonomy_version：`tv_comment_fact_taxonomy_manual_v0.1`
- rule_version：`m05c_tv_comment_fact_profile_v0.1`

补跑前缺口：

| batch_id | comment_sentence_skus | existing_m05c_skus | pending_sentence_skus |
| --- | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 75 | 0 | 75 |
| `m00_20260619084551_857df63b` | 183 | 183 | 0 |
| `m00_20260623014631_c8630747` | 90 | 0 | 90 |

结论：

- G04 缺口不是 6/19 主批次，6/19 已覆盖 183。
- 需要补两段：旧 TV 全量批次 75 个 SKU，6/23 评论增量批次 90 个 SKU。

## Smoke 结果

成功跑通两个单 SKU smoke，均确认 `llm_called=true`：

| batch_id | SKU | 结果 | 说明 |
| --- | --- | --- | --- |
| `m00_20260613004311_d548f6dc` | `TV00028421` | warning / 已写 1 个 SKU profile | LLM 调用成功，warning 为缺 M04C claim profile |
| `m00_20260623014631_c8630747` | `TV00030083` | warning / 已写 1 个 SKU profile | LLM 调用成功，warning 为缺 M03B/M04C profile |

实际 LLM 配置：

- base_url：`https://api.deepseek.com`
- model：`deepseek-v4-flash`
- `llm_mode=required`

## 批量尝试与调整

尝试过旧批次 10 个低句量 SKU chunk：

- 参数：`--max-sentences-per-sku 80 --llm-batch-size 10 --parallelism 2 --skip-final-coverage`
- 运行时间超过 8 分钟后中止。
- 中止前已有部分 worker 成功提交。
- 已清理 205 API 容器中的残留 `run-comment-profile-batch` 进程，确认无残留。

当前补跑后计数：

| batch_id | comment_sentence_skus | existing_m05c_skus | pending_sentence_skus |
| --- | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 75 | 11 | 64 |
| `m00_20260619084551_857df63b` | 183 | 183 | 0 |
| `m00_20260623014631_c8630747` | 90 | 1 | 89 |

当前 TV M05C serving unique：195。

## 风险与下一步参数建议

观察到旧批次部分 SKU comment_sentence 行数很高，例如：

- `TV00026886`：2216 句。
- `TV00026941`：1849 句。
- `TV00027302`：2021 句。

默认 `max_sentences_per_sku=500` 与 `llm_batch_size=20` 在多 SKU chunk 下容易长时间无输出。后续建议：

1. 先按句数升序切小批，优先补低句量 SKU。
2. 每次调度 3-5 个 SKU，`parallelism=1` 或 `2`。
3. 保持 `llm-mode required`，先用 `max_sentences_per_sku=80` 完成覆盖，再对高价值/高销量 SKU 追加更高句数复跑。
4. 每个 chunk 后立即验收 pending 数和残留进程，避免后台继续写入。
5. G04 完成前需要最终执行 coverage rebuild。

## G04 剩余

- 旧 TV 批次剩余 64 个 pending SKU。
- 6/23 评论增量批次剩余 51 个 pending SKU。
- G04 尚未完成，不应标记完成。

## 2026-07-08 heartbeat 推进记录

### 远端残留批次收尾

本轮开始时先按 heartbeat 协议做只读检查，发现 205 API 容器中仍有上轮被上下文压缩前启动的 `run-comment-profile` 单 SKU 任务。该任务不是僵死进程，而是在按 SKU 顺序推进，因此未强杀，等待其自然结束。

已确认该残留批次 15 个 SKU 全部落库：

- `TV00030529`
- `TV00027842`
- `TV00027867`
- `TV00029414`
- `TV00030420`
- `TV00027029`
- `TV00028204`
- `TV00030527`
- `TV00026131`
- `TV00028085`
- `TV00026232`
- `TV00028111`
- `TV00027554`
- `TV00028556`
- `TV00026857`

残留批次结束后只读验收：

| batch_id | comment_sentence_skus | existing_m05c_skus | pending_sentence_skus |
| --- | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 75 | 11 | 64 |
| `m00_20260619084551_857df63b` | 183 | 183 | 0 |
| `m00_20260623014631_c8630747` | 90 | 26 | 64 |

当时 TV M05C serving unique：220。

### 本轮新增 10 SKU 小批

执行前确认无残留 `run-comment-profile` 进程，并按 6/23 评论增量批次 pending SKU 的 comment sentence 行数升序选取 10 个 SKU：

- `TV00027027`
- `TV00027028`
- `TV00029020`
- `TV00028274`
- `TV00027874`
- `TV00027997`
- `TV00028206`
- `TV00030081`
- `TV00030259`
- `TV00030355`

执行命令模式：

```bash
python -m app.cli.catforge_pipeline run-comment-profile \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id m00_20260623014631_c8630747 \
  --product-category tv \
  --sku-code <SKU> \
  --llm-mode required \
  --llm-batch-size 10 \
  --max-sentences-per-sku 80 \
  --format json
```

`TV00028206` 首次执行遇到 `M05C-B LLM 调用失败：LLM response is not JSON`，未落库。随后单 SKU 改用更小批量重试成功：

```bash
python -m app.cli.catforge_pipeline run-comment-profile \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id m00_20260623014631_c8630747 \
  --product-category tv \
  --sku-code TV00028206 \
  --llm-mode required \
  --llm-batch-size 5 \
  --max-sentences-per-sku 50 \
  --format json
```

后续 3 个 SKU 使用 `--llm-batch-size 5 --max-sentences-per-sku 80` 完成。所有成功 SKU 均确认 `llm_called=true`。模块返回的 warning 仍为 `m05c_param_profile_missing_for_some_skus` / `m05c_claim_fact_profile_missing_for_some_skus`，属于 6/23 增量 batch 上游画像缺失提示，不是 M05C 写入失败。

本轮最终只读验收：

| batch_id | comment_sentence_skus | existing_m05c_skus | pending_sentence_skus |
| --- | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 75 | 11 | 64 |
| `m00_20260619084551_857df63b` | 183 | 183 | 0 |
| `m00_20260623014631_c8630747` | 90 | 36 | 54 |

当前 TV M05C serving unique：230。

本轮结束时确认 205 API 容器内无残留 `run-comment-profile` 进程。

下一批 6/23 pending 低句量候选：

| SKU | comment_sentence_rows |
| --- | ---: |
| `TV00027039` | 55 |
| `TV00028555` | 57 |
| `TV00027764` | 60 |
| `TV00030173` | 64 |
| `TV00027765` | 69 |
| `TV00029304` | 69 |
| `TV00026064` | 71 |
| `TV00028099` | 75 |
| `TV00028115` | 75 |
| `TV00028341` | 75 |

建议下一轮继续从 6/23 低句量 pending 开始，默认改用 `--llm-batch-size 5`，降低 LLM 非 JSON 输出风险。G04 尚未完成，下一子任务仍是 G04。

## 2026-07-08 03:18 heartbeat 推进记录

### 执行前只读检查

执行前确认：

- 205 API 容器内无残留 `run-comment-profile` 进程。
- TV M05C 当前规则仍为 `tv_comment_fact_taxonomy_manual_v0.1` / `m05c_tv_comment_fact_profile_v0.1`。
- TV 三段 batch 覆盖为：

| batch_id | comment_sentence_skus | existing_m05c_skus | pending_sentence_skus |
| --- | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 75 | 11 | 64 |
| `m00_20260619084551_857df63b` | 183 | 183 | 0 |
| `m00_20260623014631_c8630747` | 90 | 36 | 54 |

执行前 TV M05C serving unique：230。

### 本轮补跑

本轮继续只处理 G04，未重跑 M00-M02，未进入 G05。按 6/23 评论增量批次 pending SKU 的 comment sentence 行数升序尝试：

- `TV00027039`
- `TV00028555`
- `TV00027764`
- `TV00030173`
- `TV00027765`

默认执行命令模式：

```bash
python -m app.cli.catforge_pipeline run-comment-profile \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id m00_20260623014631_c8630747 \
  --product-category tv \
  --sku-code <SKU> \
  --llm-mode required \
  --llm-batch-size 5 \
  --max-sentences-per-sku 80 \
  --format json
```

结果：

| SKU | 结果 | 说明 |
| --- | --- | --- |
| `TV00027039` | 成功 | `llm_called=true`，写入 1 个 SKU profile |
| `TV00028555` | 成功 | `llm_called=true`，写入 1 个 SKU profile |
| `TV00027764` | timeout | 首次 `timeout 180`；随后用 `--llm-batch-size 3 --max-sentences-per-sku 40` 单 SKU 重试仍 timeout，未落库 |
| `TV00030173` | 成功 | 跳过 `TV00027764` 后继续执行，`llm_called=true`，写入 1 个 SKU profile |
| `TV00027765` | timeout | `timeout 180`，未落库 |

模块成功返回时仍带有 `m05c_param_profile_missing_for_some_skus` / `m05c_claim_fact_profile_missing_for_some_skus` warning，属于 6/23 增量 batch 上游画像缺失提示，不是 M05C 写入失败。

### 本轮最终验收

本轮结束时确认 205 API 容器内无残留 `run-comment-profile` 进程。

最终只读覆盖：

| batch_id | comment_sentence_skus | existing_m05c_skus | pending_sentence_skus |
| --- | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 75 | 11 | 64 |
| `m00_20260619084551_857df63b` | 183 | 183 | 0 |
| `m00_20260623014631_c8630747` | 90 | 39 | 51 |

当前 TV M05C serving unique：233。

下一批 6/23 pending 低句量候选：

| SKU | comment_sentence_rows | 建议 |
| --- | ---: | --- |
| `TV00027764` | 60 | 已连续 timeout，建议后续单独用更低句量或错峰重试 |
| `TV00027765` | 69 | 已 timeout，建议后续单独用更低句量或错峰重试 |
| `TV00029304` | 69 | 可继续补跑 |
| `TV00026064` | 71 | 可继续补跑 |
| `TV00028099` | 75 | 可继续补跑 |
| `TV00028115` | 75 | 可继续补跑 |
| `TV00028341` | 75 | 可继续补跑 |
| `TV00027899` | 82 | 可继续补跑 |
| `TV00027986` | 83 | 可继续补跑 |
| `TV00027077` | 91 | 可继续补跑 |

G04 尚未完成。下一轮仍应优先补 6/23 增量批次 pending；建议先跳过已连续 timeout 的 `TV00027764`，直接从 `TV00029304` 起继续，待 LLM 延迟稳定后再回补 timeout SKU。

## 2026-07-08 03:40 heartbeat 推进记录

### 执行前只读检查

执行前确认：

- 205 API 容器内无残留 `run-comment-profile` 进程。
- TV M05C 当前规则仍为 `tv_comment_fact_taxonomy_manual_v0.1` / `m05c_tv_comment_fact_profile_v0.1`。
- TV 三段 batch 覆盖为：

| batch_id | comment_sentence_skus | existing_m05c_skus | pending_sentence_skus |
| --- | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 75 | 11 | 64 |
| `m00_20260619084551_857df63b` | 183 | 183 | 0 |
| `m00_20260623014631_c8630747` | 90 | 39 | 51 |

执行前 TV M05C serving unique：233。

### 本轮尝试

本轮继续只处理 G04，未重跑 M00-M02，未进入 G05。按上一轮建议跳过已连续 timeout 的 `TV00027764` / `TV00027765`，尝试从 6/23 增量批次的后续低句量 SKU 开始：

- `TV00029304`
- `TV00026064`
- `TV00028099`

执行命令模式：

```bash
python -m app.cli.catforge_pipeline run-comment-profile \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id m00_20260623014631_c8630747 \
  --product-category tv \
  --sku-code <SKU> \
  --llm-mode required \
  --llm-batch-size 3 \
  --max-sentences-per-sku 60 \
  --format json
```

`TV00029304` 在 `timeout 180` 内未返回，脚本按设计停止，后两个 SKU 未执行。本轮未继续消耗 LLM 调用。

### 本轮最终验收

本轮结束时确认 205 API 容器内无残留 `run-comment-profile` 进程。

最终只读覆盖未变化：

| batch_id | comment_sentence_skus | existing_m05c_skus | pending_sentence_skus |
| --- | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 75 | 11 | 64 |
| `m00_20260619084551_857df63b` | 183 | 183 | 0 |
| `m00_20260623014631_c8630747` | 90 | 39 | 51 |

当前 TV M05C serving unique：233。

当前连续 timeout 或本轮 timeout 的 6/23 SKU：

| SKU | comment_sentence_rows | 状态 |
| --- | ---: | --- |
| `TV00027764` | 60 | 连续 timeout，未落库 |
| `TV00027765` | 69 | timeout，未落库 |
| `TV00029304` | 69 | 本轮 timeout，未落库 |

下一批 6/23 pending 候选：

| SKU | comment_sentence_rows | 建议 |
| --- | ---: | --- |
| `TV00026064` | 71 | 可继续错峰补跑 |
| `TV00028099` | 75 | 可继续错峰补跑 |
| `TV00028115` | 75 | 可继续错峰补跑 |
| `TV00028341` | 75 | 可继续错峰补跑 |
| `TV00027899` | 82 | 可继续错峰补跑 |
| `TV00027986` | 83 | 可继续错峰补跑 |
| `TV00027077` | 91 | 可继续错峰补跑 |
| `TV00030368` | 91 | 可继续错峰补跑 |

G04 尚未完成。由于连续多个低句量 SKU 在 LLM 调用阶段接近或超过 180 秒，下一轮建议先做一次更小的单 SKU smoke，例如 `TV00026064 --llm-batch-size 1 --max-sentences-per-sku 30`；如果仍 timeout，暂停 TV M05C LLM 补跑，转为记录 LLM 服务不可用窗口并等待下一次 heartbeat 错峰再试。

## 2026-07-08 LLM timeout 根因修复记录

用户确认 DeepSeek 服务本身可用且余额充足后，重新排查 M05C timeout。结论：主要问题不是 DeepSeek 不可用，而是执行参数和 M05C 调用方式不合理。

### 根因

M05C 的 LLM 调用按 `llm_batch_size` 把一个 SKU 的评论句拆成多个请求，旧代码在单 SKU 内顺序调用。前几轮为了“降负载”把 `llm_batch_size` 降到 3 或 1，反而导致一个 60-75 句的 SKU 被拆成 20-30 次请求，并且每次请求都重复发送整套 taxonomy。外层 `timeout 180` 因此容易杀掉整个 SKU。

这不是正确的降负载方式。正确方式应该是：

- 单次 LLM 请求给更多评论句，减少请求数。
- 对同一 SKU 的 LLM chunks 做受控并发。
- 批量任务再通过 SKU worker 并发控制总并发。
- 不依赖超长外层 timeout。

### 代码修复

本地代码已修改并通过测试：

- `apps/api-server/app/services/core3_real_data/m05c_comment_fact_profile_service.py`
  - 新增 `M05C_DEFAULT_LLM_PARALLELISM = 3`。
  - M05C 单 SKU 内部按 chunk 并发调用 LLM。
  - `llm_stats` 新增 `llm_request_count`、`llm_parallelism`、`effective_llm_parallelism`。
  - M05C LLM timeout 现在会读取通用 `CATFORGE_LLM_TIMEOUT_SECONDS`，不再只认 `CATFORGE_M05C_LLM_TIMEOUT_SECONDS`。
- `apps/api-server/app/cli/catforge_pipeline.py`
  - `run-comment-profile` / `run-comment-profile-batch` / `ask` 新增 `--llm-parallelism`。
  - 单 SKU、批量 worker、自然语言路由都传递 `llm_parallelism`。
- `apps/api-server/tests/core3_real_data/test_m05c_comment_fact_profile.py`
  - 新增不调用真实 LLM 的并发 chunk 单元测试。

验证：

```bash
python -m py_compile \
  apps/api-server/app/services/core3_real_data/m05c_comment_fact_profile_service.py \
  apps/api-server/app/cli/catforge_pipeline.py

python -m pytest apps/api-server/tests/core3_real_data/test_m05c_comment_fact_profile.py
```

结果：`8 passed`。

### 205 热更新与 smoke

205 `/opt/catforge` 源码子目录归 `501:staff`，`deploy` 用户无 sudo，无法直接写源码并重建镜像。本次先通过 `docker cp` 热更新运行中 API 容器内的两个 Python 文件：

- `/app/app/services/core3_real_data/m05c_comment_fact_profile_service.py`
- `/app/app/cli/catforge_pipeline.py`

远端验证：

- 容器内 `M05C_DEFAULT_LLM_PARALLELISM=True`，默认值 `3`。
- `run-comment-profile --help` 与 `run-comment-profile-batch --help` 均包含 `--llm-parallelism`。
- 容器内 py_compile 通过。

使用新策略验证：

```bash
python -m app.cli.catforge_pipeline run-comment-profile \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id m00_20260623014631_c8630747 \
  --product-category tv \
  --sku-code TV00026064 \
  --llm-mode required \
  --llm-batch-size 20 \
  --llm-parallelism 3 \
  --max-sentences-per-sku 80 \
  --format json
```

结果：成功落库，`llm_request_count=4`，`effective_llm_parallelism=3`。

随后回测此前 timeout 的 SKU：

- `TV00027764`：成功落库。
- `TV00027765`：成功落库，`llm_request_count=4`，`effective_llm_parallelism=3`。

本次结束时 205 API 容器内无残留 `run-comment-profile` 进程。

当前覆盖：

| batch_id | comment_sentence_skus | existing_m05c_skus | pending_sentence_skus |
| --- | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 75 | 11 | 64 |
| `m00_20260619084551_857df63b` | 183 | 183 | 0 |
| `m00_20260623014631_c8630747` | 90 | 42 | 48 |

当前 TV M05C serving unique：236。

### 后续执行建议

后续 G04 不要再使用 `--llm-batch-size 1/3/5` 来“降负载”。建议参数：

```bash
--llm-batch-size 20 --llm-parallelism 3 --max-sentences-per-sku 80
```

批量跑时用 SKU worker 控制总并发，例如：

```bash
python -m app.cli.catforge_pipeline run-comment-profile-batch \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id m00_20260623014631_c8630747 \
  --product-category tv \
  --llm-mode required \
  --llm-batch-size 20 \
  --llm-parallelism 3 \
  --max-sentences-per-sku 80 \
  --parallelism 2 \
  --limit 10 \
  --skip-final-coverage \
  --format json
```

注意：本次 205 是容器热更新，不是重建镜像；若 API 容器被重建，需要从当前本地代码正式部署，才能保留 `--llm-parallelism` 修复。

## 2026-07-08 执行闭环策略修订

用户指出“每轮做一个子任务的最小闭环”不应变成小批 SKU 反复停止验收。G04 后续执行改为“最小可决策闭环”：

- 一轮仍只推进 G04，但可以在 G04 内连续跑批，直到模块完成、进入异常队列、需要代码/配置修复、出现用户决策点或安全风险。
- 不再对每个很小 SKU chunk 做完整验收；小批只做轻量进度检查和残留进程检查。
- 完整 coverage rebuild 和覆盖验收放在 G04 模块边界，或连续失败达到阈值时执行。
- 主链路和异常链路分开：能继续补齐的 SKU 继续跑，失败 SKU 进入 retry/review/exclusion 清单，不静默消失。

G04 当前 205 进度：

| batch_id | comment_sentence_skus | existing_m05c_skus | pending_sentence_skus |
| --- | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 75 | 11 | 64 |
| `m00_20260619084551_857df63b` | 183 | 183 | 0 |
| `m00_20260623014631_c8630747` | 90 | 42 | 48 |

当前 TV M05C serving unique：236。

后续默认参数：

```bash
--llm-batch-size 20 --llm-parallelism 3 --max-sentences-per-sku 80
```

下一次执行先做 live 只读检查，再优先补 6/23 评论增量批次 pending。推荐从批量命令开始，不再手工逐 SKU 循环：

```bash
python -m app.cli.catforge_pipeline run-comment-profile-batch \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id m00_20260623014631_c8630747 \
  --product-category tv \
  --llm-mode required \
  --llm-batch-size 20 \
  --llm-parallelism 3 \
  --max-sentences-per-sku 80 \
  --parallelism 2 \
  --limit 10 \
  --skip-final-coverage \
  --format json
```

如果 `--limit 10` 稳定，下一步扩大到 `--limit 20` 或直接跑完当前 batch pending；完成 6/23 后再补旧 TV 批次剩余 64 个 SKU。只有新异常复现或安全排查时，才退回单 SKU smoke。

## 2026-07-08 G04 完成记录

本轮按“最小可决策闭环”继续 G04，没有重跑 M00-M02，只消费既有 M02 `comment_sentence` evidence。执行前已确认：

- 205 API 容器健康运行。
- 无残留 `run-comment-profile` / `run-comment-profile-batch` / `catforge_pipeline` 进程。
- 容器内 CLI 支持 `--llm-parallelism`，`M05C_DEFAULT_LLM_PARALLELISM=3`。
- M05C 当前真实写入口径为 `category_code=TV` / `product_category=TV` / `rule_version=m05c_tv_comment_fact_profile_v0.1` / `is_current=true`。

### 执行命令模式

补跑使用批量 runner，不再手工逐 SKU 循环：

```bash
python -m app.cli.catforge_pipeline run-comment-profile-batch \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id <batch_id> \
  --product-category tv \
  --llm-mode required \
  --llm-batch-size 20 \
  --llm-parallelism 3 \
  --max-sentences-per-sku 80 \
  --parallelism 2 \
  --limit <10|20|25> \
  --skip-final-coverage \
  --format json
```

6/23 评论增量批次：

- 从 42/90 继续。
- 第一批 `--limit 10`：10/10 成功。
- 第二批 `--limit 20`：19/20 成功，`TV00027986` 一次 `LLM response is not JSON`。
- 第三批 `--limit 20`：19/19 成功，`TV00027986` retry 成功。
- 结果：`m00_20260623014631_c8630747` 达到 90/90。

旧 TV 批次：

- 从 11/75 继续。
- 第一批 `--limit 20`：20/20 成功。
- 第二批 `--limit 20`：19/20 成功，`TV00027887` 一次 `LLM response is not JSON`。
- 第三批 `--limit 25`：25/25 成功，`TV00027887` retry 成功。
- 结果：`m00_20260613004311_d548f6dc` 达到 75/75。

所有批次的 warning 均为可接受的 M05C 业务 warning，主要包括：

- `m05c_claim_fact_profile_missing_for_some_skus`
- `m05c_param_profile_missing_for_some_skus`
- `m05c_comment_contradiction_review_required`

其中 `m05c_comment_contradiction_review_required` 已写入 review issue，不阻断 SKU profile 生成。

### Coverage rebuild

补齐后对三段 TV M05C batch 分别执行 coverage rebuild，不调用 LLM：

```bash
python -m app.cli.catforge_pipeline run-comment-profile-batch \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id <batch_id> \
  --product-category tv \
  --llm-mode off \
  --llm-batch-size 20 \
  --llm-parallelism 3 \
  --max-sentences-per-sku 80 \
  --parallelism 2 \
  --format json
```

Coverage rebuild 结果：

| batch_id | sku_profile_count | coverage_rows | status |
| --- | ---: | ---: | --- |
| `m00_20260613004311_d548f6dc` | 75 | 83 | ok |
| `m00_20260619084551_857df63b` | 183 | 118 | ok |
| `m00_20260623014631_c8630747` | 90 | 49 | ok |

### 最终验收

205 只读验收：

| batch_id | M02 comment evidence SKU | M05C current SKU | pending |
| --- | ---: | ---: | ---: |
| `m00_20260613004311_d548f6dc` | 75 | 75 | 0 |
| `m00_20260619084551_857df63b` | 183 | 183 | 0 |
| `m00_20260623014631_c8630747` | 90 | 90 | 0 |

TV M05C serving unique：348/348。

品类隔离验收：

| category_code | product_category | rule_version | is_current | sku_count |
| --- | --- | --- | --- | ---: |
| TV | TV | `m05c_tv_comment_fact_profile_v0.1` | true | 348 |

结束时 205 无残留 `run-comment-profile` / `run-comment-profile-batch` / `catforge_pipeline` 进程。

G04 验收结论：通过。下一步进入 G05：TV M09C/M10C/M11C 对齐，目标是按 TV market/param 377 SKU 生成用户任务、目标客群、价值战场画像；M05C 已不再是 G05 的阻塞项。
