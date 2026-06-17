# INFRA 真实数据 v2 工程骨架开发任务

## 1. 模块目标

INFRA 任务的目标是为 M00-M16 建立统一工程骨架，让后续模块可以按同一套模型、schema、runner、hash、fixture 和测试约定逐一开发。

INFRA 不生成业务结论，不读取真实原始表做分析，不实现 M00-M16 的模块业务逻辑。它只解决公共能力：

1. 新命名空间和目录骨架。
2. 通用枚举、状态、数据域和运行模式。
3. 稳定 hash 工具和 JSON 规范化。
4. runner 协议和 run context。
5. repository/session 边界。
6. 85E7Q fixture 和测试基础设施。
7. 第一批基础 migration 的边界。
8. 与旧 `core3_mvp` 的隔离保护。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| 总体架构 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M16 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M16_incremental_review_acceptance_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| 现有后端配置 | `apps/api-server/pyproject.toml` |
| 现有 Alembic | `apps/api-server/alembic/env.py` |
| 现有模型入口 | `apps/api-server/app/models/entities.py` |
| 现有测试入口 | `apps/api-server/tests/conftest.py` |

## 3. 本次范围

### 3.1 必须拆出的开发任务

INFRA 编码任务应拆为 8 个小闭环：

| 子任务 | 内容 | 是否编码时独立执行 |
| --- | --- | --- |
| INFRA-A | 目录和包骨架 | 是 |
| INFRA-B | 通用枚举和类型 schema | 是 |
| INFRA-C | 稳定 hash 和 JSON 规范化工具 | 是 |
| INFRA-D | runner 协议和 run context | 是 |
| INFRA-E | repository/session 边界和基类 | 是 |
| INFRA-F | 85E7Q fixture 和测试工具 | 是 |
| INFRA-G | 基础 Alembic migration 策略 | 是 |
| INFRA-H | 旧 MVP 隔离和导入注册检查 | 是 |

### 3.2 本任务不做

INFRA 不做：

- 不实现 M00 原始表扫描。
- 不实现 M01 清洗。
- 不生成 M02 evidence。
- 不写 M03-M16 业务规则。
- 不改旧 `apps/api-server/app/services/core3_mvp/` 的业务逻辑。
- 不改前端页面。
- 不部署 205。
- 不连接 205 作为单元测试依赖。

## 4. 要改文件

INFRA 编码阶段预计新增或修改以下文件。

### 4.1 后端新增文件

```text
apps/api-server/app/services/core3_real_data/__init__.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/hash_utils.py
apps/api-server/app/services/core3_real_data/run_context.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/app/services/core3_real_data/repositories.py
apps/api-server/app/services/core3_real_data/fixtures.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/tests/core3_real_data/__init__.py
apps/api-server/tests/core3_real_data/conftest.py
apps/api-server/tests/core3_real_data/test_hash_utils.py
apps/api-server/tests/core3_real_data/test_runner_contract.py
apps/api-server/tests/core3_real_data/test_fixture_baseline.py
```

### 4.2 可能修改文件

| 文件 | 修改原因 |
| --- | --- |
| `apps/api-server/app/models/entities.py` | 若首版沿用集中式 model 文件，需要添加基础表或注释边界 |
| `apps/api-server/alembic/versions/0005_core3_real_data_foundation.py` | 新增基础迁移 |
| `apps/api-server/app/main.py` | 仅在 API 骨架任务中注册 v2 router，INFRA 首轮可不改 |
| `apps/api-server/app/api/__init__.py` | 若项目需要显式导出 router |

### 4.3 文档引用

INFRA 编码完成后，应在后续 M00 任务中引用：

```text
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/app/services/core3_real_data/run_context.py
apps/api-server/app/services/core3_real_data/hash_utils.py
apps/api-server/app/schemas/core3_real_data.py
```

## 5. 不允许改文件

INFRA 编码阶段不允许修改：

```text
apps/api-server/app/services/core3_mvp/*
apps/factory-web/src/pages/core3/*
apps/factory-web/src/App.tsx
apps/factory-web/src/styles.css
docker-compose.yml
docker-compose.cloud.yml
scripts/deploy.sh
```

除非某个后续任务明确要求，不允许修改：

- Goal1/Goal2/Goal3 相关服务。
- 旧 Core3 MVP 页面。
- 205 部署配置。
- 原始数据表结构。

