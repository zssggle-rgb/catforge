# 竞品画像 V1 需求—方法—设计追溯

状态：G22 本地 RC 复核

日期：2026-07-14

## 1. 需求追溯

| 需求 | 设计落点 | 主要实现 Goal | 主要验证 Goal |
| --- | --- | --- | --- |
| CP01 关系资产 | 详细设计 1、5.3、6.3—6.4 | G05、G07、G14—G18 | G22、G24—G26 |
| CP02 无固定上限 | 详细设计 2、8、13 | G10、G12、G13 | G22、G24—G26 |
| CP03 竞品/参考分离 | 详细设计 5.3、6.3、11.4 | G05、G11、G20 | G22、G24 |
| CP04 七类关系 | 详细设计 5.7、6.4 | G05、G18 | G22、G24—G25 |
| CP05 问题级可用 | 详细设计 5.8 | G05、G11、G18 | G22、G24—G25 |
| CP06 0—3 重点 | 详细设计 5.9、6.5 | G05、G19 | G22、G24—G25 |
| CP07 新版权威输入 | 详细设计 3、8.1 | G09 | G22、G24—G25 |
| CP08 M07 主口径 | 详细设计 5.6 | G14、G17 | G22、G24—G25 |
| CP09 非因果/WTP | 详细设计 5.6、11.4 | G17、G20 | G22、G24 |
| CP10 智能体只消费 | 详细设计 11.1—11.2 | G22 单版本消费合同；G24 正式切换 | G24—G26 |
| CP11 卖点价值消费 | 详细设计 11.4 | G22 消费边界；G24 消费验收 | G24—G26 |
| CP12 单版本锁定 | 详细设计 11.1、11.3 | G08、G20—G22 | G24—G26 |
| CP13 生命周期 | 详细设计 7、9 | G06—G08 | G22、G23 |
| CP14 不原地改写 | 详细设计 7、9 | G07—G08 | G22、G23 |
| CP15 TV/AC 隔离 | 详细设计 3、4、8.1 | G05、G09、G15—G18 | G22、G25—G26 |
| CP16 顺序门禁 | 调度文档、详细设计 8.3 | G23—G26 | G24—G26 |
| CP17 旧链回退 | 详细设计 1、11.1 | G21—G23 | G23—G26 |
| CP18 unknown/review | 详细设计 5、10、14 | G05、G11、G18、G21 | G22、G24—G26 |
| CP19 确定可追溯 | 详细设计 5、8、13 | G05、G12、G20 | G22、G24—G26 |
| CP20 展示边界 | 详细设计 2、11.3、12 | G20—G22 | G22、G24—G25 |

## 2. 方法追溯

| 方法 | 设计落点 | 实现 Goal | 测试入口 |
| --- | --- | --- | --- |
| MP01 四层分离 | 2、5、8 | G10—G20 | integrated pipeline |
| MP02 无数量截断 | 8.1—8.2、13 | G10、G13 | max manifest/performance |
| MP03 召回不等于关系 | 5.3、5.7 | G10、G18 | recall-only cases |
| MP04 通用/门槛过滤 | 4、5.5 | G15—G18 | A01、A16 |
| MP05 直接替代 | 5.4—5.7 | G15—G18 | A01、A07、A10 |
| MP06 降档 | 5.6—5.7 | G17—G18 | A03、A04、A19 |
| MP07 升档 | 5.6—5.7 | G17—G18 | A05、A06 |
| MP08 同品牌相邻 | 4、5.7 | G10、G18 | A02 |
| MP09 场景 | 5.5、5.7 | G15、G18 | A08、A18 |
| MP10 同价值 | 5.5—5.7 | G16、G18 | A01、A08 |
| MP11 missing unknown | 5.4、5.6、14 | G05、G09、G11 | A09、A10、A17 |
| MP12 问题可用 | 5.8 | G11、G18 | question matrix |
| MP13 M07 量价 | 5.6 | G14、G17 | pair market tests |
| MP14 非因果 | 5.6、11.4 | G17、G20 | causal false boundary |
| MP15 reference 分离 | 5.3、6.3 | G10—G11、G20 | A13、A17 |
| MP16 0—3 非 TopN | 5.9、6.5 | G19 | A14、A15 |
| MP17 证据/复核 | 5.5、5.7、10 | G18、G21 | conflict/review cases |
| MP18 TV/AC 配置 | 3—4 | G09、G15—G18 | AC isolation tests |
| MP19 精确 authority | 3、8.1 | G09 | A11 |
| MP20 确定性 | 5、8.2、13 | G12、G20 | order reversal/hash |

## 3. 详细设计关闭矩阵

| 设计条款 | 设计证据 | 前置 | 关闭状态 |
| --- | --- | --- | --- |
| DD01 | 五层数据模型与五表 | CP01 | closed |
| DD02 | 3.1—3.2 | G02 serving scope | closed |
| DD03 | 3.3、8.1 | G02 M03B 串线 | closed |
| DD04 | 4 | G03 threshold versioning | closed |
| DD05 | 5.1 | G03 states | closed |
| DD06 | 5.7 | seven relations | closed |
| DD07 | 5.4、5.6 | missing unknown | closed |
| DD08 | 5.3、6.3 | competitor/reference split | closed |
| DD09 | 5.9、6.5 | 0—3 selection | closed |
| DD10 | 5.10、10.1 | result vs insufficient | closed |
| DD11 | 6 | persistence | closed |
| DD12 | 7、9 | immutability | closed |
| DD13 | 7、9 | publish safety | closed |
| DD14 | 7、9 | CAS safety | closed |
| DD15 | 8.3 | batch safety | closed |
| DD16 | 11.1 | reader boundary | closed |
| DD17 | 11 | 单版本 consumer context 已关闭；智能体/卡片/报告/问答路由切换待 G24 | contract closed / cutover pending |
| DD18 | 11.4 | 身份不可升级边界已关闭；卖点价值实际消费验收待 G24 | boundary closed / consumption pending |
| DD19 | 13 | max pair scale | closed |
| DD20 | 12、14、16 | safety and testing | closed |

## 4. 发布边界

本追溯只授权设计和后续 draft 生成。`review_version`、`publish_version` 和 `set_current_version` 虽然必须实现并测试，但 G23—G26 不执行；任何正式切换需要用户另行明确批准。
