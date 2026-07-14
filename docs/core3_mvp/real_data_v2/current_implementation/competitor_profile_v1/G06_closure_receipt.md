# 竞品画像 V1 G06 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/models/entities.py`：新增五个竞品画像实体；
- `apps/api-server/alembic/versions/0046_core3_competitor_profile.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_migration.py`。

## 2. 已实现表

1. `core3_competitor_profile_version`；
2. `core3_sku_competitor_profile`；
3. `core3_sku_competitor_profile_pair`；
4. `core3_sku_competitor_profile_relation`；
5. `core3_sku_competitor_profile_selection`。

## 3. 关键约束

- 版本业务键和同 release scope 单一 current published partial unique index；
- category/product category、状态计数、每 SKU 最多 3 selection、每 pair 最多 7 relation check；
- profile、pair、relation、selection 的业务唯一键；
- target 与 candidate 不同、candidate/reference 至少一种 membership；
- reference-only/review/blocked 不能 selected；
- 七类 relation code/status、selection rank 1—3、decision topic typed check；
- version→profile→pair→relation/selection 使用 draft 删除 cascade；
- migration downgrade 在任一新表有数据时拒绝执行，避免删除历史画像。

## 4. 验证

- migration/entity tests：10 passed；
- G05 schema + G06 migration：35 passed；
- upgrade + empty downgrade：通过；
- populated downgrade refusal：通过；
- constraints/indexes/cascade：通过；
- Alembic 单 head：`0046_core3_competitor_profile (head)`；
- Ruff：通过；
- Python syntax：通过；
- `git diff --check`：通过。

## 5. 状态变化

- 本地业务数据库写入：无，仅使用内存 SQLite 测试；
- 205 数据库写入/migration：无；
- repository/业务算法：无；
- 部署：无；
- draft/review/publish/current：均未修改；
- Git 暂存/提交：无。

## 6. 下一 Goal

允许创建 G07，只实现 Repository 的版本、profile、pair、relation、selection draft 写入与回读，不实现 lifecycle 状态转换，不写 205。
