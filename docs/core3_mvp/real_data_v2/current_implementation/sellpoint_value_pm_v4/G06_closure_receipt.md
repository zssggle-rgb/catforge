# G06 关闭回执：选择关联、整机价格承接与市场隐含 WTP

## Objective

在 G05 已分级的卖点组合反事实池上，实现确定性相对体验、同价/近同价选择关联、整机价格承接和严格 matched equal-choice 市场隐含 WTP；只有证据链和识别门禁全部通过才输出金额，其余状态保留价值事实并将金额置空。

## 前置输入

- G05 核心实现 commit：`5db2f7d`；
- G05 closure commit：`5b5b3d2`；
- G06 Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`；
- G06 timer：`catforge-v4-g06-10`。

## 实际产物

- 扩展 `claim_value_pm_v4_schemas.py` 的 G06 typed contracts 和单调层级校验；
- 扩展 `claim_value_pm_v4_service.py` 的 pair curve、choice、whole-product acceptance 和 WTP 总门禁；
- 新增 `test_claim_value_pm_v4_quantification.py`；
- 更新 G05 source-boundary 测试，使其只扫描 G05 函数段；
- 更新 `G06_progress.md`；
- 本关闭回执；
- `G06_artifact_manifest.json`。

未修改 repository/数据库/205、V2 registry、CLI/路由或 PM renderer。

## 业务合同

1. “卖点有用户价值”与“卖点可量化”是两个独立门禁；市场量价不能替代用户实际价值证据；
2. 相对体验不使用评论数量排序，只确认同一购后价值主题是否可比；
3. 选择关联只读取同战场、同周、同平台、有效价格、双方正销量且非促销疑似的共同单元；
4. exact same-price 与 near-same-price 互斥；同价附近有空洞时不插值，观测范围外不外推；
5. 整机价格承接只能写 `whole_product_only`，不能归给单项技术；
6. Q5 必须至少两条独立 A 级 base pair，且来自至少两个明确 model family；未知 family 不凑数；
7. 每条 Q5 pair 必须有 strong curve、负向价格方向、局部支持的五五开 crossing，并通过全部 leave-one-week-out；
8. same-value 只支持选择/整机承接，stretch 只支持相对体验观察；
9. 完全共线只输出 bundle WTP，不能拆给 MiniLED、亮度、分区、高刷等成员；
10. 版本冲突为 blocked；方向或敏感性失败为 unstable；样本/对照不足为 insufficient；三者金额都为 null；
11. 市场隐含 WTP 是观察性 equal-choice price gap，不是因果效应，也不是心理最高价；
12. M12C 旧金额与 M11D 分配权重均不参与模型、监督或结果。

## 已验证样例

| 场景 | 用户价值 | 选择/价格 | WTP |
| --- | --- | --- | --- |
| 双 family synthetic | established | exact same-price available；当前整机承接可观察 | 400-500 元，2 pair/2 family |
| 同 family 两 pair | established | available | null：model family 不足 |
| 单 pair | established | available | null：独立 pair 不足 |
| same-value-only | established | available | null：不能证明增量 |
| leave-one-week-out 不稳 | established | available | null：unstable |
| 正向价格方向 | established | unstable | null |
| 单周 | established | insufficient | null |
| value partial | partial | available 到整机层 | null：用户价值未完全成立 |
| value not observed | not_observed | 不允许归因为卖点选择 | null |
| 65E7Q 脱敏 fixture | fixture 无完整周 cell；lineage conflict | 不补造 | null：blocked |

## 测试结果

| 验证 | 结果 |
| --- | --- |
| G06 quantification tests | 19 passed |
| G03 + G04 + G05 + G06 + V2 定向回归 | 74 passed |
| G04-G06 service coverage | 92% |
| G06 runtime schema vs G02 contract | exact match |
| Ruff / py_compile / diff check | passed |
| legacy amount/allocation scan | 0 reads |
| database/server writes | 0 / 0 |

## 已知边界

- 当前只有确定性 synthetic fixture 通过完整 Q5；本 Goal 没有对任何真实 SKU 宣称 WTP 金额；
- G01 65E7Q 脱敏 fixture 没有逐周平台 cell 和原始评论 atoms，固定回放只验证“不补造、不拆项、版本冲突金额为空”；
- 品牌和其他未观察差异仍可能混杂，即使 Q5 available 也固定为非因果；
- 产品经理可读的“价值结构与市场兑现”主表、中文限制翻译和下钻属于 G07。

## Commit

- G06 核心实现：`ce1b4eb`；
- 本关闭回执、manifest 和完成状态：本文件所在的独立 closure commit。

## 下一 Goal 准入

`G07 allowed`。G07 可实现业务 DTO、短答、主表、下钻、Markdown/飞书渲染、显式 CLI 和默认关闭的 feature flag；不得让 renderer 自行计算或更改 G04-G06 结论。
