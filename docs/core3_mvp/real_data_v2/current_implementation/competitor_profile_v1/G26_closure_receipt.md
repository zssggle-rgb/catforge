# G26 关闭回执

状态：completed

日期：2026-07-15

## 1. Goal

在 G24 TV 单 SKU 和 G25 AC 单 SKU 草稿均通过验收后，继续使用同一不可变版本，为 205 上 TV 377 款、AC 155 款权威 SKU 生成完整竞品画像草稿；逐类目和跨类目完成发布准备只读复核。全过程不得执行 review、publish、set-current、deprecate，不得修改旧 M12/M13/M14 或用户卖点价值画像。

## 2. 运行版本与修复

- 分支：`new/base-publish-workbench-design`；205 最终运行提交：`3341f45c1cd33bdbcaa5a6eb342e744aaf9e9a4e`；
- Alembic：`0046_core3_competitor_profile (head)`；`/healthz=ok`，`/readyz=ready/database ok`；
- G26 在全量 TV 生成前发现重复证据 JSON 会耗尽磁盘，按最小范围完成并部署 `bcb4a31`、`b66fe37`、`30ad163`、`63cabaf`、`aaa1a14`、`2d6769b`、`d4458e9`、`90ed767`、`e006e64`、`3341f45`；
- 最终方案以无损 evidence dictionary 保存 pair，以自校验指针保存 relation，并以 8 行 ORM 批次限制草稿压缩内存；分析 payload、input fingerprint、result hash 和 reader DTO 均不改变；
- AC 已验收单 SKU 的旧存储在全量生成前单独压缩：150 pair、1,050 relation；压缩前后完整 hash receipt 相同；
- 根盘最终剩余约 `60GB`；API 容器空闲内存占用约 `297MiB/3GiB`。

## 3. 权威输入门禁

两个类目均只读取 M03B、M04C、M05C、M07、M09C、M10C、M11C、M11D、M12C、M12D 的 published/current 权威版本；未回退 draft/latest、旧 M12/M13/M14 或现场候选集合。

| 类目 | 权威 SKU | source batch | manifest hash | version input fingerprint | freshness |
| --- | ---: | --- | --- | --- | --- |
| TV | 377 | `m00_20260623014631_c8630747` | `sha256:competitor_profile_authoritative_sku_manifest_v1:9eeeadd0c3a09ea4251b257d1ff006c02be9d3a6f1fcd10dd4943f06306d0c8c` | `sha256:competitor_profile_version_input_v1:32c14ba222c2ca17f39ab6f6e5d8d8ca10fe7a57efe161f1b515cb5f03fc67b5` | current |
| AC | 155 | `m00_20260624000202_1150a669` | `sha256:competitor_profile_authoritative_sku_manifest_v1:6cf0c669f3998e644d3eebbec6a291bdc4d491a275df2a0740581bceda137b96` | `sha256:competitor_profile_version_input_v1:d0dc0ca4e168765f7924deeafa691a25d48c7033b59d20547edd80cb66e49aed` | current |

最终再次从 205 正式上游重建 category input：两个类目的 manifest、version input fingerprint、serving scope fingerprint 均与已保存版本完全一致，changed/unavailable authority 和 changed scope field 均为 `0`。

## 4. 全量草稿结果

| 项目 | TV | AC | 合计 |
| --- | ---: | ---: | ---: |
| 主画像 | 377 | 155 | 532 |
| 完整候选 pair | 126,412 | 21,897 | 148,309 |
| 七类关系 | 884,884 | 153,279 | 1,038,163 |
| 重点选择 | 60 | 11 | 71 |
| generation failure | 0 | 0 | 0 |

TV：

- version ID：`c45c0002-9b8a-4b0d-8b12-344dee020e15`；profile version：`competitor_profile_v1_tv_65e7q_g24_20260714_r1`；
- version result hash：`sha256:competitor_profile_version_result_v1:3331f446b4b86704b8d1a59829fcbdd4e25ddc1eac14abd69fed9eafe9ef108d`；
- 最终 batch checkpoint：`TV00030696`；`processing_status=completed`，`partial_count=377`，`blocked_count=0`，`failed_count=0`。

AC：

- version ID：`45725326-720c-45c8-9a3b-e86fb6cc1f0b`；profile version：`competitor_profile_v1_ac_hisense_s550_g25_20260714_r1`；
- version result hash：`sha256:competitor_profile_version_result_v1:193cfd4692706b95fcc0c22e50f891e6f1edd27c7ef40f1926c6330e3da19f66`；
- 四个串行 checkpoint：`AC00036116`、`AC00038662`、`AC00039400`、`AC00039655`；批次新增 50、50、50、4，全部失败 `0`；
- `processing_status=completed`，`partial_count=155`，`blocked_count=0`，`failed_count=0`。

