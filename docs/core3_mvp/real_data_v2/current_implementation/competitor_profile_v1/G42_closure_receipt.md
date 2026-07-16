# G42 竞品画像正式切换关闭回执

状态：completed

日期：2026-07-16

## 1. 结论

经用户明确批准，205 上 TV 与 AC 两个全量 agent snapshot v2 竞品画像已依次完成发布质量评审、`draft → review → published → current`，竞品分析智能体正式模式现已默认只读新画像。

两个版本均为 `published / limited / current`。`limited` 表示产品结论完整可用，但部分上游用户证据仍保留复核标记；不是生成失败，也没有缺 SKU、blocked 或 failed。发布过程未重跑 M03B—M12D，未修改旧 M12/M13/M14、采购理由画像或用户卖点价值画像。

## 2. 正式版本

TV：

- version id：`288b6ce0-b632-478c-9705-8297103da730`；
- profile version：`competitor_profile_agent_snapshot_v2_tv_full_g41c_20260716_r2`；
- 377 profile、7,300 pair、0 relation、1,131 selection；
- 质量：377 partial、0 blocked、0 failed；
- 状态：`published / limited / current`。

AC：

- version id：`eed759a8-a666-4257-8c4d-3405621a4244`；
- profile version：`competitor_profile_agent_snapshot_v2_ac_full_g41c_20260716_r1`；
- 155 profile、2,774 pair、0 relation、461 selection；
- 质量：155 partial、0 blocked、0 failed；
- 状态：`published / limited / current`。

切换前两个品类均不存在竞品画像 published/current，因此没有被替换的旧画像版本；旧现场分析仍只保留为显式运维路径，不是正式默认回退。

## 3. 发布质量评审

发布前只读门禁确认：

- 活动数据库 writer：0；
- TV/AC 权威 SKU 覆盖完整，version 计数与 profile/pair/selection 实际行数一致；
- integrity violations：TV 0、AC 0；
- limited quality violations：TV 0、AC 0；
- relation 为 0 符合 agent snapshot v2 合同，不再套用旧 V1 的“每 pair 七条 relation”存储假设；
- snapshot scope、画像根哈希、候选 snapshot 引用、pair 分析哈希、Top3 连续排名、selection 与 selected pair 映射均通过；
- 全量门禁采用数据库侧索引/哈希/引用校验，不反序列化整版大 JSON，205 峰值保持在约 171 MiB。

为支持正式发布，补齐了两项生命周期缺口：

1. agent snapshot v2 按 `success`、0 relation、已保存 Top3 索引执行专用完整性门禁，并以流式/数据库侧校验避免全量 JSON 内存放大；
2. release scope 锁按唯一 project 行加锁，再按 category/scope 锁版本，支持 205 上 TV/AC 共用同一 project id。

代码提交：

- `e63513b fix: release agent competitor profiles safely`；
- `3d68adb fix: lock shared competitor profile projects`。

## 4. 串行状态切换

### 4.1 review

TV 与 AC 在同一原子阶段内由 `draft` 进入 `review`，质量均明确记录为 `limited`；version 与所有 profile/pair/selection 子记录回读一致，仍为 non-current。

### 4.2 published

TV 与 AC 在同一原子阶段内由 `review` 进入 `published`，显式使用 `allow_limited=true`，发布说明记录为“覆盖完整、无阻断或失败，明确接受现有上游证据限制”；发布后仍为 non-current。

### 4.3 current

先在事务内对 TV/AC 同时执行 current 并 rollback，确认两类均恢复 non-current；随后重新执行并提交正式 current。最终 version 与全部 profile/pair/selection 子记录均为 `published/current`。

## 5. 正式智能体验收

正式读取没有传 version、scope 或 preview 参数，并把旧 `_competitor_set_legacy` 入口替换为“调用即报错”的禁止桩：

- TV `TV00029112 / 海信 65E7Q`：source=`competitor_profile_v1_1`，候选 20，Top3=`TV00027801 / TV00028909 / TV00029936`；
- AC `AC00026378`：source=`competitor_profile_v1_1`，候选 16，Top3=`AC00034712 / AC00039161 / AC00038373`；
- 两次 `atoms_used=[]`，旧实时分析调用 0，preview=false；
- 两次返回的 version id 与本回执第 2 节正式版本一致。

这证明竞品分析智能体现在直接消费画像中已保存的候选、分析、角色、业务得分和 Top3，只负责问题路由与业务表达，不再为每次问答重新召回、计算或排序。

## 6. 回退演练与运行态

正式 current 后又执行了一次无净写入的回退演练：

1. 锁定两个 current version；
2. 在未提交事务内临时撤销 version 与所有子记录的 current；
3. TV/AC formal read 均变为 `profile_unavailable`；
4. rollback 后两类 formal read 均恢复 `available`，version id 不变；
5. 最终 current flag：TV=true、AC=true。

205 最终运行态：

- API：running / healthy；
- `/healthz`：ok；`/readyz`：database ok；
- restart count：0；OOM：false；
- 活动数据库 writer：0。

## 7. 测试

- 生命周期与 agent snapshot 专项：22 项通过；
- 全部 `test_competitor_profile*.py`：100% 通过；
- ruff check、format、diff check：通过；
- 真实 205 release quality、三个生命周期阶段、正式智能体零重算读取和 post-switch rollback：通过。

G42 到此关闭。后续竞品分析智能体的正常 formal 请求默认读取上述 current 画像；只有显式运维参数才允许进入旧现场分析路径。
