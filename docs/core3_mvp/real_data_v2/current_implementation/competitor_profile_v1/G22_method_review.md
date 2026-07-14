# G22 方法评审

状态：通过，无未关闭 P0/P1 方法问题

日期：2026-07-14

## 1. 方法结论

V1 已形成一条可审计的“市场可比产品 → 正式竞品/研究参照 → 用户价值与购买池 → 量价压力 → 七类关系 → 0—3 重点竞品 → SKU 竞争决策画像”链路。它不再把“同尺寸列表”“卖得好的产品”或“有相同基础功能”直接当作竞品，也不把市场量价关联写成单卖点因果、WTP 或净新增销量。

## 2. 逐层方法

1. 候选宇宙：对权威 SKU universe 运行同购买池、同品牌梯度、升档、降档、场景、同价值和市场参考七个入口，不设置 12 款或其他固定业务上限。
2. 候选资格：召回、正式关系计算、正式竞品身份和 reference 身份分离；被召回不等于成为竞品。
3. 通用项过滤：taxonomy table-stake/generic 和 serving-scope 覆盖率共同决定通用性；缺覆盖率时只能 supporting，不能反向当差异价值。
4. 购买池：产品形态、尺寸/能力段、预算可达和任务/价值重合四门组合，不用单一相似度分数替代业务判断。
5. 用户价值替代：分别保留采购理由、任务/场景、受众需要、用户兑现、能力表达证据，并按 lineage 去重；同一个上游事实不能伪装成多个独立证据族。
6. 量价压力：以 M07 加权均价和周均销量为主口径，比较价格位置、销量位置和价值覆盖；结论是市场表现关联，不声称因果 WTP。
7. 七类关系：直接替代、同预算替代、降档分流、升档替代、同品牌梯度、场景替代、同价值替代逐条过门禁；关系不成立也保存 failed/unassessable/review_required 原因。
8. 重点竞品：按产品经理需要回答的独立问题选 0—3 款，不为凑数重复同一种信息，不从 reference-only 强行升级。

## 3. G22 发现并关闭的问题

| 问题 | 风险 | 关闭方式 |
| --- | --- | --- |
| 生成、持久化、回读未真正连通 | 只能算内存结果，不能形成画像资产 | 新增 ensure/generate/batch、materialized→persistence adapter、事务回读 hash 校验 |
| 合法 recalled/review/blocked pair 被 DB membership check 拒绝 | 审计候选被丢失 | ORM/迁移合同允许三类非 driving pair 双 membership=false |
| relation evaluator 忽略资格结果 | reference/review 候选可能被升级为正式关系 | relation_evaluation_member=false 时七类关系全部保持非 driving 状态 |
| optional module 0 行被 hard fail | missing 被误判为失败，40 款无结论问题会被放大 | optional 0 行保存 unavailable authority；M03B/M07 仍 hard-required |
| 证据只留模块级 hash | 无法判断两族证据是否同源 | 优先保留 evidence_id/source_file_id/raw_row_id/confidence，并以底层 lineage 去重 |
| 场景替代机械要求同形态/同档 | 与方法合同矛盾 | 允许不同形态/尺寸，但必须共享核心任务并有场景证据 |
| 上游 preview 设计与 typed request 矛盾 | 可能产生隐式 latest-draft 回退 | V1 明确只消费 published/current 上游；仅保存后的竞品画像允许显式 draft preview |

## 4. 方法边界

- 可以回答：哪些产品会进入同一次选择、为什么构成替代、谁形成价格/销量压力、哪些价值路线可替代、哪些配置值得跟或不值得跟、同品牌如何分工。
- 不能直接回答：去掉某卖点净减少多少销量、用户愿意为单卖点多付多少钱、某个市场差异必然由单卖点造成。
- 没有足够证据时返回 `insufficient_evidence` 或问题级 unavailable，不用负面话术填满报告。

## 5. 后续现场门禁

G22 只证明方法和代码合同成立。65E7Q 与 AC 单 SKU 的结论是否真正有产品经理价值，必须在 G24/G25 对正式数据生成的 draft、卡片、两份报告和问答逐项验收；在那之前不允许切 published/current。
