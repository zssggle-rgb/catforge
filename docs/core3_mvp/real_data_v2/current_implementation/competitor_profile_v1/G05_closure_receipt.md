# 竞品画像 V1 G05 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_persistence_schemas.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_schemas.py`。

## 2. 已实现合同

1. 5 个证据族、7 类关系、8 个业务问题、7 类 reference purpose 和 4 个重点决策主题均为 typed enum；
2. serving scope 支持 TV 多 source batch 和 AC 单 source batch，强制 project/category/taxonomy/authority 一致；
3. unknown gate 使用 `passed=null`，禁止变成 false；量价缺失保持 null；
4. `causal_claim` 固定为 false；
5. pair 强制恰好 5 个证据族、7 个关系和 8 个问题结果；
6. competitor/reference membership、candidate status、selection 可用性互相校验；
7. 重点竞品支持 0—3，rank 连续且不允许无 pair 的 selection；
8. `no_priority_competitor` 与 `insufficient_evidence` 类型约束分开；
9. draft scope、version count、published/current actor 边界已 typed；
10. persistence bundle 强制 scope 一致、pair 唯一、每个 pair 七关系完整；
11. formal read 只允许 current published，draft 必须 preview；
12. runtime boundary 递归阻止 prompt、Gold Set 和调参样本字段。

## 3. 验证

- schema tests：25 passed；
- 分析 schema coverage：92%；
- 持久化 schema coverage：87%；
- 合计 coverage：90%；
- Ruff：通过；
- Python syntax：通过；
- `git diff --check`：通过；
- 外部 LLM/API：未调用。

## 4. 状态变化

- migration/entities：无；
- repository/lifecycle：无；
- 本地/205 数据库写入：无；
- 部署：无；
- draft/review/publish/current：均未修改；
- Git 暂存/提交：无。

## 5. 下一 Goal

允许创建 G06，只实现五张新表的 SQLAlchemy entities、Alembic migration 与 upgrade/downgrade/约束/索引测试。G06 不实现 repository、不写 205、不部署。
