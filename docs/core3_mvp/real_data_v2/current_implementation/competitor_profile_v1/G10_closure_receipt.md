# 竞品画像 V1 G10 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_candidate_recall_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_candidate_recall.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_candidate_recall.py`。

## 2. 研究过的现有模式

实现前对照了三类已有候选模式：

1. `candidate_recall_service.py`：复用“全量 SKU pair、每个入口保留独立原因和 lineage”的结构；拒绝沿用旧 M12 的召回优先分、强弱分层和不足三款复核逻辑；
2. `sellpoint_value_profile_candidate_service.py`：复用 deterministic manifest、同 SKU 去重和 `limit=0` 表示完整集合的经验；拒绝在召回阶段消费旧 M12/M13/M14 eligibility/status；
3. `analyst_repository.same_size_price_candidates`：确认旧实现存在默认 20 款、预取 50 后截断和 fallback 切换，不作为新版正式画像方法。

G10 只回答“哪些 SKU 值得进入后续关系判断、为什么进入”，不回答“它是不是正式竞品”。

## 3. 已实现召回合同

- 七类入口完整保存：同购买池、同品牌梯度、降档、升档、场景、同价值、市场参考；
- 入口事实覆盖同/相邻预算、同主价值战场、辅/机会战场相邻、共同用户任务、共同目标客群、共同成交理由、共同卖点价值、同品牌产品线和量价高低绩效参照；
- 同一 target×candidate 命中多个入口时只形成一个候选行，但保留全部 `recall_sources` 和逐条 `recall_facts`；
- 每条召回事实保存 target/candidate 值、匹配代码、module/profile/rule/taxonomy、record ID、source batch 和 result hash；
- target/candidate 缺失模块保存 typed unknown reason，不填零、不把 unknown 当成关系不成立；
- target、category、project、product category、SKU prefix 和 serving scope 冲突 fail closed；
- 输入、候选、入口覆盖和完整 manifest 均生成稳定 fingerprint/hash；
- 配置保存同预算 15%、相邻预算 30%、升降档 8%、强价格差 15% 和市场表现比 1.25；
- 修改入口、阈值或 AC 兼容映射时必须使用新的 config version，不能冒用 `competitor_profile_recall_v1`；
- 服务只消费 G09 的内存 bundle，不持有 repository/session，不产生数据库追加查询。

## 4. 无数量上限与阶段边界

- schema 不存在 `max_candidates`、`limit`、`top_n` 或展示数量字段，传入会被 `extra=forbid` 拒绝；
- 验证样例一次召回 41 个候选并全部保留；
- 候选只按 SKU 稳定排序，不按价格、销量、分数或关系强弱排序；
- G10 未产生 `eligible`、`limited`、`reference_only`、relation status、重点竞品或 selected；
- 性能、分页和最大品类压力测试留在 G13，不允许通过截断改变业务集合。

## 5. TV/AC 业务规则

- TV 购买可比性使用精确屏幕尺寸；尺寸缺失时才使用已知 size segment，未知保持 unknown；
- AC 购买可比性必须先匹配产品形态，再匹配能力段或已知 size segment；挂机与柜机不因价格接近自动进入同购买池；
- 205 只读复核确认 AC 正式 M03B 155 款均包含 `installation_type` 和 `cooling_capacity_segment`，值中包含可直接消费的 `normalized_value`；
- 当前默认配置已覆盖上述正式字段，也保留其他明确的 AC form/capacity alias 作为版本化映射。

## 6. 验证

- G10 recall/schema tests：12 passed；
- G05—G10 schema/migration/repository/lifecycle/input/recall：93 passed；
- recall service + schema coverage：91%；
- TV/AC、多入口合并、同品牌梯度、升降档、同主/相邻战场：通过；
- sparse candidate typed unknown、empty manifest、disabled entry：通过；
- 41 候选无固定上限：通过；
- 输入语义 list 顺序反转后 result hash 不变：通过；
- 跨 serving scope 与 blocked target fail closed：通过；
- 配置版本、schema 顺序、membership 和 coverage 反例：通过；
- Ruff、`git diff --check` 和尾随空白检查：通过。

## 7. 状态变化

- 本地业务数据库写入：无；
- 205 数据库写入/migration：无；只执行 `SET TRANSACTION READ ONLY` 后的 AC 字段抽样并 rollback；
- 现有画像 review/publish/current/deprecated：均未执行；
- 正式候选资格、reference purpose、竞争关系、量价结论和重点选择：均未实现；
- 部署：无；
- Git 暂存/提交：无。

## 8. 下一 Goal

允许创建 G11，只实现召回候选的资格状态、正式竞品 membership、分析 reference membership 和问题级基础可用性；必须把 `recalled_only` 与 `reference_only` 分开，missing 保持 unknown，不得提前实现七类完整关系、总分排序、重点竞品选择、画像持久化、205 写入或发布状态切换。
