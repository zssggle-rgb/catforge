# G23 关闭回执

状态：completed

日期：2026-07-14

## 1. Goal

仅将 G22 RC `89929b53edb9c6cdf330e5dc1fad120b385fe00f` 部署到 205，执行 `0046_core3_competitor_profile` migration，验证代码、数据库结构、空表回滚、健康状态和业务数据保护，不生成画像、不发布、不切 current。

## 2. 部署结果

- 服务器：`deploy@123.56.42.205`；应用目录：`/opt/catforge`；
- 部署分支：`new/base-publish-workbench-design`；
- 远端与运行容器代码：`89929b53edb9c6cdf330e5dc1fad120b385fe00f`；
- Alembic：`0045_core3_sellpoint_value_profile` 成功升级至 `0046_core3_competitor_profile (head)`；
- API、Redis、Web 均已重建，restart count 均为 `0`；
- 205 本机 `/healthz` 返回 `ok`，`/readyz` 返回 `ready/database ok`；
- 公网 `:8000` 仍按既有网络策略不可直连，服务端本机检查正常。

## 3. 部署前门禁与回滚点

- 部署前远端 revision：`79e50bfe0bbddb13926517e195a2c0ad19b0d959`；工作树干净；Alembic 为 0045；
- 五张竞品画像表部署前均不存在；数据库没有其他 active session；
- 预部署回滚点：`/home/deploy/catforge-deploy-backups/competitor-profile-g23-20260714_172031`；
- 回滚点包含部署前 Git bundle、Alembic 状态、容器状态、运行环境哈希和 schema-only 数据库备份；
- Git bundle 校验通过；bundle SHA-256 为 `4ef5caa1d78fa8bf076bbb90d799dc996542d6cd3261faf68734277c7b0f6558`；schema 备份 SHA-256 为 `bcc6844bf94093182ddfec757cb6c82330a3d33298adc706babb8ff4a74f3536`；
- 部署前后 `/opt/catforge/.env` SHA-256 一致，没有用本地文件覆盖 205 运行配置。

第一次实际同步在看到 205 浅克隆历史警告后于 migration 和服务重建前安全中止，随即恢复到部署前 revision，并确认 0045、healthz 和 readyz 均未改变。随后通过本地完整提交图确认 `79e50bf` 是 `89929b5` 的祖先，线上四个修复提交已经包含在 RC 中，再执行正式部署。

## 4. 数据库验收

五张新表全部存在且均为 `0` 行：

| 表 | 列 | 外键 | unique | check | 索引 | 行数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `core3_competitor_profile_version` | 48 | 2 | 1 | 16 | 26 | 0 |
| `core3_sku_competitor_profile` | 40 | 3 | 1 | 6 | 22 | 0 |
| `core3_sku_competitor_profile_pair` | 47 | 4 | 1 | 7 | 28 | 0 |
| `core3_sku_competitor_profile_relation` | 36 | 4 | 1 | 4 | 20 | 0 |
| `core3_sku_competitor_profile_selection` | 36 | 5 | 2 | 3 | 21 | 0 |

旧竞品、采购理由和用户卖点价值保护表在部署前后行数完全一致，部署时间之后的 `updated_at` 增量全部为 `0`：

- `core3_competitor_candidate=28`；
- `core3_competitor_result=30`；
- `core3_purchase_reason_profile_version=7`；
- `core3_sku_purchase_reason_profile=1751`；
- `core3_sku_purchase_reason_anchor=17899`；
- `core3_sellpoint_value_profile_version=7`；
- `core3_sku_sellpoint_value_profile=691`；
- `core3_sku_sellpoint_value_candidate=45070`；
- `core3_sku_sellpoint_value_item=3123`。

## 5. 回滚演练

在再次确认五张表全空、没有其他 active database session 后执行：

1. 0046 downgrade 至 0045 成功；
2. 五张新表全部删除，旧保护表行数不变；
3. downgrade 状态下 healthz、readyz 正常；
4. 0045 再次 upgrade 至 0046 成功；
5. 五张新表全部恢复且仍为 0 行；
6. 最终 Alembic current/head 均为 0046。

这证明当前空表阶段可以安全回滚；一旦后续存在画像数据，0046 migration 的 downgrade guard 会拒绝删表，必须走保留数据的 forward-fix 或另行授权方案。

## 6. 代码与运行验收

- migration、entities 和 CLI 三个关键文件的本地、205 仓库、API 容器 SHA-256 完全一致；
- 竞品画像 Reader 与 Repository 容器 import smoke 通过；
- API 最近 30 分钟日志无 `ERROR`、`Traceback` 或 `CRITICAL`；
- 远端 Git 工作树干净；
- 本地 migration 专项测试 `11 passed`，Alembic 为单 head。

## 7. 未执行

- 未执行任何竞品画像生成或批量生成；
- 未写入五张竞品画像表；
- 未执行 review、publish、set-current 或 deprecate；
- 未切换竞品智能体、卡片、两份报告、问答或用户卖点价值消费者；
- 未修改或覆盖旧 M12/M13/M14；
- 未创建或执行 G24。

## 8. 下一 Goal 门禁

G24 只允许为海信 65E7Q 生成一个竞品画像 draft，并回读同一 profile version，验收画像、卡片、两份报告、问答和用户卖点价值消费一致性。G24 仍不得 review、publish 或 set-current；验收失败不得进入 AC 单 SKU G25。