两个版本始终保持 `release_status=draft`、`release_quality_status=unassessed`、`is_current=false`。竞品画像全库 published/current 版本数为 `0`。

## 5. 完整性、量价与品类隔离

全量 SQL 合同复核结果：

- authoritative manifest 与主画像差集、额外集、重复集均为 `0`；版本计数与实际行数完全一致；
- profile、pair、relation、selection 的 project/category/product category、storage batch、release scope、profile/schema/rule/method version、release/current 状态越界均为 `0`；
- pair codec、payload hash/input envelope、重复 JSON、self pair、重复 candidate、父级范围和 selected status 违规均为 `0`；
- 每个 pair 恰好 7 个不同 relation code；relation pointer code/hash、父级范围、主关系状态、问题可用性与失败原因合同违规均为 `0`；
- 每个 SKU 重点选择为 0—3 条，rank 连续；selection 与 profile/pair、候选状态、payload envelope 违规均为 `0`；
- TV/AC 四层记录的 SKU 前缀和品类串线均为 `0`。

M07 全量量价复核：

- TV 126,412 pair、AC 21,897 pair 的 `market_comparison` 均与 pair payload 一致，authority 均为 published/current M07；
- `causal_claim` 违规为 `0`；价格、周均销量没有缺失值被填成 0；零分母 ratio 和 unknown-without-reason 违规均为 `0`；
- 量价只支持描述性市场关系，不把相关性改写成卖点因果销量或单卖点 WTP。

类型化回读：

- TV 377 个主画像、每个 SKU 一个确定性代表 pair、2,639 条嵌套关系和 60 个 selection 全部通过 Pydantic 解码与 envelope 校验；
- AC 155 个主画像、每个 SKU 一个确定性代表 pair、1,085 条嵌套关系和 11 个 selection 全部通过；
- relation pointer 的全量 code/hash 一致性已经由上述 SQL 对 1,038,163 行逐行验证。

## 6. Reader、diff 与发布准备结论

- TV `TV00029112 / 65E7Q` 与 AC `AC00032008 / KFR-35GW/S550-X1` 的 formal reader 均返回 `profile_unavailable`；没有 current published 时不回退旧链或现场重算；
- 显式指定对应 version 并开启 draft preview 后，两款均返回 `available`、`preview=true`，business/evidence DTO 锁定同一版本；
- 65E7Q compact readback 为 34 pair、238 relation、1 selection；AC 样本为 14 pair、98 relation、2 selection；
- 两款 self version diff 均为 `has_changes=false`、语义变化 `0`。TV diff hash：`sha256:competitor_profile_version_diff_v1:3b934e97c2c8d2468d32446bfb4083fc3ddc863a5f108a277c6d301046c97d07`；AC diff hash：`sha256:competitor_profile_version_diff_v1:64658ddaf94d0163b669b654874fb422a31f738648c2221ffd05b1dffe0c26fb`。

只读质量推导：

- TV：40 款 `partial/available`，337 款 `partial/insufficient_evidence`；
- AC：8 款 `partial/available`，147 款 `partial/insufficient_evidence`；
- 两个类目覆盖完整、无 failure、无 blocked、无 P0/P1，因此发布准备质量应为 `limited`，不是 `blocked`；
- `limited` 的原因是真实上游证据不足。G26 不执行 review，因此数据库 `release_quality_status` 继续保持 `unassessed`；后续若要发布，必须单独完成人工 review，并明确接受 limited 版本，随后再分别审批 publish 与 current 切换。

## 7. 测试与保护边界

- 本地竞品画像专项：`299 tests collected`，全部通过；
- Ruff：`All checks passed`；`git diff --check` 通过；
- 205 最终提交、Alembic、health/ready、数据库会话和磁盘复核通过；无遗留生成进程或非 idle 数据库会话；
- 未创建或发送批量飞书卡片/文档；未修改旧 M12/M13/M14，未修改或发布用户卖点价值画像；
- 未执行 review、publish、set-current 或 deprecate；没有把 read-only 质量推导写回数据库。

## 8. 任务链结论

G01—G26 全部完成。当前已得到可审核的 TV/AC 全量竞品画像草稿，但尚未得到正式可消费版本。下一步不自动创建 Goal；只有用户单独明确批准后，才可规划 review、publish、current 切换和消费者正式启用。
