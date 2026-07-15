# G31 竞品画像 V1.1 Repository/Reader 关闭回执

状态：completed

日期：2026-07-15

## 1. Goal

在不连接或写入业务数据库、不访问 205、不生成画像、不修改 G32 之后的分析与消费模块、不修改旧 M12/M13/M14 或 V1 草稿、不执行 review/publish/current 的前提下，实现 V1.1 Repository 与 Reader，保证完整画像图原子写入、版本内共享快照精确解析以及三种读取模式无损回读。

## 2. 原子写入与幂等

- snapshot、profile、pair、relation、selection 在同一 savepoint 内写入和完整 readback；任何子表、typed closure 或 readback 失败均整体回滚；
- 禁止关闭 savepoint，写入前对 DTO 做 fresh typed validation，不能利用构造后 mutation 绕过合同；
- profile 和 SKU snapshot 在同一版本内不可变；相同输入幂等返回，冲突输入 fail-closed；
- version 行写入时锁定；并发唯一冲突只允许读取并返回完全相同的已保存图；
- self-pair 共用同一 target snapshot，zero-candidate 与全 unknown pair 均保留真实业务语义，不伪造主关系或结论。

## 3. Snapshot 精确解析

- 写入时一次读取当前 version 的全部 snapshot，建立 version-wide `snapshot_ref → sku_code` 所有权；同一 ref 不能属于不同 SKU；
- full、compact、question-specific 在进入投影前统一执行 version-wide owner 校验；
- 读取只额外查询 `sku_code + snapshot_ref`，完整 snapshot JSON 仍只加载当前 profile 的 target 与 candidate；
- target/candidate ref 必须解析到同一 version、project、category、release scope 和正确 SKU；悬空、跨 scope、跨 SKU 重用或内部 hash 不一致全部 fail-closed；
- self-pair 仍允许同一 SKU 重用同一 ref。

## 4. Full、Compact 与 Question-specific

- full 重建完整 `CompetitorProfileAnalysisDTO`，重新执行 summary、pair、selection、fact、evidence 与 relation closure；
- question-specific 先完成同一完整 DTO 校验，再按冻结 question 返回全部已保存结果，包括 unknown/unanswerable，不现场重算；
- compact 不加载 `analysis_snapshot_json`，返回 target snapshot、summary、priority selections 和完整 pair index；
- compact 使用 deterministic integrity receipt 绑定 profile context、generation receipt、完整 summary、priority selections、完整 pair index 和 profile result hash，单字段篡改 recall rank、角色、summary 结论或统计均 fail-closed；
- 三种模式查询次数均固定为 7，与候选数无关，没有 N+1 或候选截断。

## 5. 版本与服务边界

- V1.1 Repository 使用 class-level schema version 隔离版本、列表、进度、profile 与 pair 查找；V1 历史 Reader/Repository 不会把 V1.1 行冒充 V1，反向也不会串读；
- formal 只允许 current published version，且 profile/pair/relation/selection 必须全部 current published；
- draft/review 只能通过显式 version ID 与 `preview=True` 读取；
- Reader 只读取已保存画像，不调用候选召回、分析、打分、角色或排序函数。

## 6. 验证与评审

- G31 Repository/Reader 专项：22 passed；
- V1 Repository/Reader、G29 schema、G30 migration 与 G31 受影响回归：85 passed；
- SQL 次数测试：full=7、compact=7、question-specific=7；
- compact SQL 明确不包含 `analysis_snapshot_json`；
- Ruff：passed；
- Python compile：passed；
- `git diff --check`：passed；
- 独立方法终审：P0=0、P1=0、P2=0，可以关闭；
- 独立工程终审：P0=0、P1=0；P2 为 G39 增加 PostgreSQL 双 Session/`FOR UPDATE` 真实并发集成测试，不阻塞 G31。

## 7. 写入与运行边界

- 业务数据库读取或写入：0；
- 205 访问、部署或 migration：0；
- 画像生成：0；
- G32 SKU snapshot builder、G33—G38 分析或消费代码修改：0；
- 旧 M12/M13/M14 或 V1 草稿修改：0；
- review/publish/current/deprecated 状态切换：0；
- 飞书消息、卡片、报告或文档：0；
- git stage/commit：0；
- 用户其他未跟踪文件和卖点价值修改未触碰。

## 8. 后续执行效率规则

调度文档已按用户要求增加跨后续 Goal 的执行规则：10 分钟 heartbeat 只负责断点续跑；每次唤醒持续执行 active Goal 至完成或真实阻塞；G32—G38 运行专项测试和必要回归，完整回归、覆盖率、性能与总评审集中到 G39；复核意见合并修复后一次终审。

## 9. 下一 Goal

G32：从既有 category input bundle 生成版本内共享 SKU 分析快照，保证 M03B—M12D 事实、unknown/null/empty、authority、lineage、review 和 evidence refs 无损，且同一 SKU 在同一 version 只保存一次。不得访问外部 LLM，不得在 pair 内复制完整 SKU JSON。
