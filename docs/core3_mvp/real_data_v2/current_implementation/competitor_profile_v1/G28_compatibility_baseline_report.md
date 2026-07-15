# G28 旧竞品分析兼容基线报告

状态：completed

日期：2026-07-15

## 1. 本轮冻结了什么

G28 冻结的是当前竞品分析智能体已经计算出来的机器数据，不包含飞书卡片、报告正文、短回答或问答话术，也没有把 G29 尚未实现的 Typed Schema 说成已经完成。

本轮形成四类可核验基线：

1. 旧智能体真实默认调用：CLI 未传 `--limit`，实际默认上限为 20；
2. 四个真实 TV/AC 兼容样本：完整与局部缺失均有；
3. 65E7Q 的现有 V1 全候选、全部关系及旧 Top3 完整 pair 证据；
4. 单 pair、默认 20 候选单 SKU、TV/AC 最大候选规模的性能与存储基线。

后续 V1.1 必须满足：旧链已经存在的已知值、null、空列表和空对象均不得无故丢失或变成 unknown；智能体读取画像后，不得重新执行分析、打分、角色、排序或 Top3 选择。

## 2. 读取边界和调用合同

- 读取环境：205；
- 远端提交：`3341f45c1cd33bdbcaa5a6eb342e744aaf9e9a4e`；
- API image：`sha256:62fc2c560070a47bfdbdbba57043b379a8db2e6fee46c09fb7d14dc1477092ff`；
- 旧智能体调用：`competitor-set --top-n 3 --answer-style xiaoao --with-report none --format json`；
- `G28_capture_legacy_suite.py` 在同一进程内构造并执行四次应用 argv，逐次断言不存在 `--limit`，完整 argv、stdout hash、canonical hash 和 gzip hash 均写入 `G28_legacy_capture_receipts.json`；
- CLI 与 SOP 的默认候选上限均为 20；
- 抓取后只保留 `snapshot`、`legacy_input` 和 `legacy_analysis`，删除全部展示字段；
- 数据库写入 0，205 文件写入 0，飞书发送/建文档 0。

此前显式 `limit=10` 的 `G28_65e7q_legacy_analysis_205_20260715.json.gz` 只是一份早期诊断样本，不再作为 G28 正式兼容输入。正式输入是文件名含 `default20` 的四份 fixture。

## 3. 四个真实兼容样本

| 样本 | 品类 | SKU | M12D 消费状态 | 实际候选数 | 旧智能体是否形成 Top3 |
| --- | --- | --- | --- | ---: | --- |
| 65E7Q 完整样本 | TV | TV00029112 | published_ready | 20 | 是 |
| TV 局部缺失样本 | TV | TV00009549 | published_degraded | 13 | 是 |
| AC 完整样本 | AC | AC00026378 | published_ready | 16 | 是 |
| AC 局部缺失样本 | AC | AC00034959 | published_degraded | 20 | 是 |

13 或 16 并不是人为截断；它们是在默认上限 20 下旧候选池实际返回的全部候选。四个样本共同证明兼容合同必须覆盖 TV/AC、完整/降级两种数据状态，不能只由 65E7Q 单样本推导。

## 4. 65E7Q 默认 20 候选和 Top3

| 召回序 | SKU | 产品 | competitor score | business score | 旧角色 | 锚点 /15 | 压力 /10 |
| ---: | --- | --- | ---: | ---: | --- | ---: | ---: |
| 1 | TV00029020 | 小米 L65MC-SP | 0.9289 | 0.8226 | strong_direct | 11 | 7 |
| 2 | TV00029936 | 创维 65A7H PRO | 0.9180 | 0.8286 | strong_direct | 10 | 7 |
| 3 | TV00027801 | TCL 65Q9L PRO | 0.9189 | 0.9242 | primary_direct | 13 | 8 |
| 4 | TV00028909 | 华为 VISION智慧屏 5 PRO 65 | 0.9239 | 0.9269 | downtrade_diversion | 14 | 10 |
| 5 | TV00027912 | 海信 65E5Q-PRO | 0.8588 | 0.9269 | downtrade_diversion | 14 | 10 |
| 6 | TV00028166 | TCL 65T7L ULTRA | 0.8611 | 0.9008 | downtrade_diversion | 14 | 9 |
| 7 | TV00028829 | 创维 65A6F ULTRA | 0.9219 | 0.8415 | downtrade_diversion | 14 | 9 |
| 8 | TV00027861 | 华为 VISION智慧屏 5 65 | 0.9104 | 0.7923 | downtrade_diversion | 11 | 9 |
| 9 | TV00027541 | 海信 65E5Q | 0.8747 | 0.8851 | downtrade_diversion | 12 | 9 |
| 10 | TV00027899 | 索尼 K-65XR50 | 0.9179 | 0.9008 | uptrade_alternative | 13 | 9 |
| 11 | TV00027027 | 小米 L65MB-SP | 0.9198 | 0.7615 | downtrade_diversion | 10 | 8 |
| 12 | TV00028099 | 小米 L65MB-S | 0.9081 | 0.8015 | downtrade_diversion | 13 | 9 |
| 13 | TV00028546 | 海信 65D30QD | 0.7604 | 0.5911 | downtrade_diversion | 12 | 8 |
| 14 | TV00030053 | VIDDA 65VX3S | 0.9078 | 0.7535 | downtrade_diversion | 11 | 8 |
| 15 | TV00026065 | 小米 L65MA-SPL | 0.9227 | 0.8015 | downtrade_diversion | 13 | 9 |
| 16 | TV00028423 | 创维 65A5F MINI | 0.9095 | 0.7995 | downtrade_diversion | 13 | 9 |
| 17 | TV00029169 | 海信 65E52Q | 0.8647 | 0.8056 | downtrade_diversion | 14 | 9 |
| 18 | TV00028082 | 华为 VISION智慧屏 5 SE 65 | 0.8736 | 0.6921 | downtrade_diversion | 11 | 8 |
| 19 | TV00029120 | 雷鸟 65R69A | 0.8977 | 0.6607 | downtrade_diversion | 9 | 8 |
| 20 | TV00030137 | 海信 65E3S-PRO+ | 0.8298 | 0.6771 | downtrade_diversion | 12 | 9 |

