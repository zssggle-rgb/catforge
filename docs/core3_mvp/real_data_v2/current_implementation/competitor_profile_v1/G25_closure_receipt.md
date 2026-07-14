# G25 关闭回执

状态：completed

日期：2026-07-14

## 1. Goal

只在 205 为一个权威 AC SKU 生成并验收一个明确命名的竞品画像草稿，证明候选、关系、量价、卡片、两份飞书报告、深入问答和用户卖点价值消费均使用 AC 正式上游并锁定同一个已保存版本；不执行 TV 重写、批量生成、review、publish、set-current、deprecate 或旧 M12/M13/M14 修改。

## 2. 写入前只读门禁

- 205 写入前运行提交：`ac5ee8521ebc3a4832afbad3f0ccaede1a886b10`；工作树干净；
- Alembic：`0046_core3_competitor_profile (head)`；`/healthz` 为 `ok`，`/readyz` 为 `ready/database ok`；
- 其他 active database session：`0`；
- 竞品画像只有 G24 TV 草稿：1 version、1 profile、352 pairs、2,464 relations、1 selection；published/current 均为 `0`；
- AC 竞品画像 version 数为 `0`；
- AC 权威范围为 155 款 SKU、单一 source batch `m00_20260624000202_1150a669`；manifest hash 为 `sha256:competitor_profile_authoritative_sku_manifest_v1:6cf0c669f3998e644d3eebbec6a291bdc4d491a275df2a0740581bceda137b96`；
- M03B、M04C、M05C、M07、M09C、M10C、M11C、M11D、M12C、M12D 均锁定 AC project/category/product category、正式 rule/taxonomy、published/current authority 和上述 source batch；没有使用 draft/latest fallback、旧 M12/M13/M14 或现场 `competitor-set`；
- 140 款 AC SKU 十个模块完整。选择海信 `AC00032008 / KFR-35GW/S550-X1`，因为其十个模块完整、M07 覆盖 24 个活跃周，且是海信 1.5 匹壁挂样本。

## 3. 唯一 AC 草稿

- 205 最终运行提交：`b45c92fcd76edf614f72b612760f3ad458fea08f`；远端工作树干净；
- 画像版本 ID：`45725326-720c-45c8-9a3b-e86fb6cc1f0b`；
- 画像版本：`competitor_profile_v1_ac_hisense_s550_g25_20260714_r1`；
- release scope：`d8d2245b-358b-4a64-95cc-9d7f2341bd26:AC:4e8f393dc6f6482a81395b99`；
- release status 保持 `draft`，`is_current=false`，published/current 版本数为 `0`；
- version result hash：`sha256:competitor_profile_version_result_v1:193cfd4692706b95fcc0c22e50f891e6f1edd27c7ef40f1926c6330e3da19f66`；
- SKU profile result hash：`sha256:competitor_profile_sku_profile_result_v1:f6afaa177fd4465df724618f27bc84f77bfcbe2f540fedd4feb9d9a0eed6fac2`；
- 全量 readback receipt hash：`sha256:competitor_profile_g25_readback_receipt_v1:95f8b84a770e81cae6232ff71cf97243a161205bbc7745c736a47a5e6db07f6b`。

版本的 `processing_status=running` 是全品类 155 SKU 进度状态，不是该 AC SKU 失败。G25 只授权一个 SKU，因此当前为 `partial_count=1`、`failed_count=0`。

## 4. 画像完整性和品类隔离

| 对象 | G25 AC 行数 |
| --- | ---: |
| version | 1 |
| 主画像 | 1 |
| 完整候选 pair | 150 |
| 七类关系 | 1,050 |
| 重点选择 | 2 |

