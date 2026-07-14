# 竞品画像 V1 G04 设计复核

状态：passed，允许 G05

日期：2026-07-14

## 1. 评审结论

P0=0，P1=0，P2=3。P2 均有后续验证 Goal，不阻断 typed schema 实现。

设计已经把最重要的发布安全问题改成结构约束：新 draft 不改变正式画像；publish 不自动 current；current 切换单独加 scope lock、expected-current compare-and-swap，任何失败保留旧 current。

## 2. 架构复核

- 五张表足以保存完整 manifest、pair、七关系和 0—3 重点结果；
- competitor/reference 用 membership 分离，不为同一 pair 写重复行；
- 七类 failed/unassessable 也保存，避免只有正向关系而无法解释候选为何未入选；
- `storage_batch_id` 与多 source batch serving scope 分开；
- provider category bundle + pure pair functions 可避免逐候选 N+1；
- reader formal/preview 分开，正式模式没有旧链或现场计算 fallback；
- 现有 sellpoint-value 版本/repository/lifecycle 模式可复用，但 publish 自动 current 的行为明确不能照搬。

## 3. 数据安全复核

| 风险 | 设计控制 | 结果 |
| --- | --- | --- |
| published 原地覆盖 | review 后 child immutable | closed |
| publish 误切 current | publish/current 分开 | closed |
| 并发 current 竞争 | release scope row lock + CAS | closed |
| TV/AC 串线 | exact rule/taxonomy/product category/SKU membership/source batches | closed |
| 缺失当 false/0 | typed null + gate known flag | closed |
| 候选被性能截断 | full manifest + explicit failure | closed |
| reference 冒充竞品 | membership/status/reader validator | closed |
| 报告现场变更 Top3 | saved selections + version lock | closed |
| runtime 泄露工厂方法 | forbidden-key validator/export test | closed |

## 4. Schema 复核

- 11 组核心 enum 完整；
- 5 个 evidence families、7 个 relations、8 个 questions、7 个 reference purposes、4 个 decision topics 均有稳定代码；
- pair 强制 5 个 evidence family、7 个 relation、8 个 question assessment；
- selection rank 1—3、连续、candidate 唯一；
- SKU `no_priority_competitor` 与 `insufficient_evidence` 分开；
- `causal_claim=false` 固定在量价 DTO；
- scope、input fingerprint、result hash 向所有 child 传播。

## 5. 工程复核

- migration 有 upgrade/downgrade、FK/unique/check/partial index 和有数据时安全 downgrade；
- repository 写入以 SKU bundle 单事务、bulk insert/readback hash；
- batch generation 逐 SKU 事务、可恢复、失败隔离；
- progress 用轻量 projection；
- 读接口 pairs/relations 分页；
- 公开函数均有正常、边界、错误测试入口；
- 不依赖外部 LLM 通过测试。

## 6. P2

1. 通用价值和门槛功能覆盖率阈值需 G22 对 TV/AC 分布回放；调整必须升配置版本。
2. 全量 1.16M relation 上限是理论规划值，G13 需实测内存、SQL、写入和索引成本；允许优化批大小，不允许截断业务集合。
3. `limited` 版本是否未来允许正式发布需在真正发布前由用户决定；当前实现只需支持显式 allow，G23—G26 不执行 review/publish/current。

## 7. 范围

- 本轮新增设计文档和 schema contract；
- 生产/测试代码修改：0；
- 数据库/205 写入：0；
- 部署、draft 生成、review、publish、current：0。
