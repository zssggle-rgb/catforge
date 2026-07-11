# V5-G08 独立工程复核

## 结论

`PASSED FOR RC7 DEFAULT-OFF DEPLOYMENT`。

P0=0，P1=0，P2=2。

## 本地门禁

- V5：73 passed；V5+V4 related：137 passed；analyst CLI：88 passed；
- V5 总覆盖率 93%，answer 87%，service 93%，realization 98%；
- ruff、compileall、JSON 解析和 diff check 通过；
- 目标运行文件工作区无未提交修改；只提交 G08 自己产生的文件。

## 205 工程门禁

- 宿主机和容器 9/9 文件与 RC7 hash 一致；
- healthz=`ok`，readyz=`database ok`，容器 healthy、restart count 0；
- 无 flag 在 CLI 建立 session 前返回，session/query count=0；自然语言仍路由 V2；
- 显式 65E7Q 查询数 30，候选数量变化不产生逐候选 SQL；
- 18 SKU 暖进程核心 P95 1.19 秒，最大 1.201 秒；
- 单次带 tracemalloc 75.429 MB，低于 80 MB 门槛；
- report DTO 88,586—188,661 bytes；最终 65E7Q CLI JSON 约 251 KB；
- 部署前后 `tup_inserted=71,452,125`、`tup_updated=15,440,877`、`tup_deleted=7,400,628`，业务写入增量 0；
- V2 业务结果仅保留既有 generated_at 可变字段，V4 result hash 维持 `5bca5457…`；
- 回滚到部署前实际文件后入口消失、健康正常；重新恢复 RC7 后 9/9 hash 与健康正常。

## P2

1. 205 宿主仓库仍有大量既有未提交改动；本次依赖逐文件 RC 与逐文件 rollback，不以远程 Git HEAD 为回滚真值。
2. 公网 `:8000` 仍不可直连，验收使用服务器本机端点、容器 CLI 和飞书真实文档。
