# 10 /goal 执行计划

## 1. 目标

把 Core3 MVP 设计拆成可以由 `/goal` 连续执行的任务卡。每个 Goal 都必须满足：

- 输入清楚。
- 文件范围清楚。
- 代码产物清楚。
- 测试清楚。
- 退出标准清楚。
- 不依赖外部 LLM 调用。

## 2. 全局执行规则

- 按 Goal A 到 Goal G 顺序执行，不能跳过前置数据契约。
- 每个 Goal 完成后运行对应测试，失败则先修复再进入下一个 Goal。
- 只修改当前 Goal 明确列出的文件，除非测试暴露必要的邻接改动。
- 不复用会重置 fixture 的 `run_goal1_analysis()` 作为 Core3 主链路。
- 不把 Core3 页面塞进 Goal3 `WorkbenchPage`。
- 所有 SKU 级结论必须有 evidence 或明确不足原因。
- unknown 不能当 false。

## 3. Goal A：数据读取与状态 API

### 目标

打通从项目 PostgreSQL raw tables 读取数据的最小链路，提供数据状态 API 和 SKU/型号解析。

### 前置条件

- 现有项目、raw tables、测试 fixture 可用。
- 不需要新增 `core3_` 结果表。

### 文件范围

```text
apps/api-server/app/api/core3_mvp.py
apps/api-server/app/main.py
apps/api-server/app/schemas/core3_mvp.py
apps/api-server/app/services/core3_mvp/__init__.py
apps/api-server/app/services/core3_mvp/data_access.py
apps/api-server/tests/test_core3_mvp.py
```

### 实现步骤

1. 新建 `core3_mvp` router，前缀 `/api/mvp/core3`。
2. 新建 Pydantic schema：
   - `Core3DataStatusOut`
   - `Core3SkuResolveOut`
   - `Core3SkuCandidate`
3. 实现 `is_unknown(value)`。
4. 实现 `load_project_input(db, project_id)`。
5. 实现 `resolve_sku_code(db, project_id, sku_or_model)`。
6. 实现 `data_status(db, project_id)`。
7. 暴露：
   - `GET /api/mvp/core3/projects/{project_id}/data-status`
   - `GET /api/mvp/core3/projects/{project_id}/resolve-sku?query=...`

### 必测用例

- 项目不存在返回 404。
- 空项目返回 200，但 `sku_count=0` 且 status 为 degraded。
- 已导入 fixture 项目返回 5 类数据计数。
- 精确 `sku_code` 解析成功。
- 型号包含匹配成功。
- 多个型号匹配返回 409 和候选。
- 空字符串、`-`、`null` 被识别为 unknown。

### 退出标准

- `test_core3_data_status_and_resolve_sku` 通过。
- OpenAPI 中能看到 Core3 data-status 和 resolve-sku。
- 不创建任何竞品结果。

## 4. Goal B：运行上下文与 core3 表结构

### 目标

新增 Core3 运行和结果表骨架，支持 run 创建、复用和失败记录。

### 前置条件

- Goal A 已完成。

### 文件范围

```text
apps/api-server/app/models/entities.py
apps/api-server/alembic/versions/0004_tv_core3_mvp.py
apps/api-server/app/schemas/core3_mvp.py
apps/api-server/app/services/core3_mvp/report_service.py
apps/api-server/app/api/core3_mvp.py
apps/api-server/tests/test_core3_mvp.py
```

### 新增表

- `core3_pipeline_run`
- `core3_sku_market_profile`
- `core3_sku_feature_profile`
- `core3_competitor_candidate`
- `core3_competitor_result`
- `core3_evidence_card`

### 实现步骤

1. 新增 SQLAlchemy models。
2. 新增 migration，使用 `table.create(checkfirst=True)` 风格与现有 migration 一致。
3. 实现 `create_or_reuse_run()`。
4. 实现 `finish_run()` 和 `fail_run()`。
5. 实现 input fingerprint。
6. 暴露 `POST /api/mvp/core3/projects/{project_id}/run`，先只创建 run，不跑完整流水线。

### 必测用例

