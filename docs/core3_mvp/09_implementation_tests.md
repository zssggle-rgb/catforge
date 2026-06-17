# 09 实施任务、测试与验收

## 1. 实施顺序

必须按数据流顺序实现，避免先做页面壳后补数据。关键约束是：先有完整可用的预制知识和真实数据抽取框架，再做 SKU 特征、战场和竞品选择。

## 2. Phase 1：数据读取与状态 API

文件：

```text
apps/api-server/app/services/core3_mvp/data_access.py
apps/api-server/app/schemas/core3_mvp.py
apps/api-server/app/api/core3_mvp.py
apps/api-server/app/main.py
apps/api-server/tests/test_core3_mvp.py
```

任务：

1. 创建 service 包和 router。
2. 实现 `load_project_input()`。
3. 实现 `resolve_sku_code()`。
4. 实现 `data_status()`。
5. 接入 `GET /api/mvp/core3/projects/{project_id}/data-status`。

验收：

- 项目存在时返回 5 类数据计数。
- `TV00029115` 和 `85E7Q` 可解析。
- 空值按 unknown 处理。

## 3. Phase 2：运行上下文与表结构

文件：

```text
apps/api-server/app/models/entities.py
apps/api-server/alembic/versions/0004_tv_core3_mvp.py
apps/api-server/app/services/core3_mvp/report_service.py
```

任务：

1. 新增 `core3_` 表 models。
2. 新增 migration。
3. 实现 run 创建、完成、失败状态。
4. 实现 input fingerprint。

验收：

- `POST /run` 能创建 `core3_pipeline_run`。
- 每次运行有唯一 `run_id`。
- 相同输入可复用，`force_recompute=true` 可重跑。

## 4. Phase 3：彩电预制知识资产升级

文件：

```text
apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json
apps/api-server/app/services/core3_mvp/seed_loader.py
apps/api-server/app/schemas/core3_mvp.py
```

任务：

1. 基于 [彩电预制知识资产目录](03a_preset_asset_catalog.md) 扩充 seed assets。
2. 保留现有 `tv_seed_rules.json` 中已使用 code 的兼容映射。
3. 为每个参数、卖点、主题、任务、客群、战场补齐定义、别名、来源和证据要求。
4. 实现 seed loader。
5. 实现 seed schema 校验。

验收：

- seed v0.2 覆盖设计目录中的最小资产集。
- 每个预制项有 code、中文名、定义、抽取来源、证据要求。
- 预制项不直接生成 SKU 结论。

## 5. Phase 4：真实数据抽取框架

文件：

```text
apps/api-server/app/services/core3_mvp/extraction.py
apps/api-server/app/services/core3_mvp/evidence_graph.py
apps/api-server/app/services/core3_mvp/feature_pipeline.py
```

任务：

1. 实现参数字段画像。
2. 实现参数 alias 匹配和 parser。
3. 实现宣传文本切句和卖点命中。
4. 实现评论切句、主题分类和情感判断。
5. 实现 candidate aliases / claims / topics 诊断输出。
6. 实现 evidence graph。

验收：

- 参数值来自 raw 数据或文本解析。
- 卖点激活能拆出 `param_score`、`promo_score`、`comment_score`。
- 评论主题能展示样例句。
- 新发现项进入候选，不自动生效。

## 6. Phase 5：市场画像

文件：

```text
apps/api-server/app/services/core3_mvp/market_profile.py
```

任务：

1. 聚合 12 个月量价。
2. 计算渠道占比、趋势、分位数。
3. 生成市场 evidence。
4. 写入 `core3_sku_market_profile`。

验收：

- 有量价 SKU 画像完整。
- 缺量价 SKU 降级而不是崩溃。
- 修改价格/销量会改变画像和分位数。

## 7. Phase 6：参数、卖点、评论特征

文件：

```text
apps/api-server/app/services/core3_mvp/feature_pipeline.py
```

任务：

1. 调用 extraction 框架生成标准参数。
2. 调用 extraction 框架生成卖点激活。
3. 调用 extraction 框架生成评论主题聚合。
4. 写入 `core3_sku_feature_profile`。

验收：

- Mini LED、高刷、HDMI、护眼等卖点可由真实数据激活。
- 评论缺失不判 false。
- 特征有 evidence。
- 未映射字段、短语、主题进入 diagnostics。

## 8. Phase 7：任务、客群、战场

文件：

```text
apps/api-server/app/services/core3_mvp/feature_pipeline.py
```

任务：

