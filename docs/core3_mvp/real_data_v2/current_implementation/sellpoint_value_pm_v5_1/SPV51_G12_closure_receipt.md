# SPV51-G12 保存画像消费路径关闭回执

状态：completed

日期：2026-07-17

## 1. 读取边界

- 用户卖点价值报告、卡片数据和深入问答改为只读取 G11 已保存并通过 typed 回读校验的 V5.1 profile；
- formal 只接受 current published V5.1，preview 必须同时显式锁定 `profile_version` 和 version id；
- 不回退 V5、旧 M12/M13/M14、竞品分析智能体实时结果或其他 draft；同一读取结果在报告、卡片数据、Markdown 与问答中使用同一 profile result hash。

## 2. 下游可消费内容

- 纯展示/问答 adapter 投影卖点、用户价值、投入建议、价格支撑、销量与量价压力、产品角色、四层量化、局部状态和证据引用；
- 首屏主卖点只突出画像已确认的非基础卖点，基础能力仍可作为配置事实查看，但不占用产品经理的核心决策位置；
- 报告和问答只组织和业务化表达保存事实，不重新召回候选、不重算量价、参数组、市场原型、synthetic 或 strict WTP；
- V5.1 materializer 同步修正结构性 invalid 的持久化计数，确保 invalid SKU 不会被错误记录为零。

## 3. 状态与证据边界

- `no_conclusion` 统一返回“现有数据不足，暂不能形成该 SKU 的用户卖点价值结论。”；
- `invalid` 统一返回“画像数据完整性异常，暂不能形成该 SKU 的用户卖点价值结论。”，且局部 invalid 只影响对应范围；
- strict WTP 或 synthetic 缺失不会抹掉已保存的普通量价结论；普通量价仍明确为观察性市场关联，不冒充随机实验因果。

## 4. 验证结果

- 新增并通过 formal/preview 隔离、旧 V5 禁止回退、跨载体同 hash、零现场重算、strict WTP 缺失、no_conclusion、invalid 和静态导入边界专项测试；
- 连同受影响的旧报告、问答、CLI、G11 materialization 回归，共执行 56 项聚焦测试，全部通过；
- 所有 touched Python 文件 `ruff check` 与 `py_compile` 通过，3 个新增 Python 文件 `ruff format --check` 通过，`git diff --check` 通过。

## 5. 范围边界

- 未执行完整回归、覆盖率、迁移往返、性能与三类总评审，这些统一留在 SPV51-G13；
- 未写 205，未生成生产画像，未执行 review、publish 或 current；
- 未恢复或提交 `pre-spv-v5.1-workspace-20260717` stash 中的 151 个遗留文件。

## 6. 下一步

SPV51-G13 集中完成全量回归、覆盖率、migration upgrade/downgrade、最大候选性能与方法/工程/业务三类评审；通过后才允许进入 205 代码与 migration 部署。
