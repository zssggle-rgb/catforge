# V5-G05 战场组合业务与工程复核

## 结论

`PASSED — G06 ALLOWED`。

P0=0，P1=0，P2=2。

## 产品经理业务检查

- primary、secondary、opportunity、user-observed 全部先锁定为已进入战场；
- 只有 context 未出现的 battlefield 才能进入 excluded expansion 分支；
- source membership 与锁定 M11C context 不一致时直接报错，不由优化器重新贴标签；
- existing 输出沟通激活、能力补全、市场激活、组合优先级或保持/控制；
- role cap 导致的 opportunity 固定为 portfolio priority；
- excluded 依次检查尺寸/价格、产品形态、任务客群、缺口可变性、donor、市场空间和 lineage；
- rejected/deferred/recalled 不冒充 eligible；
- 没有 excluded input 时 expansion 列表合法为空；
- 不输出自动增配、定价、销量 lift 或净新增。

## 65E7Q 硬回归

- 家庭护眼舒适：M11C opportunity，且原因是辅战场数量上限，输出 existing + portfolio priority；
- 大屏家庭影院：excluded，尺寸/价格门槛失败且 screen size gap 在本 SKU 范围不可变，输出 expansion rejected；
- “参数 strong”不能覆盖 immutable market gate；
- 战场 market space 只保留为参照，不进入 increment 字段。

## 工程检查

- 新增 typed `BattlefieldPortfolioInput`，extra forbid；
- membership 从 target snapshot 确定，输入重复或漂移阻断；
- `ExpansionEligibility` 明确 hard/unknown/recall/eligible；
- 结果按 existing first + battlefield code 稳定排序；
- source scan 无 allocation lift、sales lift 或 increment 计算；
- 未修改 M11C/M11D 生产合同。

## 验收

- G05 tests：12 passed；
- V5 + M11C related：58 passed；
- V5 三文件 overall coverage：93%；service coverage：91%；
- ruff：passed；
- C06/C07 fixture 绑定；
- database/205 writes：0/0。

## P2

1. task/group adjacency 0.50 和 donor 5 属于 v1 门槛，G08 必须输出真实 eligible/recalled/rejected 分布；阈值调整要升版本。
2. 本 SKU scope 默认 size/product-form immutable；未来若分析“下一代不同尺寸 SKU”，必须新增 scope 字段和独立 Goal，不能复用当前 eligible。
