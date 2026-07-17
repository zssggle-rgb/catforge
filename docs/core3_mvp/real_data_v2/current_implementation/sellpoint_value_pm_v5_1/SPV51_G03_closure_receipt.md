# SPV51-G03 Typed Schema 与低门槛配置关闭回执

状态：completed

日期：2026-07-17

## 1. 实现结果

- 新增独立 V5.1 schema/rule/method/config 版本，不修改旧 V5 schema；
- 锁定竞品画像 formal/preview source envelope、完整候选、source rank、selected rank、角色、业务得分和 pair hash；
- 锁定问题级 candidate use，usable/unavailable 维度互不覆盖，未选候选必须给本题拒绝原因；
- 锁定四状态和四层量化；`no_conclusion` 不得自动 review；
- 直接量价支持 1 个对照 `single`、2—4 个 `small_group`、5 个及以上 `group`；
- 基础能力样本不足只能是 `not_assessed`，不 review；
- strict WTP、synthetic 和 market archetype 都不能成为 profile/release 必需项；
- release quality 只因覆盖、生成、invalid、隔离、重复、悬空引用或 hash 完整性失败而 blocked。

## 2. 产物

- `sellpoint_value_profile_v5_1_schemas.py`；
- `sellpoint_value_profile_v5_1_config.py`；
- `test_sellpoint_value_profile_v5_1_schemas.py`；
- `SPV51_G03_schema_contract.json`。

## 3. 验证

- V5.1 schema/config 专项与旧基础能力必要回归：43 项通过；
- ruff check/format、py_compile、diff check 通过；
- 未执行 migration、数据库或 205 写入；
- 完整回归、覆盖率和性能仍集中在 SPV51-G13。

## 4. 下一步

SPV51-G04 只按本合同实现最小 migration 与 entities；不得把 JSON 明细全部拆列，也不得修改旧 V5 已保存行。
