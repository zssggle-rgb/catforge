# AC 标准评论事实维度草案 v0.1

生成日期：2026-06-24

数据来源：205 `/opt/catforge`，`catforge_dev`，`project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`，`batch_id=m00_20260624000202_1150a669`。

主语料：M02 `core3_evidence_atom` 当前有效 AC 评论证据，不直接使用 M01 `core3_clean_comment` 全量留痕表。

## 1. 当前数据口径

M00/M01 评论清洗留痕：

| 口径 | 行数 | 覆盖 SKU | 说明 |
| --- | ---: | ---: | --- |
| M00 `comment_data` 注册 | 1,572,970 | 147 | AC 评论源行，2026-06-24 all-source batch 中为 `no_change` |
| M01 `core3_clean_comment` | 1,572,970 | 147 | 清洗后评论留痕，不等于下游可消费评论事实 |
| M01 `core3_clean_comment_sentence` | 749,326 | 144 | 已排除低价值和纯服务履约后的句子表 |
| M01 `core3_clean_comment_dimension` | 1,572,970 | 147 | 原生评论维度清洗留痕 |

M02 当前有效评论事实主语料：

| 口径 | 当前有效行数 | 覆盖 SKU |
| --- | ---: | ---: |
| `comment_raw` | 65,455 | 144 |
| `comment_sentence` | 159,586 | 144 |
| `comment_dimension` | 65,455 | 144 |

M02 对 M01 评论的主要过滤结果：

| 过滤/候选口径 | 行数 |
| --- | ---: |
| M01 低价值默认评价 | 140,700 |
| M01 服务履约跳过 | 1,167,179 |
| M01 模板样表达近似命中 | 31,906 |
| M01 产品候选行，去重前 | 262,347 |
| 产品候选评论文本去重后 | 65,526 |
| M02 当前有效 `comment_raw` | 65,455 |

说明：

1. M01 `clean_comment=157万` 是源评论清洗留痕，不是后续评论事实画像的有效评论池。
2. 后续标准评论维度设计只以 M02 当前有效评论证据为主语料。
3. 服务履约、默认评价、重复非代表评论和明显模板话术必须隔离，不能作为产品事实支持。
4. 与 TV 方法一致，标准参数和标准卖点只作为品类锚点，不能推出某个 SKU 已被评论支持。

## 2. 维度生成原则

参照 TV 标准评论事实维度的设计方法，AC 评论事实分两层使用。

### 2.1 品类层：生成标准评论维度

品类层输入：

- M02 AC 当前有效 `comment_raw` 与 `comment_sentence`。
- M03B AC 标准参数 taxonomy。
- M04C AC 标准卖点 taxonomy。

品类层只回答：空调评论事实应该从哪些标准维度观察。它不能回答某个 SKU 是否已经被评论验证。

### 2.2 SKU 层：判断本 SKU 是否被评论支持

SKU 层输入：

- 本 SKU 的 M02 评论句子。
- 本 SKU 的 M03B 参数事实画像。
- 本 SKU 的 M04C 卖点事实画像。

SKU 层允许形成以下关系：

| 关系 | 判断口径 |
| --- | --- |
| 参数被评论支持 | SKU 有该参数事实，且本 SKU 评论出现一致体验证据 |
| 参数被评论反证 | SKU 有该参数事实，但本 SKU 评论出现相反体验证据 |
| 参数未被评论提及 | SKU 有该参数事实，但本 SKU 评论没有相关体验证据 |
| 评论提到但参数缺失 | 评论出现明确产品体验，但 SKU 参数画像没有对应参数，进入参数缺口或弱相关复核 |
| 卖点被评论支持 | SKU 有该标准卖点，且本 SKU 评论出现一致体验证据 |
| 卖点被评论反证 | SKU 有该标准卖点，但本 SKU 评论出现相反体验证据 |
| 卖点未被评论提及 | SKU 有该标准卖点，但本 SKU 评论没有相关体验证据 |
| 评论新增产品事实 | 评论出现有价值体验，但 SKU 卖点没有覆盖，作为后续卖点补充候选 |

必须避免把品类标准参数、标准卖点或品牌宣传文本误判为单 SKU 的评论验证事实。

