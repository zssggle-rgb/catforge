# M08.6 参数-卖点-评论分层产品锚点校准开发任务

## 1. 开发目标

本任务把 M08.6 需求和详细设计落到代码实现，解决真实数据下“有参数但锚点缺失、卖点和参数混用、任务/战场/客群过宽命中”的问题。

开发完成后：

1. M03 不再产生已知错误参数映射。
2. M08.4 输出分层产品锚点。
3. M08.5 发布价值战场、用户任务、目标客群时带可解释锚点。
4. 后续 M09/M10/M11 可以消费分层锚点做 SKU 分类。
5. 205 热更新后可按初始化页面逐步重跑和查看结果。

## 2. 输入设计引用

| 类型 | 文件 |
| --- | --- |
| 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M08_6_product_anchor_evidence_layer_requirements.md` |
| 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M08_6_product_anchor_evidence_layer_design.md` |
| M03 设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M03_param_extraction_design.md` |
| M08.4 设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M08_4_product_anchor_correction_design.md` |
| M08.5 设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M08_5_business_dimension_ontology_calibration_design.md` |
| M09/M10/M11 设计 | `M09_user_task_design.md`、`M10_target_group_design.md`、`M11_battlefield_design.md` |

## 3. 要改文件

### 3.1 后端服务

```text
apps/api-server/app/services/core3_real_data/param_field_matcher.py
apps/api-server/app/services/core3_real_data/param_value_parsers.py
apps/api-server/app/services/core3_real_data/param_extraction_service.py
apps/api-server/app/services/core3_real_data/comment_native_dimension_service.py
apps/api-server/app/services/core3_real_data/dimension_ontology_service.py
apps/api-server/app/services/core3_real_data/user_task_service.py
apps/api-server/app/services/core3_real_data/target_group_service.py
apps/api-server/app/services/core3_real_data/battlefield_service.py
```

### 3.2 种子和规则

```text
apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json
```

允许补充：

1. 标准参数别名。
2. 参数黑名单/白名单规则。
3. 代理参数定义。
4. 战场、任务、客群的锚点规则。

不得把 claim code 写成 param code。

### 3.3 API 和页面

如果现有初始化页面已经能显示模块结果，只做必要补充：

```text
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/schemas/core3_real_data.py
apps/factory-web/src/pages/core3RealData/
```

页面只增加业务可读字段，不展示内部 JSON 大段。

### 3.4 测试

```text
apps/api-server/tests/core3_real_data/test_m03_param_field_mapping_guard.py
apps/api-server/tests/core3_real_data/test_m08_4_layered_product_anchor.py
apps/api-server/tests/core3_real_data/test_m08_5_dimension_anchor_publication.py
apps/api-server/tests/core3_real_data/test_m09_m10_m11_anchor_consumption.py
```

可在现有测试文件中增补，但必须保证测试名称能定位 M08.6 修正范围。

## 4. 不允许改文件

1. 不改原始四表结构。
2. 不删除已生成的历史运行记录。
3. 不重写旧 MVP `core3_mvp` 粗粒度链路。
4. 不把 M09/M10/M11 重写成单一大服务。
5. 不在前端硬编码战场、任务、客群结论。

## 5. 开发步骤

### 5.1 M03 稳定化

目标：先保证参数干净，否则后续锚点都会被污染。

任务：

1. 在 `param_field_matcher.py` 增加 `ParamMappingGuardRule` 和 guard 检查。
2. 对已知误映射加入阻断规则。
3. 在 seed 中补充代理参数别名。
4. `HDR` 改为 HDR 支持类参数，不再映射亮度。
5. `背光源/背光源细分` 映射 `backlight_type`。
6. `能效等级`、`全面屏`、`SLIM/超轻薄`、`机身厚度` 映射设计或能效代理参数。
7. 写单元测试覆盖误映射和代理映射。

完成标准：

1. 已知误映射样例全部阻断。
2. 代理参数写入质量标记。
3. M03 现有测试通过。

### 5.2 M08.4 分层锚点

目标：让每个 SKU 的产品锚点来源可解释。

任务：

1. 扩展 `ProductAnchorEvidence` 和 `ProductAnchorMatch`。
2. 增加 `proxy_param_anchor_score`、`comment_validation_score`、`market_anchor_score`。
3. 增加 `anchor_source_status` 判定。
4. 参数规则区分 `strong`、`proxy`、`weak`。
5. 卖点规则区分结构化卖点、参数支撑卖点、评论增强卖点。
6. 评论只作为 validation，不作为产品能力强证据。
7. 服务评论强制隔离。
8. 候选级 support summary 写入分层分布。
9. SKU support detail 写入分层命中明细。

完成标准：

1. `param_only` SKU 能进入基础定位。
2. `claim_plus_param` SKU 能显示卖点和参数共同支撑。
3. `claim_only` 和 `comment_only` 被降级或复核。
4. 音效、护眼缺参数时输出参数缺口，而不是伪造支撑。

### 5.3 M08.5 维度发布

目标：让本体定义可被下游分类和销量分配消费。

任务：

1. `_seed_anchor_rows()` 输出强参数、代理参数、卖点、评论主题的角色。
2. `_include_rule()` 增加分层锚点字段。
3. `_required_evidence()` 区分战场、任务、客群的证据要求。
4. `_allocation_policy()` 禁止 `comment_only` 进入强分配。
5. 用户任务增加 `linked_battlefield_codes` 和产品回链。
6. 目标客群增加间接锚点说明。
7. 服务语境保持 `never_allocate`。

完成标准：

1. 价值战场有产品锚点要求。
2. 用户任务能回链产品锚点或战场。
3. 目标客群能回链任务、战场、价格带或人群线索。
4. 页面/API 可解释每个维度为什么可用或不可用。

### 5.4 M09/M10/M11 消费调整

目标：后续分类不再按预设泛化命中。

任务：

1. M09 用户任务读取 task anchor quality。
2. M10 目标客群读取任务/战场回链和市场支撑。
3. M11 价值战场读取分层锚点，不接受 `comment_only` 强支撑。
4. 对 SKU 维度权重输出分层来源。
5. 给 M11.6/M11.7 留出销量权重校验字段。

完成标准：

1. 不再所有 SKU 命中所有战场/客群/任务。
2. SKU 在不同维度上的权重可解释。
3. M11.7 能检查横向和纵向销量权重是否对齐。

## 6. 测试任务

### 6.1 本地测试

运行：

```text
apps/api-server/.venv/bin/python -m pytest \
  apps/api-server/tests/core3_real_data/test_m03_param_field_mapping_guard.py \
  apps/api-server/tests/core3_real_data/test_m08_4_layered_product_anchor.py \
  apps/api-server/tests/core3_real_data/test_m08_5_dimension_anchor_publication.py \
  apps/api-server/tests/core3_real_data/test_m09_m10_m11_anchor_consumption.py
