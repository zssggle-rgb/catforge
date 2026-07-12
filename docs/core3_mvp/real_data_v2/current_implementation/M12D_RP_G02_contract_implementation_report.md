# M12D-RP-G02 Typed Contract 与兼容层执行报告

- 日期：`2026-07-11`
- 范围：仅实现共享 contract、schema、ORM、migration 和历史兼容读取。
- 未实现：购买阻力计算、成立度门槛、角色收敛、竞品智能体改造、部署和发布。

## 1. Contract

- 成立状态：`unassessed / established / established_limited / proposition_only / rejected`。
- 用户承接：`unassessed / user_validated / user_supported / market_supported / not_observed`。
- 压力等级：`unassessed / none / low / medium / high / critical`。
- 压力类型：局部负面、正负并存、负面占主导、M12C 价值阻力、市场不确定、事实证伪、证据错配。
- 压力记录包含锚点、方面、正负数量、主导方向、是否限制成立/比较、中文说明和证据引用。
- 比较限制明确区分锚点、市场、金额/WTP、替代和排名范围。

## 2. 历史兼容

- 历史 anchor 缺少新字段时读取为 `establishment_status=unassessed`、`user_validation_status=unassessed`、`pressure_level=unassessed`。
- `core_eligible` 为 `null`，不猜成 `false`；`establishment_score` 为 `null`，不补零。
- profile 新增已成立锚点、产品主张锚点、压力汇总和比较限制，历史值均为空集合。
- 当前 `role`、`evidence_strength`、`risk_flags_json` 和现有发布消费行为保持不变。

## 3. 存储与读取

- 新 migration：`0044_core3_m12d_reason_pressure`，唯一 Alembic head。
- profile 新增 4 个兼容字段；anchor 新增 12 个兼容字段。
- downstream contract 暴露成立、承接、核心资格、压力和比较限制。
- 不向 downstream 暴露原始/调整分、域分值、角色推导、降级内部码、输入指纹或 taxonomy 生成方法。

## 4. TV/AC 影响

| 品类 | profile 默认迁移 | anchor 默认迁移 | 业务结论变化 | 未影响回归 |
| --- | ---: | ---: | ---: | ---: |
| TV | 377 | 3,542 | 0 | 20 |
| AC | 155 | 1,879 | 0 | 20 |

允许迁移仅为历史行获得 `unassessed/null/empty` 默认值；G02 不产生任何 established、proposition 或 pressure 业务结论。

## 5. 验证

- G02 contract、非法枚举、历史兼容、TV/AC 共享契约、migration 和 export boundary：`10 passed`。
- 现有 M12D 画像与质量契约回归：`65 passed`。
- 竞品 reader 与锚点替代性回归：`11 passed`。
- 合计：`86 passed`，`0 failed`。
- Python 编译、`git diff --check` 和 Alembic 单 head 检查通过。

## 6. 下一步边界

G03 只能在本 contract 上实现购买阻力的独立计算和同锚点负面作用域；不得在 G03 提前实现 G04 的 9/8/7 成立门槛。
