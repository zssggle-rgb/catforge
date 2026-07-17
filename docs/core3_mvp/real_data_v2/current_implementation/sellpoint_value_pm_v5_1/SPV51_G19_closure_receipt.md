# SPV51-G19 发布状态机修复关闭回执

状态：completed；发布门禁已修复；尚未发布

日期：2026-07-17

## 1. 修复结果

G18 发现的 V5.1 发布阻塞已经修复。

发布完整性现在按画像方法版本分流：

- V5.1 使用 `conclusion_available + partial_conclusion + no_conclusion + invalid` 核对权威 SKU 覆盖；
- `partial_conclusion` 和 `no_conclusion` 是完整的 limited 状态，不再要求伪造 `review_required_count`；
- invalid、generation failure、blocked、integrity error、覆盖不完整和最终 readback 未完成仍阻断；
- 旧 V5 继续使用 ready/review/blocked/failed 合同，历史行为不变。

205 两个真实 G17 版本只读复核：

| 品类 | 分布 | SKU | 新发布完整性门禁 |
| --- | --- | ---: | --- |
| TV | 282 / 66 / 29 / 0 | 377 | passed |
| AC | 138 / 6 / 11 / 0 | 155 | passed |

旧 TV、AC V5 仍因 blocked 被拒绝，没有被新规则放行。

## 2. 首次发布回退能力

新增 `deactivate_current_version`：

- 只接受一个明确的 published/current 版本；
- 必须提供非 system 操作人和回退原因；
- 在一个事务中联动撤销 version、profile、candidate、value item 的 current；
- 保留 published 状态、全部画像数据和 result hash；
- 不删除版本，不把旧 blocked V5 自动切回 current；
- 任一子表更新失败，整笔回退事务恢复原 current。

回退后正式智能体返回 `profile_unavailable`，即恢复本次首次启用前的正式消费状态。

published/non-current 历史版本仍不开放业务 preview；它只能通过审计读取核对。G18 原报告中“回退后 preview 仍可锁定”的表述已同步纠正。

## 3. 测试

- 受影响专项与回归：79 passed；
- 真实 TV `282/66/29/0` limited 发布测试通过；
- 真实 AC `138/6/11/0` limited 发布测试通过；
- integrity error 阻断测试通过；
- 旧 V5 limited 合同回归通过；
- current 撤销、子表联动、hash 保留、重复撤销拒绝通过；
- 子表失败的事务原子性通过；
- 正式消费在撤销后返回 unavailable；
- ruff、compile、`git diff --check` 通过。

实现提交：`101ffd4f9c77dc40c7ba83930c6a630d64c91444`。

## 4. 205 部署与复核

为保护 205 现有 dirty/stash，没有使用会执行 `reset --hard` 和 `git clean` 的标准热修脚本。

本次只备份并替换：

`apps/api-server/app/services/core3_real_data/analyst/sellpoint_value_profile_repositories.py`

部署文件和容器文件 sha256 均为：

`d6c1c9057f9fac4527063c6bdf6939e84003cec215928f3389d6f83c834f1608`

备份：

`/home/deploy/catforge-deploy-backups/spv51-g19-publish-lifecycle-20260717`

运行状态：

- healthz=ok；
- readyz=ready；
- OOM=false；
- restart=0。

## 5. 保护边界

本 Goal：

- 没有重生成任何画像；
- 没有 review、publish、current 或 deprecated；
- 没有数据库写入；
- TV/AC G17 版本 id、result hash、532 款数据和正式竞品 source hash 均未变化；
- TV/AC current published 仍均为 0；
- 没有修改旧 V5、正式竞品画像或旧 M12/M13/M14；
- 没有清理远端 dirty 文件；
- `.env` hash 和受保护 stash OID 未变化。

## 6. 当前发布准备结论

工程阻塞已经解除，当前状态为：

`ready_for_explicit_limited_release_approval`

这不等于已经获得发布授权。下一步仍必须由用户明确批准：

- TV 版本 `37f2ef77-187a-4ee6-b0a7-87708a21856f`；
- AC 版本 `38d86772-cd31-4b0c-bf4c-cccc64de6aee`；
- 明确允许 limited；
- review 人、publish 人和发布说明；
- 执行 review、publish 和 current。

结构化证据：`SPV51_G19_publish_lifecycle_fix_evidence.json`。
