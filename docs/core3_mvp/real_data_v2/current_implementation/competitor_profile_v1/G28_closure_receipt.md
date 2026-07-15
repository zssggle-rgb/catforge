# G28 竞品分析兼容基线关闭回执

状态：completed

日期：2026-07-15

## 1. Goal

在不修改竞品算法和 V1.1 schema、不写数据库、不访问 205 写路径、不发布飞书的前提下，冻结当前竞品分析智能体的完整机器可读兼容基线，为 G29 Typed Schema 提供不可降级的输入合同。

## 2. 真实旧智能体基线

四个正式 fixture 均由 `G28_capture_legacy_suite.py` 在 205 现有 API 容器内只读执行旧 `competitor-set` 命令生成。脚本在执行前断言完整 application argv 不含 `--limit` 或 `--limit=...`，并在写入本地确定性 fixture 前核对候选数和冻结 canonical hash。

| 品类/数据状态 | SKU | 默认调用实际候选数 | Top3 是否形成 |
| --- | --- | ---: | --- |
| TV complete | TV00029112 / 海信 65E7Q | 20 | 是 |
| TV published-degraded | TV00009549 | 13 | 是 |
| AC published-ready | AC00026378 | 16 | 是 |
| AC published-degraded | AC00034959 | 20 | 是 |

`G28_legacy_capture_receipts.json` 保存四次完整 argv、stdout hash、canonical hash、gzip hash、远端 commit 和 API image；回执自身 hash 为 `add7b0e550406b0e5638f97c8045a3d8b7770cfe1d896b6793407ddd9106e9ce`。Manifest 不再手工声明“未传 limit”，而是验证回执后派生该结论。

65E7Q 默认 20 候选远端命令还做过一次独立只读重放，再由 capture suite 完整重跑；两次的原始 stdout SHA-256 均为 `5fc56fca077586b540b0f5f0c621caffb791e44bacc34a0e2104129ffcc7a496`，canonical JSON、确定性 gzip 和 Top3 均一致，满足“两次运行 hash 一致”的关闭门禁。

65E7Q 正式默认 20 候选 fixture 的 canonical hash 为 `048d0314b3c18d72279fe03a37f1149342911f7c5e4e844a5ad0bd7754edd86a`，Top3 为：

1. `TV00027801 / TCL 65Q9L PRO`；
2. `TV00028909 / 华为 VISION智慧屏 5 PRO 65`；
3. `TV00029936 / 创维 65A7H PRO`。

早期显式 `limit=10` 的 `G28_65e7q_legacy_analysis_205_20260715.json.gz` 仅保留为诊断样本；它不在正式 fixture 列表、默认验证器、manifest 或 G29 冻结输入中。

## 3. 旧 atom 到 V1.1 字段映射

四个真实 fixture 的观察并集已经形成逐叶映射清单：

- 13,756 条观察路径；
- 12,841 条普通值/null 路径；
- 915 条空列表或空对象路径；
- 65 条前缀映射规则；
- 3,624 组映射到相同 V1.1 目标路径的旧字段别名；
- 未映射路径 0，别名值冲突 0；
- inventory hash：`34be0aa0fdf42437ec3a5d96bf5325e30164a2aa25dd09ee5eb7a3dc71639381`。

每条路径保存 source atom、V1.1 target leaf、源/目标观察类型、fixture 出现次数和值序列 hash、null/空容器规则及 missing/unknown 规则。别名按 candidate SKU 对齐比较值 hash；负例会触发硬失败。本轮冻结的是“已观察兼容映射”，`typed_schema_complete=false`，最终 Typed Schema 和 roundtrip 属于 G29。

## 4. 65E7Q 全候选与 Top3 Golden

205 只读导出的现有 V1 全量对象包含：

- 352 个 pair 候选；
- 2,464 条关系，每个候选 7 条；
- 1 条重点选择；
- 旧智能体默认 20 候选全部存在；
- 旧 Top3 各有完整 pair payload 和 7 条完整 relation payload，共 21 条；
- relation index hash：`169d0c4a7c60c6fdd790f5a0ccfe3a8bf10d77f7647edbf3592007e8e44b9209`。

该 fixture 区分了“旧智能体默认展示/分析的 20 个候选”和“现有 V1 的 352 个候选宇宙”，没有把 20 当作 V1.1 候选上限。

## 5. 八类门槛合同

`G28_gate_fixture_matrix.json` 覆盖 TV complete、M12D missing、M05C review、battlefield conflict、market-only、config-only、AC complete 和 AC partial，并包含基础功能 HDMI 2.1 的下游过滤合同。

验证器真实执行 materialize、mutation 和 contract oracle，验证五类 hard exclusion、语义内容敏感性、M07 删除、AC product form/capacity 购买池、review/conflict/must-continue 及结果确定性。matrix result hash 为 `adb46dc6f7a21e01c4b913e6de455b68e19355896862720986ae01c27ffcc63e`。该对象明确标记 `runtime_behavior_proven=false`：它是 G34 的未来可执行 golden，不冒充当前 V1 已实现新门槛。

## 6. 性能和存储基线

- 旧单 pair：p50 222.0 ms，p95 236.6 ms，峰值 22.32 MiB；
- 旧单 SKU 默认 20 候选：p50 1,889.3 ms，p95 1,899.7 ms，峰值 352.51 MiB；
- 205 真实最大候选：TV 359，AC 151；
- 本地理论上界：TV 377、AC 155，各重复 3 次；
- Provider 固定 11 次 SELECT，目标 SKU 增量查询 0；
- V1 TV 377 pair 确定性序列化 81,154,326 bytes；
- V1 AC 155 pair 确定性序列化 33,371,334 bytes；
- 旧结构直接复制到 TV 377 pair 的估算为 1,757,708,853 bytes。

因此 G29 的预算输入已经冻结：共享 SKU snapshot、pair 保存比较过程和 evidence refs，以批量读取和共享存储解决规模问题，不允许裁剪候选或分析维度。

## 7. 验证与评审

- G28 专项：7 passed；
- 锚点、替代压力、购买压力、答案门禁和候选性能回归：35 passed；
- 合并执行：42 passed；
- Ruff：passed；
- Python compile：passed；
- 默认验证器：`status=passed`；
- Manifest 连续重建 hash 一致，最终 SHA-256 为 `8b4c0ff8542185f1da8933e97fec8e4f86d4890e9aef1de308e04dc75d6092cc`；
- 独立基线复核：P0=0、P1=0，可关闭；
- 独立方法复核：P0=0、P1=0，可关闭；
- 独立工程复核：P0=0、P1=0、P2=0，可关闭。

## 8. 写入边界

- 竞品算法修改：0；
- V1.1 schema 修改：0；
- 数据库写入：0；
- 205 文件写入：0；
- 飞书消息、卡片或文档发布：0；
- review、publish、current 切换：0；
- 本轮仅覆盖 G28 工件与专项测试，未改动用户已有的卖点价值文件和其他未跟踪文件。

## 9. 下一 Goal

G29：把 G28 的已观察映射完整落入 V1.1 Typed Schema，冻结类型、条件必填、alias canonicalization、空容器保存、基础功能 prevalence 合同、机器可读结论合同及性能/存储预算，并通过 roundtrip 测试。G29 尚未开始。
