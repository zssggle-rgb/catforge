# 竞品画像 V1 G01 完成回执

状态：completed

日期：2026-07-14

## 1. Goal

冻结竞品画像业务定义：明确候选宇宙、正式竞品、分析参考、SKU×SKU 关系、重点竞品、画像消费者以及旧 M12/M13/M14 的迁移和退役边界。

## 2. 产物

- `COMPETITOR_PROFILE_V1_requirements.md`
- `COMPETITOR_PROFILE_goal_dispatch.md`
- `G01_closure_receipt.md`

## 3. 已冻结决定

1. 竞品画像同时包含目标 SKU 决策画像和 SKU×SKU 关系画像；
2. 完整候选宇宙不设固定业务数量上限；
3. 正式竞品和分析参考严格分离；
4. 七类竞争关系允许多关系并存；
5. 重点竞品为 0—3 款决策标签，不截断完整候选；
6. 新版 M03B—M12D 是权威输入，旧 M08—M14 不是必需依赖；
7. 现有竞品智能体的临时计算必须上移到画像生产层；
8. 卡片、两份报告、问答和用户卖点价值画像只消费已保存画像；
9. 均价和周均销量为基础量价口径，共同周和共同平台不作硬门槛；
10. 本任务链只授权 draft，publish/current 必须另行批准；
11. 旧 M12/M13/M14 在新画像正式切换前保持可回退；
12. 65E7Q、AC 单 SKU、TV/AC 全量草稿按顺序验收。

## 4. 明确未做

- 未修改运行代码或测试；
- 未新增或执行 migration；
- 未写入 205 数据库；
- 未部署；
- 未修改、重跑或覆盖旧 M12/M13/M14；
- 未执行任何 published/current 切换；
- 未暂存或提交文件。

## 5. 验证

已完成：

- CP01—CP20 唯一编号和条款数量检查：20/20；
- 需求与调度文档中的候选、参考、消费者、发布和单 SKU 门禁一致性检查：通过；
- Markdown 标题、表格和列表基础结构检查：通过；
- `git diff --check -- docs/core3_mvp/real_data_v2/current_implementation/competitor_profile_v1`：通过；
- 精确工作树范围复核：G01 只新增 `competitor_profile_v1/` 目录，未修改运行代码、数据库或其他任务文件。

## 6. 下一 Goal

G02：只读复核 205 上 TV 377 款、AC 155 款的新画像覆盖、候选来源可行性和缺失边界。

本回执已完成；当前 Goal 标记 complete 后允许创建 G02。
