# 用户卖点价值画像 V5.2 正式发布回执

日期：2026-07-18

## 1. 用户授权

用户明确批准按顺序执行：

1. review TV、AC V5.2 全量草稿；
2. review 门禁通过后 publish；
3. 切换为各品类 current，使飞书用户卖点价值智能体正式消费 V5.2。

本次同时获得 `allow_limited` 的明确授权：证据不足的 SKU 正式返回部分结论或无结论，不补造卖点。

## 2. 发布前阻断修复

发布前检查发现，飞书正式消费入口仍只识别 V5.1。若直接切换 current，
会导致 V5.1 失去 current 而智能体无法读取 V5.2，因此发布在数据库写入前暂停。

已完成：

- 新增严格的 V5.2 formal/preview reader；
- 正式报告、Card 和问答优先读取 current V5.2；
- 没有 current V5.2 时保持 V5.1 回退；
- 所有读取只消费保存画像，不调用上游重算；
- 保留 205 已有的竞品画像缺失显式回退热修。

代码提交：

- `a9654b3 fix(core3): route formal sellpoint reads to v5.2`；
- `89f490c fix(core3): preserve competitor fallback during v5.2 routing`。

专项测试：

- V5.2 正式消费与 V5.1 兼容共 23 项通过；
- ruff 和 Python compileall 通过。

205 部署备份：

- `/home/deploy/catforge-deploy-backups/spv52-publish-consumer-20260718`。

## 3. Review 结果

TV、AC 在同一 review 事务中完成：

| 品类 | 版本 | 状态 | 质量 |
| --- | --- | --- | --- |
| TV | `spv_v5_2_tv_full_g08_20260718_r1` | reviewed | limited |
| AC | `spv_v5_2_ac_full_g08_20260718_r1` | reviewed | limited |

操作人记录：`user-approved-spv52-20260718`。

## 4. Publish 与 Current 结果

publish 与 current 切换在同一事务中完成；提交事务前已使用正式模式验证
TV、AC 报告和问答。任何一项失败都会整笔回滚，本次全部通过后才提交。

| 品类 | 正式 current 版本 | 版本结果 hash |
| --- | --- | --- |
| TV | `spv_v5_2_tv_full_g08_20260718_r1` | `sha256:sellpoint_value_version_result_v5_2:ca0df0089e3c1852187774dab5ef188ff7d9ac56977e681b9180e7ed766a6a70` |
| AC | `spv_v5_2_ac_full_g08_20260718_r1` | `sha256:sellpoint_value_version_result_v5_2:c4ff001566e28ad9f98efc8e29e064492ac5f7a3d390d0c13e436eb0362b13f7` |

两版本均为：

- `processing_status=completed`；
- `release_status=published`；
- `release_quality_status=limited`；
- `is_current=true`；
- 失败、无效、完整性错误和最终回读错误均为 0。

## 5. 飞书智能体正式消费验收

### TV

- 验收 SKU：海信 65E7Q（`TV00029112`）；
- 正式入口返回 `sku_sellpoint_value_pm_report_v1_2`；
- 深入问答返回 `sellpoint_value_profile_answer_v1_2`；
- 报告与问答读取同一 V5.2 画像 hash；
- 飞书卡片为 Card 2.0，包含 `schema/config/header/body`；
- 上游重算调用 0。

### AC

- 验收 SKU：海尔 `KFR-35GW/E1-1PLUS`（`AC00036172`）；
- 正式入口返回 `sku_sellpoint_value_pm_report_v1_2`；
- 深入问答返回 `sellpoint_value_profile_answer_v1_2`；
- 报告与问答读取同一 V5.2 画像 hash；
- 飞书卡片为 Card 2.0，包含 `schema/config/header/body`；
- 上游重算调用 0。

飞书智能体实际使用的 `catforge_analyst sellpoint-value-pm-v5` 正式命令已对
TV、AC 各执行一次，均返回 V5.2 current published 结果。

## 6. V5.1 与回退保护

旧正式版本没有删除或原地修改：

- TV：`spv_v5_1_tv_full_g17_20260717_r1`，保持 published、非 current；
- AC：`spv_v5_1_ac_full_g17_20260717_r1`，保持 published、非 current。

如需回退，必须重新获得明确授权后再执行 current 恢复；不得原地改写 V5.1
或 V5.2 结果。代码回退可恢复上述部署备份并重建 API。

## 7. 最终结论

用户批准的 1、2、3 已全部完成。TV、AC 用户卖点价值画像 V5.2 已正式发布并
成为 current，飞书用户卖点价值智能体已正式消费 V5.2。未重跑或修改
M03B—M12D、旧 M12/M13/M14 和正式竞品画像。
