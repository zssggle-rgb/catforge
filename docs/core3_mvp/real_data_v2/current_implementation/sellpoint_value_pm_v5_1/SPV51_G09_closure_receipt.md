# SPV51-G09 增强量化分层关闭回执

状态：completed

日期：2026-07-17

## 1. 复用边界

- 未重写原有市场模型，直接复用已验证的 V5 performance archetype、synthetic control、battlefield portfolio 和 V4 strict WTP；
- 新增 V5.1 adapter 只负责局部状态、业务结论、默认可见性、证据和 hash，不降低旧方法自身的 donor、balance、稳定性或金额门槛；
- 同预算原型复用 G08 已保存的 `same_budget_pool` 直接量价结果，不重复计算市场数据。

## 2. 市场原型

- 同预算：1 个参照即可形成方向性原型，保存同预算组均价、周均销量、相对本品量价差和来源 hash；
- 卖得好/卖得差：把旧 high/low performance archetype 映射为高销量组、低销量组，保存样本、代表 SKU、价格/销量、用户价值组合普及率和稳定性；
- 高低销量组均存在时输出正式市场组合结论，只有一侧时输出 `partial_conclusion`，仅 unstable 时局部 `no_conclusion`；
- 结论描述用户价值在高/低销量组合中是否更常见，只作为产品定义参照，不冒充价值组合的因果增量。

## 3. 价值战场

- 已进入的主、辅、机会等战场统一输出“增强已有战场”，保留组合优先级、能力补全、表达激活、市场激活或保持控制路径；
- 只有 `excluded` 战场才进入“是否拓展新战场”判断，且继续使用原有进入条件；
- 新战场条件未知、仅召回或被拒绝时只隐藏该拓展项，不影响已有战场、用户价值或 SKU。

## 4. 合成基线与严格 WTP

- synthetic available 且自身 gate 通过时，保存 donor、有效 donor、价格/销量差和“无该组价值”的观察性市场基线；
- donor、balance、common week/platform、留一稳定性等任一诊断失败时，synthetic 自身返回 `no_conclusion`、默认隐藏且不 review；
- 严格 WTP 仅包装原 V4 已通过完整金额合同的结果，保存区间、中心、参照价、pair/model family 和全部 gate；
- strict WTP 未通过或缺失时不暴露任何金额、默认隐藏且不 review；直接量价、参数组、用户价值和投入结论继续有效；
- synthetic 与 WTP 均保持 `causal_claim=false`，严格 WTP 也明确不是心理最高价。

## 5. 验证

- G09 adapter、V5.1 schema、G08 market comparison 及旧 synthetic/archetype/realization/battlefield 必要回归共 86 项通过；
- 覆盖同预算单参照、同预算无结论、高低销量组合与输入顺序、unstable、synthetic available/degraded、strict WTP available/insufficient、已有战场增强、新战场条件未知、TV/AC 类目边界；
- touched Python files 的 ruff、py_compile、format 和 diff check 通过；
- 未实现 G10 value/SKU/version 状态聚合，未做完整回归，未写数据库或 205；完整质量评审仍集中在 SPV51-G13。

## 6. 下一步

SPV51-G10 将 G07—G09 的局部结果聚合到 question、value、SKU 和 version：只有真实 `invalid` 阻断，`no_conclusion` 和可选增强失败只能形成 limited，不再平均全部投入 confidence 或全局传播 review。