1. 实现用户任务得分。
2. 实现目标客群得分。
3. 实现价值战场 `semantic_score`、`market_score`、`final_score`。
4. 更新 feature profile。

验收：

- 任务、客群、战场不能按 SKU 写死。
- 战场得分必须含市场分。
- 改量价会影响战场分。
- 改参数/卖点/评论会影响语义分。
- 战场结果带 evidence。

## 9. Phase 8：候选池与组件分

文件：

```text
apps/api-server/app/services/core3_mvp/competitor_engine.py
```

任务：

1. 召回候选池。
2. 计算 gate status 和 gate reasons。
3. 计算组件分。
4. 计算三个槽位分。
5. 写入 `core3_competitor_candidate`。

验收：

- 候选不包含目标自身。
- 分数随价格、销量、参数变化。
- unknown 不被当 false。

## 10. Phase 9：三槽位选择与证据卡

文件：

```text
apps/api-server/app/services/core3_mvp/competitor_engine.py
apps/api-server/app/services/core3_mvp/report_service.py
```

任务：

1. 实现 direct / pressure / benchmark_potential 硬门槛。
2. 实现 SKU、系列、品牌去重。
3. 实现不足结果。
4. 实现业务理由。
5. 实现 evidence card。
6. 写入 result 和 evidence card 表。

验收：

- 三个角色固定。
- 三个非空竞品不重复。
- 不足不硬凑。
- 高置信结果至少 4 类证据。

## 11. Phase 10：报告、导出和页面

文件：

```text
apps/api-server/app/api/core3_mvp.py
apps/api-server/app/services/core3_mvp/report_service.py
apps/factory-web/src/api/client.ts
apps/factory-web/src/types/index.ts
apps/factory-web/src/pages/core3/Core3Mvp.tsx
apps/factory-web/src/pages/core3/core3Pages.ts
apps/factory-web/src/pages/core3/core3Format.ts
apps/factory-web/src/App.tsx
apps/factory-web/src/styles.css
```

任务：

1. 实现 overview/report/evidence API。
2. 实现 CSV/JSONL 导出。
3. 新增独立菜单。
4. 新增三页工作流。

验收：

- 页面不混入 Goal3 工作台。
- `85E7Q` 报告可演示。
- evidence card 可查看。
- 导出可下载。

## 12. 后端测试清单

新增 `apps/api-server/tests/test_core3_mvp.py`。

测试：

1. `data-status` 统计正确。
2. SKU/model 解析正确。
3. seed v0.2 通过 schema 校验。
4. 未映射 raw 参数字段能进入候选 alias。
5. 高频未映射宣传短语能进入 candidate claim。
6. 高频未映射评论短语能进入 candidate topic。
7. 单 SKU run 生成 run、profile、feature、candidate、result。
8. 参数值来自 raw 数据或文本解析。
9. 卖点激活包含三类证据分。
10. 评论主题包含样例句。
11. 任务、客群、战场不是按 SKU 写死。
12. 三角色固定且不重复。
13. 高置信结果证据类型足够。
14. 缺价格降级。
15. 缺评论不判 false。
16. 修改销量影响 pressure。
17. 无合格候选输出 insufficient reason。
18. CSV 字段完整。
19. JSONL 每行合法 JSON。

## 13. 前端测试清单

新增 `apps/factory-web/src/pages/core3/core3Pages.test.ts`。

测试：

- 页面 key 固定为 `overview`、`sku-report`、`evidence`。
- 角色顺序固定为 `direct`、`pressure`、`benchmark_potential`。
- core3 页面 key 不与 `workbenchPages` 重复。
- role label、confidence label 格式化正确。

## 14. 验证命令

后端：

```bash
cd apps/api-server
uv run --extra dev python -m pytest
```

前端：

```bash
cd apps/factory-web
npm test
npm run build
```

## 15. 最小验收标准

- 能读取 PostgreSQL 项目数据。
- 能从 `85E7Q` 或 `TV00029115` 生成目标 SKU 报告。
- 报告包含市场画像、参数、卖点、评论主题、任务、客群、战场。
- 参数、卖点、评论、任务、客群、战场结果来自真实数据抽取和派生，不是按 SKU 写死。
- 预制知识和抽取证据分离，页面能看到 evidence。
- 输出 direct、pressure、benchmark_potential 三角色。
- 不足时输出原因，不硬凑。
- 高置信竞品 evidence category 足够。
- evidence_id 可回溯。
- 三页可演示。
- CSV/JSONL 可导出。
- 测试和构建通过。

