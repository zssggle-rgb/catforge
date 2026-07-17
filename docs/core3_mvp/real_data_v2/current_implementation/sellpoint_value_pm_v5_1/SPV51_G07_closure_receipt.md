# SPV51-G07 基础能力与局部投入判断关闭回执

状态：completed

日期：2026-07-17

## 1. 基础能力识别

- 每项能力分别保存 `known_present`、`known_absent`、`missing`、`contradicted` 数量，missing 不再当作 absent；
- 已知样本不足或比较范围不完整时返回 `not_assessed`，只保存局部限制，不要求人工复核；
- 只有已知样本、比较范围和普及率均满足规则时才确认 `confirmed_table_stake`；
- 确认是基础能力只将该能力移出核心卖点，不删除候选、不屏蔽用户价值、不阻断 SKU；
- 对照产品能力事实发生真实矛盾时，基础能力识别自身保存 `invalid`、原因和证据。

## 2. 投入分类

- 投入判断按 `project → category → SKU → question → value bundle → capability` 最小作用域独立计算；
- “投入是否转化”只使用本品能力、用户兑现、相对体验、投入程度和已有市场支持，输出继续保留、投入未转化、基础能力或无结论；
- “竞品配置是否要跟”只使用本品缺失事实、对照产品具备事实和当前竞争表现，输出无需跟进、产品定义缺口或无结论；
- unknown、missing、样本不足和普通 limitations 只返回 `no_conclusion`，不再触发 review；
- 不再平均所有投入项 confidence，不再使用 `linked_investment_review`，也不把一项投入的状态传播到整个用户价值或 SKU。

## 3. 局部 review

- 只有当前问题直接使用的事实发生真实 conflict 才返回该问题的 `invalid`；
- 用户反馈冲突只影响投入转化题，不影响配置跟进题；
- 竞品能力事实冲突只影响直接使用这些事实的配置跟进题；
- review overlay 只在相同 SKU、问题和用户价值内汇总，其他价值、其他问题和其他类目保持原状态；
- 每条局部结论和 overlay 保存确定性 hash、具体冲突原因和去重后的证据引用。

## 4. 验证

- G07 classifier、V5.1 schema 和旧阈值必要回归共 63 项通过；
- 覆盖 known/missing 计数、范围不完整、基础能力过滤、保留/未转化、无需跟进/配置缺口、unknown 不复核、直接冲突局部化、TV/AC 隔离、确定性和证据保留；
- touched Python files 的 ruff、py_compile、format 和 diff check 通过；
- 未修改旧 V5 materializer，未实现 G08 量价与参数组，未运行完整回归，未写数据库或 205；完整质量评审仍集中在 SPV51-G13。

## 5. 下一步

SPV51-G08 使用 G06 的问题级候选，实现单个对照即可回答的周均量价比较和任意不同参数取值分组；局部缺价格、销量或参数只跳过该行。
