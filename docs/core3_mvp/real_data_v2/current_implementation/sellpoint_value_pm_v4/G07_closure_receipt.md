# G07 关闭回执：产品经理业务答案、报告与显式入口

## Objective

把 G03-G06 已经成立的价值关系和量化边界翻译成产品经理能直接使用的“SKU 用户价值账”，并让 JSON、短答、固定七列主表、下钻和飞书卡片消费同一个业务 DTO；新增默认关闭的显式 V4 CLI，但不切换自然语言默认路由。

## 前置输入

- G06 核心实现 commit：`ce1b4eb`；
- G06 closure commit：`c3b52b3`；
- G07 Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`；
- G07 timer：`catforge-v4-g07-10`。

## 实际产物

- 扩展 `claim_value_pm_v4_schemas.py` 的 G07 report contracts；
- 新增 `claim_value_pm_v4_answer.py`，作为唯一业务 DTO builder 和全部 renderer；
- 增加只读 V4 context atom、薄 SOP 编排、ability registry 与显式 CLI；
- 新增 `test_claim_value_pm_v4_answer.py`、`test_claim_value_pm_v4_cli.py`；
- 更新 `G07_progress.md`；
- 本关闭回执；
- `G07_artifact_manifest.json`。

未修改数据库/205、V2 registry 语义或自然语言默认路由。

## 产品经理最终看到的结构

| 价值战场及市场空间 | 本品核心采购理由 | 用户实际获得的价值 | 支撑卖点组合 | 相对基础与同价值竞品 | 选择和价格兑现 | 产品角色 |
| --- | --- | --- | --- | --- | --- | --- |

这张表直接回答：产品投入有没有形成用户实际感知到的价值；该价值是否表现为选择差异；市场量价最多支持到整机承接，还是达到严格的市场隐含支付区间。无法量化只说明识别边界，不等于没有价值。

## 业务合同

1. 一行是一笔“价值战场—采购理由—用户实际价值—卖点组合”价值账，不是每个技术参数一行；
2. 用户实际价值只来自购后体验，不推测购买前传播心智；
3. 市场空间、采购理由、价值、卖点组合、反事实、市场兑现和产品角色分栏，避免口水式总评；
4. 主表不出现内部模块码、量化等级、隔离等级、SQL 或证据 ID；
5. QA appendix 可保存审计信息，但全部 PM renderer 禁止读取或泄漏；
6. 同一个 report/result hash 驱动短答、Markdown 和飞书卡片，renderer 不重新计算；
7. 共线组合只显示组合支付区间，绝不拆单项；
8. 无法量化、负向体验、事实版本冲突是三种不同业务状态；
9. 不生成涨降价、增减配、验证清单或通用工作清单；
10. 双链接分别为 `查看用户选择对比` 与 `查看分析依据`；
11. V4 命令必须显式 `--enable-v4`，未启用时在 DB context 前停止；
12. 自然语言入口仍路由既有 V2，G07 不扩大上线范围。

## 样例结果

合成可识别样例输出为：高端画质升级战场 → 画质配置解释加价 → 用户实际感知到画质升级 → 明亮环境与明暗层次＋色彩真实组合 → 2 个较低价值档对照可进入市场比较 → 同价条件销量份额 57.2%、市场隐含支付区间 400-500 元 → 核心差异价值。

65E7Q 脱敏固定样例没有原始评论 atoms 和逐周平台 cell，并存在版本冲突，因此只显示候选结构与边界：用户实际价值未观察，价格归因 blocked，金额为空；没有补造真实 SKU 的支付意愿。

## 测试结果

| 验证 | 结果 |
| --- | --- |
| G07 answer/CLI tests | 17 passed |
| G03-G07 + V2 answer/service | 96 passed |
| 既有 analyst CLI | 88 passed |
| 合计 | 184 passed |
| V4 answer coverage | 93% |
| G02 frozen contract | exact match |
| 主表禁止词与无产品动作 | passed |
| 双链接与跨载体同源 | passed |
| database/server writes | 0 / 0 |

## 已知边界

- G07 复用了现有飞书 publisher 合同，但没有连接飞书或创建真实文档；真实发布和回读属于 G09；
- 当前只有 synthetic fixture 在报告中显示 400-500 元，真实 SKU 金额声明仍为 0；
- 65E7Q 脱敏 fixture 不能替代 205 真实逐周数据和评论回放；
- G08 尚需做完整回归、性能、查询计数、fixture hash 和独立方法/工程/业务语言评审。

## Commit

- G07 核心实现：`1e10a04`；
- 本关闭回执、manifest 和完成状态：本文件所在的独立 closure commit。

## 下一 Goal 准入

`G08 allowed`。G08 只做本地综合验收与独立评审；发现核心合同错误时创建修复 Goal，不在验收 Goal 中临时重写设计。
