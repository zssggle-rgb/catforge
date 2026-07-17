# SPV51-G05 竞品画像 Reader Adapter 关闭回执

状态：completed

日期：2026-07-17

## 1. 实现结果

- 新增 `SellpointValueCompetitorProfileAdapter`，唯一读取入口是 `CompetitorProfileAgentSnapshotRepository.read_agent_snapshot()` 和版本回读；
- formal 不接受显式 version id，只读取 `competitor_profile_agent_snapshot_v2` 的 current published 完整画像；
- preview 必须同时给出 version id 和 release scope，只接受一个 non-current draft 或 current published 版本；
- profile 不可用时明确返回 `profile_unavailable`，不回退旧候选池、不现场重算；
- 输出保留全部已保存候选，并按 `source_rank` 排列；Top3 只作为 `selected_rank`/`priority_order` 标签，不截断候选；
- 每个候选原样映射 role/role_cn、business score、pair result hash、候选量价和 19 组已保存 pair facts；
- 分别保存 competitor version result hash、目标 SKU profile result hash 和每个候选 pair result hash；
- adapter 同时映射目标 SKU 的周均价格/销量，供后续直接量价比较使用；
- 空字典/空列表不会自动当作 missing；只有来源字段确实缺失时才进入 `unavailable_fact_groups`，且只影响该事实组。

## 2. 完整性边界

- adapter 二次核对 repository、request、version、profile 的 project/category/version/scope/target 一致性；
- schema/rule/method 必须分别是 V1.1、agent snapshot rule v2、agent snapshot method v2；
- formal/preview 状态与 repository 返回的 preview 标记必须一致；
- 任一版本身份、类目、scope、method 或 hash 缺失直接报完整性错误，不尝试其他来源；
- pair/profile hash 的底层闭图校验继续由 agent snapshot repository 完成，adapter 消费其已验证 full read。

## 3. 禁止旧路径

- adapter 不导入 `sellpoint_value_profile_candidate_service`、旧候选 repository、candidate recall、pair feature 或 live competitor answer；
- 严格 repository stub 只暴露 `read_agent_snapshot` 和 `get_version_by_id`，任何额外读取都会使专项测试失败；
- 未实现 G06 的竞品池/分析参考池和问题级候选资格，未连接或写入 205。

## 4. 验证

- adapter、V5.1 schema 和 agent snapshot 必要回归共 47 项通过；
- 覆盖 formal current published、显式 draft preview、全候选/Top3、pair facts、市场量价、三级 hash、profile unavailable、跨 project/category/version/scope/method/hash 拒绝及旧路径禁止桩；
- actual repository 的 preview roundtrip 与 limited published/current formal read 均通过 adapter 回读；TV/AC 类目合同均有专项覆盖；
- touched Python files 的 ruff check、py_compile 和 diff check 通过；新增 adapter/test 文件的 ruff format check 通过；
- 完整回归、覆盖率、性能和三类总评审仍集中在 SPV51-G13。

## 5. 下一步

SPV51-G06 使用本 adapter 输出建立两个明确分离的集合：完整正式竞品 manifest 与市场/参数/价值战场分析参考池；再按每个问题的可用事实独立选择或拒绝候选，不能因一个字段缺失淘汰整款产品。
