# SPV51-G13 工程评审

状态：passed

日期：2026-07-17

## 1. 评审结论

V5.1 已形成 typed schema → migration/entities → competitor adapter → question-local calculation → materializer → repository → saved-profile consumer 的完整链路。正式和 preview 读取、immutable hash、事务隔离、V5 历史保护和工厂边界均有测试。预提交评审发现的 4 个问题已修复，没有未解决的 P0/P1。

## 2. 已修复的评审问题

1. 单 SKU consumer 原先先装载整版 profile 大 JSON，再在内存匹配目标；现改为只查询 7 个身份字段，明确 SKU/model 由数据库定向过滤，再对唯一目标做 typed 回读；
2. 版本进度原先逐 SKU 调用 `_read_bundle`，会形成候选/价值子表 N+1；现按 64 SKU 分页，每页批量读取 profile、candidate、item；130 SKU 回归限定不超过 15 次 SELECT；
3. 产品经理可见短答、Markdown 和飞书卡片正文原先混入版本、hash 和候选范围编号；现只在结构化 metadata/audit 字段保留，正文只呈现业务答案；
4. 能力目录原先宣称支持版本变化，CLI 的 `compare_profile_version` 实际没有双版本 id 合同；现能力目录不再宣传，显式传入时返回错误，不静默忽略或跨版本回退。

## 3. 数据与状态安全

- V5.1 版本、SKU、候选和值项沿用既有唯一约束；create/write 处理并发唯一键冲突并核对 immutable fingerprint/hash；
- 每个 SKU 使用 savepoint，失败只回滚本 SKU；版本汇总记录 generation failure、缺失、意外 SKU、typed readback/hash 和悬空引用错误；
- formal 只读取 V5.1 current published；preview 必须同时锁定 `profile_version` 与 version id；不回退 V5、旧 M12/M13/M14 或其他 draft；
- repository 每次 typed 回读重算 input fingerprint、result hash，核对竞品画像 version/hash、candidate pool hash、持久化投影和悬空 SKU 引用。

## 4. 测试、覆盖率与性能

- sellpoint-value 与 competitor-profile consumption 完整回归：796 项通过，0 failure/error/skip，JUnit 总耗时 344.714 秒；
- 目标模块覆盖率 90%；V5.1 consumer 80%、QA 95%、repository 88%、报告 90%；
- 20 正式竞品 + 51 分析参照的保存画像读取：候选不截断，最多 8 次 SELECT、读取段小于 2 秒、峰值内存小于 32 MiB；JUnit 含 fixture 生成总耗时 2.255 秒；
- 130 SKU 版本进度回归：最多 15 次 SELECT，JUnit 总耗时 1.426 秒，证明查询量按页增长而不是按 SKU 子表增长；
- migration upgrade/downgrade、V5 历史保护、SQLite/PostgreSQL DDL 合同测试均通过；Alembic head 为 `0048_core3_sellpoint_value_profile_v5_1`；
- 全部 V5.1 Python、migration、相关报告/路由文件 Ruff 与 `py_compile` 通过，新增文件格式检查和 `git diff --check` 通过。

## 5. 已知非阻断项

- 测试输出中的 `datetime.utcnow()` 与 Starlette TestClient/httpx 警告来自既有基础设施，不由 V5.1 引入；不影响本次功能正确性，后续可独立升级；
- 当前任务合同禁止并发数据库生成；进程内 generation lock 与数据库唯一约束/行锁共同保护当前串行路径。若未来允许多进程同时生成同一版本，需要另行设计数据库级任务租约，不在本次授权范围内。
