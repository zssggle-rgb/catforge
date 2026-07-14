# G22 工程评审

状态：本地 RC 通过；允许进入 G23“只部署代码和 migration”

日期：2026-07-14

## 1. 架构结论

实现遵循 provider → deterministic materializer → repository/lifecycle → formal/preview reader → one-version consumption context 的分层。计算模块不查数据库、不调用外部 LLM；数据库访问集中在 provider/repository；展示消费者不能重新召回、重算 pair 或重新挑 Top 3。

## 2. P0/P1 关闭表

| 等级 | 发现 | 处理 | 状态 |
| --- | --- | --- | --- |
| P0 | 缺生成到持久化/readback 主链 | 新增 generation service、typed request/result、每 SKU 事务和 hash 回读 | closed |
| P0 | pair membership DB check 与合法审计状态冲突 | 同步 ORM、schema contract、migration test | closed |
| P0 | 缺 formal/preview reader、单版本消费合同和可执行入口 | 新增 reader、consumer context、generate/batch/read CLI | closed；线上路由切换按 G24 门禁 |
| P1 | 不合格候选仍可能进入关系判断 | relation evaluator 首先执行 eligibility member gate | closed |
| P1 | optional 0 行被当系统失败 | unavailable authority + unknown 语义 | closed |
| P1 | 上游 preview 合同不可执行 | V1 明确 fail-closed，只允许 published/current upstream | closed |
| P1 | evidence identity/confidence 丢失 | provider 下钻 evidence/source/raw-row/confidence | closed |
| P1 | 只有候选层性能，无全链规模证据 | 增加 377 pair/2,639 relation 全链测试和 snapshot load 计数 | closed |
| P1 | 单 SKU 恢复会清除同版本其他失败状态 | version readback 保留安全失败清单；成功只移除当前 SKU，并增加双失败单恢复测试 | closed |

## 3. 数据库与状态机

- Alembic 0046 基于 0045，当前为唯一 head；创建 version/profile/pair/relation/selection 五表。
- version、profile、pair、relation、selection 均保留 project/category/scope/version/hash/audit 字段。
- draft 可幂等复用，review/published analytical content 不可原地覆盖。
- publish 与 set-current 分事务；current 使用 scope lock/CAS；本 Goal 未调用任何发布方法。
- downgrade 只允许空表；已有画像时明确拒绝，避免静默删数据。
- 单 SKU 写入一个事务；batch 逐 SKU 隔离、失败信息脱敏、可续跑。

## 4. CLI 与运行边界

- `competitor-profile-generate`、`competitor-profile-batch-generate` 必须显式 `--enable-profile-write`，且门禁发生在创建 DB session 前。
- 生成通过 `--request-json` 接收完整 typed request，不让 CLI 猜测 category config、source population 或 draft version。
- `competitor-profile-read` formal 只读 current published；preview 必须同时给出明确 version ID 和 `--allow-draft-preview`。
- 现有 `competitor-set` 和用户卖点价值线上路由没有切换。consumer context 只是 G24 需要的版本锁定接口。

## 5. 安全与隔离

- 无外部网络/LLM 调用；测试确定性。
- 业务 DTO 不暴露表名、hash、阈值、snake_case、prompt 或 Gold Set；证据 DTO 只用于审核/佐证。
- TV/AC category_code、product_category、SKU prefix、source authority 全链校验。
- runtime forbidden keys 在基础 schema 递归拒绝。
- 未改旧 M12/M13/M14 实现；未把 factory prompt/Gold Set 放入 runtime export。

## 6. 回归与已知基线

竞品画像 270 项专项全部通过。Core3 全量回归的 7 个失败均位于本任务未修改的 taxonomy/constants/旧清洗 fixture；详细见 `G22_test_matrix.md`。当前分支没有对应 PR，因此无 Greptile/人工 PR 评论需要处理。

## 7. G23 允许与禁止

允许：部署本提交代码、运行 0046 migration、验证 health/ready 和空表 rollback 演练。

禁止：生成画像、review、publish、set-current、deprecate、切换现有竞品智能体或用户卖点价值消费者。