当前工作区已有旧 MVP 和部署相关未提交变更，INFRA 编码时必须只 stage/提交当前任务文件，不能使用 `git add .`。

## 6. 数据库任务

### 6.1 迁移边界

INFRA 首批 migration 建议命名：

```text
apps/api-server/alembic/versions/0005_core3_real_data_foundation.py
```

该迁移只允许放公共治理和最小骨架表，不放 M00-M16 全量业务表。

### 6.2 首批可选表

INFRA 可先落以下 M16 基础表，方便后续模块都有 run 和 module 状态可记录：

| 表 | 来源设计 | 是否首批建议 |
| --- | --- | --- |
| `core3_pipeline_run` | M16 | 建议首批落地或扩展旧表 |
| `core3_module_run` | M16 | 建议首批落地 |
| `core3_module_dependency_snapshot` | M16 | 可首批落地 |
| `core3_pipeline_watermark` | M16 | 可首批落地 |

如果现有旧 `core3_pipeline_run` 已存在，编码任务必须先做兼容评估：

1. 字段是否满足 M16 v2。
2. 是否会影响旧 `core3_mvp` 测试。
3. 是否需要新表名或扩展字段。

建议首版避免破坏旧表，优先使用 v2 表名或兼容扩展策略，并在 migration 中保证旧测试不受影响。

### 6.3 暂不落地的表

以下表留给对应模块：

| 表 | 留给模块 |
| --- | --- |
| `core3_source_batch` | M00 |
| `core3_source_row_registry` | M00 |
| `core3_source_impacted_sku` | M00 |
| `core3_clean_*` | M01 |
| `core3_evidence_atom`、`core3_evidence_link` | M02 |
| 抽取、画像、候选、评分、报告表 | M03-M15 |
| `core3_review_queue`、`core3_review_decision`、`core3_acceptance_report`、`core3_release_gate` | M16 |

### 6.4 migration 验收

迁移任务完成后必须验证：

- SQLite 测试库可 `Base.metadata.create_all`。
- Alembic 文件可导入。
- 不修改原始四表。
- 不删除旧 MVP 表。
- 旧 `test_core3_mvp.py` 不因表名冲突失败。

## 7. model/schema 任务

### 7.1 SQLAlchemy model 策略

当前 Alembic 环境只导入：

```python
from app.models import entities  # noqa: F401
```

首版建议：

1. 在 `entities.py` 中保留现有模式，新增 v2 基础 model。
2. 如果后续拆 `app/models/core3_real_data.py`，必须同步修改 Alembic env 和 `init_db()` 导入。
3. 不在 INFRA 中一次性加入 M00-M16 全部表 model。

### 7.2 Pydantic schema

新增：

```text
apps/api-server/app/schemas/core3_real_data.py
```

首批 schema 只定义公共类型：

| 类型 | 用途 |
| --- | --- |
| `Core3CategoryCode` | 品类枚举，首版 `TV` |
| `Core3ModuleCode` | M00-M16 |
| `Core3RunMode` | bootstrap_full/daily_incremental/ruleset_replay/single_target_refresh/review_rework/acceptance_only |
| `Core3RunStatus` | pending/running/success/warning/review_required/blocked/failed/skipped_reused/skipped_by_dependency/released/deprecated |
| `Core3ReleaseGateStatus` | not_ready/review_required/releasable/released/blocked |
| `Core3DataDomain` | sku/market/param/claim/comment/... |
| `Core3RunContextSchema` | runner 上下文 |
| `Core3ModuleRunResultSchema` | runner 返回 |
| `Core3ReviewIssueSchema` | runner 标准复核问题 |

### 7.3 schema 边界

INFRA schema 不定义高层报告 payload，不定义具体 M00 清洗字段，不定义 M15 证据卡展示结构。这些留给对应模块。

## 8. repository 任务

### 8.1 目标

INFRA repository 只提供会话边界和通用接口，不实现模块业务查询。

建议新增：

```text
apps/api-server/app/services/core3_real_data/repositories.py
```

### 8.2 基础类

建议定义：

| 类 | 职责 |
| --- | --- |
| `Core3RepositoryContext` | 保存 `Session`、`project_id`、`category_code` |
| `Core3BaseRepository` | 通用初始化、时间、分页、JSON 工具 |
| `RawSourceReadOnlyGuard` | 原始表只读约束说明和测试辅助 |

不在 INFRA 中实现：

