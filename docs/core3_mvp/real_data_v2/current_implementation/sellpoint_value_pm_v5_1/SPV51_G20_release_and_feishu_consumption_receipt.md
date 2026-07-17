# SPV51-G20 正式发布与飞书智能体消费回执

状态：completed；TV、AC 已正式发布并切换飞书智能体消费

日期：2026-07-17

## 1. 发布结果

根据用户“明确批准发布，发布后让飞书用户卖点价值智能体消费该画像数据”的授权，已由 `sjs` 在同一受控发布流程中完成 TV、AC 精确版本的 review、publish 和 current 切换。

| 品类 | 正式版本 | 画像数 | 结论分布 | 状态 |
| --- | --- | ---: | --- | --- |
| TV | `37f2ef77-187a-4ee6-b0a7-87708a21856f` | 377 | 282 / 66 / 29 / 0 | published / current / limited |
| AC | `38d86772-cd31-4b0c-bf4c-cccc64de6aee` | 155 | 138 / 6 / 11 / 0 | published / current / limited |

四个数字依次为：有完整结论、部分结论、数据不足无结论、无效。limited 表示部分 SKU 只能给出部分结论或明确返回数据不足，不表示正式版本不可用。

数据库复核结果：

- TV、AC 各只有一个 V5.1 `published + current` 版本；
- 532 款画像及其 40,236 条候选记录、2,167 条价值项记录全部同步为 published/current；
- 两个版本引用的正式竞品画像仍为 published/current，保存哈希与当前竞品画像哈希完全一致；
- 发布前后的版本结果哈希未变化，发布没有重算或覆盖画像。

## 2. 飞书智能体现在如何消费

小奥家电市场分析专家的宽口径“某 SKU 的用户卖点价值是什么”已统一切换为：

`sellpoint-value-pm-v5 --enable-v5`

消费规则：

- 只读取当前品类唯一的正式 V5.1 画像；
- `latest` 只用于定位当前市场上下文，不再错误地要求画像必须保存在同一个原始批次；
- 飞书输入中的“海信65E7Q”可直接匹配“海信 65E7Q”画像；
- 不使用 preview，不现场重建画像，也不回退到旧 `sku-claim-value` 实时分析；
- 有结论时生成业务卡片、报告和深入问答；数据不足时明确返回无结论。

OpenClaw 新会话验收记录：

- session：`f5038a3d-f2be-4470-88c1-4c7cf9419e5e`；
- 实际调用：`sellpoint-value-pm-v5 --query 海信65E7Q --batch-id latest --enable-v5`；
- 没有调用旧 `sku-claim-value`；
- 返回了“保留什么、哪里没转化、竞品配置怎么处理、当前价格是否撑得住、如果要销量、SKU 角色”六部分正式画像结论；
- 完整画像文档：[海信 65E7Q 用户卖点价值分析](https://my.feishu.cn/docx/IDNgdg2I3on3UsxfoHJcpcP2nwB)。

## 3. 真实结果验收

海信 65E7Q：

- 已形成用户价值：明亮环境与明暗层次、影院声场、色彩与画面真实、大屏客厅沉浸、系统与交互效率；
- 尚未转化：游戏与运动流畅；
- 价格支撑：4 组价值组合对照中，本品周均价高 262.1～427.4 元，周均销量仍高 45.6～75.7 台；
- 产品动作：不把降价作为第一动作，优先保护已转化价值并修复游戏与运动流畅体验；
- SKU 角色：继续承担 65 英寸高端画质升级款，不转为低价走量款。

正式深入问答“当前价格为什么撑得住”读取同一画像结果哈希：

`sha256:sellpoint_value_profile_result_v5_1:fdc4720e9f04b58049773be516a7f2a2e7742065d2c02c2c6c1e24966c442b1d`

AC 样例 `AC00039187` 也已通过 `latest` 正式读取，给出价格支撑压力和销量优先时的产品动作。

数据不足样例 `TV00009549` 明确返回：

> 现有数据不足，暂不能形成该 SKU 的用户卖点价值结论。

## 4. 发布中修复的两个消费问题

正式验收发现并修复：

1. 正式画像原来被错误绑定到调用时的原始批次，导致飞书 `latest` 找不到已经发布的画像；现已按项目、品类唯一 current published V5.1 版本读取，preview 仍严格锁批次和版本。
2. 飞书常用的“品牌+型号”连续写法无法匹配带空格的显示名；现已统一规范化查询文本。

对应提交：

- `4d609c8`：跨原始批次解析正式 current 画像；
- `8c4bffb`：支持“海信65E7Q”等品牌型号查询。

专项回归共 44 项通过，同时覆盖 current 唯一性、preview 不跨批次和品牌型号匹配。

## 5. 部署与运行状态

- API：healthz=ok，readyz=ready，容器 healthy，OOM=false，restart=0；
- OpenClaw gateway：running，RPC 正常，配置审计无问题；
- 服务器现有未提交改动未被覆盖；
- 部署备份：`/home/deploy/catforge-deploy-backups/spv51-g20-release-consumption-20260717`；
- 首次发布回退能力保留，未执行回退。

结构化证据：`SPV51_G20_release_and_feishu_consumption_evidence.json`。
