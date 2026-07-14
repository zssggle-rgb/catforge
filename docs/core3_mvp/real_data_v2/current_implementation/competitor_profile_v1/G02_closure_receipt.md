# 竞品画像 V1 G02 完成回执

状态：completed

日期：2026-07-14

## 1. Goal

只读复核 205 上 TV/AC 新版画像覆盖、候选来源可行性、跨品类隔离和真实缺失边界。

## 2. 产物

- `G02_readonly_probe.py`
- `G02_data_feasibility_report.md`
- `G02_closure_receipt.md`
- 更新 `COMPETITOR_PROFILE_goal_dispatch.md`

## 3. 结果

1. M07、M03B、已发布 M12D 覆盖 TV 377/377、AC 155/155；
2. 全部 TV/AC SKU 均能从新版画像召回候选；
3. M04C/M05C/M09C/M10C/M11C/M11D/M12C 缺失按问题降级，不需要补跑旧 M08—M14；
4. raw broad union 过宽，不能直接作为正式竞品宇宙；
5. 65E7Q 同产品形态同预算为 3 款，但 broad union 为 349，证明必须增加关系资格门槛；
6. M03B 存在 155 条 TV category 下的历史 AC rule 记录，读取器必须精确锁定品类、rule、taxonomy 和 serving scope；
7. TV 需要三批次 serving scope，AC 为单批次；
8. 数据足以进入 G03 方法设计。

## 4. 验证

- 探针本地语法编译：通过；
- 205 health/ready：通过；
- 两次只读探针 stdout hash 一致；
- 快照业务 hash 固定；
- `git diff --check`：通过；
- 205 数据库写入：0；
- 部署、migration、发布切换：0。

## 5. 下一 Goal

G03：冻结候选召回、正式关系资格、七类关系、问题级可用性和重点竞品选择方法。

只有本回执最终检查通过且当前 Goal 标记 complete 后，才允许创建 G03。
