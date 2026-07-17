# SPV51-G17 TV/AC 全量 V5.1 Draft 关闭回执

状态：completed

日期：2026-07-17

## 1. 目标与结果

已在 205 基于正式 current/published 竞品画像和已保存旧 V5 事实，分别生成一个明确命名、不可变的 V5.1 全量 draft：

- TV：`spv_v5_1_tv_full_g17_20260717_r1`，377/377；
- AC：`spv_v5_1_ac_full_g17_20260717_r1`，155/155；
- 合计：532/532。

两个版本均为：

- `release_status=draft`；
- `is_current=false`；
- `release_quality_status=limited`；
- `processing_status=completed`。

最终 generation failure、invalid、integrity error、missing SKU、unexpected SKU、cross-category、self pair、duplicate 和 orphan 均为 0。

## 2. 结论分布

- TV：282 个 `conclusion_available`、66 个 `partial_conclusion`、29 个 `no_conclusion`；
- AC：138 个 `conclusion_available`、6 个 `partial_conclusion`、11 个 `no_conclusion`；
- 合计 492 个 SKU 可返回完整或部分业务结论，40 个 SKU 明确返回数据不足。

V5.1 全量版本没有 `review_required` SKU。严格 WTP 和参数组无结论只保留为增强层状态，没有污染直接量价、市场原型、价值项、SKU 或版本。

## 3. 来源与范围

TV 正式竞品唯一来源：

- version id：`288b6ce0-b632-478c-9705-8297103da730`；
- profile version：`competitor_profile_agent_snapshot_v2_tv_full_g41c_20260716_r2`。

AC 正式竞品唯一来源：

- version id：`eed759a8-a666-4257-8c4d-3405621a4244`；
- profile version：`competitor_profile_agent_snapshot_v2_ac_full_g41c_20260716_r1`。

旧 V5 用户价值和市场参考来源：

- TV：`spv_profile_v5_65e7q_g09_20260713_r5`；
- AC：`spv_profile_v5_ac_g10_20260713_r2`。

每个 SKU 只使用自己的正式竞品候选和市场参考池。377/155 是批量目标数量，不是单 SKU 的逐款比较范围。

## 4. 全量执行中修复的 P1

为完成 G17，只修复了两处真实全量运行问题：

1. 新增 saved V5 轻量、强类型 generation source，只查询 V5.1 实际消费的画像标量、reference 候选、价值字段和 6 个投资字段；不再装载旧 V5 的报告、QA 和重复 evidence payload；
2. 进度更新改为读取轻量 SKU 状态，不再在每个子批后重验全部历史 SKU；全量完成后显式执行一次、每次一款的流式完整性审计。

批处理 CLI 同时实现：

- scope manifest 落盘和恢复；
- 串行子进程分块；
- 单 SKU 失败隔离；
- checkpoint 状态；
- 最终完整性审计；
- 小型版本摘要，避免输出巨大 source scope。

这些修改没有改变 65E7Q 和 AC39187 的业务结论。两款全量版与 G15/G16 单 SKU 版的首屏、价值账、投入取舍和候选池完全一致。

## 5. 消费一致性

抽样 TV `TV00029112` 和 AC `AC00039187`：

- 报告、卡片和问答锁定同一保存 profile hash；
- 上游分析调用为 0；
- 没有读取旧 M12/M13/M14 或现场量价计算表；
- TV/AC 没有术语串线；
- 可见正文没有版本号和 hash。

抽样无结论 SKU `TV00009549` 和 `AC00034959`：

- 报告、卡片和问答共同返回“现有数据不足，暂不能形成该 SKU 的用户卖点价值结论”；
- 没有临时补算或伪造产品动作。

## 6. 测试与运行时

- 相关专项与受影响回归：68 passed；
- ruff、compile、`git diff --check` 通过；
- API image：`sha256:537af0f41d79591e8a837df0339f597d805be1b3b626723ae42a604f94e50048`；
- `/healthz=ok`；
- `/readyz=ready`；
- OOM killed：false；
- restart count：0。

保护性备份：

- `/home/deploy/catforge-deploy-backups/spv51-g17-streaming-p1-20260717`；
- `/home/deploy/catforge-deploy-backups/spv51-g17-profile-only-p2-20260717`；
- `/home/deploy/catforge-deploy-backups/spv51-g17-lightweight-v5-p3-20260717`；
- `/home/deploy/catforge-deploy-backups/spv51-g17-lightweight-progress-p4-20260717`。

## 7. 保护门禁

本 Goal：

- 没有 review、publish、current 或 deprecated 切换；
- 没有重跑 M03B—M12D；
- 没有修改旧 M12/M13/M14；
- 没有修改正式竞品画像或旧 V5；
- 没有覆盖 G15/G16；
- 没有清理或提交远端用户 dirty/stash；
- `.env` hash 保持 `7243971662532eaa036d64f7d73d71920c586286a94df5eacead1713e6e5b56a`；
- 受保护 stash OID 保持 `2156593622e0f07af67695da1e0e965153349b05`。

完整业务验收：`SPV51_G17_full_draft_acceptance_report.md`。

结构化证据：`SPV51_G17_full_draft_evidence.json`。

G17 已通过。后续只允许另行创建 SPV51-G18 只读发布准备审计；不得自动 review、publish 或 current。
