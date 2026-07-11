# G02 V4 测试计划

测试框架：pytest。所有算法测试确定性运行，不调用外部 LLM、网络或真实飞书。

## 1. 测试文件计划

| 文件 | 类型 | 负责范围 |
| --- | --- | --- |
| `test_claim_value_pm_v4_schemas.py` | unit | extra forbid、enum、invariant、unknown |
| `test_claim_value_pm_v4_context.py` | repository integration | target、authority、lineage、batch、query count |
| `test_claim_value_pm_v4_linkage.py` | unit | reason/value/bundle、评论去重、value status |
| `test_claim_value_pm_v4_counterfactual.py` | unit | 三类角色、可比性、隔离等级、共线 |
| `test_claim_value_pm_v4_quantification.py` | unit | pair curve、Q0-Q5、matched WTP、敏感性 |
| `test_claim_value_pm_v4_answer.py` | unit/snapshot | PM DTO、短答、Markdown、card |
| 扩展 `test_catforge_analyst_cli.py` | integration | explicit command、feature flag、V2 回归 |
| `test_claim_value_pm_v4_fixture_replay.py` | fixture integration | G01 五 cohort、65E7Q |

## 2. Code path coverage

```text
CODE PATH COVERAGE TARGET
=========================

[G03] resolve target + authority
  ├─ exact SKU ........................................ unit/integration
  ├─ model unique ..................................... integration
  ├─ not found / ambiguous ............................ integration
  ├─ configured rule version ......................... unit
  ├─ published M12D release .......................... integration
  ├─ multiple current same rule -> blocked ........... integration
  ├─ historical batch isolation ...................... integration
  ├─ aligned lineage ................................. unit
  ├─ stale revalidated ............................... unit
  ├─ stale conflict .................................. 65E7Q replay
  └─ unresolved -> blocked ............................ unit

[G04] reason -> value -> bundle
  ├─ core purchase reason + realized value ........... unit
  ├─ weak expression does not promote ................ unit
  ├─ post-purchase result != pre-purchase mind ....... unit
  ├─ direct technical sentence ....................... unit
  ├─ scenario outcome sentence ....................... unit
  ├─ generic praise stays bundle-level ............... V2 regression + unit
  ├─ negative/contradicted evidence .................. unit
  ├─ same sentence deduplicated ...................... unit
  ├─ capability unknown stays unknown ................ schema/unit
  ├─ lineage conflict affects only related link ...... unit
  └─ no M12D does not rebuild purchase reason ........ integration

[G05] counterfactual builder
  ├─ M14 provenance .................................. integration
  ├─ fallback provenance not mislabeled .............. integration
  ├─ M12C pool candidate ............................. unit
  ├─ same-family candidate ........................... unit
  ├─ base value role ................................. unit
  ├─ same value role ................................. unit
  ├─ stretch role .................................... unit
  ├─ A/B/C/unusable grade ............................ parameterized unit
  ├─ missing price overlap ........................... unit
  ├─ insufficient common cells ....................... unit
  ├─ experience not comparable ....................... unit
  ├─ promotion suspect ............................... unit
  ├─ inventory unavailable explicit .................. schema/unit
  └─ full collinearity merges bundle ................. C03 replay

[G06] quantification
  ├─ Q0 -> Q1 ........................................ unit
  ├─ Q1 -> Q2 ........................................ unit
  ├─ Q2 -> Q3 ........................................ unit
  ├─ Q3 -> Q4 ........................................ unit
  ├─ Q4 -> Q5 all gates .............................. synthetic identified
  ├─ cannot skip levels .............................. schema/unit
  ├─ same-price observed ............................. unit
  ├─ near-same-price label ........................... unit
  ├─ zero outside observed gap -> null ............... unit
  ├─ gap around zero too wide -> null ................ unit
  ├─ PAVA monotonicity ............................... V2 regression + unit
  ├─ no price variation .............................. C04 replay
  ├─ same-value only ................................. C02 replay
  ├─ crossing in range ............................... synthetic identified
  ├─ crossing out of range -> null ................... unit
  ├─ promotion-clean sensitivity ..................... unit
  ├─ leave-one-week-out stable ....................... unit
  ├─ direction flip -> unstable/null ................. synthetic unstable
  ├─ single pair below strict gate ................... 65E7Q replay
  ├─ full collinearity -> single WTP null ............ C03 replay
  ├─ lineage conflict -> WTP blocked ................. C05 replay
  └─ M12C allocated amount ignored ................... CRITICAL regression

[G07] output
  ├─ one row per battlefield + purchase reason ....... snapshot
  ├─ value/quantification separate ................... snapshot
  ├─ no automatic worklist ........................... forbidden-text test
  ├─ no internal codes in PM main table .............. forbidden-text test
  ├─ JSON/short/Markdown/card same conclusion ........ snapshot/integration
  ├─ Feishu publish success .......................... mocked integration
  ├─ Feishu failure preserves JSON/Markdown .......... mocked integration
  ├─ feature flag off ................................ integration
  └─ V2 route unchanged .............................. CRITICAL regression
```

