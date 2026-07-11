# V5-G07 工程与边界复核

## 结论

`PASSED — G08 ALLOWED`。

P0=0，P1=0，P2=2。

## 架构检查

- `claim_value_pm_v5_answer.py` 是唯一 assembler/renderer 模块；不在 renderer 中推导新结论；
- V4 context adapter 只复用已加载快照，不产生数据库写入；
- G03 反事实、G04 市场参照、G05 战场组合、G06 量价分账通过 typed contract 组合；
- report hash 排除交付 URL 和临时路径，JSON/短答/Markdown/卡片共享同一 hash；
- feature flag 在 CLI 创建数据库会话之前阻断，在 orchestrator 加载上下文之前二次阻断；
- `sellpoint-value-pm-v5` 未加入自然语言路由规则，默认仍为 V2；
- 真实 handler 可在显式启用后复用既有 competitor-set 形成最多 30 个 fallback 候选，V4 快照合同仍执行有界筛选。

## 验收结果

- G07 tests：15 passed；
- 全部 V5 tests：68 passed；
- V4 answer/CLI/quantification：40 passed；
- analyst CLI regression：88 passed；
- V5 overall coverage：92%；V5 answer coverage：85%；
- ruff passed；compileall passed；
- 默认关闭 CLI 实跑返回 1，且测试证明数据库 session 创建次数为 0；
- database/205 writes：0/0。

## P2

1. 实际 205 候选生成包含 competitor-set 的额外只读查询；G08 需记录 query count、P95 和内存，超过冻结预算则阻断 RC。
2. 飞书发布网络仍由既有发布器负责；G08 必须做真实文档/卡片 readback，不能只验 payload。
