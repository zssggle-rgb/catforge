# G32 竞品画像 V1.1 SKU Snapshot 关闭回执

状态：completed

日期：2026-07-15

## 1. Goal

在不连接或写入业务数据库、不访问 205、不生成 pair/relation/selection/profile、不修改 G33—G38、旧 M12/M13/M14 或 V1 草稿、不执行 review/publish/current 的前提下，实现 `VersionSkuAnalysisSnapshotBuilder`，把冻结的 category input bundle 中 M03B—M12D 权威事实组装为版本内共享、可追溯且确定的单 SKU 分析快照。

## 2. 共享快照与事实语义

- 每个 version + SKU 只生成一份共享 snapshot，pair 只引用 snapshot ref，不复制完整 SKU JSON；
- identity、产品形态、量价窗口、参数/卖点、价值战场、用户任务、目标客群、M12C 卖点价值、M12D 采购理由与用户兑现均进入 typed snapshot；
- missing、空字符串、显式 null、空集合、false、0、unknown 和 conflict 分开保存，不把缺失伪造成否定或零；
- 同一逻辑事实的全部原始 occurrence 保留；同一实体同一路径出现不同已知值时生成 conflict，合法的多 claim、多 dimension 不互相误判；
- 单模块缺失、冲突或需复核只降低该模块 availability，不阻断其他模块。

## 3. Authority、Lineage 与 Evidence

- 每个模块保存 profile/schema/rule/taxonomy version、release/current 状态、source batch 和 result hash；
- evidence_id、source_file_id、raw_row_id、record_id 与原始 occurrence 均可追溯；
- 同 version + SKU + input 的 snapshot ref、input fingerprint 和 result hash 稳定；输入变化会产生不同 hash；
- Builder 不调用数据库、Repository、外部 LLM、网络或 G33 之后的分析模块。

## 4. M12C 卖点价值快照

- Provider 继续保持每品类固定 11 个 SELECT；M12C 在一个 SELECT 中同时读取卖点价值量化、市场池、池内量价指标和 SKU 归因；target 读取不增加额外查询；
- typed projection 保存 claim/value role、上下文、证据强度、with/without pool、参数竞争力、市场位置、价格/销量表现和 SKU excess 解释；
- authoritative attribution 的 confidence、baseline、observed、SKU gap、summary，以及 positive/drag/opportunity 列表按上游原序保存；只有权威归因缺失时才从 claim row 做明确降级；
- 多个合法 claim 使用 entity-set 语义，不会被误判为同一事实冲突。

## 5. M12D 采购理由快照

- 完整且合法的采购理由/价值锚点进入 typed snapshot；
- 不完整或 schema 不合法的 anchor 被逐条跳过并形成 limitation，模块降级为 partial/review_required；
- availability 判断与 typed construction 复用同一解析器，避免一边判可用、一边构造失败；
- 单条坏数据不抹去同 SKU 其余合法 anchor。

## 6. TV/AC、确定性与性能

- TV 与 AC 使用各自产品形态事实；AC 冲突不会串成 TV 屏幕形态；
- TV 377 SKU：23.576 秒，峰值 322.2 MiB，序列化 78.3 MiB，通过 60 秒 / 1200 MiB 预算；
- AC 155 SKU：9.995 秒，峰值 133.2 MiB，序列化 32.2 MiB，通过 30 秒 / 600 MiB 预算；
- `build_many` 对 SKU 顺序、snapshot ref 和 result hash 保持确定性。

## 7. 测试与评审

- Provider、候选召回/确定性、pair 基础特征、V1.1 schema、Repository 与 G32 Builder 必要回归：124 passed；
- G32 Builder 专项覆盖 TV/AC complete/partial/missing/conflict、unknown/null/empty/false/0、合法多记录、真实冲突、M12C 权威归因、M12D 局部降级、hash/幂等和无外部调用；
- Python compile：passed；
- `git diff --check`：passed；
- 当前虚拟环境未安装 Ruff，因此本 Goal 未把 Ruff 记为已执行；完整静态工具链检查仍按调度集中在 G39；
- 独立终审：P0=0、P1=0、P2=0，可以关闭。

## 8. 写入与运行边界

- 业务数据库读取或写入：0；
- 205 访问、部署或 migration：0；
- pair/relation/selection/profile 生成：0；
- G33—G38 分析或消费代码修改：0；
- 旧 M12/M13/M14 或 V1 草稿修改：0；
- review/publish/current/deprecated 状态切换：0；
- 飞书消息、卡片、报告或文档：0；
- git stage/commit：0；
- 用户其他未跟踪文件和卖点价值修改未触碰。

## 9. 下一 Goal

G33：实现完整 `PairAnalysisCalculator` 与 `PairAnalysisAssembler`。Calculator 显式调用并冻结 `ValueAnchorMatcher`、`ReplacementPressureClassifier`、`PurchasePressureComparator` 的 method/config version，产出完整 15 分制、10 分制和购买压力过程；Assembler 只做 typed 无损组装、证据引用和 hash，不从简化摘要反推结果。