## 3. AC 实际评论覆盖观察

以下统计来自 M02 当前有效 `comment_raw=65,455`。该统计用于判断标准维度是否有真实语料支撑，不等同于最终标签覆盖率；不同维度允许重叠。

### 3.1 原生评论维度分布

| 原生一级维度 | 原生二级维度 | 有效评论行 | 覆盖 SKU |
| --- | --- | ---: | ---: |
| 营销服务 | 产品体验 | 17,682 | 143 |
| 产品质量 | 冷暖效果 | 7,666 | 136 |
| 产品质量 | 使用体验 | 7,432 | 140 |
| 产品设计 | 外观设计 | 6,661 | 132 |
| 送装维保 | 客服服务 | 6,201 | 137 |
| 营销服务 | 产品价格 | 5,341 | 136 |
| 送装维保 | 安装服务 | 4,207 | 132 |
| 产品质量 | 产品性能 | 3,304 | 127 |
| 产品设计 | 产品交互 | 1,989 | 117 |
| 送装维保 | 物流配送 | 1,702 | 124 |
| 空维度 | 空维度 | 1,226 | 114 |
| 送装维保 | 售后维保 | 1,172 | 118 |
| 营销服务 | 营销活动 | 872 | 98 |

原生维度中仍有服务履约和营销服务残留。标准评论 taxonomy 应将产品体验、价格价值、人群/用途/品牌线索和服务履约隔离开。

### 3.2 关键词覆盖

| 候选标准维度 | 命中评论行 | 覆盖 SKU | 观察 |
| --- | ---: | ---: | --- |
| 冷暖效果 | 20,578 | 141 | AC 评论主轴，覆盖制冷、制热、降温升温、冷暖效果 |
| 速度响应 | 10,515 | 138 | 与冷暖效果重叠，突出速冷速热、开机后见效速度 |
| 能效电费 | 8,767 | 136 | 包含省电、节能、电费、一级能效、长期成本 |
| 送风舒适 | 4,378 | 130 | 包含风量、出风、柔风、直吹、扫风、风感 |
| 静音睡眠 | 15,553 | 139 | 声音、噪音、安静、卧室、睡眠高频 |
| 健康洁净空气 | 1,026 | 102 | 新风、自清洁、净化、除菌、抗菌、防霉等 |
| 除湿控湿 | 255 | 79 | 量小但为空调独立场景，应保留 |
| 智控交互 | 4,119 | 124 | APP、语音、遥控、WiFi、远程、智能生态 |
| 外观空间安装形态 | 17,181 | 139 | 外观、颜值、尺寸、挂机/柜机、安装位置、占地 |
| 质量稳定风险 | 8,252 | 141 | 质量、故障、漏水、异响、压缩机、铜管、耐用 |
| 价格价值 | 19,279 | 143 | 价格、性价比、优惠、补贴、划算、贵/便宜 |
| 人群线索 | 1,719 | 123 | 老人、孩子、宝宝、父母、家人 |
| 用途场景 | 3,356 | 129 | 卧室、客厅、租房、办公室、房间面积 |
| 品牌/竞品线索 | 13,183 | 139 | 格力、美的、海尔、小米、奥克斯、TCL、对比、替换 |

### 3.3 评论样本观察

有效评论中高频出现以下真实表达类型：

- 制冷制热：`制冷效果好`、`升温快`、`开机一会儿房间温度就降下来了`。
- 能效电费：`新一级能效`、`省电节能`、`ECO 模式夜间耗电低`。
- 舒适送风：`出风柔和`、`不会直吹`、`风量足`。
- 静音睡眠：`声音很小`、`放卧室安静`、`睡觉不被打扰`。
- 健康清洁：`自清洁功能省心`、`抗菌滤网`、`空气杀菌`。
- 智能控制：`手机远程控制`、`米家智能`、`语音控制`。
- 外观空间：`外观漂亮`、`挂机不突兀`、`外机位置远需要延长铜管`。
- 质量风险：`希望耐用`、`漏水/异响/故障`、`质量如何还有待考证`。
- 价格价值：`以旧换新价划算`、`买完降价`、`性价比高`。
- 人群用途：`给父母买`、`卧室使用`、`客厅大空间`、`租房党`。
- 品牌竞品：`再次选择海尔`、`格力值得信赖`、`比原来的品牌效果强`。

