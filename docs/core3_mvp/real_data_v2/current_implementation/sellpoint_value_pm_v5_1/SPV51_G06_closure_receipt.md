# SPV51-G06 两池与问题级资格关闭回执

状态：completed

日期：2026-07-17

## 1. 两池结果

- 正式竞品池只接受 G05 的 `SellpointValueCompetitorSource`，完整复制竞品画像保存的全部候选、来源顺序、角色、业务得分、量价、pair facts 和三级 hash；
- `priority_order`、`selected_rank` 只作为来源 Top3 标签保存，不改变候选顺序，不参与候选过滤；
- 分析参考池独立保存市场、参数组、价值战场、同品牌尺寸梯度、同预算、市场原型和 synthetic donor 等用途；
- 既有 `SellpointValueReferenceManifestItem` 可以直接适配到新参考池，重复用途按 SKU 合并，并保留互补的价格、周均销量、参数、价值和战场事实；
- 同一 SKU 可以同时出现在正式竞品池和分析参考池，但分别保存 `competitor`、`market_reference` 身份及独立来源证据，不能互相冒充。

## 2. 问题级资格

- 八个问题都逐一保存全部正式竞品和全部分析参考的 candidate use，不存在候选整体 eligibility 或全局 stop switch；
- 每个 candidate use 保存 `selected/rejected`、`usable_dimensions`、`unavailable_dimensions`、本题原因和证据引用；
- 价格、销量、用户价值兑现、同品牌梯度、配置跟进、具体竞品、参数转化和战场拓展分别使用本题最小事实；
- 缺参数只拒绝配置/参数题，缺销量只拒绝销量题，缺价格只拒绝价格题；其他问题仍继续使用同一候选；
- `no data` 形成问题级 rejection reason，不生成全局 review；只有来源本身的合法性、类目或 typed contract 破坏才拒绝构建；
- 空字典/空列表只要被竞品画像明确列入 `available_fact_groups`，仍视为已保存可用事实，不被擅自改成 missing。

## 3. 合同完整性

- `SellpointValueCandidatePools` 强制八个问题按固定顺序齐全，并要求每题覆盖两个池的所有成员；
- 正式竞品的 `source_rank`、`priority_rank` 在每题中必须与竞品画像标签一致；
- 参考池 overlap 标记必须与正式池真实交集一致，TV/AC 类目不能串线；
- 结果使用确定性顺序和 hash；参考输入顺序或同 SKU 用途记录顺序变化不改变结果；
- G06 模块不导入旧候选 service/repository，不读取 M12/M13/M14，也不调用现场竞品分析。

## 4. 验证

- G06 candidate pools、V5.1 schema 和 G05 adapter 必要回归共 53 项通过；
- 覆盖全候选/Top3、两个池同 SKU 双身份、价格/销量/参数局部缺失、空事实组、市场/参数/战场/同品牌参考、重复参考互补合并、八题全覆盖、确定性、TV/AC 隔离和旧路径禁止；
- touched Python files 的 ruff check、py_compile、format check 和 diff check 通过；
- 未实现 G07 基础能力/投入分类，未实现 G08 量价计算，未写数据库或 205；完整回归、覆盖率、性能和三类总评审仍集中在 SPV51-G13。

## 5. 下一步

SPV51-G07 在问题级候选基础上重构基础能力和投入分类：样本不足只返回 `not_assessed`，unknown 不向价值/SKU 传播，只有真实冲突才形成局部 review。
