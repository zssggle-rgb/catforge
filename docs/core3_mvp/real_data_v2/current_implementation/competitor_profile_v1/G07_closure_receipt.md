# 竞品画像 V1 G07 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_repositories.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_persistence_schemas.py`：补充数据库主键回读字段；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_repository.py`。

## 2. 已实现能力

1. 幂等创建 draft 版本，同业务键但不可变输入不同则拒绝覆盖；
2. 单 SKU 的 profile、pair、relation、selection 五表单事务写入；
3. 相同 draft bundle 重试幂等，主画像或子记录结果变化时拒绝原地覆盖；
4. 版本、SKU 画像和完整五表 bundle 回读；
5. SKU 轻量进度列表；
6. pair、relation、selection 分页查询，并支持候选状态、关系状态、选中状态等过滤；
7. project、category、version、release scope 一致性保护；
8. 非 draft 版本拒绝通过本 Repository 写入。

## 3. Repository 边界

- 本 Goal 只实现 draft 持久化和查询；
- 未实现 review、publish、current、deprecated 状态转换；
- 未实现竞品召回、关系判定、关键竞品选择等业务算法；
- JSON 列使用 JSON-safe 序列化，数据库 Numeric 列继续保留 typed Decimal；
- 正式消费者仍不得通过本 Repository 回退读取 draft。

## 4. 验证

- Repository tests：8 passed；
- G05 schema + G06 migration + G07 Repository：43 passed；
- Repository coverage：92%；
- 五表完整 round-trip：通过；
- draft 幂等与不可变保护：通过；
- project/category scope isolation：通过；
- pagination/filter：通过；
- Ruff：通过；
- `git diff --check`：通过。

## 5. 状态变化

- 本地业务数据库写入：无，仅使用内存 SQLite 测试；
- 205 数据库写入/migration：无；
- 业务算法：无；
- 部署：无；
- draft/review/publish/current：均未修改；
- Git 暂存/提交：无。

## 6. 下一 Goal

允许创建 G08，只实现版本 lifecycle 的 review、publish、current、deprecated 边界、scope-lock/CAS 与失败回滚测试；不得实现竞品算法、写入 205 或部署。
