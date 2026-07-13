# 用户卖点价值画像需求追溯矩阵

状态：G01 冻结候选

日期：2026-07-13

## 1. PF 追溯

| 需求 | 实现 Goal | 主要模块 | 必测验收 |
| --- | --- | --- | --- |
| PF01 全部 M12/M13 候选 | G02 | candidate service/repository | 候选数 0/1/12/>30，无截断 |
| PF02 M14 只加标签 | G02 | candidate service | M14 0/1/3 不改变 universe count |
| PF03 竞品与参考池分离 | G02/G04 | schema/candidate tables | pool_type、用途和报告语言分离 |
| PF04 按问题选择集合 | G02/G05 | question analysis | 每题 full eligible/selected/rejected + reason |
| PF05 同尺寸池非竞品定义 | G02 | fallback/reference resolver | 无 M12/M13 时只生成 reference |
| PF06 全量轻 manifest | G02/G08 | batch loader | 最大候选、query count、lazy evidence |
| PF07 门槛功能三值统计 | G03 | thresholds | missing 不作 false，known/prevalence 可审计 |
| PF08 六类投入分类 | G03 | classifier | 正常、边界、冲突、TV/AC |
| PF09 单一当前分类 | G03/G05 | classifier/materializer | 冲突 review，版本变化 diff |
| PF10 四类持久化记录 | G04 | entities/migration/repository | upgrade/downgrade/CRUD/schema 回读 |
| PF11 类目/lineage/hash | G04/G05 | profile schema/service | TV/AC isolation、hash 验证 |
| PF12 单 SKU/批量生成 | G05 | materializer/batch | resume、失败隔离、幂等 |
| PF13 草稿不覆盖发布 | G04/G05 | repository/version service | 历史回读、事务和并发 |
| PF14 报告只读画像 | G06 | profile answer/orchestrator | report 路径零上游业务查询 |
| PF15 跨载体同 DTO | G06 | renderers | JSON/短答/Markdown/飞书/卡片一致 |
| PF16 画像 topic 问答 | G07 | qa index/router | 10 类问题 |
| PF17 同版本与事实路径 | G07 | ask contract | profile hash、fact/candidate/item refs |
| PF18 画像版本 diff | G05/G07 | diff service | 候选/分类/价格/答案差异 |
| PF19 缺失/过期/阻断 | G05/G06/G07 | validation | unavailable/stale/blocked 不降级重算 |
| PF20 生成/预览/发布分离 | G05/G06/G08 | CLI/ability registry | 默认关闭、命令权限边界 |

## 2. 数据源追溯

| 画像内容 | 权威源 | 缺失处理 |
| --- | --- | --- |
| 参数与能力事实 | M03B | unknown，不推断 false |
| 宣传 claim 事实 | M04C | unknown，不等于未宣传 |
| 用户反馈与体验 | M05C | 未覆盖，不等于不认可 |
| 价格、销量、周数 | M07/clean weekly | 缺失则对应量价问题不可用 |
| 用户任务/目标群体 | M09C/M10C | 降级替代关系置信度 |
| 价值战场/分配 | M11C/M11D | 不把分配当新增销量 |
| 采购理由 | M12D published | proposition 不写成已成立理由 |
| 候选召回 | M12 | 无记录则 competitor universe unavailable |
| 候选组件/角色 | M13 | 缺失为 recalled_only |
| 重点竞品 | M14 | 仅标签，不是宇宙门禁 |

## 3. 65E7Q 业务验收追溯

| 产品经理问题 | 画像字段 | 验收重点 |
| --- | --- | --- |
| 哪些投入保留 | investment_decisions retain + value items | 画质体验组合有具体对照和量价证据 |
| 哪些未转化 | unconverted | 1920 分区事实与分区体验未覆盖分开 |
| 哪些不用跟 | do_not_follow | 量子点等必须有真实替代候选和当前胜负 |
| 价格是否支撑 | price_role.current_band | 同预算与同价值对照分开，不混成 WTP |
| 如何追求销量 | price_role.scale_strategy | 当前价格带、走量带、同品牌蚕食和边界 |
| HDMI 2.1 是否亮点 | table_stake | 事实普及率门禁，不看评论缺失 |
| 为什么选某竞品 | question analyses/candidates | 保存 M12/M13 关系、选择与拒绝原因 |
| 深入追问 | qa_index | 同 profile version、fact path 和 boundary |

## 4. Goal 关闭证据

每个 Goal 关闭至少记录：

- 精确文件清单和 git status；
- 测试命令、结果和覆盖范围；
- schema/migration/query/hash 等任务特有门禁；
- 未解决限制和下一 Goal 前置条件；
- 独立 commit SHA；
- 涉及 205 时的 revision、migration、SQL、health 和 rollback 证据。

G09 必须有 65E7Q 单 SKU回执；G10 必须引用 G09 complete 状态。G10 只生成 draft，不能包含 publish/current 切换证据。