样本中也存在类卖点稿或平台营销式长句。该类内容应进入模板/营销文案复核，不应直接提高评论验证强度。

## 4. 标准参数锚点

M03B AC 标准参数应作为评论事实维度的品类锚点：

| 参数组 | 关键标准参数 | 对评论维度的作用 |
| --- | --- | --- |
| 基础规格 | `horsepower_hp`、`product_type_combo`、`installation_type` | 支撑匹数、挂机/柜机/移动空调、房间面积和空间适配 |
| 冷暖能力 | `cooling_capacity_w`、`heating_capacity_w`、`heat_cool_mode` | 支撑制冷制热效果、速冷速热、冷暖模式验证 |
| 能效 | `energy_grade_normalized`、`energy_efficiency_ratio`、`inverter_flag` | 支撑一级能效、APF、省电、电费体验 |
| 送风 | `airflow_volume_m3h`、`comfort_airflow_flag` | 支撑风量、覆盖、柔风、防直吹、舒适风 |
| 健康清洁 | `fresh_air_flag`、`purification_flag`、`self_cleaning_flag` | 支撑新风、净化除菌、自清洁体验 |
| 智能 | `wifi_control_flag`、`voice_control_flag`、`smart_sensing_flag` | 支撑 APP、语音、远程、智能感应体验 |
| 外观空间 | `indoor_unit_dimensions_mm`、`product_type_combo`、`installation_type` | 支撑尺寸、占地、安装形态、空间适配 |
| 耐用品质 | `refrigerant_type` | 只能弱支撑冷媒相关表达；压缩机、铜管、噪音、控温精度等参数仍缺口明显 |
| 品牌身份 | `brand_name_standard`、`model_name`、`sku_code` | 支撑品牌信任、复购、竞品提及和替换来源识别 |

参数缺口建议：

- `indoor_noise_min_db`、`sleep_mode_flag`
- `temperature_control_precision_c`
- `operation_temperature_min_c`、`operation_temperature_max_c`
- `dehumidification_flag`、`humidity_control_flag`
- `fresh_air_volume_m3h`
- `compressor_type`、`copper_pipe_flag`、`condenser_material`
- `warranty_years`、`installation_fee_policy`

## 5. 标准卖点锚点

M04C AC 标准卖点可作为评论事实维度的锚点：

| 卖点维度 | 标准卖点 | 评论事实观察 |
| --- | --- | --- |
| `energy_efficiency` | `ac_claim_energy_efficiency_apf`、`ac_claim_ai_energy_saving` | 评论应观察是否省电、电费是否低、能效是否被真实体验认可 |
| `temperature_performance` | `ac_claim_fast_cooling_heating`、`ac_claim_wide_temperature_operation` | 评论应观察制冷制热效果、速度、极冷极热环境稳定性 |
| `airflow_comfort` | `ac_claim_large_airflow_coverage`、`ac_claim_soft_wind_no_direct`、`ac_claim_quiet_sleep`、`ac_claim_precision_temperature_control` | 评论应观察风量覆盖、柔风不直吹、静音睡眠、恒温控温 |
| `health_clean_air` | `ac_claim_humidity_dehumidification`、`ac_claim_fresh_air`、`ac_claim_purification_antibacterial`、`ac_claim_self_cleaning` | 评论应观察除湿、新风、净化除菌、自清洁是否被实际体验提及 |
| `smart_control` | `ac_claim_smart_app_voice_iot` | 评论应观察 APP、语音、遥控、远程、智能生态是否好用 |
| `installation_design` | `ac_claim_installation_space_design` | 评论应观察外观、空间占用、挂机/柜机适配、安装位置约束 |
| `durability_quality` | `ac_claim_durability_core_material` | 评论应观察质量、耐用、压缩机、铜管、漏水漏氟、异响等风险 |
| `price_value` | `ac_claim_price_value_subsidy` | 评论应观察价格、补贴、划算、降价、同价位感知 |
| `authority` | `ac_claim_authority_sales_certification` | 只作为背书线索，不直接证明产品体验 |
| `service_fulfillment` | `ac_claim_warranty_install_service` | 服务履约隔离，不进入产品评论事实画像 |

