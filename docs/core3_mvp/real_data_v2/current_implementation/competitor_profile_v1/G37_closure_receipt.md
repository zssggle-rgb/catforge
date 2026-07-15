# G37 关闭回执：竞品画像 Adapter 与纯展示入口

日期：2026-07-16

状态：completed

## 1. 本 Goal 完成的能力

1. 新增 `CompetitorProfileAgentAdapter`，只接受 G31 Reader 的 full、compact、question-specific typed projection；画像不可用时明确返回 `profile_unavailable`，不回退旧现场分析。
2. full projection 无损保留目标 SKU、全部可分析候选、硬排除审计、召回顺序、六维结果、关系角色、问题结论、重点顺序、新旧重点差异及 fact/evidence index。
3. compact 与 question-specific projection 分别保存独立 source receipt；question-specific 额外校验目标、候选和 pair 属于同一画像版本及范围，并校验问题结论的 fact/evidence 闭环。
4. source receipt 锁定 profile、target snapshot、candidate snapshot、pair、summary、priority selection 和完整 projection hash；构造后的嵌套字段被修改时，serializer fail closed。
5. 新增 `render_competitor_answer_from_profile()`：只组织已经保存的重点顺序、角色、得分、结论和证据，不调用现场召回、分析、打分、排序或选择函数。
6. 完整保留 TV、AC、65E7Q 20 候选、market-only、hard-excluded、非重点候选、零候选画像和 unknown/partial 的明确表达。

## 2. 独立复核及修正

一次性独立复核发现并关闭以下问题：

1. 合法零候选画像因 receipt hash map 的最小长度约束无法消费；已允许空映射，并覆盖 full/compact/question 三种读取。
2. V1.1 实际替代压力枚举未完整翻译；已按保存合同补齐中文映射，避免展示英文 code。
3. 旧看板会把市场强度重新换算为雷达分数；V1.1 路径已改为只展示保存的六个主体维度分数，市场验证不再被二次打分。
4. partial projection 对跨版本、跨范围和缺失 fact/evidence 的输入约束不足；已补齐 fail-closed 校验。
5. 非法展示参数未显式拒绝、关闭报告时仍预先生成完整 Markdown；已增加参数门禁并仅在请求 Markdown 时生成报告。

终审无未关闭 P0/P1，也没有需要用户决策的剩余项。

## 3. 验证证据

- Adapter + Typed Schema 专项：39 passed。
- materializer/generation、repository、competitor answer gates、Feishu publish mock、PM report、card routing 受影响回归：67 passed。
- 合计：106 passed。
- Ruff format/check：通过。
- Python compileall：通过。
- `git diff --check`：通过。
- fail-fast spy：`_enrich_competitor`、`_sort_key`、`_assign_top_roles`、`_select_top_competitors`、`_market_validation_score`、PairAnalysisCalculator、PairGateEvaluator、CompetitorProfileV11Selector 均为 0 调用。

## 4. 边界确认

- 未修改 G38 智能体路由；旧 `build_competitor_answer()` 现场路径仍保留。
- 未连接或写入真实业务数据库，未访问 205。
- 未执行 review/publish/current 切换，未发送飞书消息或创建文档。
- 未修改旧 M12/M13/M14、V1 草稿或 V1 默认行为。
- 未暂存、提交或触碰用户其他未跟踪文件。

## 5. 下一步

进入 G38：让竞品分析智能体在 preview/formal 模式读取 G31 Reader，经 G37 Adapter 后只调用纯展示入口；旧现场路径仅保留为显式运维回退参数。
