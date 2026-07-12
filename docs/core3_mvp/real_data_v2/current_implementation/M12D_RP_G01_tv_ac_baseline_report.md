# M12D-RP-G01 TV/AC 成立度与阻力基线

- 生成时间：`2026-07-11T15:49:52.404924+00:00`
- 性质：只读审计，不是生产规则发布。
- 核心口径：购买理由成立只看同锚点正向证据；普通负面和 M12C 负向作为并行压力。

## TV

- SKU：`377`；当前无核心：`139`。
- 分层可成立且无普通压力：`18`；成立并有普通压力：`75`。
- 仅产品价值主张：`17`；评论错维度：`258`。
- 负面占主导：`7`；M12C 负向：`163`；事实证伪阻断：`0`。
- 未影响回归样本：`20`。

### 已知基准复核

| 集合 | 已知基准 | 本次观察 | 一致 |
| --- | ---: | ---: | --- |
| `no_core` | 139 | 139 | 是 |
| `guarded_reason_established` | 37 | 18 | 否，需在 G04 前解释 |
| `ordinary_pressure` | 29 | 75 | 否，需在 G04 前解释 |
| `proposition_only` | 29 | 17 | 否，需在 G04 前解释 |

### 验收样本

| 类型 | 观察数量 | 样本数量 |
| --- | ---: | ---: |
| `positive_established` | 637 | 5 |
| `localized_negative` | 156 | 5 |
| `negative_dominant` | 15 | 5 |
| `m12c_value_headwind` | 558 | 5 |
| `proposition_only` | 1278 | 5 |
| `evidence_misalignment` | 955 | 5 |
| `objective_falsification` | 0 | 0 |

## AC

- SKU：`155`；当前无核心：`25`。
- 分层可成立且无普通压力：`2`；成立并有普通压力：`12`。
- 仅产品价值主张：`0`；评论错维度：`143`。
- 负面占主导：`4`；M12C 负向：`107`；事实证伪阻断：`0`。
- 未影响回归样本：`20`。

### 验收样本

| 类型 | 观察数量 | 样本数量 |
| --- | ---: | ---: |
| `positive_established` | 152 | 5 |
| `localized_negative` | 45 | 5 |
| `negative_dominant` | 4 | 4 |
| `m12c_value_headwind` | 511 | 5 |
| `proposition_only` | 371 | 5 |
| `evidence_misalignment` | 1000 | 5 |
| `objective_falsification` | 0 | 0 |

## 只读证明

- 三张 M12D 表前后快照一致：`True`。
- G01 验收：`通过`。
- TV 已知数量只用于发现口径漂移，不作为配额，也不允许用白名单凑数。
