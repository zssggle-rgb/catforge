# SPV51-G16 AC 单 SKU V5.1 Draft 关闭回执

状态：completed

日期：2026-07-17

## 1. 目标与结果

只在 205 为海信 `KFR-35GW/E5E1-1`（`AC00039187`）生成并验收了一个明确命名、不可变的用户卖点价值画像 V5.1 draft：

- profile version：`spv_v5_1_ac39187_g16_20260717_r1`；
- version id：`79da586e-f655-45c9-ba32-95c957e57a80`；
- profile id：`3171c15a-781c-4384-9616-8fcbc313692d`；
- version / profile / candidate / item：`1 / 1 / 96 / 8`；
- `release_status=draft`、`is_current=false`；
- `release_quality_status=ready`、`processing_status=completed`；
- `analysis_state=ready`、`conclusion_status=conclusion_available`；
- `review_required=false`、`invalid=0`、`integrity_error=0`。

V5.1 的 TV 与 AC 均仍只有各自单 SKU 验收草稿，published/current 均为 0。

## 2. 数据来源与隔离

目标 SKU 从正式 current/published AC 竞品画像中选择，唯一正式竞品来源为：

- version id：`eed759a8-a666-4257-8c4d-3405621a4244`；
- profile version：`competitor_profile_agent_snapshot_v2_ac_full_g41c_20260716_r1`；
- method：`competitor_profile_agent_snapshot_v2`；
- version result hash：`sha256:competitor_profile_agent_snapshot_version_result_v1:b9cecd9d62402ade393f31b872b4a564895bc6e9985ac7c6ef853b7e2057bbe4`；
- target profile result hash：`sha256:competitor_profile_agent_profile_result_v2:61c5794bf148c8b155363049c01fc4ed32d1873adea40bc568198ecde9f6b476`。

画像保存正式竞品 20 款、市场与产品设计参照 76 款，Top 3 为：

- `AC00035950`；
- `AC00038855`；
- `AC00038232`。

没有调用旧 M12/M13/M14 fallback，没有重跑 M03B—M12D，没有跨品类候选。

## 3. AC 业务验收

### 用户价值与战场

8 个用户价值项全部为 `conclusion_available`，覆盖：

- 冷暖效果；
- 新风与空气健康；
- 大空间冷暖；
- 长期省电；
- 低价核心体验；
- 匹数与空间匹配；
- 小空间安装适配；
- 远程与智能控制。

已保存的价值战场为：

- 1匹及以下挂机舒适升级；
- 2匹挂机大房间均衡。

保存结果、报告和问答中 TV 术语、TV 参数角色和跨品类假设均为 0。

### 产品投入

8 类投入均为 `unknown`，基础能力状态均为 `not_assessed`。这属于局部证据未知，不影响用户价值、量价、SKU 或版本形成可用结论。

产品经理输出已明确：

- 暂不能判断哪些投入值得继续加码；
- 暂不能判断哪些投入已经转化、哪些没有转化；
- 不能把未知解释成没有短板；
- 先补齐现有投入的用户价值转化判断，再决定竞品配置跟进或补缺。

### 量价与产品动作

6 条直接量价结论去重后形成 4 组首屏对照：

- 本品周均价高 `150.3～233.9 元`；
- 本品周均销量低 `1281.2～4803.2 台`。

因此首屏结论为：

- 当前价格支撑存在压力；
- 若销量优先，先验证已成立的用户价值能否改善销量；
- 仍无改善时，再下调价格或把 SKU 调整为走量角色；
- 本品当前处于舒适升级款与走量款的定位取舍点。

完整业务报告：`SPV51_G16_AC39187_acceptance_report.md`。

## 4. 验收中发现并修复的 P1

本 Goal 只修复真实 AC 验收暴露的必要问题：

1. `47af89a`：清除 AC 竞品输入中遗留的 TV 参数角色标签，保留真实 AC 参数、值、证据和 pair hash；
2. `f725fba`：将 Markdown 中内部门槛码翻译为产品经理可理解的结论边界；
3. `4358322`：确保投入 unknown 不再被写成“没有价值转化短板”；
4. `f54849b`：让投入问答和价值战场问答与已保存画像一致。

四个提交均已推送当前分支。画像生成算法和已保存画像未因后两项展示修复而重算。

## 5. 消费一致性与零重算

profile result hash：

`sha256:sellpoint_value_profile_result_v5_1:ec75c00e05d91906af949cf212bb8f7e8c59d47e02fad61aefa41c398b20bff7`

报告、飞书卡片和七类问答均返回该 hash。SQL 录制共 56 条语句，只读取：

- `core3_competitor_profile_version`；
- `core3_sellpoint_value_profile_version`；
- `core3_sku_sellpoint_value_profile`；
- `core3_sku_sellpoint_value_candidate`；
- `core3_sku_sellpoint_value_item`。

没有读取竞品 pair、旧 M12/M13/M14 或现场市场计算表。因此报告、卡片和问答只消费同一个已保存画像。

## 6. 测试与运行时

- AC adapter 专项测试：30 passed；
- 报告边界专项测试：41 passed；
- unknown 投入专项测试：42 passed；
- 最终问答消费测试：12 passed；
- Python compile 与 `git diff --check` 通过；
- 完整回归沿用已通过的 SPV51-G13，没有在 G16 重复执行；
- 205 API image：`sha256:36b7e2af0e474580c599551e6b247696faa578a24f8c3c7d1525345024eb8867`；
- Alembic：`0048_core3_sellpoint_value_profile_v5_1 (head)`；
- `/healthz=ok`、`/readyz=ready`、restart count `0`；
- 最终复核窗口 `ERROR / Traceback / CRITICAL = 0`；
- 并发生成进程为 0。

保护性备份：

- `/home/deploy/catforge-deploy-backups/spv51-g16-p1-20260717`；
- `/home/deploy/catforge-deploy-backups/spv51-g16-p2-20260717`；
- `/home/deploy/catforge-deploy-backups/spv51-g16-p3-20260717`；
- `/home/deploy/catforge-deploy-backups/spv51-g16-p4-20260717`。

## 7. 保护门禁

本 Goal：

- 没有 review、publish、current 或 deprecated 切换；
- 没有生成其他 AC SKU；
- 没有执行 TV/AC 全量生成；
- 没有修改旧 V5、旧 M12/M13/M14 或正式竞品画像；
- 没有切换远端 Git HEAD；
- 没有删除、清理或提交远端用户 dirty/stash；
- 远端 `.env` hash 保持 `7243971662532eaa036d64f7d73d71920c586286a94df5eacead1713e6e5b56a`；
- 受保护 stash OID 保持 `2156593622e0f07af67695da1e0e965153349b05`。

结构化证据：`SPV51_G16_AC39187_acceptance_evidence.json`。

G16 已通过，后续允许另行创建 SPV51-G17；本 Goal 不创建、不执行全量生成。
