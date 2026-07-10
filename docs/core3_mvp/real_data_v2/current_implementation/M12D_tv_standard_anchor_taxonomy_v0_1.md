# M12D TV 标准价值主题与购买理由 taxonomy v0.1

日期：2026-07-08

本文件是 M12D-G04R2 的人审标准产物，用来说明 TV 品类第一版两层 taxonomy 是什么、为什么这么划分、运行时程序如何消费它。

## 1. 标准定位

TV taxonomy 不是运行时程序自动生成的结果，而是 Codex/业务基于以下输入提炼、再固化为版本化 config：

- 评论事实、参数画像、卖点事实、市场画像。
- M09C 用户任务、M10C 目标客群、M11C 价值战场。
- M11D 语义市场图谱、M12C 用户卖点支付价值。
- M12D-G01 样本审计、G04R1 候选提炼报告和弱表达边界。

G04R2 将旧的单层“标准锚点族”拆成两层：

| 层级 | 回答的问题 | 是否进入 G05 角色判定 |
| --- | --- | --- |
| 标准价值主题 | 用户获得什么可感知价值 | 否，只做解释维度和证据归因 |
| 标准购买理由 | 用户为什么选择这个 SKU | 是，进入证据强度和角色判定 |

运行时程序只读取本标准并匹配 SKU 证据，不负责创造标准锚点族。后续 G07 小批量验证可基于真实 SKU 结果修订标准版本。

## 2. 版本边界

| 字段 | 值 |
| --- | --- |
| taxonomy_version | `m12d_tv_purchase_reason_anchor_taxonomy_v0.1` |
| product_category | `TV` |
| product_category_label_cn | 彩电 |
| 代码配置 | `apps/api-server/app/services/core3_real_data/purchase_reason_anchor_taxonomy.py` |
| 读取器 | `M12DAnchorTaxonomyLoader` |
| 候选生成器 | `AnchorCandidateGenerator` |

TV 与空调、冰箱、洗衣机等品类不得复用同一套标准 taxonomy。其他品类需要独立读取对应品类的评论、参数、卖点、任务、客群和战场后再提炼。

## 3. 标准价值主题

| 排序 | value_theme_code | 中文名 | 定义 |
| ---: | --- | --- | --- |
| 10 | `picture_upgrade_perception` | 画质升级感 | 用户能感知到画面清晰度、亮度、控光、色彩或显示技术升级。 |
| 20 | `dynamic_stability_perception` | 动态画面稳定感 | 游戏、体育、运动画面中流畅、低延迟、少拖影的体验获得感。 |
| 30 | `living_room_immersion_perception` | 客厅沉浸感 | 大屏、音效、杜比、观影距离与客厅空间共同形成的沉浸感。 |
| 40 | `budget_configuration_efficiency` | 预算配置效率 | 在给定预算和尺寸池里，用户获得核心配置、价格和销量承接的效率。 |
| 50 | `long_watch_comfort_perception` | 长看舒适感 | 护眼、低蓝光、无频闪、抗反光和家庭长时间观看形成的舒适安心。 |
| 60 | `operation_convenience_perception` | 操作便利感 | AI、语音、投屏、IoT、系统易用带来的家庭使用便利。 |
| 70 | `space_aesthetic_fit` | 空间审美适配 | 外观、超薄、贴墙、全面屏、壁画和新家装修的空间适配价值。 |

## 4. 标准购买理由

| 排序 | purchase_reason_code | 中文名 | 对应价值主题 |
| ---: | --- | --- | --- |
| 10 | `picture_upgrade_justifies_price` | 画质配置解释加价 | picture_upgrade_perception |
| 20 | `low_price_core_experience_intact` | 低价不明显牺牲核心体验 | budget_configuration_efficiency, picture_upgrade_perception, operation_convenience_perception |
| 30 | `same_price_core_config_gain` | 同价位核心配置获得感 | budget_configuration_efficiency, picture_upgrade_perception, dynamic_stability_perception |
| 40 | `same_size_picture_step_up` | 同尺寸画质越级获得感 | picture_upgrade_perception, budget_configuration_efficiency |
| 50 | `worth_paying_more_for_experience_upgrade` | 贵得值的体验升级 | picture_upgrade_perception, dynamic_stability_perception, living_room_immersion_perception |
| 60 | `av_user_willing_to_pay_for_picture` | 影音用户愿为画质升级付费 | picture_upgrade_perception, living_room_immersion_perception |
| 70 | `gaming_device_fit_reduces_risk` | 游戏设备适配降低踩坑风险 | dynamic_stability_perception |
| 80 | `sports_motion_stability` | 体育/运动画面流畅更稳 | dynamic_stability_perception |
| 90 | `big_screen_cinema_substitution` | 大屏影音替代影院感 | living_room_immersion_perception, picture_upgrade_perception |
| 100 | `living_room_upgrade_one_step` | 客厅换新一步到位 | living_room_immersion_perception, picture_upgrade_perception |
| 110 | `family_long_watch_comfort_assurance` | 家庭长时间观看更安心 | long_watch_comfort_perception |
| 120 | `family_operation_less_friction` | 家庭多设备使用更省操作 | operation_convenience_perception |
| 130 | `new_home_aesthetic_fit` | 新家客厅审美适配 | space_aesthetic_fit |

## 5. 候选生成原则

`AnchorCandidateGenerator.generate()` 输出 `M12DAnchorCandidateSet`：

- `value_theme_candidates`：价值主题候选，只解释用户获得的价值类型。
- `purchase_reason_candidates`：购买理由候选，后续 G05 只消费这一层做证据强度和角色判定。

候选生成只回答四个问题：

1. 这个 SKU 是否命中了某个标准价值主题。
2. 这个 SKU 是否具备某个标准购买理由的候选证据组合。
3. 命中来自哪些上游模块和证据域。
4. 是否存在只能封顶为弱表达的候选。

候选生成不直接输出 `core_payment`、`supporting`、`weak_expression` 或 `risk_drag` 的最终结论。最终角色由 G05 在购买理由候选基础上结合证据强度、冲突、缺失和置信度判定。

## 6. 关键门槛

| 规则 | 说明 |
| --- | --- |
| 价值主题不等于购买理由 | `picture_upgrade_perception` 只能说明画质升级感存在，不能直接输出成交理由。 |
| 购买理由必须过候选门槛 | 例如 `worth_paying_more_for_experience_upgrade` 必须同时具备价格位置、体验证据和评论/M12C/市场承接。 |
| 弱表达封顶 | `value_price`、`price_value`、`tv_claim_value_price` 等只有厂家表达或位置标签时，只能生成弱表达候选。 |
| 品类隔离 | TV taxonomy 不得用于空调、冰箱、洗衣机。 |

## 7. 后续修订规则

G07 小批量验证后，如果发现主题/理由过宽、过窄、误命中或漏命中，应新增 taxonomy 版本，而不是覆盖历史版本。修订时必须记录：

- 修订原因。
- 受影响 value_theme_code 或 purchase_reason_code。
- 受影响 SKU 样本。
- 新旧版本的匹配差异。
