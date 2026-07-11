# G08 本地综合验收报告

## 验收结论

`FAILED — G09 NOT ALLOWED`。

V4 当前已经形成可读的产品经理用户价值账，并在大量不足场景下守住“不补造价值、不补造金额”的边界；但本次独立方法和工程评审确认，Q5 稳定性算法、线谱 hash gate、战场样本权重、候选截断、确定性 hash、固定 cohort 回放和纯负向体验语义仍存在核心缺口。不能生成 RC，也不能部署 205 影子环境。

## 验收覆盖

### 功能与回归

- V4 schema/context/linkage/counterfactual/quantification/answer/CLI：77 passed；
- 加 V2 sellpoint-value service/answer：107 passed；
- analyst CLI：88 passed；
- M11C/M11D/M12C/M12D：108 passed；
- competitor purchase-reason reader：6 passed；
- 相关测试合计：309 passed；
- V4 schema/service/answer statement coverage：93%。

### 合同与边界

- G03-G07 五份 manifest 在各自 artifact commit 上 23/23 SHA-256 匹配；
- G02 frozen typed model 字段/required 集合现有测试均通过；
- V4 默认关闭，CLI 未带 `--enable-v4` 时在 DB context 前停止；
- 自然语言路由仍不选择 V4；
- 新 V4 服务没有 DB write、外部 LLM 或网络调用；
- M12C 旧金额没有进入 V4 WTP，M11D allocation 没有被冒充为消费者购买归因；
- JSON/短答/Markdown/飞书卡片由同一 report object 构造，业务行和双链接一致；
- PM 主表禁止词、无通用动作清单和无购买前心智猜测测试通过。

### 性能

| 指标 | 实测 | 预算 | 结果 |
| --- | --- | --- | --- |
| 首页 SQL queries | 单/多候选固定且 <=20 | <=20 | pass |
| 10,000 synthetic rows peak memory | 25.413MB | <256MB | pass |
| 10,000 rows 转换耗时 | 0.283883s | 记录项 | pass |
| 65E7Q-like local report P95 | 0.000325s | <1s | pass |
| Markdown render P95 | 0.000060s | <0.5s | pass |

## 阻断清单

| ID | 领域 | 阻断 |
| --- | --- | --- |
| B01 | 方法 | Q5 缺少 cluster bootstrap、质量加权中心和联合保守区间 |
| B02 | 线谱 | 同版本同批次 hash 变化被误判 aligned |
| B03 | 市场单元 | M11D weight 未用于战场样本权重 |
| B04 | 反事实 | 候选在比较前总计截为 3，违反 recall/snapshot/per-role 分层预算 |
| B05 | 数据裁剪 | weekly rows 全量加载后静默取前 2,000，可能截断 cell 且无警告 |
| B06 | 确定性 | configured profile list 无稳定排序，hash 可能随 DB 返回顺序变化 |
| B07 | 验收 | 五 cohort 未按 frozen payload/hash 真正回放，base-missing 也缺显式断言 |
| B08 | PM 语义 | pure negative 被写成“正反并存”，与 mixed 和数据冲突没有分开 |

## 非阻断记录

- V4 专属和修改入口 Ruff 全通过；`analyst_repository.py` 全文件的 7 个 Ruff 问题来自 V4 之前的 `79343371`，不纳入本任务；
- schema/service 顶部阶段说明已过时，随修复 Goal 机械更新；
- 65E7Q 脱敏 fixture 只足以验证 value/WTP 不补造，不能在本地证明真实数据上的 Q3；真实回放仍属于通过修复后的 G09。

## 下一步

建立独立 `G08R1` Goal，冻结修复合同后逐项修复 B01-B08并重跑 G08。G08R1 完成并重新评审通过前，任务链停在 G08，不创建 G09 RC，不连接 205，不切默认路由。
