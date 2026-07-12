# M12D-RP-G09 提交部署报告

- 完成时间：`2026-07-12T08:56:54+08:00`
- 分支：`new/base-publish-workbench-design`
- 功能提交：`67a11d6`
- migration 修复提交：`adeab0a`
- 205 部署 revision：`adeab0a1c8b5b05b3abfd1a29d893b038a5d4a96`

## 提交前验证

- M03B-M12D、竞品 reader、CLI、报告和 TV/AC 隔离：`378 passed`。
- 静态清理后受影响模块：`84 passed`。
- JSON GIN migration 修复：`32 passed`。
- ruff、compileall、Alembic 单 head 均通过。

## 回滚点

- 路径：`/var/backups/catforge/m12d-rp-g09-20260712_084936`
- 大小：`180M`
- 内容：三张 M12D 表的 custom-format dump、全库 schema、运行环境、应用源码、远端 Git 工作树和 index patch、远端运行产物。
- 校验：SHA256 全部通过，`pg_restore -l` 通过。

## 部署过程

1. 第一次同步在 checkout 前停止：205 仍有历史热修复脏工作树，未构建、未迁移、未重启。
2. 备份远端热修复和运行产物后，按部署脚本的干净工作树策略切换到已提交分支。
3. 第一次 migration 因 PostgreSQL `json` 列不能直接建立 GIN 索引而事务回滚，数据库保持 `0042`，旧服务保持运行。
4. 将 GIN 索引改为 `json::jsonb` 表达式索引，补测试并提交 `adeab0a`。
5. 最终完整部署成功，migration 升级至 `0044_core3_m12d_reason_pressure`，API/web/Redis 重建完成。

## 上线验证

- profile 新字段：`5/5`；anchor 新字段：`12/12`；索引：`5/5`。
- 三张 M12D 表部署前后保持 `687 profiles / 7057 anchors / 3 versions`，最大更新时间不变。
- 历史 profile 的成立理由/产品主张默认为空；历史 anchor 的成立度/购买阻力均为 `unassessed`，没有猜测新语义。
- current/published 未切换，没有执行 TV/AC 正式全量重跑。
- 代码仓库与运行容器关键文件 hash 一致；新模块 import smoke 通过。
- API 日志无 ERROR/Traceback；205 本机 `/healthz` 为 `ok`，`/readyz` 为 `ready/database ok`。
- 公网 `:8000` 仍按既有网络策略不可直连，不属于本次回归。

## 下一步

G09 已完成。G10 将在 205 正式全量重跑 TV/AC，并按品类分别达到发布门槛后切换 current；该步骤涉及生产数据发布，仍需明确批准。