```

同时运行现有相关测试：

```text
apps/api-server/.venv/bin/python -m pytest \
  apps/api-server/tests/core3_real_data/test_m03_param_extraction.py \
  apps/api-server/tests/core3_real_data/test_m08_4_comment_native_dimension.py \
  apps/api-server/tests/core3_real_data/test_m08_5_dimension_ontology.py \
  apps/api-server/tests/core3_real_data/test_m09_user_task.py \
  apps/api-server/tests/core3_real_data/test_m10_target_group.py \
  apps/api-server/tests/core3_real_data/test_m11_battlefield.py
```

如果实际测试文件名不同，按现有文件名替换，但覆盖点不能减少。

### 6.2 205 验收

热更新到 205 后，按初始化页面顺序执行：

```text
M03 -> M04a -> M04b -> M08 -> M08.4 -> M08.5 -> M09 -> M10 -> M11 -> M11.6 -> M11.7
```

每步记录：

1. 处理 SKU 数。
2. 新增/更新/跳过产物数。
3. warning/review 数。
4. 典型失败原因。
5. 对下游是否可用。

M03 验收 SQL/API 要确认：

1. `内置WIFI` 不再映射 `speaker_power_w`。
2. `HDMI数量/USB数量/机身厚度` 不再映射 `color_depth_bit`。
3. `HDR` 不再映射 `peak_brightness_nits`。
4. `背光源`、`HDR`、`能效等级`、`全面屏` 等代理参数被正确识别或进入复核。

M08.4/M08.5 验收要确认：

1. 每个候选维度有参数/卖点/评论/市场来源拆分。
2. 没有卖点的 SKU 可以有 `param_only` 定位。
3. 有卖点 SKU 能看到 claim 支撑。
4. 服务语境不进入产品战场。
5. 战场、任务、客群分布有区分度。

## 7. 风险和处理

| 风险 | 处理 |
| --- | --- |
| M03 改动影响后续全部模块 | 必须按顺序重跑，不能只重跑 M08.5 |
| 代理参数过宽导致泛化 | 给代理参数设置 score cap 和 review 标记 |
| claim_only 被误当强支撑 | M08.5 allocation policy 阻断 |
| 评论信号过强 | comment validation 只加权，不单独成立 |
| 音效/护眼缺参数导致业务质疑 | 明确输出“参数待补”，保留卖点/评论候选 |

## 8. 完成标准

1. 文档中的已知误映射全部有测试覆盖。
2. M03、M08.4、M08.5、M09/M10/M11 相关测试通过。
3. 初始化页面可展示 M08.6 修正后的业务字段。
4. 205 热更新后可由用户点击执行，不依赖 Codex 手工脚本。
5. 205 重跑后能说明每个 SKU 为什么属于某个战场、任务、客群。
6. M11.7 能继续做销量权重横纵校验。

