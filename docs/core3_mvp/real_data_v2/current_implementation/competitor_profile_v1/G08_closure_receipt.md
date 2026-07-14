# 竞品画像 V1 G08 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_lifecycle.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_repositories.py`：增加按 version ID 的 scope-safe 版本读取；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_persistence_schemas.py`：增加持久化行与 typed payload 的 fingerprint/hash 一致性约束；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_lifecycle.py`；
- 对应 schema、repository 测试更新。

## 2. 已实现状态机

```text
draft -> review -> published -> deprecated
                       |
                       +-- 独立 set_current / unset old current
```

- review、publish、set_current、deprecated 均有独立 actor/time 审计；
- review 后四类 analytical child rows 全部冻结；
- publish 只改变发布状态，不自动成为 current；
- set_current 只接受 published，并要求 expected-current CAS；
- 同 release scope 的 current 切换先锁 project/category 稳定行，再锁 scope versions；
- 清旧 current 使用保存点内即时条件 UPDATE，之后才设置新 current，避免唯一索引写入顺序不确定；
- CAS 冲突或中途异常时旧 current 和全部 child current 标记保持不变；
- current published 不允许 deprecated，必须先在同一显式切换中由替代版本接管；
- deprecated 保留版本及全部历史 child rows。

## 3. review 与发布门禁

- review 校验 authoritative SKU/profile 数、ready/partial/blocked/failed 计数；
- 校验 pair/relation/selection 数量、每 pair 七种关系、selection rank 连续、selected pair 与 selection 一致；
- 校验 version 与五表 project/category/storage batch/release scope/version 全链路一致；
- 校验 profile/pair/relation/selection 持久化 hash 与 typed payload 回读一致；
- `ready` 要求全量 ready 且无 review-required rows；
- `limited` 要求覆盖完整、存在真实 partial、无 blocked/failed，并在 publish 时显式 `allow_limited`；
- `blocked` 必须有具体完整性或质量原因；
- publish 和 set_current 均要求非 system 的明确审批人。

## 4. 禁止行为已覆盖

- draft 直接 published/current；
- unassessed 或未知 quality 进入 review；
- review/current；
- publish 自动 current；
- current CAS 不一致时覆盖旧 current；
- current 版本直接 deprecated；
- review 后原地改写 analytical child rows；
- project/category 跨 scope 读取和转换；
- published/deprecated 元数据通过不同 actor/reason 原地改写。

## 5. 验证

- lifecycle tests：10 passed；
- G05—G08 schema/migration/repository/lifecycle：57 passed；
- lifecycle coverage：90%；
- CAS 成功、stale expected conflict、注入失败回滚：通过；
- current 唯一索引切换顺序重复验证：2/2 通过；
- ready/limited/blocked review quality：通过；
- hash/scope/cardinality/selection QA：通过；
- Ruff：通过；
- `git diff --check`：通过。

## 6. 状态变化

- 本地业务数据库写入：无，仅使用内存 SQLite 测试；
- 205 数据库写入/migration：无；
- 现有画像 review/publish/current/deprecated：均未执行；
- 竞品召回、关系判定和选择算法：未实现；
- 部署：无；
- Git 暂存/提交：无。

## 7. 下一 Goal

允许创建 G09，只实现新版已发布上游输入 bundle、source authority/version lock、missing-is-unknown、lineage 和 TV/AC scope gate；不得实现候选召回算法、写入 205、部署或切换任何发布状态。
