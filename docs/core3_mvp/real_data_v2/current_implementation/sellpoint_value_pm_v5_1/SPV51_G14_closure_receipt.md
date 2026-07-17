# SPV51-G14 205 代码与 Migration 部署关闭回执

状态：completed

日期：2026-07-17

## 1. 部署结果

- 205 代码从 `b491bd070b4515da98e02a7055066a9427b4605c` 快进到 G13 已验收提交 `a0fe719eec2068ec1270babcaf2b49b7bfdb0b4b`；
- Alembic 从 `0047_core3_competitor_profile_v1_1` 升级到 `0048_core3_sellpoint_value_profile_v5_1 (head)`；
- 只重建 API 镜像与容器，没有重建 Web、Redis，也没有清理既有 orphan 任务容器；
- 未创建 V5.1 version，未生成 65E7Q、AC 或任何其他 SKU 画像，未执行 review、publish、current 或 deprecated 切换。

## 2. 远端用户修改保护

部署前 205 有 17 个 tracked 修改和 1 个 untracked 测试文件。本次没有使用 `git reset`、`git clean` 或覆盖式 rsync，而是先完成三层保护：

- 备份目录：`/home/deploy/catforge-deploy-backups/spv51-g14-20260717_113025`；
- predeploy bundle SHA256：`88acb1f586f9c98165a9d74e1b19e02390f86703bb369ffd4a449de06b4418b0`；
- dirty patch SHA256：`7f87278a1aae891bac3c469a51dbe6c3bebd16240b6cab9860d612504656639c`；
- untracked archive SHA256：`78f60fccd0a595c6975bf475c71bf40b4c26b5115c7804c9798375819fb779e0`；
- 保护 stash：`spv51-g14-preserve-20260717_113025`，对象 `2156593622e0f07af67695da1e0e965153349b05`，保留未删除。

stash 在快进后无冲突恢复，`git diff --check` 通过。最终仍保留 13 个 tracked 修改和 1 个 untracked 文件；部署前另外 4 个竞品 snapshot/lifecycle 文件的相同修改已经包含在快进提交中，因此不再显示为 dirty，不是丢失。

## 3. 运行时验收

- API image：`sha256:bd01de3ba293a744127701ac5ad66132fb0c2994492af7fab052133d6dee74b4`；
- API container：`9f50d92770eebc5280c46293b8925e0516f4801435af94b2167bcbc28b8b8d59`；
- container 状态：running、healthy、restart count 0；
- `/healthz`：`{"status":"ok"}`；
- `/readyz`：`{"status":"ready","database":"ok"}`；
- 部署窗口 `ERROR`、`Traceback`、`CRITICAL` 日志行：0；
- migration、entities、consumer、repository、generation、schema、report 共 7 个关键文件，宿主、容器与本地提交 SHA256 全部一致；
- `SellpointValueV51ConsumerReader`、`SellpointValueV51Repository`、`SellpointValueV51GenerationService`、`SellpointValueV51QaService` import smoke 通过；
- `sellpoint-value-profile-generate --help` 与 `sellpoint-value-profile-ask --help` 通过；
- `.env` SHA256 部署前后均为 `7243971662532eaa036d64f7d73d71920c586286a94df5eacead1713e6e5b56a`。

## 4. 数据零写入与保真

部署前后 V5.1 version 均为 0。下列受保护业务表行数不变：

| 数据域 | 行数 |
| --- | --- |
| 竞品画像 version / profile / pair / relation / selection | 22 / 1,079 / 158,668 / 1,038,163 / 1,708 |
| 采购理由 version / profile / anchor | 7 / 1,751 / 17,899 |
| 用户卖点价值 version / profile / candidate / item | 7 / 691 / 45,070 / 3,123 |

部署期间未发现画像生成进程，没有运行 M03B—M12D，没有修改旧 V5、旧 M12/M13/M14 或竞品画像已发布数据。

## 5. Migration 回滚演练

在再次确认 V5.1 version=0 后，使用已运行 API container 完成真实往返：

1. `0048` downgrade 到 `0047` 成功，V5.1 扩展列全部移除；
2. 四张用户卖点画像表行数保持 `7 / 691 / 45,070 / 3,123`，health/ready 正常；
3. 从 `0047` 再 upgrade 到 `0048` 成功，扩展列和约束恢复；
4. V5.1 version 仍为 0，四张表行数仍保持不变，health/ready 正常。

回滚演练没有删除、重建或发布任何业务画像。

## 6. 下一步

SPV51-G15 只允许在 205 为海信 65E7Q 生成一个明确的 V5.1 draft，并完成保存画像回读、20 款正式竞品与 Top 3、51 款分析参照、直接量价、局部状态、报告和问答验收。G15 通过前不得创建 AC 或全量生成 Goal。
