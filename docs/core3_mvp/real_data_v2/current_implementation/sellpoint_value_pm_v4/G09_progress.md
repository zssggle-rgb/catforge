# G09 进度：不可变 RC 与 205 默认关闭影子验收

## 目标与边界

- 唯一代码基线：`1653bff5bf3eb1f66da262a5dcddd1203ccbc9bd`；
- RC：`sellpoint-value-pm-v4-rc1-1653bff`；
- 部署范围：9 个完整运行时文件，禁止同步本地工作树、禁止 `--delete`、禁止覆盖范围外文件；
- 运行边界：V4 feature flag 默认关闭，自然语言默认路由关闭，只允许显式 `sellpoint-value-pm-v4 --enable-v4`；
- 数据边界：只读分析，数据库与服务业务写入必须为 0；
- 发布边界：G09 只给出 G10 准入建议，不进入 G10，不切默认路由。

## 任务状态

1. `[completed]` 冻结 RC、精确变更清单、文件 checksum、部署包和线上逐文件回滚包；
2. `[completed]` 记录 205 部署前 commit、配置边界、health/ready、进程和数据库写计数；
3. `[completed]` 默认关闭影子部署，复核 health/ready、V2 默认路由与显式 V4；
4. `[completed]` 65E7Q 与五 cohort 双跑 hash、跨载体、金额边界、异常语义、性能/并发/写边界；
5. `[completed]` 回滚演练并恢复 RC；G09 验收通过，G10 默认路由暂不建议准入。

## 205 部署前事实

- 仓库 HEAD：`5fe4851cab098a613ce9ad0e88c1f9974f22a748`；分支 `new/m12c-claim-value-analysis`；
- 服务器工作树 dirty count：108；目标 9 文件中已有 6 个未提交热修；
- `healthz={"status":"ok"}`；`readyz={"status":"ready","database":"ok"}`；
- 旧线上 CLI 没有 V4 `ROUTER_COMMANDS` 合同，V4 影子入口尚不可用；
- API 容器 `catforge-api-1` 为 `running/healthy`、重启次数 0；
- 部署前数据库累计计数：`xact_commit=338239`、`xact_rollback=9012`、`tup_inserted=71452125`、`tup_updated=15440877`、`tup_deleted=7400628`；
- 因线上存在未提交热修，回滚真值必须是部署前逐文件内容与 SHA-256，而不是服务器 Git HEAD。

## RC 冻结结果

- 包：`sellpoint-value-pm-v4-rc1-1653bff.tar.gz`；
- SHA-256：`8c1b62ddde63add4196cb424856a06269870c4720fbcba55a2d46b45d0925b95`；
- 大小：132,256 bytes；
- 内容：9 个完整运行时文件 + 1 个包内 manifest；
- `2a985f8..1653bff` 精确变化：22 文件，1,717 insertions、62 deletions；影子部署不直接使用该 diff，而使用 closure commit 的 9 个完整文件。

## 立即停止条件

health/ready 异常、默认路由泄漏、连续运行 hash 不一致、Q5 v2 门禁越级、M12C 旧金额进入、真实 SKU 异常金额、数据库业务写入、范围外文件变化，任一出现即停止并恢复部署前 9 文件。

## 最终状态

- 205 处于 RC 影子态，API `running/healthy`；
- 无 flag 拒绝，自然语言默认路由仍为 `sku-claim-value`；
- 65E7Q 与 C01-C05 双跑确定；
- 真实飞书文档已发布并回读；
- 数据库 tuple 写计数前后不变；
- 回滚与 RC 再恢复演练通过；
- G09 passed，G10 default route not recommended until live lineage and counterfactual availability are repaired.
