# V5-G04 方法与工程复核

## 结论

`PASSED — G05 ALLOWED`。

P0=0，P1=0，P2=3。P2 均有明确后续真实数据验证，不阻断当前纯函数实现。

## 市场合成复核

- donor 必须是已知 lower tier；unknown 不当作 lower；
- 有效 cell 必须同时有 target 和至少 3 个 donor；
- broad donor ≥5、有效 donor ≥3、max weight ≤0.5；
- target price 必须位于 donor 支持范围；
- after-SMD ≤0.10 才可 available，0.10—0.20 也降级，>0.20 failed；
- leave-one-donor 与 leave-one-week 合并方向一致率 ≥0.75；
- week-cluster bootstrap 500 次，seed 来自 sample hash；
- placebo <0.80 只阻止 market highlight，不删除已通过平衡的观察性区间；
- inventory unavailable 和 promotion suspect 边界使 causal claim 固定 false；
- 不读取 M12C legacy amount，不生成 strict bundle price interval。

## 高低绩效原型复核

- 每个 week×platform 内使用其他 SKU 的市场均值做 contemporaneous normalization，不读取本 SKU 自己作为 baseline；
- 按 week 留出，训练 regularized linear baseline，再对 held week 预测；
- 控制相对价格、尺寸、品牌层级和活跃周，week×platform 已由 peer normalization 控制；
- SKU 残差以 cell 中位聚合，时间方向稳定率 ≥0.70；
- high/low 各为稳定 residual 上/下四分位且至少 10 SKU；
- bundle prevalence 差 ≥15pp，并通过 500 次 SKU bootstrap 方向一致率 ≥0.80；
- unknown bundle tier 不当 absent；只有显式 `absent` 才计为不具备；
- 原型始终 causal claim=false，不生成单项金额。

## G02 方法说明细化

G02 所称“week 固定效应 + week-group OOF”在 G04 落成：held week 的 week×platform 市场水平来自该 cell 的其他 SKU，目标 SKU 自身被排除；ridge 只拟合相对市场水平后的特征。这样既保留 contemporaneous week/platform 控制，又避免把目标 SKU 的 held-week outcome 作为自己的预测输入。

## 测试与性能

- G04 synthetic/archetype tests：8 passed；
- V5 + V4 quantification related：54 passed；
- G04 service coverage：91%；
- V5 三个运行文件整体 coverage：≥90%；
- ruff：passed；
- 40 SKU × 12 周 × 2 平台 archetype 测试在 3 秒硬门禁内通过；
- synthetic 顺序反转 full DTO/result hash 一致；
- archetype 顺序反转 result hash 一致。

## P2

1. constrained least-squares 权重在真实 C03 上的 effective donor/SMD 分布需 G08 回放；阈值变更必须升配置版本。
2. brand tier 当前缺失时按 unknown numeric 0 进入平衡；真实输出必须把该缺失放入 limitations，不能把 0 解释成低品牌层级。
3. 当前 placebo 是 donor 内伪处理排序，适合亮点过滤但不是正式显著性检验；产品经理文案不得出现“显著”。

## 范围检查

- 新增运行文件：1；
- battlefield/price-volume accounting/renderer/CLI：0；
- database/205 writes：0/0。
