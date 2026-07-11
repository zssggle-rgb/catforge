# G08 关闭回执：本地综合验收未通过

## Objective

对 G03-G07 完整链路执行本地综合验收、需求追溯、性能和跨载体检查，并分别完成方法识别、工程质量和产品经理业务语言独立评审；发现核心合同错误时停止 G09 准入，不在 G08 临时重写设计。

## 验收结果

`G08 review completed; acceptance failed; G09 not allowed`。

验收任务本身已经完成，但被验收的 V4 实现未达到 RC 条件。任务链必须插入独立修复 Goal `G08R1`，修复并重新验收通过前不得进入 G09。

## 已完成验证

- G03-G07 artifact manifest：23/23 hash matched；
- V4：77 passed；
- V4 + V2 service/answer：107 passed；
- analyst CLI：88 passed；
- M11C/M11D/M12C/M12D：108 passed；
- competitor purchase-reason reader：6 passed；
- 相关回归合计：309 passed；
- V4 schema/service/answer coverage：93%；
- V4 专属文件 Ruff、py_compile、diff check：passed；
- query count：单/多候选固定且 <=20；
- 10,000 synthetic rows：0.283883s、peak 25.413MB；
- 65E7Q-like fixture P95：0.000325s；
- Markdown render P95：0.000060s；
- default-off、自然语言路由隔离、无外部 LLM、M12C 旧金额隔离、跨载体同源和 PM 主表禁止词：passed。

## 核心阻断

1. Q5 缺少 cluster bootstrap、质量加权中心和联合保守区间；
2. lineage gate 会把同版本同批次但不同 hash 的事实误判 aligned；
3. M11D battlefield weight 没有用于战场样本权重；
4. 候选池在角色/可比性判断前总计截为 3；
5. weekly rows 全量加载后静默取前 2,000；
6. configured profile list 顺序不稳定可能导致 hash 漂移；
7. G01 五 cohort 没有按 frozen payload/hash 真正回放；
8. 纯负向用户反馈被产品经理文案写成“正反并存”。

详细证据见：

- `G08_method_review.md`；
- `G08_engineering_review.md`；
- `G08_pm_language_review.md`；
- `G08_acceptance_report.md`。

## 独立审查说明

预发布 review 技能使本 Goal 增加了范围漂移隔离、数据安全/枚举/副作用检查、覆盖率图式审计和对抗 review。独立 Codex 结构化 pass 在 5 分钟窗口内未产出结论，按超时记录；对抗 pass 返回 8 个候选问题，主审逐项回读后确认 7 个成立，1 个 Session autoflush 候选因 CatForge `SessionLocal(autoflush=False)` 判定为不成立。

## Commit

- G08 评审与验收 artifact commit：`b54418e`；
- 本关闭回执、manifest 和完成状态：本文件所在的独立 closure commit。

## 下一 Goal 准入

`G08R1 allowed`；`G09 denied`。G08R1 必须先冻结修复合同，覆盖 B01-B08，重跑 309 项相关回归和全部 G08 门禁，再决定是否恢复 G09 准入。