- `RawSourceRepository`
- `SourceRegistryRepository`
- `CleanRepository`
- `EvidenceRepository`

这些由 M00-M02 对应任务实现。

### 8.3 只读保护

INFRA 需要定义只读原则和测试辅助：

1. 原始表 repository 只能暴露 select 方法。
2. 原始表 mutation 方法禁止出现。
3. 测试中可通过 fake repository 验证下游不能调用 raw write。

## 9. service 任务

### 9.1 hash 工具

新增：

```text
apps/api-server/app/services/core3_real_data/hash_utils.py
```

必须支持：

| 函数 | 要求 |
| --- | --- |
| `canonicalize_json(value)` | key 排序，保留 null/空/unknown/`-` 区别 |
| `stable_hash(value, version)` | 输出带版本的稳定 hash |
| `hash_records(records, keys, version)` | 多记录排序后 hash |
| `normalize_for_hash(value)` | datetime、Decimal、dict/list 稳定序列化 |

### 9.2 run context

新增：

```text
apps/api-server/app/services/core3_real_data/run_context.py
```

核心字段：

| 字段 | 说明 |
| --- | --- |
| `run_id` | M16 run |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 数据批次，可为空 |
| `run_mode` | 运行模式 |
| `ruleset_version` | 总规则版本 |
| `module_versions` | 模块版本 |
| `seed_versions` | seed 版本 |
| `target_scope` | 目标范围 |
| `input_watermarks` | 输入水位 |

### 9.3 constants

新增：

```text
apps/api-server/app/services/core3_real_data/constants.py
```

包含：

- 模块顺序。
- DAG 边。
- 数据域到起始模块映射。
- 真实数据 v2 默认版本。
- 85E7Q fixture 关键标识。
- 高层展示禁用字段模式。

## 10. runner/API 任务

### 10.1 runner 协议

新增：

```text
apps/api-server/app/services/core3_real_data/runner.py
```

定义：

| 类型 | 要求 |
| --- | --- |
| `Core3ModuleRunner` | Protocol 或基类 |
| `Core3ModuleTargetScope` | batch/sku/target_sku/candidate/report |
| `Core3ModuleRunResult` | status、count、hash、warnings、review_issues、downstream_impacts |
| `Core3RunnerRegistry` | 注册和获取 runner |
| `NoopModuleRunner` | 测试用，不生成业务结论 |

### 10.2 runner 返回字段

runner 必须返回：

```text
status
input_count
changed_input_count
output_count
output_hash
warnings
review_issues
downstream_impacts
summary_json
```

### 10.3 API

INFRA 不实现 API。API 注册留给 `API_development_tasks.md`。

但 INFRA 需要预留 schema，使后续 API 可以复用：

- 运行模式枚举。
- 状态枚举。
- 目标范围 schema。
- 模块运行结果 schema。
- 复核问题 schema。

## 11. fixture 任务

### 11.1 目录

建议新增：

```text
apps/api-server/tests/fixtures/core3_real_data/
```

### 11.2 fixture 内容

首批 fixture 不需要复制 205 全量数据，只需要小型、确定性样本：

| 文件 | 内容 |
| --- | --- |
| `week_sales_data_85e7q_sample.json` | 85E7Q 和 2-3 个同品牌候选的周销量价 |
| `attribute_data_85e7q_sample.json` | 85E7Q 参数，含 unknown、空、`-` |
| `selling_points_data_limited_sample.json` | 只覆盖部分 SKU，不覆盖 85E7Q |
| `comment_data_85e7q_sample.json` | 去重、重复、服务类评论混合 |
| `expected_85e7q_baseline.json` | 预期数据事实，不含最终业务结论 |

### 11.3 fixture 原则

- 不包含生产密码或连接信息。
- 不依赖 205 网络。
- 数据量小到适合单元测试。
- 必须覆盖 85E7Q 无结构化卖点。
- 必须覆盖同品牌候选不被过滤。
- 必须覆盖 unknown/null/空字符串/`-` 区分。

## 12. 测试任务

### 12.1 必写测试

| 测试文件 | 覆盖 |
| --- | --- |
| `test_hash_utils.py` | 稳定 hash、JSON 排序、null/空/unknown/`-` 不混淆 |
| `test_runner_contract.py` | runner result 字段完整、状态枚举合法 |
| `test_fixture_baseline.py` | 85E7Q fixture 覆盖真实样例约束 |
| `test_core3_real_data_constants.py` | 模块顺序、DAG、数据域映射 |

