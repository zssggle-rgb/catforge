# G08R1 Test Matrix

## 1. Contract tests

| Case | Expected |
| --- | --- |
| same version + same batch + different hash | `stale_conflict` |
| same content refs in different order | same authority/input/result hash |
| missing source hash | `unresolved` |
| v1 method config presented as Q5 | schema reject |
| pure negative comments | `negative`，PM 不出现“正反并存” |
| positive + negative | `mixed` |
| lineage conflict | data conflict 文案，不写用户体验 mixed |

## 2. Candidate and cell tests

| Case | Expected |
| --- | --- |
| valid second-family base ranks 4th | recalled and can enter snapshot |
| 30 recalled across three declared roles | <=12 snapshots, role coverage deterministic |
| >3 candidates in one computed role | final assessments <=3 for that role |
| 2,001 weekly rows | DB bounded; <=2,000 output; no partial week/platform group; warning present; Q5 blocked |
| different DB row order | same selected cells and hash |
| allocation weight changes | real share unchanged; curve observation weight changes |
| allocation missing | explicit limitation; no purchase attribution claim |

## 3. Q5 method tests

| Case | Expected |
| --- | --- |
| two families, stable synthetic | deterministic bounded interval; config v2 |
| same input repeated | identical bootstrap summary/result hash |
| cluster bootstrap crossing spans zero | WTP null |
| bootstrap success <80% | WTP null |
| LOO stable but bootstrap unstable | WTP null |
| high-quality and low-quality pair differ | weighted center follows quality weights; interval remains conservative |
| same family / one pair / same-only / base missing | <=Q4 and WTP null |
| promotion / zero sales / gap hole / positive direction / single week | WTP null |

## 4. Frozen cohort replay

1. 每个 G01 cohort 读取 manifest 中实际字段并验证 `input_manifest_sha256`；
2. C01 验证 candidate-only，不预填金额；
3. C02 验证 same-value-only；
4. C03 验证 bundle-only 和单项 WTP 禁止；
5. C04 验证 single-week/no temporal price variation；
6. C05 验证版本/事实冲突局部阻断；
7. 65E7Q 脱敏 fixture 继续只验证不补造用户价值和金额；
8. frozen payload 无法执行时测试必须失败或明确 skip reason，不能重建无关 synthetic 后算通过。

## 5. Full acceptance

- 原 G08 309 项相关回归全部通过并增加 G08R1 tests；
- V4 schema/service/answer coverage >=90%，所有新增公共分支有正负测试；
- query count <=20，候选数量不产生 N+1；
- 10,000 rows peak <256MB，fixture P95 <1s，renderer P95 <0.5s；
- G03-G08R1 manifest/hash 全匹配；
- JSON/短答/Markdown/飞书对 negative/mixed/conflict 和 Q5 区间同源；
- 方法、工程、PM 三审全部 PASS 后才允许 G09。
