# SPV52-G03 分层映射与分类回执

状态：completed

日期：2026-07-18

## 1. 实现内容

新增确定性 `LayeredSellpointMapper`：

- M04C 原始卖点到 M03B 参数链接；
- 原始卖点到 V5.1 已保存用户价值链接；
- 内部价值主题独立保存；
- 本品卖点四分类；
- 产品参数五分类；
- table-stake 卖点/参数分流；
- 竞品卖点机会与纯参数差异分离；
- layer integrity 计数与 result hash。

## 2. 已验证业务边界

- “游戏影音双丝滑”只能作为原文连续子串出现；
- “游戏与运动流畅”只进入 internal value theme；
- 170Hz、300Hz、HDMI 2.1、48Gbps 只能进入参数链接；
- 有原始卖点的 table-stake 可进入基础卖点；
- 无原始卖点的 table-stake 只进入基础参数；
- 单纯量子点参数缺失只形成参数短板，不生成卖点机会；
- 卖点机会必须有竞品原始卖点、用户价值优势、本品价值弱势和市场支撑；
- AC claim 只映射 AC value unit，不串入 TV。

## 3. 专项验证

- V5.2 claim reader + mapping：14 passed；
- touched files `ruff check`：passed；
- `git diff --check`：passed。

按调度合同未重复执行完整回归、覆盖率、性能或三类总评审。

## 4. 未执行

- 未接入 materializer/repository；
- 未修改报告、卡片或问答；
- 未部署 205；
- 未生成画像；
- 未 review、publish 或切 current。

下一 Goal：SPV52-G04 持久化、回读和 V5.1 兼容。
