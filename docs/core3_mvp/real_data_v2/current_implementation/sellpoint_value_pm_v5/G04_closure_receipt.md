# V5-G04 关闭回执

## 结论

`PASSED — V5-G05 ALLOWED`。

market synthetic control 和 high/low performance archetype 已实现为确定性、只读、观察性纯函数。

## 交付

- non-negative normalized balancing weights；
- price support、effective donors、max weight、SMD 和 row cap；
- target + 至少 3 donor 的共同 cell 门禁；
- leave-one-donor/week 方向稳定；
- 500 次 week-cluster bootstrap；
- donor placebo 仅控制 highlight；
- held-week cross-fitted ridge residual；
- high/low residual 四分位、时间稳定和 bundle prevalence bootstrap；
- explicit absent 与 unknown 分离；
- causal claim 全部 false。

## 验收

- G04 tests 8 passed；
- V5/V4 quantification related 54 passed；
- service coverage 91%；
- ruff passed；
- 40×12×2 archetype <3s；
- cell/donor 顺序反转结果 hash 一致；
- source scan 无 strict amount、legacy amount 或 causal=true；
- 主提交：`b5497eaad2024f6fa76cd9d5338738513ad17cfd`；
- database/205 writes：0/0。

## 边界

- 当前结果是观察性市场参照，不是“增加卖点必然多卖”；
- brand tier 缺失会明确进入 limitations；
- real C03 donor 的平衡通过率留待 G08/205 回放；
- G04 不生成 battlefield option、net increment、strict amount 或 PM 文案。

## G05 范围

实现 battlefield portfolio optimizer：所有 main/secondary/opportunity/user-observed 走 existing strengthening；只有 excluded 经 immutable/mutable gap、task adjacency、donor 和 overlap 门禁后才进入 expansion option。
