# M12D-RP-G04 TV/AC 成立度与用户承接影子测算

- 生成时间：`2026-07-11T17:09:51.179164+00:00`
- 性质：205 当前发布范围只读测算；未写生产表、未改变 current。
- 成立分：只读正向、同锚点证据；普通负面和购买阻力不扣成立分。
- 本任务只填充新 contract；旧角色、SKU 状态、版本质量和竞品结果保持不变。

## TV

- SKU：`377`；锚点：`3542`。
- 成立状态：`{"established": 1178, "established_limited": 636, "proposition_only": 170, "rejected": 1558}`。
- 用户承接：`{"market_supported": 12, "not_observed": 536, "user_supported": 1602, "user_validated": 1392}`。
- 门槛路径（锚点数）：`{"no_core_8": 64, "none": 2139, "reason_specific_7": 161, "standard_9": 1178}`。
- 至少一个 core eligible：`335` SKU；至少一个 proposition：`69` SKU。
- 基线无核心：`139`；其中新增核心资格：`107`；仍无核心资格：`32`。
- 无核心 SKU 的新增门槛路径（锚点数，可同 SKU 多理由并存）：`{"no_core_8": 64, "reason_specific_7": 161, "standard_9": 295}`。
- 评论错配 SKU：`114`。
- 旧结果变化：`0`；G03 pressure 变化：`0`。
- 低于 7 分核心：`0`；proposition 核心：`0`；无来源核心：`0`。
- 未影响回归样本：`20`。

## AC

- SKU：`155`；锚点：`1879`。
- 成立状态：`{"established": 888, "established_limited": 138, "proposition_only": 71, "rejected": 782}`。
- 用户承接：`{"market_supported": 4, "not_observed": 367, "user_supported": 918, "user_validated": 590}`。
- 门槛路径（锚点数）：`{"no_core_8": 3, "none": 978, "reason_specific_7": 10, "standard_9": 888}`。
- 至少一个 core eligible：`143` SKU；至少一个 proposition：`45` SKU。
- 基线无核心：`25`；其中新增核心资格：`14`；仍无核心资格：`11`。
- 无核心 SKU 的新增门槛路径（锚点数，可同 SKU 多理由并存）：`{"no_core_8": 3, "reason_specific_7": 10, "standard_9": 65}`。
- 评论错配 SKU：`30`。
- 旧结果变化：`0`；G03 pressure 变化：`0`。
- 低于 7 分核心：`0`；proposition 核心：`0`；无来源核心：`0`。
- 未影响回归样本：`20`。

## 业务复核

- TV 的 139 个基线无核心 SKU 中，G01 正向审计识别 93 个可成立 SKU；G04 为 107 个，多出的 14 个全部来自 G03 后完整评论维度统计补回的同锚点正向证据，不是降低门槛或白名单。
- 14 个新增 TV SKU：`TV00022396 TCL 55V8M`、`TV00027406 雷鸟 50F295C`、`TV00027699 雷鸟 55F295C`、`TV00027858 海尔 55H5C`、`TV00028087 雷鸟 32F195C`、`TV00028088 雷鸟 43F195C`、`TV00028238 长虹 55D55H`、`TV00028243 酷开 55P3F-J`、`TV00028388 创维 32A3F`、`TV00028389 创维 43A3F`、`TV00028472 创维 40A3F`、`TV00029034 雷鸟 55S78A`、`TV00029167 VIDDA 40VR1Q`、`TV00030337 雷鸟 32F195C-JN`。
- 抽查证据包含明确的“价格实惠/性价比”、高刷或看球流畅、画质正向评论，并同时通过对应价格带、尺寸或场景边界。低于 7 分核心、边界失败核心和无证据引用核心均为 0。
- AC 的 25 个基线无核心 SKU 中，G01 与 G04 均为 14 个获得新核心资格，没有额外扩张。
- TV 的“家庭操作更省心”和“新家家装更适配”仅产品事实/场景时形成 proposition 的 SKU 并集为 27 个；没有自动升级为用户购买理由。
- 海信 65E7Q 的 `same_price_core_config_gain` 为 6 分且缺场景，保持 rejected/core 不可用；`big_screen_cinema_substitution` 因 65 英寸未过 75 英寸边界而不可成为核心。已有画质、体验升级和用户感知理由按同锚点正向证据成立。

## 验收

- 三张 M12D 表前后快照一致：`True`。
- G04 验收：`通过`。
- 未通过项：`[]`。
