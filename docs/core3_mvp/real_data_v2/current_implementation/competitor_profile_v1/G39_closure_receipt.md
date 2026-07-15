# G39 竞品画像 V1.1 综合验收与提交关闭回执

状态：completed

日期：2026-07-16

## 1. 目标与结果

G39 已在不连接业务数据库、不访问 205、不生成业务画像、不重跑
M03B—M12D、不修改旧 M12/M13/M14 或 V1 草稿、不执行
review/publish/current/deprecated 状态切换的边界内，完成 G27—G38 的一次性
综合测试、性能与存储验收、方法/工程/业务总评审和问题修复。

终审结果：P0=0、P1=0；G27 CA01—CA30 均有实现和自动化证据，可进入 G40
仅代码与 migration 部署。

## 2. 一次性完整回归与覆盖率

- V1.1 专项、当前 V1、CLI、竞品答案、产品经理报告、飞书离线发布和相关
  回归：621 passed，0 failed；高于 G39 要求的 299 项基线；
- competitor answer、PM report、Feishu publish 全部使用 mock/offline 路径，
  外部消息发送和文档创建为 0；
- V1.1 十个核心模块 branch coverage：总计 86%；各模块 83%—91%；
- 性能优化后受影响的全部 V1.1 与 hash 回归再次通过；
- migration、性能证据和 hash 专项终验：31 passed；
- ruff、Python compileall、`git diff --check`：全部通过。

## 3. Migration 与历史 DDL 防漂移

- 0047 upgrade/downgrade、重复 upgrade、V1 数据保真、SQL NULL/JSON null、
  downgrade guard、SQLite/PostgreSQL DDL compile 全部通过；
- 0046 已等价冻结为自包含 V1 DDL，不携带任何 V1.1 表、列或约束；
- SQLite 0046 golden hash：
  `b6255c8a223fe0f52baa24c4acce7e23f86bb097fc9b1e377cd2ac5f331f2cae`；
- PostgreSQL 0046 golden hash：
  `5d1782ea8bf178a05c819a785ab9773341e2c978a2a446c6b98f80048b12d174`。

## 4. 最大候选性能、存储与确定性

冻结口径为：G32—G35 工作结果准备完成后，计时 V1.1 materialize 和完整
draft 序列化；内存记录准备完成并 GC 后的当前 RSS 基线之上的新增进程峰值。
输入准备时间、输入峰值、物化绝对峰值和进程绝对峰值仍逐轮保存，不隐藏。

| 品类 | 候选 | 物化+序列化 p95 | 新增峰值内存 | draft bytes | 三轮 hash | 结果 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| TV | 377 | 30,859.091 ms | 1,085.875 MiB | 352,784,263 | 一致 | passed |
| AC | 155 | 12,005.755 ms | 540.344 MiB | 145,203,967 | 一致 | passed |

对应冻结预算分别为 TV 60 秒/1,200 MiB/512 MiB，AC 30 秒/600 MiB/256 MiB。
候选截断和分析维度删除均为 false。Provider 固定 11 次 SELECT、target 增量
SELECT 为 0；Repository full/compact/question 三种读取共 7 次 SELECT，候选循环
SELECT 为 0。

证据文件：`G39_v11_max_scale_benchmark.json`。

## 5. 65E7Q、旧 Top 3 与零重算

- G28 冻结的 65E7Q 旧候选和 Top 3 对账完整；旧候选不存在因 review、
  authority、taxonomy 或非正式直接竞品而停止全部分析的情况；
- TCL 65Q9L PRO、华为 VISION 智慧屏 5 PRO 65、创维 65A7H PRO 均进入
  完整多维计算和问题级选择；
- 重点名单差异由保存的 score、role、question、strength 和 selection reason
  解释，不由统一门槛或缺失当零产生；
- V1.1 智能体正式路径只执行 SKU 解析、Reader、Adapter 和纯展示入口；
  AtomicHandlers、原始 Provider、enrichment、Calculator、Gate、Selector、
  打分、角色、排序和 Top 3 选择的调用次数均为 0；
- formal 只读 current published V1.1；preview 必须显式 scope、version 和 opt-in；
  不可用时明确返回，不静默回退旧现场链。

## 6. CA01—CA30 总评审

- CA01—CA05：Typed Schema、共享 SKU snapshot、完整 pair 过程、结论和
  adapter 合同覆盖全部旧智能体最低数据基线；
- CA06—CA13：hard exclusion、dimension availability、conclusion strength、
  review overlay 四轴独立；unknown 不变 0，score 三元组和问题级最低证据闭合；
- CA14—CA20：基础功能 prevalence、量价非单卖点因果、候选/角色/重点名单
  分层、未入选原因、逐维度强度/证据/限制均持久化；
- CA21—CA23：智能体单版本读取、零现场重算、局部 unknown 不跨维度传播；
- CA24—CA30：V1 只读、新版本 draft、65E7Q→AC→全量串行门禁、性能不裁剪、
  publish/current 另行授权均保持。

G29 typed mapping、G34 四轴门槛、G35 重点选择、G36 物化与生成、G37 Adapter、
G38 智能体读取路径逐项复核后，无未关闭合同缺口。

## 7. G39 发现并关闭的问题

1. 初版性能脚本把 `tracemalloc` 套在输入准备、三轮物化和序列化全过程，
   追踪器自身把内存和耗时严重放大；改为每轮独立子进程，并明确拆分输入准备、
   物化序列化和 RSS 口径。
2. 大画像 result hash 原先会同时保留完整 dumped tree、normalized tree 和
   canonical string；新增与既有 `stable_hash` 字节合同完全一致的逐 typed-row
   streaming hash，画像 hash 不变，避免额外整树复制。
3. G30 工程复核对 0046 的等价冻结与早期设计文字存在表述冲突；详细设计已
   明确 V1.1 结构只由 0047 增加，0046 只做无结构变化的历史 DDL 自包含冻结。
4. 为 0046 双方言 DDL 和 G39 最大规模性能结果增加自动化 golden 回归，防止
   后续无意漂移。

## 8. 写入与发布边界

- 真实业务数据库读写：0；
- 205 访问、部署、migration 执行：0；
- 业务画像生成：0；
- review/publish/current/deprecated 切换：0；
- M03B—M12D 重跑：0；
- 飞书消息发送或文档创建：0；
- 用户卖点价值、飞书窗口模式、百科修复、图片、tmp/output 和其他未跟踪文件
  均不进入本任务提交。

## 9. 下一 Goal

G40 只部署本次精确提交的代码和 migration 到 205，完成 commit/container、
migration、health、ready 和 rollback 验证；不得生成任何画像。G40 完成后才允许
创建 G41A，并且 G41A 只生成海信 65E7Q 单 SKU draft。