## 6. AC 首版标准评论事实维度

### 6.1 冷暖效果与温度响应

定义：用户对空调制冷、制热、降温升温速度、温度稳定性和极端环境可用性的直接体验。

二级维度：

- 制冷效果：制冷、凉快、降温、冷气足、冷得快。
- 制热效果：制热、暖和、升温、热风、冬天使用。
- 速冷速热：速冷、速热、开机几分钟见效、很快凉/很快热。
- 温度稳定：恒温、温控准、不会忽冷忽热、自动模式过冷/过热。
- 极端环境：高温制冷、低温制热、外机环境、宽温域。

标准参数锚点：`cooling_capacity_w`、`heating_capacity_w`、`horsepower_hp`、`heat_cool_mode`、`inverter_flag`。

标准卖点锚点：`ac_claim_fast_cooling_heating`、`ac_claim_wide_temperature_operation`、`ac_claim_precision_temperature_control`。

后续用途：支撑冷暖性能战场、卧室/客厅/大空间任务、速冷速热卖点验证和反证。

### 6.2 能效、电费与长期使用成本

定义：用户对省电、能效等级、APF、ECO 模式、电费和长期成本的体验判断。

二级维度：

- 一级能效/APF：新一级能效、APF、能效比。
- 省电体验：省电、节能、耗电低、ECO 模式。
- 电费成本：一晚几度电、每月电费、长期成本。
- 省电反证：不省电、耗电、能效感知不明显。

标准参数锚点：`energy_grade_normalized`、`energy_efficiency_ratio`、`inverter_flag`。

标准卖点锚点：`ac_claim_energy_efficiency_apf`、`ac_claim_ai_energy_saving`、`ac_claim_price_value_subsidy`。

后续用途：支撑能效价值战场、长期持有成本分析、AI 省电卖点验证。

### 6.3 送风舒适与覆盖

定义：用户对风量、送风范围、柔风、防直吹、风感和全屋覆盖的体验。

二级维度：

- 风量覆盖：风量大、循环风量、全屋覆盖、客厅/大空间够用。
- 出风均匀：出风、扫风、上下/左右送风、角落覆盖。
- 柔风不直吹：柔风、无风感、不直吹、防冷风、风感舒服。
- 风感负向：风太硬、吹得头疼、风小、风不均匀。

标准参数锚点：`airflow_volume_m3h`、`comfort_airflow_flag`、`installation_type`、`horsepower_hp`。

标准卖点锚点：`ac_claim_large_airflow_coverage`、`ac_claim_soft_wind_no_direct`。

后续用途：支撑舒适风战场、老人儿童客群、防直吹卖点验证。

### 6.4 静音与睡眠体验

定义：用户对运行声音、卧室夜间使用、睡眠模式和噪音干扰的体验。

二级维度：

- 静音正向：声音小、安静、低噪、不吵。
- 睡眠场景：卧室、夜间、睡觉、不影响休息、睡眠模式。
- 噪音风险：噪音大、异响、外机响、夜里吵。

标准参数锚点：当前缺 `indoor_noise_min_db`；可弱关联 `inverter_flag`、`installation_type`。

标准卖点锚点：`ac_claim_quiet_sleep`、`ac_claim_soft_wind_no_direct`。

后续用途：支撑卧室睡眠任务、静音舒适战场、噪音风险复核。

### 6.5 健康洁净空气

定义：用户对新风、净化、除菌、抗菌、防霉、自清洁、异味和空气清新感的体验。

二级维度：

- 自清洁/自洁：自清洁、省心、内机自洁、56°C、高温清洁。
- 净化除菌：净化、杀菌、除菌、抗菌、防霉、PM2.5、空气杀菌。
- 新风换气：新风、换气、鲜氧、空气流通。
- 异味/霉味：异味、霉味、吹出来味道、空气不清新。

标准参数锚点：`fresh_air_flag`、`purification_flag`、`self_cleaning_flag`。

标准卖点锚点：`ac_claim_self_cleaning`、`ac_claim_purification_antibacterial`、`ac_claim_fresh_air`。

后续用途：支撑健康空气战场、母婴/老人/鼻炎等人群线索、健康卖点验证。

