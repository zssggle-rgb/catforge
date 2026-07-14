# 竞品画像 V1 G17 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_price_volume_pressure_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_price_volume_pressure.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_price_volume_pressure.py`。

## 2. 研究过的现有模式

实现前对照了三类以上现有模式：

1. G03 方法合同 §10 与 A04/A05/A06/A12/A13/A19：固定使用加权均价、周均销量、描述性差异和非因果边界；
2. G04 detailed design §5.6 与基础 `PairMarketComparison`：沿用 M07 authority、analysis population/window、安全分母、percentile 和 diagnostics；
3. `competitor_profile_candidate_recall`/`eligibility` 的 weekly-volume ratio：沿用正分母和 missing unknown，不用零值伪造比值；
4. 既有用户卖点价值 QA 禁止项：固定关闭降价销量增量、单卖点因果 WTP 和去卖点损失销量。

## 3. 已实现的描述性量价模式

只消费 G14 已保存的 M07 事实，输出：

- same budget + candidate higher volume；
- same budget + candidate lower volume；
- lower price + candidate higher volume；
- higher price + candidate higher volume；
- higher price + lower volume；
- lower price + lower volume；
- volume parity；
- no market comparison；
- review required。

保存双方均价、周均量、总销量/销额、差值、比值和价格/销量百分位。所有分母安全规则沿用 G14；价格或周均量为零、缺失或比值不可用时返回 no comparison/unknown，不填 0。

## 4. 已实现的市场压力方向

结合 G15 purchase pool 与 G16 value evidence，输出：

- `direct_budget_pressure`：同预算候选获得更高周均销量承接；
- `downtrade_volume_pressure`：更低价格、基础购买可比性成立且周均销量更高；
- `uptrade_market_acceptance`：更高价格、价值证据可用且周均销量更高；
- `value_route_pressure`：同/相邻预算下另一条价值路线获得更高承接；
- `reference_only`：P3、预算外或价值证据不足，只能作市场参照；
- `no_observed_pressure`：量价组合未显示候选获得更强承接；
- `unassessable`：购买池、量价或 review 门禁不足。

低价但销量也低固定返回 `no_observed_pressure`，不允许写“降价能提升销量”。更高价且销量更高只说明该候选整体价值/品牌路线获得市场接受，不归因于单项卖点。

## 5. 非因果边界

每个 pair 固定：

- `causal_claim=false`；
- `wtp_claim=false`；
- `price_change_sales_increment_claim=false`；
- `formal_relation_status=not_evaluated`。

量价压力是同口径市场关联，不是单卖点 WTP、净新增销量、价格弹性实验或“去掉卖点会损失多少销量”。

## 6. Diagnostics、追溯与确定性

- common week/common platform 只在上游明确存在时保存为 diagnostic，不改变 pattern/pressure；
- pair evidence 只保存 exact M07 refs；
- M07 review/lineage conflict 或 G15/G17 budget config 不一致时 review_required；
- config、G14/G15/G16 result hash 和受保护量价事实全部进入 input fingerprint；
- 保留全部候选，一对一守恒，无数据库查询和候选截断；
- TV/AC config category 不一致时 fail closed。

## 7. 验证

- G17 schema/service tests：17 passed；
- G05—G17 全链：188 passed；
- G17 service + schema coverage：92%；
- 全部 market pattern 与 pressure direction：通过；
- same/adjacent/outside、volume parity 边界：通过；
- 零价格/零周均量/不可比分母：通过；
- P0/P1/P3/unknown 与 value limited/different/unassessable：通过；
- lower price + lower volume 非增量边界：通过；
- common week/platform、price/volume percentile diagnostics：通过；
- M07 review 与 config mismatch：通过；
- TV/AC、候选守恒、config hash 变化：通过；
- 无数据库、repository、SQLAlchemy、外部 LLM 和正式关系生成：通过；
- Ruff、format check、compileall：通过。

默认 4 个 TV candidate 的事实烟测：同预算承接压力、仅升档参照、低价规模分流、unknown/unassessable；所有因果/WTP/降价增量字段均为 false。

## 8. 状态变化

- 本地数据库写入：无；
- 205 连接、数据库写入和 migration：无；
- 画像 materialize、review/publish/current/deprecated：均未执行；
- G18 七类正式关系、G19 重点选择：均未实现；
- 部署：无；
- Git 暂存/提交：无。

## 9. 下一 Goal

允许创建 G18，只基于 G15 购买池、G16 价值替代证据、G17 量价压力和 G14 其他证据族实现七类正式关系、置信度、question eligibility 与 review；不得实现重点选择、画像持久化、205 写入、部署或 Git 提交。
