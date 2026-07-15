# G38 关闭回执：竞品分析智能体只读 V1.1 画像

日期：2026-07-16

状态：completed

## 1. 目标与结果

G38 已将 `competitor-set` 的默认数据路径从现场重新召回、比较、打分、定角色、排序和选择，切换为：

```text
目标 SKU 解析（仅在未给 SKU code 时）
  -> CompetitorProfileV11Reader 单次读取冻结画像
  -> CompetitorProfileAgentAdapter 合同校验
  -> render_competitor_answer_from_profile 纯展示
```

正式模式只消费 current published V1.1；草稿预览必须同时显式提供 release scope、profile version 和 opt-in。没有正式画像、指定版本不存在或画像不完整时明确返回 `profile_unavailable`，不静默执行旧现场链。旧路径只可通过 `legacy_live_analysis=True` 或 CLI 的显式运维开关调用。

## 2. 实现范围

- `sop_orchestrators.py`
  - `competitor-set` 默认切入 V1.1 Reader；
  - 精确 SKU 不调用任何 AtomicHandlers，型号/自然语言只允许调用 `resolve-sku`；
  - formal、preview、scope、version 和 target 全部 fail-closed；
  - 保存的全部候选和重点竞品顺序原样输出，`top_n` 不触发重排；
  - profile unavailable 不执行 Adapter、renderer 或 legacy fallback；
  - 旧卖点价值 fallback 和低销量诊断明确使用 legacy 运维路径，避免跨功能隐式改义。
- `analyst_service.py`
  - 注入 `CompetitorProfileV11Repository -> CompetitorProfileV11Reader`；
  - 竞品画像参数只进入 `competitor-set`，不泄漏给其他问答路由。
- `catforge_analyst.py`
  - competitor-set/ask 增加 formal/preview、version、scope、draft opt-in 和 legacy 运维开关；
  - 精确 SKU 的画像请求不再为旧分析链解析 latest batch。
- `competitor_profile_v1_1_reader.py` / `competitor_profile_v1_1_repositories.py`
  - formal 可在不暴露内部 source-fingerprint scope 的情况下，只从 V1.1 current published 且 SKU 已正式 current 的版本中，按最近 `current_at` 确定 serving 画像；
  - 显式 scope 仍严格按指定 scope 读取；preview 仍要求显式 scope。
- `competitor_answer.py`
  - 外部报告只发布 G37 已生成的 markdown，不触发任何分析重算。

未修改卡片、报告或问答样式；未修改旧 M12/M13/M14、V1 草稿或线上默认数据。

## 3. 门禁覆盖

G38 新增 15 项专项测试，覆盖：

- TV、AC formal 读取；
- 普通业务调用自动定位正式 serving scope；
- preview scope/version/opt-in 三重门禁和单请求版本锁；
- 无画像明确返回且 legacy 零调用；
- 65E7Q 20 个候选全量返回，`top_n` 不重排；
- 零候选、hard-excluded、market-only 和局部 unknown；
- query 只调用 `resolve-sku`；
- `build_competitor_answer`、AtomicHandlers、Calculator、Gate、Selector、enrichment、打分、角色、排序和选择函数 fail-fast 零调用；
- 飞书报告只消费预渲染 markdown，外部调用全 mock；
- 错误 version/scope、构造后篡改 fail-closed；
- legacy 仅显式启用；
- service Reader 注入、CLI 参数和精确 SKU 不读取旧 latest batch。

受影响回归一次性执行 166 项并全部通过：

- `test_competitor_profile_v1_1_agent_routing.py`：15；
- `test_competitor_profile_v1_1_repository.py`：22；
- `test_competitor_profile_v1_1_adapter.py`：12；
- `test_competitor_profile_v1_1_schemas.py`：27；
- `test_catforge_analyst_cli.py`：90。

此外通过：

- `ruff check`；
- 相关 Python 文件 `py_compile`；
- `git diff --check` 在 G38 收口时执行。

## 4. 独立复核与修复

一次性独立复核发现并关闭以下问题：

1. 普通正式请求原先猜测 `project:category` scope，但实际 scope 带 source fingerprint，会造成已发布画像误报不可用；改为只在 current published V1.1 中按正式激活时间定位 serving scope。
2. ask 的竞品专用参数会进入非竞品 AtomicHandler；在路由边界按 command 剥离。
3. profile unavailable 路径曾先运行 Adapter 再标记 skipped；现改为 Reader unavailable 后立即返回，执行轨迹与事实一致。
4. 辅助函数插入位置导致错误路径局部变量越界；ruff 检出后修复，并重新执行全部受影响回归。

终审无未关闭 P0/P1 或信息性问题。

## 5. 数据与发布边界

- 真实业务数据库连接/写入：0；
- 205 访问、部署或生成：0；
- review/publish/current/deprecated 状态切换：0；
- M03B—M12D 重跑：0；
- 外部飞书文档或消息创建：0（测试均 mock）；
- staging/commit/push：0，精确提交留到 G39。

## 6. 下一步

进入 G39：执行 V1.1 完整回归、迁移 upgrade/downgrade、65E7Q golden diff、旧 Top 3、零重算、最大候选性能/SQL/存储预算、deterministic/hash、覆盖率、方法/工程/业务总评审，并只暂存本任务链精确文件后提交。