### 12.2 不在 INFRA 测试中做

- 不测试 M00 原始扫描。
- 不测试 M01 清洗。
- 不测试 M02 evidence。
- 不测试 API。
- 不测试前端。
- 不连接 205。

### 12.3 验证命令

编码完成后运行：

```bash
cd apps/api-server
.venv/bin/pytest tests/core3_real_data/test_hash_utils.py tests/core3_real_data/test_runner_contract.py tests/core3_real_data/test_fixture_baseline.py
```

如果改动了 `entities.py` 或 migration，还要运行：

```bash
cd apps/api-server
.venv/bin/pytest tests/test_core3_mvp.py
```

## 13. 205/85E7Q 验收

INFRA 阶段不连接 205 做真实数据运行，但必须通过 fixture 固化以下事实：

| 事实 | 验收 |
| --- | --- |
| 85E7Q `TV00029115` | fixture 中存在 |
| 有市场、参数、评论 | fixture 覆盖三类输入 |
| 无结构化卖点 | fixture 明确 selling points 不覆盖 85E7Q |
| 同品牌候选可存在 | fixture 至少包含 1 个海信候选 |
| 线上渠道限制 | fixture 标记线上、平台电商/专业电商 |
| unknown/null/空/`-` | hash 和数据事实测试覆盖 |

## 14. 完成标准

INFRA 编码完成必须满足：

1. 新增 `core3_real_data` 后端服务包。
2. 新增公共 schema。
3. 新增稳定 hash 工具。
4. 新增 runner 协议和 registry。
5. 新增 run context。
6. 新增 fixture 目录和 85E7Q fixture。
7. 必要时新增首批 foundation migration。
8. 后端相关测试通过。
9. 旧 `test_core3_mvp.py` 不被破坏。
10. 没有前端、部署、旧 MVP 业务逻辑改动。

## 15. 风险和回滚

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 改 `entities.py` 破坏旧表 | 旧 MVP 测试失败 | 只追加不改旧类，跑旧测试 |
| Alembic 导入新 model 失败 | 迁移不可用 | 若拆 model 文件，必须更新 env 和 init_db |
| hash 语义不稳定 | 后续增量重算错误 | 单元测试固定 JSON、列表、日期、空值 |
| fixture 过大 | 测试慢 | 只保存小样本和预期事实 |
| runner 协议过早绑定业务 | 后续模块受限 | INFRA 只定义协议，不定义模块规则 |
| 与旧 `core3_mvp` 命名冲突 | API/表混乱 | 使用 `core3_real_data` 包和 `/v2` API |

回滚策略：

1. 如果只新增包和测试，删除新增文件即可。
2. 如果新增 migration，必须新增反向 downgrade，不手工改库。
3. 如果修改 `entities.py`，回滚只移除新增 v2 类，不改旧类。

## 16. 下游依赖

后续模块依赖 INFRA 输出：

| 下游 | 依赖 INFRA 内容 |
| --- | --- |
| M00 | hash 工具、run context、repository 基类、runner result |
| M01 | hash 工具、fixture、状态枚举 |
| M02 | evidence schema 基础、hash 工具、runner 协议 |
| M03-M15 | 模块 code 枚举、状态枚举、review issue schema |
| M16 | runner registry、run context、module result schema |
| API | 公共 schema 和状态枚举 |
| FRONTEND | 业务展示状态和中文映射由 API 任务进一步收敛 |

## 17. 子任务执行建议

INFRA 编码建议拆成以下执行顺序：

1. INFRA-A：创建包、空模块和测试目录。
2. INFRA-B：实现 constants 和公共 schema。
3. INFRA-C：实现 hash 工具和测试。
4. INFRA-D：实现 run context、runner 协议和测试。
5. INFRA-E：实现 repository 基类和只读保护约定。
6. INFRA-F：实现 85E7Q fixture 和 baseline 测试。
7. INFRA-G：如需要，新增 foundation migration。
8. INFRA-H：跑旧 core3 MVP 测试，确认隔离。

每个子任务都应能单独测试和回滚。

## 18. 下次任务

下次应生成：

```text
docs/core3_mvp/real_data_v2/development/M00_development_tasks.md
```

M00 文档需要基于 INFRA 的 hash、runner、run context 和 repository 边界，拆清原始数据批次、行登记、水位、source row hash、受影响 SKU 和与 M16 的接口。
