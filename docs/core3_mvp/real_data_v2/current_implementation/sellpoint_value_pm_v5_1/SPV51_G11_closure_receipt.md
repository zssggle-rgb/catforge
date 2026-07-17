# SPV51-G11 生成与持久化集成关闭回执

状态：completed

日期：2026-07-17

## 1. 已集成的画像内容

- materializer 将竞品画像来源、正式竞品池、分析参考池、问题级候选、局部投入判断、直接量价、参数组、市场原型、synthetic、strict WTP、question→value→SKU 结论统一装配为一份 typed V5.1 profile；
- profile、value、candidate、quantification、investment、reference 与证据仍写入 G04 已扩展的既有表和 JSON 合同，不创建第二套平行事实；
- 低 confidence、单一对照和可选增强无结论不会自动触发 review；局部 invalid 留在价值与证据摘要，只有 SKU 自身 invalid 才进入 SKU/version 的 invalid 计数。

## 2. 来源与确定性

- 每个 draft 保存 `competitor_profile_version_id`、竞品画像 method/version result hash、SKU snapshot、两池 result hash、方法配置和全部上游 lineage；
- profile fingerprint 绑定竞品画像来源、候选池、分析输入、规则配置和上游 lineage；version fingerprint 同时绑定权威 SKU 清单与每个 SKU 的 candidate pool hash；
- 来源、候选、分析或配置变化会产生新 fingerprint；等价输入只改变列表/字典顺序时 fingerprint 不变；
- repository 在创建版本及每次 typed 回读时重新核对竞品画像真实版本、scope、current/release 状态和 result hash，不允许旧 M12/M13/M14 或现场召回回退。

## 3. 写入、回读与隔离

- generation service 只创建新的 V5.1 draft，不修改 V5 历史，不执行 review、publish 或 current 切换；同一输入重复生成复用同一版本和同一 SKU draft；
- repository 回读重建完整 typed profile，重算 input fingerprint/result hash，并逐字段核对 profile/candidate/value 投影及悬空候选引用；
- 每个 SKU 在独立 savepoint 中写入，单 SKU 输入或持久化失败只回滚自身，批次继续处理其他 SKU 并在版本状态中记录 failure；
- 版本状态按 conclusion/partial/no_conclusion/invalid、完整性错误和生成失败聚合，optional enhancement 无结论不提升为版本阻断。

## 4. 验证结果

- G11 专项测试 8 项通过：完整 typed payload、低门槛、双池同 SKU 身份、来源/候选/分析/配置 fingerprint、顺序确定性、幂等、V5 published/current 保护、typed 篡改、缺失子记录、来源 hash、单 SKU 回滚和旧路径隔离；
- 既有 persistence 16 项、V5.1 migration 5 项通过；本 Goal 共执行 29 项聚焦测试，全部通过；
- touched Python 文件 `ruff check`、`ruff format`、`py_compile` 与 `git diff --check` 通过；完整回归、覆盖率、性能和三类总评审仍集中在 SPV51-G13。

## 5. 范围边界

- 未实现 G12 报告/问答消费路径；
- 未写 205，未生成生产画像，未改旧 M12/M13/M14；
- 未执行 review、publish、current，也未恢复或提交 `pre-spv-v5.1-workspace-20260717` stash 中的遗留文件。

## 6. 下一步

SPV51-G12 将竞品分析和用户卖点价值的报告、卡片数据适配与深入问答改为只读取已保存 V5.1 profile；下游只负责业务化组织和表达，不重新召回竞品、不重算量价或 WTP。
