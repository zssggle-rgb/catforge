# G05 关闭回执：卖点级反事实与可比性门禁

## Objective

基于 G03 V4 context 与 G04 reason/value/bundle link，构建 base-value、same-value、stretch-benchmark 三类卖点级候选，保留 M14、competitor-set fallback、M12C pool、same-family provenance；在价值战场、尺寸、周、平台共同市场单元上完成价格重叠、促销、其他 bundle 差异、体验可比性与 A/B/C/unusable 分级。本 Goal 不计算选择贡献、价格承接或 WTP。

## 前置输入

- G04 核心实现 commit：`7cc39fa`；
- G04 closure commit：`4132077`；
- G05 Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`；
- G05 timer：`catforge-v4-g05-10`。

## 实际产物

- 扩展 `claim_value_pm_v4_schemas.py` 的 G05 typed contracts；
- 扩展 `claim_value_pm_v4_service.py` 的候选角色、市场共同单元与隔离门禁；
- 新增 `test_claim_value_pm_v4_counterfactual.py`；
- 更新 `G05_progress.md`；
- 本关闭回执；
- `G05_artifact_manifest.json`。

未修改 repository/数据库/205、V2 registry、CLI/路由或 PM renderer。

## 业务合同

1. 反事实单位是“采购理由对应的卖点组合”，不是把评论逐条折算金额；
2. base-value 表示候选价值档位低于目标，same-value 表示同档，stretch 表示高于目标；
3. 已观察档位关系优先于召回 slot；二者冲突时按事实角色输出并降级；
4. 高等级比较必须同尺寸、同战场，并具有相同周和平台的共同在售单元；
5. 价格仅判断共同单元观测范围重叠，不外推、不插值、不生成支付意愿；
6. 其他 bundle 差异过多、关键 unknown、促销清洁单元不足均降级；
7. inventory 只能标记 `unavailable`，不能声称已控制；
8. same-value 不能证明目标卖点的增量价值；stretch 不能替代 base-value；
9. A 级 base pair 只获得进入 G06 Q5 总门禁的资格，最终仍要求至少两条独立 pair 且跨两个 model family；
10. 完全共线时沿用 G04 bundle，不拆任何成员的单项 WTP；
11. M12C 只作候选 pool/tier 线索，旧金额完全不参与召回、评分或分级。

## 测试结果

| 验证 | 结果 |
| --- | --- |
| G05 counterfactual tests | 11 passed |
| G03 + G04 + G05 + V2 定向回归 | 55 passed |
| G04 + G05 service coverage | 91% |
| G05 runtime schema vs G02 contract | exact match |
| Ruff | passed |
| py_compile | passed |
| `git diff --check` | passed |
| G01 C01-C05 replay | passed |
| 65E7Q fallback replay | 三角色保留；无逐周 cell 时保持不可量化 |
| forbidden scope | 无旧金额、选择曲线、价格建议、工作清单或数据库写入 |

## 已知边界

- G01 65E7Q 脱敏 fixture 只有汇总市场表现，没有逐周平台 cell；G05 因此只验证候选角色与 provenance，不伪造隔离等级；
- C01 以基础款 75E5Q 为目标时，75E5Q-PRO 是 stretch；反向以 PRO 为目标时，基础款才是 base-value；
- `eligible_quantification_levels` 中的 Q5 只表示单 pair 通过前置资格，绝不表示最终 WTP 已成立；
- 最终选择关联、整机价格承接、两 pair/两 family 总门禁、方向稳定性与金额区间属于 G06。

## Commit

- G05 核心实现：`5db2f7d`；
- 本关闭回执、manifest 和完成状态：本文件所在的独立 closure commit。

## 下一 Goal 准入

`G06 allowed`。G06 可实现确定性量化与严格 WTP 门禁；仍不得启用 CLI/路由、PM renderer、数据库写入或 205。
