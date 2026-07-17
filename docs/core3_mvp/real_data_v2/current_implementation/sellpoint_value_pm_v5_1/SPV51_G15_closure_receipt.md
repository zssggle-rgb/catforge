# SPV51-G15 65E7Q V5.1 Draft 关闭回执

状态：completed

日期：2026-07-17

## 1. 目标与结果

只在 205 为海信 65E7Q（`TV00029112`）生成并验收了一个明确命名、不可变的用户卖点价值画像 V5.1 draft：

- profile version：`spv_v5_1_65e7q_g15_20260717_r1`；
- version id：`40803663-3562-4426-b97e-db3f5e6aa9a4`；
- profile id：`7986ae9d-6734-486d-a3fb-5311df507699`；
- version / profile / candidate / item：`1 / 1 / 71 / 5`；
- `release_status=draft`、`is_current=false`；
- `analysis_state=ready`、`conclusion_status=conclusion_available`；
- `processing_status=success`、`review_required=false`；
- V5.1 published/current 均为 0。

重复执行相同生成命令复用了同一个不可变 version 和 profile，没有创建第二份结果。

## 2. 启动前保护与数据来源

启动时确认：

- 205 Git HEAD 为 `a0fe719eec2068ec1270babcaf2b49b7bfdb0b4b`；
- Alembic 为 `0048_core3_sellpoint_value_profile_v5_1`；
- 不存在并发画像生成进程；
- V5.1 version 初始为 0；
- 远端用户 dirty 和 stash 均原样保留。

本次唯一竞品来源为正式 current/published 竞品画像：

- version id：`288b6ce0-b632-478c-9705-8297103da730`；
- profile version：`competitor_profile_agent_snapshot_v2_tv_full_g41c_20260716_r2`；
- method：`competitor_profile_agent_snapshot_v2`；
- version result hash：`sha256:competitor_profile_agent_snapshot_version_result_v1:db6e58bbf37346dc18d02532905263287d6dbf58be7d6ad8ba8b35dfc98daa89`；
- 65E7Q profile result hash：`sha256:competitor_profile_agent_profile_result_v2:bd7e899a989f192cc35c06d7ded02ca05bc0aa54cf323dca4cf8a320f3ab9ae6`。

没有调用旧 M12/M13/M14 fallback，没有重跑 M03B—M12D。

## 3. 真实问题与必要修复

### P0：候选置信度落库精度不一致

首次真实生成暴露候选置信度 hash 与数据库数值精度不一致，导致严格回读校验失败。只修复 V5.1 候选置信度的确定性精度对齐，提交为：

- `9d4342c fix: align sellpoint candidate confidence precision`

### P1：保存事实没有转成产品决策

首次验收发现首屏重复展示原始价量结论，没有直接回答价格是否得到支撑、销量策略、SKU 角色；无结果的竞品配置句子仍占据首屏；未转化的游戏能力被放入核心卖点组合；战场问答重复同一事实。

只修改报告与问答的只读业务投影：

- 首屏固定回答保留投入、未转化投入、竞品配置取舍、价格支撑、销量策略、SKU 角色；
- 核心卖点只保留 `retain` 且非基础的卖点；
- 空竞品配置结论改成可执行的预算取舍；
- 四组保存的量价对照聚合成价格支撑和销量动作；
- 同义战场事实去重。

提交为：

- `1af8805 fix: turn sellpoint profile facts into product decisions`

生成入口和正式竞品画像输入适配提交为：

- `10d8495 feat: generate sellpoint value v5.1 from saved profiles`

## 4. 画像回读验收

### 候选与问题池

- 正式竞品 20 款，Top 3 为 `TV00027801`、`TV00028909`、`TV00029936`；
- 分析参照 51 款；
- 八类问题均保存独立候选选择，价格支撑和规模转化使用全部 71 款，其他问题按正式竞品或同品牌子集选择；
- Top 3 只是重点顺序，没有截断其余可用竞品。

### 用户价值与投入

- 4 个价值项为 `conclusion_available`，1 个游戏与运动流畅为 `partial_conclusion`；
- 保留投入：明亮环境与明暗层次、影院声场、色彩与画面真实、大屏客厅沉浸、系统与交互效率；
- 未转化投入：游戏与运动流畅；
- 游戏与运动流畅不进入核心卖点组合；
- `invalid=0`、`review_required=false`，局部无结论没有传播为 SKU 或版本阻断。

### 分层量化

- 直接价值组合量价结论 4 组，价差为 `+262.1～+427.4 元`，周均销量差为 `+45.6～+75.7 台`；
- 市场原型结论 1 组，三款同预算参照下价差 `+278.9 元`、周均销量差 `+61.9 台`；
- 16 组参数比较均诚实保留为 `no_conclusion`，没有编造竞品参数；
- 5 个严格 WTP 均为 `no_conclusion`、`pair_count=0`，不进入产品经理首屏；
- 直接量价只表达价值组合的市场关联，没有标成随机实验因果。

## 5. 产品经理业务验收

报告、卡片和问答均直接回答：

1. 下一代继续保留五类已经形成用户价值的投入；
2. 游戏与运动流畅先修复体验兑现，不再追加纸面参数预算；
3. 不因竞品纸面参数新增配置预算；
4. 当前价格得到用户价值支撑，降价不是第一动作；
5. 增长优先来自继续做强已兑现价值和修复未转化体验；
6. 65E7Q 继续承担 65 英寸高端画质升级款角色，不转成低价走量款。

完整业务报告：`SPV51_G15_65E7Q_acceptance_report.md`。

## 6. 零重算与一致性

profile result hash：

`sha256:sellpoint_value_profile_result_v5_1:7b54f4e8baf2030ff10cf28ed443687a5dec57f0ba71d4c084781e7496a82746`

报告、卡片和七类问答均返回该 hash。SQL 录制共 56 条语句，只读取 V5.1 version/profile/candidate/item 和竞品画像 version lineage 表；没有读取竞品 pair、旧 M12/M13/M14 或现场市场计算表。

因此三个消费面只使用同一份已保存画像，没有现场重算。

## 7. 测试、部署与运行时

- V5.1 相关专项测试：267 passed；
- Python compile 和 `git diff --check` 通过；
- 实施提交均已推送当前分支；
- 205 只重建 API；
- API image：`sha256:6d708b660472427bdd2796c0275866b5234ebc2c21f8221437f73de0625b0f69`；
- P1 部署备份：`/home/deploy/catforge-deploy-backups/spv51-g15-p1-20260717`；
- `/healthz=ok`，`/readyz=ready`；
- 最终复核窗口没有 `ERROR`、`Traceback` 或 `CRITICAL` 日志，画像生成进程为 0；
- `.env` SHA256 保持 `7243971662532eaa036d64f7d73d71920c586286a94df5eacead1713e6e5b56a`。

## 8. 保护门禁

本 Goal：

- 没有 review、publish、current 或 deprecated 切换；
- 没有创建 AC 或其他 SKU 的 V5.1 结果；
- 没有执行全量生成；
- 没有修改旧 V5、旧 M12/M13/M14 或正式竞品画像；
- 没有切换远端 Git HEAD；
- 没有删除、清理或提交远端用户 dirty/stash。

结构化证据：`SPV51_G15_65E7Q_acceptance_evidence.json`。

G15 已通过。后续允许另行创建 SPV51-G16，但本 Goal 不创建、不执行 AC 验收。