- `POST /run` 创建 `core3_pipeline_run`。
- `force_recompute=false` 时相同 fingerprint 复用 completed run。
- `force_recompute=true` 创建新 run。
- batch=true 时目标 SKU 列表来自项目所有有效 SKU。
- 单 SKU 目标不存在不创建 run。

### 退出标准

- 所有 `core3_` 表在 SQLite 测试库可创建。
- run 状态流可测试。
- 未实现市场画像时 API 明确返回 `status=created` 或 `status=completed_empty`，不能伪造结果。

## 5. Goal C：seed v0.2 预制知识资产

### 目标

把预制知识资产从示例级升级为 Core3 可用的彩电 v0.2 seed，并能 schema 校验。

### 前置条件

- Goal A-B 已完成。

### 文件范围

```text
apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json
apps/api-server/app/services/core3_mvp/seed_loader.py
apps/api-server/app/schemas/core3_mvp.py
apps/api-server/tests/test_core3_mvp.py
```

### 实现步骤

1. 新建 `tv_core3_mvp_seed_v0_2.json`。
2. 覆盖设计目录中的最小资产集：
   - 标准参数。
   - 标准卖点。
   - 评论主题。
   - 用户任务。
   - 目标客群。
   - 价值战场。
3. 每个 asset 必须包含：
   - code。
   - name。
   - definition。
   - aliases/keywords。
   - source_types。
   - evidence_requirement。
   - mapped_*。
4. 实现 `load_core3_seed()`。
5. 实现 `validate_core3_seed()`。

### 必测用例

- seed JSON 可加载。
- 每类资产数量达到最小要求：
   - params >= 35
   - claims >= 18
   - topics >= 15
   - tasks >= 9
   - target_groups >= 8
   - battlefields >= 9
- 每个 code 唯一。
- 每个映射引用的 code 存在。
- seed 不包含 SKU 级结论字段。

### 退出标准

- seed 校验测试通过。
- 后续 extraction 可以依赖 seed aliases、parser 和 mapping。

## 6. Goal D：真实数据抽取框架

### 目标

实现真实数据抽取基础能力：字段画像、参数 parser、宣传切句、评论主题、候选发现和 evidence graph。

### 前置条件

- Goal C 已完成。

### 文件范围

```text
apps/api-server/app/services/core3_mvp/extraction.py
apps/api-server/app/services/core3_mvp/evidence_graph.py
apps/api-server/app/services/core3_mvp/feature_pipeline.py
apps/api-server/app/schemas/core3_mvp.py
apps/api-server/tests/test_core3_mvp.py
```

### 实现步骤

1. 实现参数字段画像：
   - coverage。
   - non_empty_rate。
   - top_values。
   - matched_param_code。
2. 实现 parser：
   - inch、hz、nits、zones、gb、ports、resolution、percentage、watt、ms、boolean_keyword、enum_keyword。
3. 实现宣传文本切句和卖点命中。
4. 实现评论切句、产品/服务分类、主题分类和情感判断。
5. 实现候选发现：
   - candidate_param_alias。
   - candidate_claim。
   - candidate_comment_topic。
6. 实现 `get_or_create_evidence()`，保证同一 raw ref 不重复膨胀。

### 必测用例

- `85英寸` 解析为 85。
- `144Hz` 解析为 144。
- `1600nits` 解析为 1600。
- `1296分区` 解析为 1296。
- `4GB+64GB` 可拆 RAM/ROM。
- `2个HDMI2.1` 解析为 2。
- Mini LED/OLED/VRR/无频闪可解析布尔。
- 未映射高覆盖 raw 字段进入 candidate alias。
- 未映射宣传短语进入 candidate claim。
- 未映射评论短语进入 candidate topic。
- 评论主题包含样例句和情感。

### 退出标准

- 抽取框架不生成竞品结果。
- 抽取结果都有 evidence 或 diagnostics。
- unknown 没有被转成 false。

## 7. Goal E：市场画像与 SKU 特征快照

### 目标

把市场画像和抽取结果写入 SKU 级快照，形成后续任务/战场和竞品候选的统一输入。

### 前置条件

- Goal D 已完成。

### 文件范围

```text
apps/api-server/app/services/core3_mvp/market_profile.py
apps/api-server/app/services/core3_mvp/feature_pipeline.py
apps/api-server/app/services/core3_mvp/report_service.py
apps/api-server/tests/test_core3_mvp.py
```

