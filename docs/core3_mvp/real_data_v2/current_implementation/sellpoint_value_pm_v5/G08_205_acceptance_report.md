# V5-G08 205 默认关闭真数验收报告

验收日期：2026-07-12（Asia/Shanghai）

## 结论

`PASSED FOR DEFAULT-OFF SHADOW; DEFAULT ROUTE SWITCH NOT ALLOWED`。

RC7 已完成开发、提交、205 定向部署、18 SKU 双跑、性能/内存/查询、V2/V4 回归、飞书回读和回滚演练。功能能够把产品配置与卖点转成产品经理可读的用户价值账，并在当前数据不支持时守住亮点、金额、销量增量和新战场边界。

当前不能切默认路由：18 个冻结 SKU 全部因发布画像与当前 M03B/M04C/M05C/M07/M11D hash 冲突等问题处于 blocked；这使本轮没有可发布亮点，也没有真实严格金额样本。

## RC 与部署

- RC：`sellpoint-value-pm-v5-rc7-9a5a147`；
- code commit：`9a5a147bec2a8be5c2a37839e3e9d7fc3ccc54bc`；
- package SHA-256：`ad1aceb49bd46c6031b936b91c6e15075786e7387b335597017e7f2752276ee7`；
- 9 个宿主机文件和 9 个容器文件均与 RC hash 一致；
- 默认关闭，无 flag 的 session/query count=0；
- 自然语言默认路由仍为 `sku-claim-value`；
- healthz/readyz 正常，数据库业务写入增量 0。

## 65E7Q 最终结果

- result hash：`10d3c28b140eb0aba91577e141a2432d90b976bbb2d0617a2b3c68ddeb3a61ff`；
- 飞书回读：[最终验收文档](https://my.feishu.cn/docx/HF9Pd1kRKohRjaxaSAlckgvVnAV)；
- 5 笔“战场 × 用户价值组合”价值账；
- 13 个 TV 战场全部进入 DTO 判断，主页面只显示 5 个已进入战场，无未命名战场；
- 0 亮点：线谱冲突时亮点总门禁生效；
- 0 严格金额、0 合成销量差、0 净新增、0 eligible 新战场；
- 页面无内部码、因果销量、伪金额、自动涨降价或泛化任务清单；
- JSON、短答、Markdown、飞书文档和卡片共享 result hash；双链接存在。

## 18 SKU 双跑

- 18/18 完整 report DTO 与 result hash 双跑一致；
- 16/18 具备同预算可比，10/18 具备同宣传不同兑现可比；
- 每 SKU 3—6 行价值账；report DTO 88,586—188,661 bytes；
- 13 个战场全部评估，每 SKU 4—10 个 excluded；0 个通过新战场 eligibility；
- 用户价值状态覆盖：positive、partial、mixed、negative、not observed；
- 全部 analysis state 为 blocked，因此全部亮点为空。

## 性能与资源

- 18 SKU 暖进程 36 次核心分析：P95 1.19 秒、最大 1.201 秒；
- 65E7Q 单次带 tracemalloc：4.489 秒、峰值 75.429 MB；
- 65E7Q 外层容器 CLI + JSON/Markdown：约 3.16 秒；
- 显式 latest 入口 SQL 30 次：10 次权威批次解析、3 次候选池/解析、17 次有界 V4 上下文；不随候选逐条增长；
- API 容器稳定约 188 MiB / 5 GiB，healthy、restart count 0。

## 量化与反事实结论

- 同预算与同宣传不同兑现成为多数 SKU 可用反事实；
- 完整候选证据快照固定为 3，满足 80 MB 门禁；
- 广义市场池不能直接当“无/弱价值”合成对照；当前缺少弱价值档位和共同市场支持，所以合成销量差为空；
- value existence 与 quantifiability 分离：用户价值状态仍可展示，但价格/销量归因和亮点在 lineage conflict 下暂停；
- opportunity/user-observed 作为已进入战场，完整 excluded 只走 expansion eligibility。

## V2/V4 与回滚

- V2 业务结果保持，唯一可变字段仍是既有 `audit.generated_at`；
- V4 result hash 保持 `5bca5457c9b4e618700e50de3f32cebbde52061e2a180a084db705f83a4b2b1a`；
- 回滚到部署前实际文件后入口消失且健康正常；恢复 RC7 后 9/9 hash、默认关闭、健康和数据库零写再次通过。

## 后续准入条件

不自动创建工作清单。默认路由切换只在另一个经批准的 Goal 中讨论，最低前提是：发布线谱重新对齐；至少一个真实非 blocked SKU；至少一个可审核的相对亮点；若输出金额，至少一个严格组合金额通过全部门槛；飞书真实页面再次通过产品经理复核。
