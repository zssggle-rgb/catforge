# G40 竞品画像 V1.1 205 代码与 Migration 部署关闭回执

状态：completed

日期：2026-07-16

## 1. 目标与结果

G40 已将 G39 的精确代码提交
`2829a05c77b5bed938a18216d8cfb6dc21a2f61f` 部署到 205，并把数据库从
`0046_core3_competitor_profile` 升级到
`0047_core3_competitor_profile_v1_1`。

本 Goal 只完成代码、镜像、migration、运行时与回滚能力验收；V1.1 业务版本、
SKU snapshot 和画像行均保持为 0。未生成 65E7Q 或其他 SKU 画像，未执行
review/publish/current/deprecated 切换。

## 2. 部署前门禁与备份

- 205 部署前 commit：`3341f45c1cd33bdbcaa5a6eb342e744aaf9e9a4e`；
- 部署前 Alembic：`0046_core3_competitor_profile`；
- V1.1 version 行：0；V1.1 snapshot 表尚不存在；活动数据库写入：0；
- `/healthz` 与 `/readyz` 均通过；未发现画像生成进程；
- 完整备份目录：
  `/home/deploy/catforge-deploy-backups/competitor-profile-v11-g40-20260716_052052`；
- predeploy bundle SHA256：
  `01ed9613300a685ad525bec430605bfad41a5caf2837cab0152781b3585e6ae6`；
- dirty patch SHA256：
  `5e59d3d2ac86fb06afb4b17a307f7c1509c29cfbb195549e5badf53d2b3bd595`；
- schema-before SHA256：
  `b30c8a56119fa68a8ed36a5497d85cb170e870d97a46cd1e83da9a633b8e7a66`；
- `.env` SHA256 部署前后均为
  `7243971662532eaa036d64f7d73d71920c586286a94df5eacead1713e6e5b56a`。

205 原有 11 个 tracked 修改和 1 个 untracked 测试文件先独立备份并 stash，代码
fast-forward 后再恢复。唯一 import 上下文冲突已按“保留原用户改动，同时增加
V1.1 Reader/Repository 注入”合并；最终仍为原 12 项 dirty 文件，unmerged=0，
`git diff --check` 通过。保护性 stash 保留为
`competitor-profile-v11-g40-preserve-20260716_052052`，未删除。

## 3. Commit、镜像与运行时核验

- 205 当前代码 commit：
  `2829a05c77b5bed938a18216d8cfb6dc21a2f61f`；
- API container image id：
  `sha256:4dbc18c3327f95d47928fc2f71a0fbd38e8bd9a6f22421ec02d9cc1285fa34e7`；
- API container：running、healthy、restart count=0；
- `/healthz`：`{"status":"ok"}`；
- `/readyz`：`{"status":"ready","database":"ok"}`；
- 部署窗口 API 日志中 `ERROR`、`Traceback`、`CRITICAL`：0；
- `competitor-set --help` 和 `competitor-profile-read --help`：exit 0；
- V1.1 Repository、GenerationService、Reader import smoke：passed。

容器内 migration、entities、V1.1 Repository、Generation、Reader 和
AnalystService 六个关键源文件 SHA256 均与部署提交对应的本地文件一致。

## 4. 0047 结构与数据保真

首次 upgrade 和回滚再 upgrade 后均得到：

- Alembic head：`0047_core3_competitor_profile_v1_1`；
- V1.1 version 行：0；snapshot 行：0；活动数据库写入：0；
- snapshot/profile/pair/relation/selection 列数分别为 19/47/59/38/42；
- snapshot 外键 2、唯一约束 1；V1.1 checks 与读取索引均存在；
- V1.1 新表为空，已有 V1、采购理由和用户卖点价值数据行数未变化。

受保护表在 upgrade、downgrade、再次 upgrade 前后行数一致：

| 表 | 行数 |
| --- | ---: |
| `core3_competitor_profile_version` | 2 |
| `core3_sku_competitor_profile` | 532 |
| `core3_sku_competitor_profile_pair` | 148,309 |
| `core3_sku_competitor_profile_relation` | 1,038,163 |
| `core3_sku_competitor_profile_selection` | 71 |
| `core3_competitor_candidate` | 28 |
| `core3_competitor_result` | 30 |
| `core3_purchase_reason_profile_version` | 7 |
| `core3_sku_purchase_reason_profile` | 1,751 |
| `core3_sku_purchase_reason_anchor` | 17,899 |
| `core3_sellpoint_value_profile_version` | 7 |
| `core3_sku_sellpoint_value_profile` | 691 |
| `core3_sku_sellpoint_value_candidate` | 45,070 |
| `core3_sku_sellpoint_value_item` | 3,123 |

## 5. 空表 Rollback 演练

在再次确认 V1.1 version=0、snapshot=0、活动写入=0 后执行：

1. `0047_core3_competitor_profile_v1_1` downgrade 到
   `0046_core3_competitor_profile`：成功；
2. snapshot 表不存在，全部受保护表行数不变，health/ready 通过；
3. 从 0046 再 upgrade 到 0047：成功；
4. snapshot 表恢复且为 0，全部受保护表行数不变，health/ready 通过。

演练没有绕过 downgrade guard，没有删除或重建业务数据。

## 6. 运行时异常处置记录

一次 Alembic 只读核验误用了 `docker compose run`。该命令在实际 Alembic
进程启动前因宿主 5432 端口占用失败，没有执行数据库命令；它创建的未启动
`catforge-postgres-1` 随即被删除，未删除 volume。compose 同时重建了 Redis
容器；Redis 最终 `PONG`、DBSIZE=0，API health/ready 持续通过，API 与数据库
行数未变化。后续所有核验和 rollback 均改为对已部署 API container 使用
`docker exec`，不再触发 compose dependency lifecycle。

## 7. 写入与发布边界

- V1.1 业务画像/version/snapshot 写入：0；
- 65E7Q、AC 或 TV/AC 全量画像生成：0；
- V1 草稿修改：0；
- M03B—M12D 重跑：0；
- 旧 M12/M13/M14 修改：0；
- review/publish/current/deprecated 切换：0；
- 飞书消息发送或文档创建：0；
- 本地及 205 用户 dirty/untracked 文件均未进入部署提交。

## 8. 下一 Goal

G41A 只允许为海信 65E7Q 生成一个明确的 V1.1 draft，并完成生成回读、完整
pair 多维结果、旧 Top 3、新旧差异、Reader/Adapter/智能体零重算、compact
读取性能和旧画像不变验收。G41A 通过前不得创建 G41B。
