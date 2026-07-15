# G30 竞品画像 V1.1 Migration/Entities 关闭回执

状态：completed

日期：2026-07-15

## 1. Goal

在不连接业务数据库、不访问 205、不生成画像、不修改 Repository/Reader、竞品算法、旧 M12/M13/M14 或 V1 草稿、不执行 review/publish/current 的前提下，实现竞品画像 V1.1 的数据库表、扩展列、约束、索引、upgrade/downgrade guard 和兼容测试，原样落地 G29 冻结合同。

## 2. 已完成的数据库合同

新增并冻结：

- `core3_competitor_profile_sku_snapshot` 共享 SKU 快照表；
- version 四列唯一键 `(competitor_profile_version_id, project_id, category_code, release_scope_key)`；
- snapshot 到 version 的同四列复合外键及 `ON DELETE CASCADE`；
- snapshot 的 version/SKU 唯一约束、TV/AC category check、V1.1 schema check、AuditMixin 字段和读取索引；
- profile 的 summary、fact index、evidence index、result hash 和三类统计列；
- pair 的 scope、hard exclusion、target/candidate snapshot ref、完整 analysis、score/available weight、review 和问题级选择列；
- relation 的 V1.1 status 与独立 review items；
- selection 的 policy、score、available weight、strength、role 和 score breakdown；
- full/compact/question-specific 所需的 version/target/candidate/status 读取索引。

所有 V1.1 扩展列保持 nullable，以兼容 V1 历史行；V1.1 conditional checks 再按 schema version 强制完整性。

## 3. Scope、Strength、Review 与选择约束

- scope 只允许 `analyzable` / `excluded`；
- hard exclusion 只允许 `self_pair`、`project_mismatch`、`category_mismatch`、`candidate_outside_manifest`、`identity_decode_failed`；
- self pair 必须保存为 `excluded + self_pair`，非 self pair 不得冒用 `self_pair`；
- excluded pair 不得保存伪造 score/available weight，strength 必须为 `unknown`；
- analyzable pair 的 available weight 和 score 使用冻结范围，available weight 为 0 时 score 必须为 null；
- 所有 V1.1 nullable enum、strength、score、review、question 和 relation 必填列均显式 `IS NOT NULL`，不能利用 SQL `CHECK(NULL)` 绕过；
- V1.1 `selected=true` 只接受 analyzable scope、合法问题和非 unknown strength；旧 `candidate_status` 不参与 V1.1 选择；
- relation status 只接受 passed/limited/unassessable/failed，review items 独立保存。

## 4. 历史 Migration 与 V1 兼容

独立工程复核发现原 0046 revision 直接 import 当前 ORM，导致历史 revision 会随 entities 漂移。为避免同一个 0046 stamp 对应不同数据库结构，本 Goal 将 0046 改为自包含的冻结 V1 DDL；0047 snapshot DDL 同样自包含，不再 import 当前 ORM。

验证结果：

- 正式 0046 节点没有 snapshot、V1.1 扩展列、V1.1 checks 或 version scope identity index；
- 冻结 0046 与 G30 前 V1 entities 的 SQLite/PostgreSQL CreateTable/CreateIndex 完全一致；
- 第二次 0047 upgrade 不重复建表或重建已一致 checks；
- V1 完整五表行经过 0047 upgrade、二次 upgrade、强制四子表恢复和 downgrade 后逐表状态一致；
- SQLite SQL NULL 与 JSON literal null 分别保存和恢复，不互相改写；
- downgrade 恢复 V1 的 distinct、selected 和 relation primary checks。

## 5. Typed JSON 形状

数据库实体与 G29 Typed Schema 对齐：

- SKU `snapshot_json`：dict；
- `module_availability_json`：list；
- `source_lineage_json`：dict；
- profile `analysis_fact_index_json`：dict；
- profile `analysis_evidence_index_json`：dict；
- evidence/review/role 等集合字段：list。

测试执行了 snapshot ORM roundtrip，并验证 module availability 与 source lineage 的实际回读形状。

## 6. Downgrade Guard

以下任一条件存在时，0047 downgrade 明确拒绝：

- version 行使用 V1.1 schema version；
- version 行使用 V1.1 rule version；
- version 行使用 V1.1 method version；
- snapshot 有持久化行；
- profile、pair、relation 或 selection 任一 V1.1 扩展列有值。

仅存在旧 V1 行时允许回退，且 V1 五表行、约束和索引保持可用。

## 7. 验证与评审

- migration 专项与旧 0046 回归：30 passed；
- 全部 `test_competitor_profile*.py`：350 passed；
- 0046/0047 migration branch coverage：92%；
- SQLite/PostgreSQL 双方言 CreateTable/CreateIndex compile：passed；
- frozen 0046 与 V1 entity shape/type/nullability/check/index 对账：passed；
- 真实 0046→0047→0046 全字段及 JSON null-kind 保真：passed；
- 重复 upgrade 幂等与零重复 index：passed；
- Ruff：passed；
- Python compileall：passed；
- `git diff --check`：passed；
- Alembic：`0047_core3_competitor_profile_v1_1` 为唯一 head；
- 独立方法复核：P0=0、P1=0、P2=0，可关闭；
- 独立工程复核：P0=0、P1=0，可关闭；P2 仅建议在 G39 固化已部署 0046 DDL golden hash，不阻塞 G30。

本轮 review 技能促使实现补齐 self-pair 持久化、SQL UNKNOWN 防绕过、历史 migration 自包含和 SQL NULL/JSON null 保真，而不只检查测试是否为绿色。

## 8. 写入与运行边界

- 业务数据库读取或写入：0；
- 205 访问、部署或 migration：0；
- 画像生成：0；
- Repository/Reader/竞品算法修改：0；
- 旧 M12/M13/M14 或 V1 草稿修改：0；
- review/publish/current/deprecated 状态切换：0；
- 飞书消息、卡片、报告或文档：0；
- git stage/commit：0；
- 用户已有卖点价值修改和其他未跟踪文件未触碰。

## 9. 下一 Goal

G31：实现 V1.1 Repository 与 Reader。必须原子写入和完整回读 snapshot/profile/pair/relation/selection；`target_snapshot_ref` / `candidate_snapshot_ref` 必须解析到同一 version/scope 的共享 snapshot，任何悬空引用 fail-closed；同时保持 V1/V1.1 reader 分流和 formal published / explicit draft preview 边界。

G31 尚未创建，必须由下一次 heartbeat 在确认没有 active Goal 后创建。