### 6.6 除湿与湿度控制

定义：用户对除湿、防潮、干爽、梅雨季和温湿双控的体验。

二级维度：

- 独立除湿：除湿、抽湿、独立除湿。
- 潮湿环境：潮湿、梅雨、回南天、防潮。
- 舒适湿度：干爽、不闷、湿度控制。
- 除湿反证：太干、除湿弱、湿度不舒服。

标准参数锚点：当前缺 `dehumidification_flag`、`humidity_control_flag`。

标准卖点锚点：`ac_claim_humidity_dehumidification`。

后续用途：支撑南方潮湿场景、健康舒适战场、参数缺口补充。

### 6.7 智控交互体验

定义：用户对 APP、语音、遥控、WiFi、远程控制、智能生态和自动模式的操作体验。

二级维度：

- APP/远程：手机 APP、远程开关、WiFi、联网。
- 语音/生态：语音控制、小爱、米家、智能家居。
- 遥控/面板：遥控器、操作简单、老人易用。
- 自动模式/智能感应：自动模式、AI、智能调节、人感。
- 交互反证：连接失败、APP 难用、遥控不灵、自动模式不舒服。

标准参数锚点：`wifi_control_flag`、`voice_control_flag`、`smart_sensing_flag`。

标准卖点锚点：`ac_claim_smart_app_voice_iot`、`ac_claim_ai_energy_saving`。

后续用途：支撑智能控制战场、老人易用任务、IoT 生态卖点验证。

### 6.8 外观、安装形态与空间适配

定义：用户对外观颜值、挂机/柜机/移动空调形态、尺寸、占地、安装位置和房间面积适配的评价。

二级维度：

- 外观颜值：外观、好看、颜值、颜色、质感。
- 安装形态：挂机、柜机、移动空调、外机、铜管、打孔。
- 空间占用：占地、体积、尺寸、挂墙位置、外机位置。
- 面积适配：11 平、25 平、客厅、卧室、够用/不够用。
- 安装约束：延长铜管、高空作业、支架、孔位、位置远。

标准参数锚点：`installation_type`、`indoor_unit_dimensions_mm`、`product_type_combo`、`horsepower_hp`。

标准卖点锚点：`ac_claim_installation_space_design`、`ac_claim_large_airflow_coverage`。

后续用途：支撑空间适配任务、柜机/挂机竞品池、安装约束复核。纯服务态度不进入产品事实。

### 6.9 质量稳定性与产品风险

定义：用户对质量、耐用、故障、漏水漏氟、异响、压缩机、铜管、做工和售后前置风险的反馈。

二级维度：

- 耐用品质：耐用、质量好、做工扎实、真材实料。
- 核心部件：压缩机、铜管、冷媒、外机、内机。
- 故障风险：坏、故障、漏水、漏氟、异响、不制冷、不制热。
- 质量不确定：刚买待观察、希望耐用、质量待考证。

标准参数锚点：`refrigerant_type`；建议补 `compressor_type`、`copper_pipe_flag`、`condenser_material`。

标准卖点锚点：`ac_claim_durability_core_material`。

后续用途：支撑质量风险复核、卖点反证、售后风险预警。

### 6.10 价格、补贴与价值感知

定义：用户对价格、性价比、优惠、国补、以旧换新、降价和同价位价值的判断。

二级维度：

- 性价比正向：性价比高、划算、值得、实惠。
- 价格负向：贵、降价、买亏、差价、坑。
- 补贴优惠：国补、以旧换新、券、活动、百亿补贴。
- 同价位判断：同价位、平台比价、配置对得起价格。

标准参数锚点：无直接硬参数；应结合 M07 价格带、销量和市场位置。

标准卖点锚点：`ac_claim_price_value_subsidy`、`ac_claim_energy_efficiency_apf`。

后续用途：支撑价格价值战场、性价比客群、同价位竞品分析。

### 6.11 人群线索

定义：评论中明确出现使用者、购买对象或家庭成员线索。该维度只保留事实，不直接生成最终目标客群。

二级维度：

