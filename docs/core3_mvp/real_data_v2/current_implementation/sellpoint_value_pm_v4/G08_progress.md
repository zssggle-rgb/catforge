# G08 本地综合验收与独立评审进度

- Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`
- Goal 状态：`completed_with_failed_acceptance`
- 定时器：`catforge-v4-g08-10`
- 验收提交范围：`b903c2a^..095016d`（G03-G07）
- 前置 G07 artifact commit：`1e10a04`
- 前置 G07 closure commit：`095016d`
- 允许修改：G08 验收、审查、清单和回执文档；发现纯测试覆盖缺口时可新增本任务测试
- 禁止事项：修改核心合同、数据库/205 写入、部署、默认路由切换、吸收工作区无关 M12D 改动

## 当前门禁

| 门禁 | 状态 |
| --- | --- |
| 审查范围与 dirty worktree 隔离 | completed |
| G02 需求追溯与 typed contract | failed：Q5 稳定性合同未完整实现 |
| G03-G07 manifest artifact commit hash | completed：23/23 |
| 只读、无外部 LLM、默认关闭、路由边界 | completed |
| V4 全链路与固定 cohort | completed；发现方法合同缺口 |
| V2、M11C、M11D、M12D、M12C、CLI 回归 | completed：相关回归全通过 |
| 查询计数、性能和内存预算 | completed |
| JSON/短答/Markdown/飞书同源一致 | completed |
| 方法识别独立评审 | failed |
| 工程质量独立评审 | failed：2 P1 / 5 P2 / 1 PM 语义阻断 |
| 产品经理业务语言独立评审 | failed：pure negative 被误写为正反并存 |

## 验收原则

1. 只审查 G03-G07 的已提交 V4 变更；工作区现存、未提交的 M12D 质量修复不属于本 Goal；
2. G08 是验证 Goal，不在验收中临时改变 G02 合同；若发现核心合同错误，停止并另立修复 Goal；
3. manifest 哈希按各 Goal 的 `artifact_commit` 读取 Git 对象核验，不能用后来 Goal 改写后的工作树文件替代；
4. 方法结论限定为观察性市场隐含区间，不得写成因果效应、心理最高支付意愿或可直接执行的定价；
5. 本地验收不连接数据库、205 或任何外部 LLM，不发布飞书结果；
6. 业务主表必须让产品经理直接看懂产品价值结构，内部等级、证据 ID、模块码只允许出现在 QA 审计层。

## 过程记录

- 已确认当前分支为 `new/base-publish-workbench-design`，V4 提交连续落在 `d8f972b..095016d`；
- 已确认工作区存在与本 Goal 无关的 M12D 质量修复和资料文件，后续使用精确路径与提交范围隔离；
- 已读取预发布工程审查清单，工程评审将覆盖数据安全、只读边界、类型与枚举完整性、条件副作用、性能和测试覆盖。
- G03-G07 五份 manifest 已按各自 `artifact_commit` 核验，23 个 artifact SHA-256 全部匹配；
- V4 77 项、V4+V2 107 项、analyst CLI 88 项、M11C/M11D/M12C/M12D 108 项及 competitor reader 6 项均通过；V4 三个运行模块覆盖率 93%；
- 查询计数为单/多候选固定且均不超过 20；10,000 synthetic rows 峰值 25.413MB；本地 65E7Q-like fixture P95 0.000325s；Markdown P95 0.000060s；
- 方法审查发现核心合同缺口：G02 12.2/12.3 要求 Q5 通过 bootstrap 与 leave-one-week-out 联合稳定性门禁，并使用多 pair 质量加权中心与联合保守包络；当前实现只有 leave-one-week-out，金额区间直接取合格 pair 的 min/max。按 G08 停止规则，不在本 Goal 修改算法。
- 独立对抗审查返回 8 个候选问题；逐项回读后 7 个成立，`Session autoflush` 候选因 CatForge `SessionLocal(autoflush=False)` 不成立；
- 产品经理业务语言审查确认 pure negative 与 mixed 共用 `conflicted`，导致纯负向评论被写成“正反并存”；
- 综合验收结论为 `FAILED — G09 NOT ALLOWED`，需要独立 G08R1 修复后重新验收。

## 关闭状态

- G08 验收任务已完成；
- 被验收实现未通过，G09 准入为 false；
- 允许创建 G08R1 修复 Goal；
- artifact commit：`b54418e`。