- 候选状态：`eligible` 2、`limited` 5、`reference_only` 7、`review_required` 136；
- 正式竞品成员 7 款；独立 reference-only 7 款；sellpoint consumer 的 reference members 为 14 款，其中包含 7 款正式竞品的重叠参照身份；
- 150 个 pair 的 candidate code 唯一，全部具有召回来源和 result hash；
- 每个 pair 恰好 7 条关系，七个 relation code 齐全；selection rank 为 1、2，未凑满 3 款；
- 每个 pair 恰好 8 条 question availability，共 1,200 条：eligible 15、limited 15、unavailable 1,170；
- M07 采用 full observed window 周平均量价。共同周、共同平台均保存为 `null`，150/150 pair 未把缺失填成 0；
- pair、relation、selection 的跨品类行均为 0；target/candidate SKU 均为 `AC%`，source lineage 只含 AC rule/taxonomy/source batch；
- 全量 hash receipt 回读 150 pair hashes、1,050 relation hashes 和 2 selection hashes，与保存的 profile hash 一致；
- G24 TV 基线保持 1 profile、352 pairs、2,464 relations、1 selection，画像内容未被改写。

## 5. AC 业务结果

1. **用户直接选择**：华凌 `KFR-35GW/N8HA1III-P` 与本品形成同预算选择关系；其均价低 7.1%，周均销量为本品 10.03 倍。
2. **另一种场景方案**：统帅 `KFR-26GW/LXCA-1PRO` 是另一种场景方案，不再被写成“同品牌产品线”；其均价低 3.2%，周均销量为本品 1.03 倍。
3. **价值替代压力**：集中在同价位能效/能力获得感、长期省电抵消更高价格、小房间/租房安装适配。
4. **配置决策**：非基础差异集中在静音睡眠；先核对档位和用户兑现，再决定强化或放弃。
5. **产品动作**：先明确本品相对华凌的目标用户和价值取舍，再在能效获得感和长期省电上建立一至两项明确领先；现有量价证据不支持把降价作为第一动作。

G25 发现并修复了两个展示问题：AC 型号不再转成小写；跨品牌竞品不再使用“产品角色分工”。未来生成的 `portfolio_or_scenario` 选择理由也按 `same_brand_ladder` 和 `scenario_substitute` 分开表达。

## 6. 卡片、报告、问答和卖点价值消费

- 卡片：`G25_ac_s550_feishu_card.json`；SHA-256 `30be23f7a9009a30f6ce04625e10e96decda9abb08a2b6b2d44e325e98e89ec8`；包含两份报告按钮，无版本/hash/内部模块等运行痕迹；
- 产品经理报告：[海信 KFR-35GW/S550-X1 竞品决策与用户选择分析](https://my.feishu.cn/docx/G85Ud5SRKoIwQVxuetvcdZSDnkd)；
- 分析依据报告：[海信 KFR-35GW/S550-X1 竞品识别与分析依据](https://my.feishu.cn/docx/RxjJdl98Oogu1txNL5fcdz1Inzg)；
- 两份文档均以当前用户身份创建并回读成功，revision 均为 `5`；标题、AC 型号和正文正确，TV SKU、电视、画质、HDMI 等串线词为 `0`；
- 最终 205 presentation hash：`sha256:competitor_profile_presentation_bundle_v1:38eddd42cf4e6c9223c1a8b56b2be1ed6d5307a077e86fc1b75afa0cbb66f9fa`；
- 6 个默认问答均锁定 `45725326-720c-45c8-9a3b-e86fb6cc1f0b` 和同一 profile result hash；
- 用户卖点价值消费读取 7 款 formal candidates、14 款 reference members，`read_only=true`、`sellpoint_profile_write=false`、`fallback_used=false`；没有生成或修改卖点价值画像。

## 7. 测试、服务和旧链保护

- 本地竞品画像专项共收集 `292 tests`，全部通过；
- 205 运行提交、container、`/healthz`、`/readyz` 和 Alembic head 均通过；
- 数据库无其他 active session；
- 旧保护表保持 G24 基线：竞品候选 28、竞品结果 30、采购理由版本 7、采购理由画像 1,751、采购理由锚点 17,899、卖点价值版本 7、卖点价值画像 691、卖点价值候选 45,070、卖点价值项 3,123；
- 未修改旧 M12/M13/M14，未改写 TV 草稿，未执行 batch、review、publish、set-current 或 deprecate。

## 8. 下一 Goal 门禁

G24 TV 单 SKU 与 G25 AC 单 SKU 均验收通过，G26 可进入全量 TV/AC **draft** 生成；G26 尚未创建、尚未执行。全量生成仍不得 review、publish 或切换 current，任何正式发布动作继续需要单独明确授权。