当前 Top3 Golden 仍为：

1. `TV00027801 / TCL 65Q9L PRO / primary_direct`；
2. `TV00028909 / 华为 VISION智慧屏 5 PRO 65 / downtrade_diversion`；
3. `TV00029936 / 创维 65A7H PRO / strong_direct`。

Top3 与早期 10 候选诊断样本一致，但正式兼容基线以默认 20 候选的结果为准。选择序既不等于召回序，也不等于 business score 简单降序，所以 V1.1 必须保存最终角色、选择序和未入选原因，展示层不能重新选。

最新一次只读捕获由同一脚本完成“构造精确 argv、远端执行、解析 stdout、核对冻结 canonical hash、写确定性 fixture、生成回执”的完整链路。65E7Q 的 canonical JSON SHA-256 仍为 `048d0314b3c18d72279fe03a37f1149342911f7c5e4e844a5ad0bd7754edd86a`，Top3 未变化；这不是只做本地重放，也不是在 manifest 中手工声明未传 `--limit`。

## 5. 65E7Q 的 V1 全候选对账

205 现有 V1 画像版本 `c45c0002-9b8a-4b0d-8b12-344dee020e15` 中，65E7Q 有：

- 352 个 pair 候选；
- 2,464 条关系，恰好每个候选 7 条；
- 1 条 V1 重点选择；
- 旧智能体默认 20 候选全部存在于 352 个候选中；
- 旧 Top3 各保存完整 V1 pair payload 和 7 条完整 relation payload，共 21 条；
- 2,464 条关系均保存候选 SKU、关系 code、状态、主关系标志、问题资格、result hash 和复核状态；
- 重新按行统计的 pair/relation 状态分布与 profile 内的汇总完全一致。

这证明的是“旧智能体 20 候选与 V1 352 候选之间的身份和关系对账”，不是用 352 推断旧智能体本身会分析 352 款。V1.1 的完整候选宇宙必须由画像候选规则决定，不能由智能体展示参数决定。

## 6. 旧字段到 V1.1 的观察映射

四个真实 fixture 的并集结果：

- 观察路径：13,756；
- 普通值/null 路径：12,841；
- 空列表/空对象路径：915；
- 前缀映射规则：65；
- 已覆盖观察路径：13,756；
- 未映射：0；
- 映射到同一目标路径的别名组：3,624；
- 别名值冲突：0。

别名不是用路径名猜测相等。验证器按 candidate SKU 对齐 `legacy_input.candidates[]` 与 `legacy_analysis.all_candidates[]`，逐 fixture 比较值 hash；每组还保存 canonical source、alias source、等值结果和冲突失败策略。

这仍然只是“已观察兼容清单”，不是最终 Typed Schema。G29 必须把这些观察路径转成类型化字段并做 roundtrip；G28 不宣称四个样本之外不存在其他路径，也不宣称每条旧路径都对应独立数据库列。

## 7. 八类门槛 fixture 的证据边界

八类 fixture 为：TV 完整、TV M12D 缺失、TV M05C 复核、TV 战场冲突、TV 仅市场、TV 仅配置、AC 完整、AC 局部缺失。

它们是 G34 的未来可执行合同 golden，不是当前 V1 运行时已经符合新门槛的证明。验证器当前证明的是合同自身确定且具有敏感性：

