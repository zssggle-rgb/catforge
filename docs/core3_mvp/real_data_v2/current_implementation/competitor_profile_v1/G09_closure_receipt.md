# 竞品画像 V1 G09 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_input_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_input_provider.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_schemas.py`：允许各正式上游保留各自 taxonomy authority，不再错误强制等于竞品画像 manifest taxonomy；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_input_provider.py`。

## 2. 研究过的现有模式

实现前对照了三类已有读取模式：

1. `sellpoint_value_profile_input_provider.py`：复用 context scope、typed bundle 和稳定 fingerprint 模式；
2. `purchase_reason_profile_reader.py`：复用正式 M12D version/profile 的发布状态读取语义；
3. `analyst_repository.py`：识别并拒绝其 batch/latest 回退和读取时混入候选业务逻辑的做法。

竞品画像输入层只负责锁定和读取正式上游事实，不在这里召回竞品、判断关系或临时生成采购理由。

## 3. 已实现输入合同

- 一次 category snapshot 锁定 M03B、M04C、M05C、M07、M09C、M10C、M11C、M11D、M12C、M12D 十个 source authorities；
- TV 支持已声明的多个 source batch，AC 强制单 batch；
- M07 构成 authoritative SKU manifest，所有其他模块只能在 manifest 内批量读取；
- 按 project、category、product category、source batch、rule、taxonomy、population、market window、current/release status 和 SKU prefix 做 exact gate；
- M12D 必须锁定唯一 `published/current` 且质量可消费的 version，不按创建时间或最新行回退；
- 单记录模块同一 SKU 出现不同 result hash 时直接报 authority conflict，不用 batch 新旧覆盖；
- M03B、M07 为目标 SKU hard-required；可选模块缺失保存为 typed `unknown` 和 limitation，不填零、不借别的 SKU 或历史 M12/M13/M14；
- 每条输入保留 module、record ID、source batch、profile/schema/rule/taxonomy version、result hash 和事实快照；
- category、module、target 三层均生成确定性 fingerprint；
- target snapshot 完全由已加载 category bundle 构造，不再查询数据库。

## 4. 205 只读事实复核

- 当前正式 M12D：TV 为多 source batch，AC 为单 source batch；
- M11D 的 TV/AC population 不相同，M12C 使用独立 claim-value population，因此请求合同分别保存 category、semantic-market、claim-value 三类 population；
- 在 exact rule、taxonomy、current 和 serving scope 下复核，M03B/M04C/M05C/M07/M09C/M10C/M11C 未发现同 SKU 多个不同 hash 的 authority 冲突；
- 所有线上检查均为只读，没有执行 migration、生成、review、publish 或 current 切换。

## 5. 验证

- G09 input provider/schema tests：24 passed；
- G05—G09 schema/migration/repository/lifecycle/input：81 passed；
- input provider coverage：99%；
- input schema coverage：100%；
- TV 多 batch、AC 单 batch、跨类目 M03B 污染阻断：通过；
- 可选模块缺失降级、必需模块缺失阻断：通过；
- M12D 唯一正式版本、质量、source scope 和 profile 一致性门禁：通过；
- 非 current/错误 taxonomy/错误 rule 不回退：通过；
- manifest、authority、module、target fingerprint 稳定性：通过；
- category snapshot 固定 11 次 SELECT，target snapshot 0 次追加 SELECT：通过；
- Ruff、`git diff --check` 和尾随空白检查：通过。

## 6. 状态变化

- 本地业务数据库写入：无，仅使用内存 SQLite 测试；
- 205 数据库写入/migration：无；
- 现有画像 review/publish/current/deprecated：均未执行；
- 候选召回、资格判断、关系算法和重点竞品选择：均未实现；
- 部署：无；
- Git 暂存/提交：无。

## 7. 下一 Goal

允许创建 G10，只实现多入口、无固定数量的全量候选召回：候选入口必须可解释、同品牌与多关系来源都保留，暂不实现候选资格、竞争关系打标、排序截断或画像持久化；不得写入 205、部署或切换任何发布状态。