## 3. User flow coverage

```text
USER FLOW COVERAGE TARGET
=========================

Product manager asks explicit V4 question
  -> target uniquely resolved
  -> main value structure rendered
  -> quantified boundary is visible
  -> drilldown explains counterfactual and limitations
  -> optional Feishu document

Cases:
  [unit+integration] ready result with Q1-Q4 rows
  [fixture]          65E7Q: value exists, WTP null
  [fixture]          identifiable synthetic: bounded WTP
  [integration]      ambiguous SKU: clear error, no partial wrong report
  [integration]      source missing: affected row unavailable, no invented copy
  [integration]      version conflict: visible scope, unaffected rows preserved
  [integration]      flag off: existing V2 remains response
  [mock integration] Feishu failure: local result remains usable
```

## 4. Schema tests

1. 每个 model `extra=forbid`；
2. availability missing 时业务值只能 null/empty-with-missing-status；
3. `inventory_status` 只能 `unavailable`；
4. Q5 必须 WTP available 且金额区间完整；
5. Q0-Q4 的 WTP amount 必须 null；
6. `causal_claim` 和 `psychological_max_price` 固定 false；
7. same-value-only 不可 Q5；
8. collinearity group 禁止 member 单项 WTP；
9. result hash 输入排除 generated_at/delivery URL；
10. category/project/batch/version/source refs 必填。

## 5. Authority 与 repository tests

使用 SQLite fixture，按真实表结构 seed：

- 每模块一个允许版本；
- 多个 rule version 同时 current，resolver 只选 configured version；
- 同 rule version 多 current -> blocked；
- M12D published version唯一；
- M12D refs v0.1 + current v0.2 -> stale revalidated/conflict；
- `latest` 包含三个 serving batches；
- 显式历史 batch 不读未来数据；
- M14 missing 时 fallback provenance；
- 所有候选 snapshot 和 weekly rows 批量加载；
- SQL query counter <= 20；
- repository/source scan 不引用任何 runner/write service。

## 6. Linkage tests

参数化覆盖：

- purchase reason family 映射到一个/多个 value families；
- 一个 bundle 多成员；
- 同一 member 支撑多个理由但 evidence 不重复；
- 直接技术词、场景结果、泛化好评、反向评论；
- 服务评论排除；
- weak expression 只能 partial/insufficient；
- stale revalidated 不沿用旧 M12D confidence；
- stale conflict 只阻断 affected relation；
- 无用户体验时 value_status not_observed，但 capability 仍可 configuration_support。

## 7. Counterfactual tests

| 输入 | 预期 |
| --- | --- |
| 同尺寸同战场、低一档、其他差异 0 | base/A |
| 同尺寸同档位 | same-value，不能证明增量 WTP |
| 更高档位 | stretch |
| 另一个主要 bundle 差异 | B |
| 多个差异/关键 unknown | C |
| 无共同周/平台 | unusable |
| 无价格重叠 | 不进入 Q3+ |
| 促销疑似占全部 cell | 主量化 unavailable |
| M14 source | provenance M14 |
| fallback source | provenance fallback，不得写 M14 |

## 8. Quantification tests

### 8.1 Pair curve

- 相对价差和选择份额公式；
- 2pp 分箱；
- P90 权重截尾；
- PAVA 单调不增；
- block 保留 x min/max；
- 同价只在观测范围和局部支持内读取；
- 近同价和同价标签互斥；
- 不外推；
- 单边零销量主分析排除。

### 8.2 Q5 gate

用 table-driven tests 对 12 个门禁逐个翻转。每次只移除一个条件，断言：

- level 从 Q5 降级；
- WTP amount null；
- exclusion reason 精确；
- value_status 不被错误否定。

### 8.3 Synthetic identified fixture

构造两个 A 级 base pairs：

