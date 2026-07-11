# V5-G05 关闭回执

## 结论

`PASSED — V5-G06 ALLOWED`。

V5 battlefield portfolio optimizer 已实现，existing strengthening 与 excluded expansion 在 typed boundary 和状态机上互斥。

## 验收结果

- main/secondary/opportunity/user-observed 不可能进入 expansion；
- 角色上限、能力缺口、表达缺口、市场承接和保持/控制五类路径确定；
- excluded 具备 rejected/deferred/recalled/eligible 四态；
- immutable size/product-form gate 优先于 param strong；
- real donor、market space、task adjacency、gap mutability 和 lineage 全部检查；
- membership 漂移和重复输入阻断；
- 输入顺序反转 DTO 一致；
- C06/C07 和 65E7Q 硬回归通过；
- G05 12 passed、related 58 passed、overall coverage 93%、service 91%、ruff passed；
- 主提交：`2cd435b5a516c808c6e1dda288ec3afb667bcebf`；
- database/205 writes：0/0。

## 边界

战场空间、current allocation 和 expansion donor 目前只作为 option 事实，不生成 gross/net/price amount。G06 才允许实现互不混淆的量价分账和 strict amount wrapper。
