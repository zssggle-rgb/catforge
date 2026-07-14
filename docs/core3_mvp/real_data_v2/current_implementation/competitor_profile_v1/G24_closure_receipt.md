# G24 关闭回执

状态：completed

日期：2026-07-14

## 1. Goal

只在 205 为海信 65E7Q（`TV00029112`）生成并验收一个明确命名的竞品画像草稿，围绕同一个已保存版本完成全量回读校验、产品经理卡片、两份飞书报告、六类深入问答和用户卖点价值只读消费证明；不执行 AC、批量生成、review、publish、set-current、deprecate 或旧链改写。

## 2. 版本与生成结果

- 205 最终运行提交：`ac5ee8598e036d3733434a59087b7248da318180`；远端工作树干净；
- 画像版本 ID：`c45c0002-9b8a-4b0d-8b12-344dee020e15`；
- 画像版本：`competitor_profile_v1_tv_65e7q_g24_20260714_r1`；
- 生成请求：`/tmp/g24-generation-request-r3.json`；SHA-256 `16bba9279197c070590e55897f2db3756f3d471b881fcde0b22d016d981aad7c`；
- 单 SKU 幂等复跑返回 `reused`，未新增版本、主画像或子记录；
- release status 保持 `draft`，`is_current=false`，published/current 版本数为 `0`；
- version result hash：`sha256:competitor_profile_version_result_v1:3331f446b4b86704b8d1a59829fcbdd4e25ddc1eac14abd69fed9eafe9ef108d`；
- SKU profile result hash：`sha256:competitor_profile_sku_profile_result_v1:6d11931e594e19aad3549eb4a822a1c86112fa7ab8cb905128aad0027224d056`。

版本的 `processing_status=running` 是全品类 377 SKU 进度状态，不是 65E7Q 失败。G24 只授权一个 SKU，因此当前为 `partial_count=1`、`failed_count=0`，必须等后续获准的全量草稿任务完成后，版本进度才可能关闭。

## 3. 数据库与完整性验收

五张新表只有本次唯一草稿：

| 对象 | 行数 |
| --- | ---: |
| version | 1 |
| 65E7Q 主画像 | 1 |
| 完整候选 pair | 352 |
| 七类关系 | 2,464 |
| 重点选择 | 1 |

候选状态分布：

- `eligible` 2 款，其中 1 款入选重点；
- `limited` 23 款；
- `reference_only` 9 款；
- `review_required` 318 款；
- 正式竞品成员共 25 款；独立分析参考池合计 34 款。

全量 hash receipt 校验了 352 pair、2,464 relation 和 1 selection；精简消费者视图只加载 25 款正式竞品与 9 款独立参照、238 条关系，仍由全量 receipt 校验完整落库结果。每个 pair 恰好 7 类关系，8 类问题可用性齐全，重点 rank 连续；空召回来源、缺失 hash、非法 selected、跨 TV/AC 串线、非 draft/current 子记录均为 `0`。

## 4. 产品经理业务结论

1. **用户直接选择**：当前不能把任何一款产品列为 65E7Q 的直接二选一对象；海信 75E7Q 是产品线与使用场景参照，不被冒充为直接替代品。
2. **本品优势**：没有找到 65E7Q 相对可比较产品的稳定用户价值优势，现有卖点不能直接作为加价或继续追加投入的依据。
3. **价值替代**：竞争最集中在客厅换新一步到位（22 款）、游戏低延迟（15 款）、画质配置解释加价（13 款）、贵得值的体验升级（13 款）和局部控光（9 款）。
4. **量价压力**：海信 75E7Q 均价高 19.7%、周均销量为本品 2.45 倍；雷鸟 85R69A ULTRA 均价高 1.4%、周均销量为本品 3.34 倍。两项压力首先指向价值表达和产品角色，降价不应作为第一动作。
5. **配置取舍**：过滤 HDMI 2.1、屏幕尺寸和语音控制等基础/规格差异后，需要进入产品定义评审的非基础差异集中在局部控光和游戏低延迟，各涉及 10 款产品；仍需先核对具体档位和用户兑现，不自动追配。
6. **产品动作**：先明确 65E7Q 与 75E7Q 的角色分工；再从客厅换新一步到位、游戏低延迟中选择一至两项建立领先；价格先对照 75E7Q 与雷鸟 85R69A ULTRA 的量价表现。

## 5. 卡片、报告、问答和卖点价值消费

- 可审计卡片：`G24_65e7q_feishu_card.json`，SHA-256 `90d25f4f22485db212e4d1858411f6a7c15de94f6d8342d85b4dd478770ab282`；
- 产品经理报告：[海信 65E7Q 竞品决策与用户选择分析](https://my.feishu.cn/docx/VYJmdXnnfogsMWxmo7scvYC3n7c)；
- 分析依据报告：[海信 65E7Q 竞品识别与分析依据](https://my.feishu.cn/docx/YCfzd1zQIoao4mxjXrScbb6RnQe)；
- 两份飞书文档均以当前用户身份创建并回读成功，revision 均为 `3`；
- 最终 205 presentation 预览 SHA-256 为 `f2bdb9d8f28ec4e14f734889cf402d4eadca752f0f2a7f5ae2d3e465b72b0f6d`；
- 六个默认问答全部锁定同一 profile version/result hash；价格销量问题正确返回海信 75E7Q 与雷鸟 85R69A ULTRA 的量价压力，不再误路由为“用户比较谁”；
- 用户卖点价值消费证明读取 25 款正式竞品和 34 款 reference member，`read_only=true`、`sellpoint_profile_write=false`、`fallback_used=false`；没有生成、修改或发布新的卖点价值画像。

## 6. 测试、服务与旧链保护

- 本地竞品画像专项 `289 tests collected`，全部通过；
- 205 `/healthz` 返回 `ok`，`/readyz` 返回 `ready/database ok`；
- 数据库无其他 active session；
- 旧保护表行数与 G23 基线一致：竞品候选 28、竞品结果 30、采购理由版本 7、采购理由画像 1,751、采购理由锚点 17,899、卖点价值版本 7、卖点价值画像 691、卖点价值候选 45,070、卖点价值项 3,123；
- 未修改或覆盖旧 M12/M13/M14，未写 AC，未做批量生成。

## 7. 下一 Goal 门禁

G24 验收通过，调度状态更新为 G24 completed / G25 pending。G25 尚未创建、尚未执行；下一步只允许选择一个 AC SKU 做品类隔离草稿验收，仍不得 publish/current 或全量生成。
