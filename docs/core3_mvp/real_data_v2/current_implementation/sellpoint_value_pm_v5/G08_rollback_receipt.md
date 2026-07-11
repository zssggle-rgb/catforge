# V5-G08 205 回滚演练回执

## 回滚真值

- 远程 Git HEAD：`5fe4851cab098a613ce9ad0e88c1f9974f22a748`，但工作树已有 112 项改动，未作为回滚依据；
- 回滚包：`/tmp/catforge-v5-g08-predeploy.tar.gz`；
- SHA-256：`b1438a82ec80ece126649159b707befb8e79dfd2869100c7aef636f8e1ac1c37`；
- 宿主机和容器各有 4 个部署前实际文件、5 个明确 absent 文件；
- 部署前 CLI 不包含 `sellpoint-value-pm-v5`。

## 演练

1. 精确恢复 4 个原文件，删除部署前不存在的 5 个 V5 文件；
2. 重启 API，healthz/readyz 正常，V5 命令回到“invalid choice/入口不存在”的部署前状态；
3. 使用 RC7 包恢复 9 个运行文件；
4. 重启 API，默认关闭提示恢复；
5. 宿主机与容器 9/9 文件 hash 一致，容器 healthy；
6. 数据库 tuple 写计数前后相同。

## 最终状态

205 已恢复到 RC7 默认关闭影子态；未切默认路由，未修改数据库业务数据。