- 老人/父母：老人、父母、爸妈、老人家。
- 孩子/宝宝：孩子、小孩、宝宝、母婴、防直吹。
- 家庭/全家：家人、一家人、全家、父母孩子。
- 租房/年轻用户：租房党、宿舍、年轻人、单间。
- 特殊敏感人群：鼻炎、怕冷、怕直吹、睡眠不好。

标准参数锚点：无直接硬参数；间接关联静音、柔风、健康空气、易操作、能效和价格。

标准卖点锚点：`ac_claim_soft_wind_no_direct`、`ac_claim_quiet_sleep`、`ac_claim_purification_antibacterial`、`ac_claim_smart_app_voice_iot`、`ac_claim_price_value_subsidy`。

后续用途：作为 M10 目标客群生成输入，不直接输出最终客群结论。

### 6.12 用途与使用场景线索

定义：评论中明确出现的房间、用途、环境和任务场景。该维度只保留事实，不直接生成最终用户任务。

二级维度：

- 卧室睡眠：卧室、睡觉、夜间、小房间。
- 客厅大空间：客厅、大空间、全屋、3P、柜机。
- 租房/宿舍：租房、宿舍、移动空调、安装简单。
- 办公/门店：办公室、店里、商用、小店。
- 南方潮湿：除湿、防潮、梅雨、回南天。
- 冬夏冷暖：夏天降温、冬天制热、冷暖两用。

标准参数锚点：`horsepower_hp`、`installation_type`、`airflow_volume_m3h`、`cooling_capacity_w`、`heating_capacity_w`。

标准卖点锚点：`ac_claim_fast_cooling_heating`、`ac_claim_large_airflow_coverage`、`ac_claim_quiet_sleep`、`ac_claim_humidity_dehumidification`。

后续用途：作为 M09 用户任务生成输入，不直接输出最终任务结论。

### 6.13 品牌力与复购推荐

定义：评论中出现品牌信任、复购、推荐、长期使用和品牌口碑表达。

二级维度：

- 品牌信任：大品牌、值得信赖、老牌子、放心。
- 复购/长期使用：家里一直用、再次选择、买了多台。
- 口碑推荐：朋友推荐、家人推荐、网上口碑。
- 品牌情绪：喜欢某品牌、不再买某品牌。

标准参数锚点：`brand_name_standard`、`model_name`。

标准卖点锚点：无固定产品卖点；具体能力需同时落到冷暖、能效、静音、质量等维度。

后续用途：支撑品牌力画像、复购分析、口碑推荐分析。

### 6.14 竞品比较与替换来源

定义：评论中出现跨品牌、跨型号、旧机替换、平台比价或明确对比表达。

二级维度：

- 跨品牌对比：比格力/美的/海尔/小米/奥克斯等更好或更差。
- 旧机替换：原来用某品牌，现在换新。
- 同价位比较：同价位、平台价格比较、配置比较。
- 能力对比：制冷更快、省电更好、声音更小、价格更划算。

标准参数锚点：`brand_name_standard`、`model_name`、M07 市场价格带。

标准卖点锚点：按具体比较能力映射到对应 AC 标准卖点。

后续用途：支撑竞品池、替换来源分析、同价位对比证据。

### 6.15 服务履约隔离维度

定义：物流、配送、安装师傅、客服、售后、包修、上门、退换货、发货速度等服务履约内容。

处理原则：

1. 不进入产品评论事实画像。
2. 不用于支持参数、卖点、用户任务、目标客群或价值战场。
3. 可保留在清洗质量审计或独立服务履约分析里。
4. 若一句话同时包含服务和产品事实，应拆句后只保留产品事实句。

标准卖点锚点：`ac_claim_warranty_install_service` 仅作为服务履约隔离锚点，不作为产品事实支撑。

### 6.16 模板/营销文案复核维度

定义：评论中出现疑似卖点稿、平台营销稿、批量模板化长句或过度结构化宣传表达。

处理原则：

1. 进入评论质量复核，不直接提升评论验证强度。
2. 若其中包含真实用户体验句，可拆句后保留产品事实；否则降权。
3. 对同一 SKU 高重复模板应走重复代表评论逻辑。

后续用途：减少 M05C LLM 把宣传话术当成真实用户体验事实的风险。

## 7. 首版标准评论维度清单

建议发布 AC M05C 首版 taxonomy：

