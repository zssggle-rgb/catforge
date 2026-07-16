# G41C TV/AC 全量竞品画像草稿验收回执

状态：completed

日期：2026-07-16

## 1. 结论

G41C 已在 205 完成 377 款 TV 与 155 款 AC 的 agent snapshot v2 全量草稿生成、精确回读和智能体零重算验收。

每个 SKU 只消费现有竞品分析智能体已经计算出的实际候选结果，候选数允许为 0—20；本次真实数据中 TV 为 3—20 款，AC 为 1—20 款。画像保存逐款事实、分析过程、结论、候选池原始顺序、分析顺序、角色、业务得分和 Top 3，没有恢复 300 多款全品类候选扫描、category-wide pair/relation 图或固定补足 20 款。

两个正式验收版本均为 `success / draft / non-current`，权威 SKU 差集 0、重复 target 0、跨品类候选 0、失败 0。未执行 review、publish、current 或 deprecated，未重跑 M03B—M12D，未修改旧 M12/M13/M14。

## 2. 实现与代码

G41C 增加并验证：

- 全品类单写者 advisory lock，TV/AC 不允许并发写库；
- 一次准备权威范围与现有竞品智能体上下文，不再为每个 SKU 重载 377/155 款上游；
- 每个目标 SKU 独立事务、失败隔离、每 10 款检查点、DB 支持断点续跑；
- 已成功目标按保存结果直接复用，不再调用竞品智能体；
- 实际 0—20 候选及 0—3 Top3 的 typed schema、Repository 和业务读取支持；
- 共享 SKU snapshot 的数值规范化，消除同一数值因目标/候选序列化精度不同造成的伪冲突；
- compact readback 保持与候选数量无关的固定 SQL 数量。

代码提交：

- `bdb73f3 feat: add resumable competitor snapshot batches`；
- `42ec2e9 fix: canonicalize competitor snapshot metrics`；
- `f492351 fix: quantize shared competitor metrics`。

专项测试 8 项通过；竞品画像相关整组回归 100% 通过。ruff、format、py_compile 和 diff check 均通过。

## 3. 205 权威范围

TV：

- M12D authority：`m12d_ver_e4867984531b4300254eddb2`；
- profile version：`m12d_tv_purchase_reason_profile_v0_3`；
- batch：`m00_20260623014631_c8630747`；
- result hash：`f037e8bd82af23f2e2c515cd20db2fcdd81a4ab45cf6d0b60278874ab3655d52`；
- published/current SKU：377，唯一且全部为 TV 前缀。

AC：

- M12D authority：`m12d_ver_58797b2bb888a566216896d0`；
- profile version：`m12d_ac_purchase_reason_profile_v0_4`；
- batch：`m00_20260624000202_1150a669`；
- result hash：`f4007c13877cc46d36bd16a77b5cec3c6b2f2c51df28b29dbecced723dce70cc`；
- published/current SKU：155，唯一且全部为 AC 前缀。

## 4. 正式验收草稿

TV：

- version id：`288b6ce0-b632-478c-9705-8297103da730`；
- profile version：`competitor_profile_agent_snapshot_v2_tv_full_g41c_20260716_r2`；
- 状态：`success / draft / non-current`；
- profile：377；pair：7,300；selection：1,131；shared snapshot：377；relation：0；
- 候选数分布：3 款×4、13 款×14、17 款×18、19 款×20、20 款×321；
- Top3 分布：377 款均保存 3 个重点竞品；
- 全量 combined manifest hash：`a2f3edba708a058f40eb278ed60345f87d36e5a89d401a13361a7fabcdf1e54d`。

AC：

- version id：`eed759a8-a666-4257-8c4d-3405621a4244`；
- profile version：`competitor_profile_agent_snapshot_v2_ac_full_g41c_20260716_r1`；
- 状态：`success / draft / non-current`；
- profile：155；pair：2,774；selection：461；shared snapshot：155；relation：0；
- 候选数分布：1 款×2、9 款×10、10 款×11、16 款×17、20 款×115；
- Top3 分布：153 款保存 3 个重点竞品，2 款因实际候选仅 1 款而保存 1 个；
- 全量 combined manifest hash：`cb143a0aca532a18ac352f51309e6c72019fbd1c44f13087274e2e46b989e05e`。

本次所有候选都来自权威范围内 SKU，因此每类 shared snapshot 数量恰好等于权威 SKU 数量；不存在重复或孤立 snapshot。

## 5. 完整性验收

TV 与 AC 均通过：

