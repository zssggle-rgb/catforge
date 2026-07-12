# M12D-RP-G10 TV/AC 正式发布报告

日期：`2026-07-12`

## 1. 发布结论

M12D-RP-G10 / M12D-QF-19 已完成。TV 和 AC 使用各自 taxonomy、业务边界、市场池、batch 和独立版本完成 canonical draft、重复生成比较、分品类发布及线上消费验收。两个品类均为 `published-ready`，各只有一个 current 版本。

| 品类 | 发布版本 | SKU | 锚点 | 状态分布 | 发布质量 |
| --- | --- | ---: | ---: | --- | --- |
| TV | `m12d_tv_purchase_reason_profile_v0_3` | 377 | 3,542 | ready 335 / ready_limited 13 / weak_expression_only 29 | ready |
| AC | `m12d_ac_purchase_reason_profile_v0_4` | 155 | 1,879 | ready 143 / ready_limited 1 / weak_expression_only 11 | ready |

两次 canonical 生成比较的 `difference_count` 均为 `0`。发布后的 profile、anchor、状态分布、摘要和 current 指针与发布前验收结果一致。

## 2. 线上消费

65E7Q 的最终全量 Top 3 为 TCL 65Q9L PRO、创维 65A7H PRO、华为 VISION智慧屏 5 PRO 65。华为在“价格下探分流”槽中，购买理由重合 `14/15`、替代压力 `10/10`，并在价值战场、任务和客群总分上高于创维 65A6F ULTRA。G07 的 65A6F ULTRA 结果来自受限 fixture 回放，不能用于硬编码正式全量名单。

美的 KFR-88LW/N8KS1-1U 的最终 Top 3 为格力 KFR-72LW/(72527)FNHAB-B1、格力 KFR-72LW/NHMA1BG、格力 KFR-72LW/(72587)FNHAD-B1。两组 Top 3 候选的 M12D 消费状态均为 `published_ready`。

最终飞书报告：

- TV：[海信 65E7Q 重点竞品识别与分析依据报告](https://my.feishu.cn/docx/Fni2dXd9loQ4cnx2W8DcBsJYnTH)
- AC：[美的 KFR-88LW/N8KS1-1U 重点竞品识别与分析依据报告](https://my.feishu.cn/docx/K60Hd8l5woJNzrxupvocn3Ctnlh)

两份文档均已从飞书端回读。TV 修正版不再把购买阻力作为竞品评分维度、独立分析章节或顶部看板模块；Top 3 表格只展示排名、竞品、角色和重合，不单列替代压力；顶部市场验证固定展示均价、周均销量和销量量级，不展示重合周数。分析过程目录包含购买池、价值战场、用户任务、目标客群、关键价值锚点、替代压力、市场验证及候选池附录。候选附录不再输出内部英文码；卡片只保留“查看分析依据”和“查看详细对比结果”，没有“用户选择对比”链接。

## 3. 修复和验证

G10 增加了发布结果持久化、不可变发布版本、canonical 业务摘要、重复 draft 比较、证据读取稳定排序和购买阻力证据稳定排序。线上飞书验收发现候选附录仍泄漏内部门槛码后，补充 `7b61cbd`：原始门槛保留在 JSON 追溯层，报告层统一转为中文业务条件，正常状态不展示，未知内部码不原样输出。

最终验证包括 M12D/reader/竞品相关回归 `106 passed`、完整 CLI 报告回归 `1 passed`，以及报告口径修正回归 `16 passed`、顶部看板定向回归 `3 passed`、压力列修正定向回归 `2 passed`、分数排序竞品回归 `53 passed`、Ruff、compileall、飞书文档回读、API 健康和日志检查。排序修复 revision 为 `4da2279`；205 当前应用 Git revision 为包含该修复的 `4bc68be`，Alembic 为 `0044_core3_m12d_reason_pressure`。

## 4. 回滚点与事件

回滚目录为 `/var/backups/catforge/m12d-rp-g10-20260712_091334`，原始数据库 dump SHA256 为 `a6bda4c5cbab84036d3fefcb510e7a3616362eeb258187e4c320b43996f7f053`。

执行中出现的并发 runner、3G one-off 退出 137、默认 Compose 误调用和飞书发布器环境缺失均已恢复并记录。未使用 SKU/品牌白名单，未降低 7 分成立门槛，未把 M12D 生产逻辑写入竞品智能体；API 服务最终 healthy/ready，数据库版本和发布指针验收通过。