| dimension_code | 中文名 | dimension_type | 下游策略 |
| --- | --- | --- | --- |
| `temperature_effect_experience` | 冷暖效果与温度响应 | `product_experience` | 参数/卖点支持与反证 |
| `energy_cost_experience` | 能效、电费与长期使用成本 | `product_experience` | 能效卖点验证、价值战场 |
| `airflow_comfort_experience` | 送风舒适与覆盖 | `product_experience` | 舒适风卖点验证 |
| `noise_sleep_experience` | 静音与睡眠体验 | `product_experience` | 卧室睡眠任务、噪音风险 |
| `health_clean_air_experience` | 健康洁净空气 | `product_experience` | 健康清洁卖点验证 |
| `humidity_control_experience` | 除湿与湿度控制 | `product_experience` | 潮湿场景、参数缺口 |
| `smart_control_experience` | 智控交互体验 | `product_experience` | 智控卖点验证 |
| `appearance_installation_space` | 外观、安装形态与空间适配 | `product_experience` | 空间适配和安装约束 |
| `quality_reliability_risk` | 质量稳定性与产品风险 | `product_risk` | 风险复核和卖点反证 |
| `price_value_perception` | 价格、补贴与价值感知 | `price_value` | 价格价值战场 |
| `audience_signal` | 人群线索 | `audience_signal` | M10 输入，不直接成结论 |
| `use_case_signal` | 用途与使用场景线索 | `use_case_signal` | M09 输入，不直接成结论 |
| `brand_power_signal` | 品牌力与复购推荐 | `brand_power_signal` | 品牌力画像 |
| `competitor_comparison_signal` | 竞品比较与替换来源 | `competitor_comparison_signal` | 竞品池和替换来源 |
| `service_fulfillment_excluded` | 服务履约隔离维度 | `service_fulfillment_excluded` | 不进入产品事实 |
| `template_campaign_review` | 模板/营销文案复核维度 | `quality_review` | 降权或复核 |

## 8. 后续程序化输出建议

标准维度确认后，应新增 AC M05C taxonomy 和规则版本：

- taxonomy version：`ac_comment_fact_taxonomy_manual_v0.1`
- rule version：`m05c_ac_comment_fact_profile_v0.1`

建议句级处理流程：

1. 以 M02 `comment_sentence` 为最小单元。
2. 规则先识别冷暖、能效、风感、静音、健康、智控、价格、人群、场景、品牌和竞品关键词。
3. 对多维句、冲突句、模板样长句使用 LLM 批处理，每批 30-80 句，输出结构化 JSON。
4. 每个句子可输出多个评论事实原子。
5. 再按 SKU 聚合成 SKU 评论事实画像。

建议句级输出字段：

```text
sku_code
sentence_evidence_id
comment_dimension_code
comment_subdimension_code
polarity
evidence_strength
audience_signal
use_case_signal
price_value_signal
brand_power_signal
competitor_comparison_signal
linked_sku_param_codes
linked_sku_claim_codes
support_relation
confidence
quality_flags
evidence_text
```

建议 SKU 级聚合字段：

```text
sku_code
comment_fact_profile
supported_param_codes
contradicted_param_codes
unmentioned_param_codes
comment_only_param_candidates
supported_claim_codes
contradicted_claim_codes
unmentioned_claim_codes
comment_only_claim_candidates
audience_signals
use_case_signals
price_value_signals
brand_power_signals
competitor_comparison_signals
risk_signals
service_excluded_summary
template_review_summary
review_required
evidence_ids
```

## 9. 实施注意事项

1. AC 不复用 TV 的画质、音响、游戏、HDMI、投屏等电视标准评论维度。
2. AC 的服务履约量很大，M05C 必须继续隔离安装、配送、客服、售后、包修。
3. AC 有较多品牌和竞品提及，必须区分品牌信任/复购和真正跨品牌对比。
4. 能效、电费、价格、补贴高度重叠；事实层先拆开，价值判断延后给市场和战场模块。
5. 静音、控温精度、除湿、宽温域、压缩机/铜管等参数缺口不能被评论或卖点自动补成参数事实。
6. 模板样长评论应降权或进入复核，避免把宣传卖点稿当用户体验事实。