### 实现步骤

1. 聚合 12 个月量价。
2. 计算渠道占比、趋势、价格/销量/销额分位。
3. 生成市场 evidence。
4. 调用 extraction 生成标准参数、卖点激活、评论主题。
5. 写入：
   - `core3_sku_market_profile`
   - `core3_sku_feature_profile`

### 必测用例

- 有量价 SKU 画像完整。
- 缺价格或缺销量时画像降级。
- 修改销量会改变 sales_percentile。
- 卖点激活包含 `param_score`、`promo_score`、`comment_score`。
- 评论缺失不判 false。
- feature profile 带 extraction diagnostics。

### 退出标准

- 单 SKU report 的前半部分可由 API 返回。
- 还不要求输出三竞品。

## 8. Goal F：任务、客群、战场、候选池和三竞品

### 目标

从 SKU 快照派生任务、客群、战场，召回候选，计算组件分，选择三槽位竞品和证据卡。

### 前置条件

- Goal E 已完成。

### 文件范围

```text
apps/api-server/app/services/core3_mvp/feature_pipeline.py
apps/api-server/app/services/core3_mvp/competitor_engine.py
apps/api-server/app/services/core3_mvp/report_service.py
apps/api-server/tests/test_core3_mvp.py
```

### 实现步骤

1. 实现任务得分。
2. 实现客群得分。
3. 实现战场 `semantic_score`、`market_score`、`final_score`。
4. 召回候选池。
5. 计算组件分和槽位分。
6. 实现 direct / pressure / benchmark_potential 选择。
7. 实现去重、品牌分散和不足结果。
8. 实现 evidence card。

### 必测用例

- 任务/客群/战场不是按 SKU 写死。
- 改参数/卖点/评论会影响 semantic_score。
- 改价格/销量会影响 market_score 和 pressure。
- 候选不包含目标自身。
- 三个非空竞品不重复。
- 无合格候选输出 insufficient reason。
- 高置信结果至少 4 类 evidence category。

### 退出标准

- `GET /sku/{sku_or_model}/report` 能返回完整三竞品报告。
- `GET /competitors/evidence` 能返回证据卡。

## 9. Goal G：页面、导出和端到端验收

### 目标

新增独立 Core3 MVP 页面组和导出，完成可演示 MVP。

### 前置条件

- Goal F 已完成。

### 文件范围

```text
apps/api-server/app/api/core3_mvp.py
apps/api-server/app/services/core3_mvp/report_service.py
apps/factory-web/src/api/client.ts
apps/factory-web/src/types/index.ts
apps/factory-web/src/pages/core3/Core3Mvp.tsx
apps/factory-web/src/pages/core3/core3Pages.ts
apps/factory-web/src/pages/core3/core3Format.ts
apps/factory-web/src/pages/core3/core3Pages.test.ts
apps/factory-web/src/App.tsx
apps/factory-web/src/styles.css
```

### 实现步骤

1. 完成 overview/report/evidence/export API。
2. 新增 API client 方法。
3. 新增 Core3 独立菜单。
4. 实现三页：
   - 批量总览。
   - 单 SKU 竞品报告。
   - 竞品证据卡。
5. 实现 CSV 和 JSONL 导出。
6. 浏览器验证桌面和移动视口。

### 必测用例

- 页面 key 不与 Goal3 `workbenchPages` 重复。
- 三角色展示顺序固定。
- `85E7Q` 搜索能展示 report。
- evidence card 能展开 evidence_id。
- CSV 字段完整。
- JSONL 每行合法 JSON。

### 退出标准

- 后端 pytest 通过。
- 前端 vitest 通过。
- 前端 build 通过。
- 浏览器页面无空白、无明显重叠、无控制台错误。

## 10. 执行时停止条件

遇到以下情况应停止当前 Goal 并报告：

- 生产源表字段与 `raw_*` 兼容层完全不匹配。
- fixture 无法覆盖目标测试，且无法安全生成本地 fixture。
- seed 映射存在循环或大量缺失 code。
- 需要外部 LLM 才能继续。
- 需要用户确认真实业务口径，例如价格窗口、同系列判定、品牌去重阈值。

