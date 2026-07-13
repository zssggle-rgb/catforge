# 用户卖点价值画像 G07A 本地质量审计

状态：完成

日期：2026-07-13

审计范围：提交 `9f54ec4`、`54cc6d2`、`31b223e`、`ffb25ff`、`a33af70`

本轮不连接 205，不生成真实画像，不写业务数据库，不执行 review、publish 或 current 切换。

## 1. 审计结论

G02—G06 已形成可进入正式 G07“画像深入问答”开发的本地基线：竞品宇宙不受展示数量限制，M14 只增加标签，竞品与分析参考池分离；能力事实保留 known、missing、contradicted 边界；画像草稿、审核、发布和 current 生命周期分离；报告默认只读 current published，草稿必须显式指定版本，渲染阶段不读取 M03B—M14。

本轮发现并修复 1 个报告追溯缺口：报告虽然已展示画像版本、发布状态和结果编号，但遗漏需求明确要求的生成时间、发布时间和候选范围编号。修复后短答、JSON、Markdown、飞书卡片和飞书文档正文均从同一画像 DTO 取得这些字段；短答压缩时追溯信息不再被业务正文截断。

未发现 P0/P1 代码缺陷。正式 G07 仍需实现的功能不是本轮回归问题：画像问答路由、四段答案合同，以及问题级 eligible、selected、rejected 候选和原因的完整事实路径。该工作必须在 G07 中完成，不能由报告临时重算。

## 2. 验收矩阵

| 验收项 | 证据 | 结论 |
| --- | --- | --- |
| 全部 M12/M13 候选 | 0、1、12、35 等候选测试；查询数不随候选数增长 | 通过 |
| M14 仅标签 | M14 0、1、3 不改变 universe count | 通过 |
| 竞品与参考池分离 | `pool_type`、reference 资格和报告用途分别验证 | 通过 |
| missing 不作 false | missing/contradicted、阈值边界、TV/AC 测试 | 通过 |
| 基础竞争能力过滤 | HDMI 类普及能力与可差异化体验分开 | 通过 |
| 六类投入判断 | retain、unconverted、do_not_follow、table_stake、missing gap、unknown | 通过 |
| 画像不可变和版本隔离 | 幂等、同版本变更拒绝、历史 diff、draft/published/current | 通过 |
| 类目隔离 | TV/AC repository、阈值和报告适配 | 通过 |
| 报告零业务重算 | 上游 handler 调用即抛错的测试仍返回画像报告 | 通过 |
| 默认 published / 显式 preview | draft 默认不可见；指定 `preview_profile_version` 可读 | 通过 |
| stale / blocked | 保留画像结论并明确禁止作为正式产品取舍 | 通过 |
| 跨载体一致 | profile version、release、candidate manifest、result hash 同源 | 通过 |
| PM 语言 | 报告不出现“反事实、合成对照、合成控制、门禁、M12/M13/M14” | 通过 |
| 迁移链 | Alembic 唯一 head 为 `0045_core3_sellpoint_value_profile` | 通过 |
| 运行时边界 | schema 和表不暴露 prompt、Gold Set | 通过 |

## 3. 验证记录

执行命令：

```text
ruff check <G06/G07A 精确代码和测试文件>
python -m compileall -q app/services/core3_real_data/analyst app/cli/catforge_analyst.py
alembic heads
pytest -q tests/core3_real_data/test_claim_value_pm_v4_*.py \
  tests/core3_real_data/test_claim_value_pm_v5_*.py \
  tests/core3_real_data/test_sellpoint_value_profile_*.py
pytest -q --cov=app.services.core3_real_data.analyst.sellpoint_value_profile_report \
  --cov=app.services.core3_real_data.analyst.sellpoint_value_profile_repositories \
  tests/core3_real_data/test_sellpoint_value_profile_report.py \
  tests/core3_real_data/test_sellpoint_value_profile_persistence.py
```

结果：

- Ruff：通过；
- compileall：通过；
- Alembic：`0045_core3_sellpoint_value_profile (head)`；
- 相关回归：245 项通过；
- 新报告与读取仓库覆盖率：90%；
- 仅存在既有 `datetime.utcnow()` 弃用警告，本任务未新增运行失败或数据边界警告。

## 4. 下一 Goal 硬边界

正式 G07 只消费 `SellpointValueProfileReadBundle`，不得调用上游分析原子。问答必须锁定 `profile_version + result_hash`，按问题返回直接答案、画像事实、产品工作含义和证据边界；画像没有事实时返回 unknown。G07 需要补齐问题级候选选择事实，使产品经理能追问“为什么用了这款产品、为什么没用另一款产品”，并能定位到 candidate/value item 记录。