- 五类 hard exclusion 分别做独立负向变异，均只返回对应排除 code；
- 在模块可用性不变时，把候选任务/客群/战场改成完全不同，直接选择结论从 supported 降为 directional，证明内容差异会影响结论；
- AC 购买池使用 `ac_product_form + cooling_capacity_segment`，完整和局部样本均得到 P0，不依赖电视尺寸；
- HDMI 2.1 样例只验证“外部已判为基础功能后，原始差异保留但不贡献差异化排序”。基础功能 prevalence 分类和阈值仍由 G29 冻结，G28 没有证明分类器。

## 8. 性能与存储基线

### 8.1 当前旧智能体

| 场景 | cold | p50 / p95 | 峰值内存 |
| --- | ---: | ---: | ---: |
| 单 pair 完整旧答案计算 | 213.9 ms | 222.0 / 236.6 ms | 22.32 MiB |
| 单 SKU、默认 20 候选完整旧答案计算 | 1,900.8 ms | 1,889.3 / 1,899.7 ms | 352.51 MiB |

默认 20 候选重复计算得到相同 analysis hash：`198af4ff753192749b6e06b443ee339ffe9430f97a7a48bbeb14f75597c4faa0`。

### 8.2 最大候选规模

205 只读统计的真实最大值为：TV `TV00025784`，359 个候选；AC `AC00028642`，151 个候选。本地按品类理论上界继续测试 TV 377 和 AC 155：

| 场景 | pair / relation | p95 | 峰值内存 | Provider SELECT |
| --- | ---: | ---: | ---: | ---: |
| TV 候选流水线 | 377 | 5,503.4 ms | 41.18 MiB | 11 |
| TV materializer | 377 / 2,639 | 20,154.0 ms | 563.24 MiB | — |
| AC 候选流水线 | 155 | 2,237.0 ms | 16.99 MiB | 11 |
| AC materializer | 155 / 1,085 | 8,461.4 ms | 231.76 MiB | — |

Provider 为固定 11 次 SELECT，目标 SKU 新增查询为 0，没有随候选数增长的 N+1。

### 8.3 存储

| 对象 | 确定性 JSON 大小 |
| --- | ---: |
| 目标 SKU 事实快照 | 3,327,949 bytes |
| 单 pair 中位 | 5,753,986 bytes |
| 单 pair 最大 | 7,316,335 bytes |
| 默认 20 pair 合计 | 93,247,154 bytes |
| 旧结构直接复制到 377 pair 的估算 | 1,757,708,853 bytes |
| 当前 V1 TV 377 pair 实际序列化 | 81,154,326 bytes |
| 当前 V1 AC 155 pair 实际序列化 | 33,371,334 bytes |

因此 G29 必须共享 SKU snapshot，pair 只保存实际比较过程、分数、结论和 evidence refs；但不能以节省空间为由删除旧智能体已经算出的维度。

## 9. 当前验证状态

- G28 专项测试：7 passed；
- 相关竞品算法回归：35 passed；合并执行：42 passed；
- 四次远端调用的精确 argv 回执、fixture hash 和回执自身 hash：passed；
- 默认 20 候选 Top3 确定性：passed；
- 四个真实 fixture 的展示字段递归排除：passed；
- 13,756 个观察路径映射、915 个空容器和 3,624 组别名等值：passed；
- 352 pair、2,464 relation、旧 Top3 完整 V1 payload 对账：passed；
- 八类合同 fixture、五类 hard exclusion 和语义负向敏感性：passed；
- 数据库、205 文件、飞书写入：0。

独立基线、方法和工程复核均确认 P0=0、P1=0；工程最终复核 P2=0。方法复核提出的手工 `local_remote_analysis_code_hashes_equal_at_capture=True` 冗余字段已删除；基线复核建议的 gate matrix 计算 hash 与 manifest 直接对账断言已补齐。G28 关闭条件全部满足。

## 10. G29 必须消费的冻结输入

1. 四个 `G28_*legacy_analysis_default20_205_20260715.json.gz` 真实 fixture；
2. `G28_legacy_capture_receipts.json`；
3. `G28_legacy_to_v11_field_mapping.json`；
4. `G28_legacy_leaf_mapping_inventory.json.gz`；
5. `G28_gate_fixture_matrix.json`；
6. `G28_65e7q_v1_full_universe_205_20260715.json.gz`；
7. `G28_legacy_runtime_benchmark.json`；
8. `G28_profile_scale_benchmark.json`；
9. `G28_legacy_baseline_manifest.json`。

G29 的关闭条件是：把观察映射完整落入 Typed Schema，补齐类型、条件必填、alias canonicalization、空容器保存和 roundtrip 测试；不能把 G28 的 100% 观察覆盖误写成最终 Schema 已完成。
