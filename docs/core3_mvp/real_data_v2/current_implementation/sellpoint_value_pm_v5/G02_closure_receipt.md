# V5-G02 关闭回执

## 结论

`PASSED — V5-G03 IMPLEMENTATION ALLOWED`。

V5 的 typed schema、反事实状态机、合成市场门禁、高低绩效原型、战场拓展资格、量价分账、PM DTO、测试和追溯已经冻结。方法、工程和 PM 语言审查 P0=0、P1=0。

## 冻结的不可绕过边界

1. broad recall 不能直接成为 eligible counterfactual；
2. synthetic balance/overlap/stability 失败时不输出观察性 gross；
3. high/low archetype 不产生单卖点因果或金额；
4. opportunity/user-observed 属于 existing battlefield；
5. excluded expansion 必须通过 immutable size/product-form gate 和真实 donor；
6. M11D allocation 固定 incremental=false 并绑定自身 lineage；
7. gross、cannibalization、net 和严格组合价格区间分别保存；
8. cannibalization 不可识别时 net=null；
9. strict amount 只沿用 V4 A-grade base 门禁；
10. 亮点可以为空，不能用高价、参数具备或通用结论补位。

## 验收

- schema JSON valid；
- F01-F14 和追加业务边界全部映射到 schema/method/test/Goal；
- C01-C08 全部进入测试计划；
- 查询、内存、row cap、确定性和默认关闭预算明确；
- `git diff --cached --check` 通过；
- 主提交：`0071379bcd5aede4962467a793e879f04ce59621`；
- 运行代码、数据库、205 修改均为 0。

## G03 范围

G03 只实现 V5 typed schemas 和多层 counterfactual resolver，包括 direct、same-budget、brand ladder、param tier、same-claim realization、own curve 与 broad synthetic recall；不实现 synthetic effect、archetype、battlefield option、量价分账或 PM renderer。
