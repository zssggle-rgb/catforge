# SPV51-G04 Migration/Entities 关闭回执

状态：completed

日期：2026-07-17

## 1. 实现结果

- 新增 Alembic head `0048_core3_sellpoint_value_profile_v5_1`，只扩展既有 version、SKU profile 和 value item 三张表，没有新增问题表、量化表或候选表；
- version 保存竞品画像来源 version id/method/result hash、四类 SKU 结论分布和 integrity error 计数；
- SKU profile 保存结论状态及 conclusion/partial/no_conclusion/invalid 计数；
- value item 保存结论状态和直接市场量价结果是否可用；
- 问题级候选、四层量化、证据和限制仍保存在现有 typed JSON 字段中；
- 新字段全部可空以保护 V5 历史行，只有 method 为 V5.1 时才由条件约束要求来源、状态和计数完整；
- V5.1 downgrade 在任何 V5.1 method 行或新增 payload 非空时先明确阻断，要求先清理 V5.1 draft，不会静默丢列；
- 已有 published/current 部分唯一索引在 SQLite 重建后保留，仍保证同一 project/category/batch 只有一个正式 current 版本。

## 2. 迁移边界

- `source_competitor_profile_version_id` 使用可检索的来源标识和 version/hash 完整性合同，不增加数据库外键；原因是历史 `0045` 会先于 `0046` 创建 SPV 表，增加跨表外键会破坏 PostgreSQL 全新迁移链；
- 来源版本是否真实存在、类目/项目是否一致及 hash 是否匹配，由 G05 Reader Adapter 和 G11 repository/materializer 做强校验；
- SQLite 开启外键时，migration 先捕获 profile/candidate/item 全部历史行，按依赖顺序临时清空，完成父子表重建后原样恢复；PostgreSQL 使用原生 `ALTER TABLE`，不执行该复制路径；
- 未实现 Reader Adapter，未连接或写入 205，未修改旧 V5 已保存行。

## 3. 验证

- V5.1 migration 专项：5 项通过，覆盖实体/迁移合同、SQLite 外键开启的 upgrade/downgrade/idempotent、V5 历史行逐表保护、条件约束、current isolation、downgrade blocker、SQLite/PostgreSQL DDL 编译和不完整旧 schema 预检；
- 旧 V5 persistence 必要回归：16 项通过，唯一键、发布状态机、旧 bundle 写入和隔离行为保持；
- Alembic 唯一 head 为 `0048_core3_sellpoint_value_profile_v5_1`；
- touched Python files 的 ruff check、py_compile 通过；新增 migration/test 文件的 ruff format check 通过；diff check 通过；
- 完整回归、覆盖率、性能和三类总评审仍集中在 SPV51-G13。

## 4. 下一步

SPV51-G05 只实现正式/预览竞品画像 Reader Adapter：formal 读取 current published agent snapshot v2，preview 显式锁定版本，并禁止回退旧 M12/M13/M14 或现场重算竞品集合。