- profile target 与当前 M12D authority 集合完全相等，missing/extra 均为 0；
- duplicate target、duplicate shared snapshot、self pair 和跨品类候选均为 0；
- profile 中候选集合与 pair 表一致；
- `candidate_pool_order` 与 source rank 一致；
- `analysis_order` 与保存 candidate record 顺序一致；
- `priority_order` 与 selection rank 逐项一致；
- target/candidate snapshot ref 与 snapshot result hash 逐项一致；
- version pair/selection 计数与逐 profile 汇总一致；
- typed profile 流式校验 532/532；TV/AC 抽样 full Reader + Adapter 回读均成功。

G41A 的 `TV00029112 / 海信 65E7Q` 与 G41B 的 `AC00026378` 在全量版本中，候选池顺序、分析顺序、Top3 和 source analysis hash 均与单 SKU 验收版本逐项一致。

## 6. 分析状态与复核分布

两类 532 份 profile 的 `conclusion_state` 均为 `available`，`analysis_available_dimension_count` 均为 7。

TV：

- profile：partial 377；auto_pass 41，review_required 336；
- pair：eligible 7,178，limited 122；auto_pass 5,439，review_required 1,861；
- selection：auto_pass 949，review_required 182；
- purchase pool：P0 3,916，P1 2,433，unknown 951。

AC：

- profile：partial 155；auto_pass 19，review_required 136；
- pair：eligible 2,773，limited 1；auto_pass 2,097，review_required 677；
- selection：auto_pass 368，review_required 93；
- purchase pool：P2 1,430，P3 1,014，unknown 330。

这里的 `partial` 和 `review_required` 继承现有竞品分析及 M12D 的证据限制/复核标记，不表示画像缺失或生成失败；所有 532 款均已保存可用结论和 7 个分析维度。G41C 只保存事实，不替代 G42 的发布质量评审。

## 7. 生成、断点与幂等

- TV 正式版本首次生成：2,693.7 秒，377/377，失败 0；
- AC 正式版本首次生成：392.3 秒，155/155，失败 0；
- TV 同版本真实复跑：0.50 秒，generated 0、reused 377；
- AC 同版本真实复跑：0.50 秒，generated 0、reused 155。

首次 TV r1 在第一个检查点发现 Decimal/float 表示精度造成的共享 snapshot 伪冲突后立即停止；12 个已成功草稿保持不可变，2 个失败目标被记录。该版本现已明确标记为 `failed / draft / non-current`：

- version id：`132a7c54-44b9-4c01-9fe4-55ab3843ca5f`；
- 失败目标：`TV00025500`、`TV00025519`；
- 未删除、未覆盖、未发布，仅作为失败审计记录保留。

修复后对前 20 个 TV 目标涉及的 237 个共享 SKU 做只读一致性预检，冲突 0，再创建 r2 正式验收草稿。该过程证明逐 SKU 失败隔离、成功保护和新版本恢复路径有效。

## 8. 读取性能与智能体零重算

compact preview 对最少候选和最多候选 SKU 均固定为 3 条 SQL：

- TV：4.833 ms / 2.141 ms；
- AC：4.863 ms / 2.048 ms。

SQL 数量不随候选数增长，未出现 candidate N+1。

现场把旧 `_competitor_set_legacy` 分析入口替换为立即报错的禁止桩后：

- TV `TV00029112` 仍从正式验收草稿恢复 20 款候选及 Top3：`TV00027801`、`TV00028909`、`TV00029936`；
- AC `AC00026378` 仍恢复 16 款候选及 Top3：`AC00034712`、`AC00039161`、`AC00038373`；
- 两次结果 source 均为 `competitor_profile_v1_1`，legacy recomputation 均为 false。

由此确认 Reader、Adapter 与竞品分析智能体 preview 只消费已保存画像，不重新召回、打分、排序或选择。

## 9. 数据保护与运行态

生成前后受保护数据行数完全一致：

- 旧竞品画像 V1：version 2、profile 532、pair 148,309、relation 1,038,163、selection 71；
- 采购理由画像：version 7、profile 1,751、anchor 17,899；
- 用户卖点价值画像：version 7、profile 691、candidate 45,070、item 3,123；
- G41A TV 单 SKU version：`99c944ba-6ff4-467b-9ab3-93fccfff1b19`，保持 success/draft/non-current；
- G41B AC 单 SKU version：`e89c4575-f137-4917-9c3d-ead871a6b335`，保持 success/draft/non-current。

验收结束时活动数据库 writer 为 0。

205 runtime：

- migration：`0047_core3_competitor_profile_v1_1 (head)`；
- API：running / healthy；
- healthz：ok；readyz：database ok；
- restart count：0；OOM：false；
- runtime 三个任务代码文件与本地 `f492351` 内容 SHA-256 完全一致。

## 10. 发布边界

G41C 到此关闭。G42 不自动创建，也未执行任何发布状态切换。

只有用户查看本回执和实际草稿结果后再次明确批准，才允许创建 G42，并分别执行 release quality review、draft→review、review→published、set current、正式智能体默认切换和回退演练。