- 两个 pair 来自两个独立 model family，不得用同一系列的重复配对凑数；
- 16 周 × 2 平台；
- base/enhanced 两档；
- 唯一变化是焦点 bundle；
- 已知 crossing 为 +8% 和 +10%；
- base reference price 5000；
- 无促销疑似；
- leave-one-week-out 稳定。

断言：

- method matched equal-choice gap；
- pair_count=2 且 model_family_count=2；
- method_config_version 固定为 `sellpoint_value_pm_v4_matched_wtp_config_v1`；
- 区间覆盖 400-500；
- 不超出观测区间；
- causal/psychological flags false；
- 重复运行 result hash 一致。

### 8.4 Synthetic unstable fixture

移除不同周后 crossing 方向翻转。断言 `status=unstable`、amount null。

## 9. G01 real fixture replay

### 9.1 65E7Q

- primary battlefield premium picture；
- published M12D vs current M03B/M04C/M12C lineage conflict；
- base 65E5Q 因 M04C/M12C missing 降级；
- same-value L65MC-SP；
- stretch Sony；
- Q3 maximum；
- same-price choice association 可保留；
- WTP null；
- 不出现 MiniLED/亮度/分区/高刷单项金额。

### 9.2 五 cohort

- C01：只通过 eligible-for-model，不预填 WTP；
- C02：same-value-only -> <=Q4；
- C03：full collinearity -> bundle-only；
- C04：single week -> no price sensitivity；
- C05：lineage conflict -> affected WTP blocked。

## 10. Output tests

PM 主表禁止词：

- `M03B/M04C/M12C/M12D/M14`；
- `Q0-Q5`；
- `isolation_grade`；
- SQL/英文 error code/evidence ID；
- `建议涨价/建议降价/增配/减配/下一步工作清单`。

业务 DTO 允许在 QA appendix 保存上述内部信息，但 renderer 不得泄漏到主表。

跨载体断言基于同一 `result_hash` 和 row IDs，不逐字复制文本。

## 11. Regression tests

CRITICAL：

1. V2 `sellpoint-value-pm` 117 项相关回归保持；
2. 旧 `sku-claim-value` 不变；
3. competitor-set Top 3 和 M12D 消费边界不变；
4. feature flag off 时自然语言仍走 V2；
5. M12C `estimated_price_premium_abs` 无任何路径进入 V4 WTP；
6. 既有飞书发布器不因 V4 失败而影响 V2。

## 12. Failure mode matrix

| Failure | Test | Error handling | PM-visible behavior |
| --- | --- | --- | --- |
| 多 current | integration | blocked | 明确数据版本冲突 |
| M12D stale | fixture | localized gate | 显示受影响判断不可用 |
| duplicate comment | unit | stable dedupe | 无重复自证 |
| fallback mislabeled | integration | enum validation | 正确写既有竞品候选 |
| promotion contamination | unit | exclude/sensitivity | 不输出金额 |
| no price overlap | unit | no interpolation | 无法量化 |
| unstable crossing | unit | WTP null | 市场结果不稳定 |
| Feishu timeout | mock integration | fallback | 本地结果仍可用 |

无 silent critical gap。

## 13. Performance tests

- query counter <= 20；
- 30 candidates recall / 12 full snapshots cap；
- 2,000 market cells cap；
- 65E7Q fixture analysis <= 1s 本地；
- 10,000 synthetic rows peak memory < 256MB；
- renderer <= 0.5s；
- no N+1 assertion by SQL statement spy。

## 14. Commands

实现后至少运行：

```bash
cd apps/api-server
uv run pytest tests/core3_real_data/test_claim_value_pm_v4_schemas.py -q
uv run pytest tests/core3_real_data/test_claim_value_pm_v4_context.py -q
uv run pytest tests/core3_real_data/test_claim_value_pm_v4_linkage.py -q
uv run pytest tests/core3_real_data/test_claim_value_pm_v4_counterfactual.py -q
uv run pytest tests/core3_real_data/test_claim_value_pm_v4_quantification.py -q
uv run pytest tests/core3_real_data/test_claim_value_pm_v4_answer.py -q
uv run pytest tests/core3_real_data/test_claim_value_pm_v4_fixture_replay.py -q
uv run pytest tests/core3_real_data/test_claim_value_pm_service.py tests/core3_real_data/test_claim_value_pm_answer.py -q
uv run pytest tests/core3_real_data/test_catforge_analyst_cli.py -q
```

覆盖目标：新增纯函数/合同 100%，集成层至少 90%，总新增代码不低于 90%。
