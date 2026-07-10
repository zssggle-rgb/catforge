# TV 标准购买理由 v0.1 草案

生成时间 UTC：2026-07-08T07:54:50.113439+00:00

本草案来自 M12D-G04R1 候选提炼报告，尚需业务审核。购买理由必须是选择逻辑型解释，回答为什么选择这个 SKU，而不是只描述价值方向。

| purchase_reason_code | 中文名 | 对应价值主题 | 成立逻辑 | 弱表达边界 | 审阅状态 |
| --- | --- | --- | --- | --- | --- |
| `picture_upgrade_justifies_price` | 画质配置解释加价 | picture_upgrade_perception | 需要画质事实证据 + 用户感知或 M12C 支付价值 + 价格/市场位置。 | 只有“高端画质”口号或单一 claim 时不能成立。 | draft_accept |
| `low_price_core_experience_intact` | 低价不明显牺牲核心体验 | budget_configuration_efficiency, picture_upgrade_perception, operation_convenience_perception | 需要低/中低价格位置 + 至少一个核心体验证据；销量或评论正向可强化。 | 只有低价、补贴或促销表达时，不进入产品购买理由。 | draft_accept |
| `same_price_core_config_gain` | 同价位核心配置获得感 | budget_configuration_efficiency, picture_upgrade_perception, dynamic_stability_perception | 需要价格/市场证据 + 配置事实或评论价值感；厂家性价比表达只能弱支撑。 | 只有 value_price/price_value 时封顶弱表达。 | draft_accept |
| `same_size_picture_step_up` | 同尺寸画质越级获得感 | picture_upgrade_perception, budget_configuration_efficiency | 需要同尺寸/价格池参照 + 画质事实证据；评论或 M12C 可作为强化。 | 只有 MiniLED/画质口号但没有同尺寸参照或体验证据时，只能弱支撑。 | draft_accept |
| `worth_paying_more_for_experience_upgrade` | 贵得值的体验升级 | picture_upgrade_perception, dynamic_stability_perception, living_room_immersion_perception | 需要中高/高价格位置 + 至少一个可感知强体验证据 + 评论、M12C 或市场承接；若反馈反向则转为价格压力。 | 只有高端口号、品牌溢价或参数堆叠，用户感知不到升级时，不能作为正向购买理由。 | draft_accept |
| `av_user_willing_to_pay_for_picture` | 影音用户愿为画质升级付费 | picture_upgrade_perception, living_room_immersion_perception | 需要画质事实 + 观影/影音任务或评论 + M12C 正向支付价值。 | 只有影音/影院宣传语，缺少画质事实或 M12C 时不能强判。 | draft_accept |
| `gaming_device_fit_reduces_risk` | 游戏设备适配降低踩坑风险 | dynamic_stability_perception | 需要高刷/接口/低延迟事实证据 + 游戏任务或评论感知。 | 只有“游戏电视”表达时不能成立。 | draft_accept |
| `sports_motion_stability` | 体育/运动画面流畅更稳 | dynamic_stability_perception | 需要刷新率/MEMC/高刷事实 + 体育或运动评论/任务支撑。 | 只有高刷口号，没有体育/运动场景证据时不能强判。 | draft_accept |
| `big_screen_cinema_substitution` | 大屏影音替代影院感 | living_room_immersion_perception, picture_upgrade_perception | 需要大屏/音画事实 + 观影评论或影院沉浸任务；市场同尺寸承接可强化。 | 只有“影院级/沉浸感”宣传语，没有音画事实或评论时不能成立。 | draft_accept |
| `living_room_upgrade_one_step` | 客厅换新一步到位 | living_room_immersion_perception, picture_upgrade_perception | 需要尺寸/观影事实 + 用户任务或评论感知 + 市场承接。 | 只有屏幕尺寸数字，不足以成为购买理由。 | draft_accept |
| `family_long_watch_comfort_assurance` | 家庭长时间观看更安心 | long_watch_comfort_perception | 需要护眼参数或认证 + 评论/任务支撑；泛健康口号不足。 | 只有健康宣传或认证口号时不能强判。 | review |
| `family_operation_less_friction` | 家庭多设备使用更省操作 | operation_convenience_perception | 需要智能/互联事实证据 + 任务或评论易用感知。 | 只有 AI 或智能口号时只能弱支撑。 | review |
| `new_home_aesthetic_fit` | 新家客厅审美适配 | space_aesthetic_fit | 需要外观/安装事实 + 新家/家装任务或评论支撑。 | 只有外观好看表达时不能直接成为核心购买理由。 | review |

审核规则：购买理由必须具备用户任务/场景、价格或竞品取舍、SKU 证据组合和弱表达边界。
