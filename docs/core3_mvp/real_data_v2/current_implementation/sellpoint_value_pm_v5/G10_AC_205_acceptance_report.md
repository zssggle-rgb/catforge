# V5-G10 AC 扩展与 205 验收报告

验收日期：2026-07-12（Asia/Shanghai）

## 结论

`PASSED — V5 EXTENDED FROM TV TO AC; TV OUTPUT PRESERVED`。

用户卖点价值分析 V5 已从 TV 扩展到 AC，并只读消费 205 当前发布的 AC M12D v0.4。AC 使用自身的参数、宣传主张、评论事实、用户任务、目标人群、价值战场、M12C 量化池和 M12D 采购理由口径；没有套用电视尺寸、画质主题或 TV 价值战场。V5 仍保持显式 `--enable-v5`，默认路由未切换。

## AC 类目补齐内容

1. V4 只读上下文允许 AC，并按类目选择 M03B/M04C/M05C/M09C/M10C/M11C/M12C 的 AC rule/taxonomy version。
2. AC 的“同规格”定义为相同安装形态与匹数档（如 `wall_hp_1_5`），不再要求 `screen_size_inch`。
3. 新增 9 类 AC 用户价值单元：冷暖能力与空间匹配、长期用电成本可控、睡眠静音舒适、柔风不直吹、空气洁净与维护省心、大空间快速覆盖、安装与空间适配、远程控制与操作省事、极端天气与潮湿环境稳定。
4. 直接消费 AC M12D 的 9 个价值主题与 13 个购买理由，形成“价值战场 × 采购理由”的用户价值行，再回溯支撑卖点组合。
5. V5 补齐 11 个 AC 价值战场名称；市场合成的规格协变量改用 AC 安装/匹数档位。
6. AC M12C population 只在 AC 链路中从 `fact_complete_with_comment` 转换为 `claim_value_ready_with_comment`；TV 维持原口径和原 result hash。
7. 飞书报告标题改成业务语言“核心结论”“用户价值与市场表现”，不再使用“产品经理现在能用的结论”等自证式标题。

## 发布数据边界

- AC M12D version：`m12d_ac_purchase_reason_profile_v0_4`
- version id：`m12d_ver_58797b2bb888a566216896d0`
- release status：`published / current`
- published SKU count：155
- M12D result hash：`f4007c13877cc46d36bd16a77b5cec3c6b2f2c51df28b29dbecced723dce70cc`
- 本 Goal 对 M12D 的生成、写入、发布和 current 切换次数均为 0。

## 代表 SKU 结果

SKU：`AC00032338`，格力 `KFR-35GW/(35551)FNHAA-B1`，1.5 匹挂机高价格带。

- analysis state：`ready`
- result hash：`f978f16568933cef5a3f032d26d2ac23c2564734406d4b49b0b91118545b5d4b`
- 7 行“价值战场 × 用户价值组合”
- 亮点：`操作维护省心`
- 用户感知：用户购后反馈显示控制步骤和维护负担更少
- 对照依据：同宣传但用户兑现较弱的产品、同预算产品
- 价格承接：整机价格同池 P75，但不能拆出单组价值金额
- 销量承接：整机销量同池 P88，控制后差异不可识别
- M12C：189 条本品与候选量化/池证据进入上下文
- 严格卖点金额 0、合成销量差 0；没有把整机市场位置写成卖点 WTP
- 已进入 4 个可复核战场；当前没有通过完整门槛的新战场候选

飞书回读报告：[格力 KFR-35GW/(35551)FNHAA-B1 用户感知价值与市场兑现（V5 AC）](https://my.feishu.cn/docx/HDicdEOyAorCplxnanec7mI1nke)，revision 3。

回读确认页面真实包含：

- `一、核心结论`
- `亮点 1：操作维护省心`
- `二、用户价值与市场表现`
- AC 用户价值、卖点组合、相对市场、价格承接、销量承接和结论边界七列表格

## AC cohort 验收

### 4 个已发布代表 SKU 双跑

| SKU | 型号 | 状态 | 价值行 | 亮点 | M12C 行 | 双跑 hash |
| --- | --- | --- | ---: | --- | ---: | --- |
| AC00026378 | KFR-26GW/V1A1 | ready | 5 | 操作维护省心 | 260 | 一致 |
| AC00032338 | KFR-35GW/(35551)FNHAA-B1 | ready | 7 | 操作维护省心 | 189 | 一致 |
| AC00028640 | KFR-72LW/N1A1 | ready | 7 | 操作维护省心 | 281 | 一致 |
| AC00028642 | KFR-35GW/N1A1 | ready | 6 | 操作维护省心 | 72 | 一致 |

4/4 ready、4/4 双跑 hash 一致、0 严格卖点金额、0 合成销量差。

### 12 个跨规格/品牌扩展样本

覆盖 1 匹及以下挂机、1.5 匹挂机、2 匹挂机、3 匹挂机、2 匹柜机、3 匹柜机，以及华凌、美的、格力、小米、长虹。

- 11 ready、1 blocked；blocked SKU 的已发布 M12D 状态为 `weak_expression_only`，不是运行错误
- 5 个 SKU 形成 8 条亮点，7 个 SKU 没有亮点
- 亮点分布：操作维护省心 5 次、安装与空间适配＋预算配置效率 1 次、操作维护省心＋舒适风与健康空气 2 次
- 0 严格卖点金额、0 合成销量差
- 结果没有退化为“所有 SKU 都有相同亮点”

## TV 不变回归

65E7Q 在最终 205 runtime 上重新运行：

- analysis state：`ready`
- result hash：`3bf1668afd39eadd19814e3be40ee16a917deb3ae9c3dc9ec8e7a8f0ba5c2614`，与 V5-G09 完全一致
- 亮点仍为“画质升级感”
- TV M12C 输入口径未因 AC population 修复而改变

## 测试与部署

- V4/V5 相关回归：170 passed
- AC 专项测试：4 passed
- 合计：174 passed
- `ruff check`：passed
- 205 runtime revision：`c06a0a49ab087aa8a3d6335d5f3d15507b0e930f`
- `/readyz`：`{"status":"ready","database":"ok"}`
- 飞书文档 user 身份回读成功，revision 3

## 发布边界

V5 继续 default-off，仅能通过 `sellpoint-value-pm-v5 --enable-v5` 显式运行。本次结果证明 AC 已能形成用户感知价值、卖点组合、反事实参照、整机量价位置和价值战场组合结论；严格 WTP、合成销量差与净新增仍必须逐 SKU 通过样本门槛，未通过时保持不可识别，不补数字。
