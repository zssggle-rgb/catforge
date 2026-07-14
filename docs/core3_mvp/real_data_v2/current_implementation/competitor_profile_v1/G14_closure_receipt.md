# 竞品画像 V1 G14 完成回执

状态：completed

日期：2026-07-14

## 1. 产物

- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_pair_feature_schemas.py`；
- `apps/api-server/app/services/core3_real_data/analyst/competitor_profile_pair_feature.py`；
- `apps/api-server/tests/core3_real_data/test_competitor_profile_pair_feature.py`。

## 2. 研究过的现有模式

实现前对照了至少三类已有模式：

1. G03 方法合同 §5—§7 与 G04 detailed design：沿用 pair 一对一守恒、source availability、exact evidence、描述性量价和 unknown 边界；
2. 现有 `PairMarketComparison` 与 M07 market facts：沿用均价、周均量、总销量/销售额、差值和安全比值口径，共同周/平台只作可选诊断；
3. M03B 参数画像：沿用 `param_code` 对齐、多值归一、来源记录和缺失不补零；
4. M04C/M05C/M09C/M10C/M11C/M11D/M12C/M12D typed 资产：沿用稳定 code、review/lineage、evidence ref 和多值去重，不在本层重新生成用户理由或价值语义。

## 3. 已实现的 pair 基础特征合同

- `PairFeatureBuilder` 只消费 G12 canonical pipeline，不读取数据库、不调用外部 LLM；
- 每个 recalled candidate 严格生成一个 `PairFeatureRecord`，并校验 recall、eligibility、determinism 的 hash 与候选守恒；
- pair 保存 target/candidate identity、品类、产品形态、尺寸/能力段、预算和基础量价；
- 完整覆盖 M03B、M04C、M05C、M07、M09C、M10C、M11C、M11D、M12C、M12D 十个模块；
- 每个模块显式保存 target/candidate availability、unknown reason、review/conflict、exact evidence refs 和 source lineage；
- 九类业务事实按稳定 code 对齐：参数、卖点表达、用户兑现、任务、客群、价值战场、市场位置、卖点价值角色、采购理由；
- 多记录、多值按规范化值去重排序，输入顺序不改变业务 hash；
- TV 只允许屏幕尺寸/尺寸段字段，AC 只允许形态/能力段字段，schema 阻止跨品类串用；
- bundle、pair、feature 均有稳定 hash，受保护事实变化必须改变结果 hash。

## 4. 事实层的业务边界

本 Goal 只表达双方已有数据中的事实：

- 同一 code 下哪些值共同、不同、仅本品有、仅候选有；
- 双方均价、周均量、总销量/销售额、价格差、周均量差和分母有效时的比值；
- 上游明确提供时，共同周/平台可作为诊断信息保存。

本层不把共同值或差异直接解释为：

- 购买池、主辅战场重合或拖累；
- 用户价值替代、优势或关系成立；
- WTP、卖点因果销量或净新增销量；
- 七类正式竞品关系、总分或重点竞品。

这些结论必须由 G15—G19 使用本 Goal 的事实特征和对应方法合同继续判断。

## 5. Missing、零值与冲突

- missing、空值和模块缺失均保持 `unknown`，不转换成 0 或 false；
- 目标均价或周均量为 0 时，比值和百分比保持 unknown，绝不制造无限大或虚假差异；
- review required、冲突状态和 lineage conflict 原样保留并进入 pair 质量原因；
- sparse candidate 仍保留完整 typed pair，不因证据少而从候选集合消失；
- 空 manifest、scope/schema 不一致和候选/hash 不守恒均 fail closed。

## 6. 验证

- G14 schema/service tests：12 passed；
- G05—G14 schema/migration/repository/lifecycle/input/recall/eligibility/determinism/performance/pair feature：136 passed；
- G14 service + schema coverage：92%；
- TV/AC、完整/sparse/missing：通过；
- 零销量、零目标价格与安全比值：通过；
- 参数同值/异值/多记录：通过；
- 卖点角色与采购理由多值去重：通过；
- 模块冲突、review 与 lineage：通过；
- 输入顺序等价、受保护事实改变 hash：通过；
- 空 manifest、scope/schema 反例与候选守恒：通过；
- 无数据库、repository、SQLAlchemy 与外部 LLM 依赖：通过；
- Ruff、format check、compileall：通过。

## 7. 状态变化

- 本地数据库写入：无；
- 205 连接、数据库写入和 migration：无；
- 画像 materialize、review/publish/current/deprecated：均未执行；
- G15 购买池、G16 替代、G17 量价压力、G18 正式关系、G19 重点选择：均未实现；
- 部署：无；
- Git 暂存/提交：无。

## 8. 下一 Goal

允许创建 G15，只基于 G14 事实特征实现购买池与主/辅/机会/拖累语义重合判断及 unknown 降级；不得实现采购理由替代、量价压力、七类正式竞品关系、重点选择、画像持久化、205 写入、部署或 Git 提交。
