# 用户卖点价值分析智能体 V2 执行台账（2026-07-10）

## 总目标

并行实现面向产品经理的用户卖点称重与价格承接智能体，完成本地测试、精确提交、205 部署，并用海信 65E7Q 生成和回读飞书文档。

## 调度状态

- Goal：active
- 10 分钟心跳：active
- 当前任务：G07
- 分支：`new/base-publish-workbench-design`
- 工作区：存在用户既有未跟踪文件；本任务只精确暂存新增/修改文件

## 阶段记录

| 任务 | 状态 | 输入/动作 | 验证证据 | 下一步 |
| --- | --- | --- | --- | --- |
| G00 文档与基线 | completed | 已审查旧版 claim value、analyst、M05C、M07、M14；已建立需求、详细设计和任务链；经产品经理输出与市场量化两路只读复核，将价格模型收敛为 M14 直接竞品的周×平台条件选择曲线 | 需求 199 行、设计 313 行、任务链 149 行；边界、降级、65E7Q 验收齐备 | G01 |
| G01 上游合同与闸门 | completed | 新增类型合同；只读加载 M03B/M04C/M05C atoms/M07 周明细/M09C/M10C/M11C/M11D/M14；实现 M03B/M04C 一致性闸门 | 缺失、冲突、M14 优先/回退测试通过 | G02 |
| G02 价值单元与评论 | completed | 实现 TV 六个用户价值组合；按评论句去重，区分直接、体验结果、泛化不可归因和反向 | “好高清/画面清晰”不再直接支持 MiniLED；评论归因测试通过 | G03 |
| G03 市场量化 | completed | 实现周×平台直接竞品条件选择曲线、PAVA、同价选择优势、区间内选择保持价差和价格情景 | 单调、不外推、同价、交点、样本降级测试通过 | G04 |
| G04 竞品对照 | completed | M14 Top 3 优先；缺失时只复用现有 competitor-set 候选 ID；按价值组合比较事实、用户反馈和市场位置 | M14 来源与 fallback 均通过集成测试；V2 输出不含旧 M12C 金额字段 | G05 |
| G05 输出与 CLI | completed | 新增 `sellpoint-value-pm`、自然语言窄路由、短答、卖点经营盘、飞书卡片和 Markdown/飞书发布 | 报告与卡片测试通过；旧 `sku-claim-value` 相关回归通过 | G06 |
| G06 本地验收 | completed | 完成算法逆向场景、真实状态枚举、批次隔离、产品经理互斥卡片、当前价格承接状态和真实 M03B 字段可达性修正；完成市场模型与产品经理输出两路最终只读门禁 | 116 项相关测试全部通过；新模块综合覆盖 88%（schemas 100%、service 85%、answer 93%）；compileall 与 git diff --check 通过；两路门禁均无 P0/P1 | G07 |
| G07 提交与 205 | in_progress | 205 只读预检 health/ready 正常；已核对 65E7Q 真实 M03B 字段与 M14 状态，待精确提交和选择性部署 | 65E7Q 系统字段包含 `processor_chip_model/ram_gb/storage_gb`；当前无 M14 run，将按合同回退既有竞品智能体 | 提交、部署、生成并回读飞书文档 |

## 65E7Q 已知基线（部署前）

- 目标 SKU：`TV00029112`；
- M03B：5200nit、300Hz、1920 分区、MiniLED、98% 色域、MT9655 等事实存在；
- M04C：存在 `m03b_param_profile_missing` 与 `fact_claim_count=0` 等自相矛盾质量信号；
- M05C：评论大量泛化“清晰/画质好”，具体 MiniLED、高刷、强光/暗场结果证据弱；
- 芯片的用户反馈主要落在系统流畅，不足以证明 AI 画质价值；
- 旧 M12C/M12D 的金额或购买理由比例不作为 V2 真值。
- 205 预检确认当前 `TV00029112` 没有 M14 selection run；本轮必须验证既有竞品智能体 fallback，不得伪装成 M14。
- 205 预检确认 M03B 系统字段使用 `ram_gb/storage_gb`，护眼 core 当前只有亮度/HDR/刷新率；影院声场和长时间观看舒适可合法保持事实未知。

以上基线在 G06/G07 必须重新由实际输出核验，不能只引用本记录。

## 变更清单

- 新增 `claim_value_pm_schemas.py`、`claim_value_pm_service.py`、`claim_value_pm_answer.py`；
- 修改 analyst repository/atom/SOP/router/CLI；
- 新增服务和报告测试，并扩展 analyst 集成测试；
- 新增需求、详细设计、Goal 任务链和本执行台账。

## 测试与验收

- 相关回归：116 passed；
- 新模块定向覆盖：综合覆盖 88%，其中 schemas 100%、service 85%、answer 93%；
- Python compileall：通过；
- `git diff --check`：通过；
- 市场模型最终门禁：通过，无 P0/P1；
- 产品经理输出最终门禁：通过，无 P0/P1；
- 本机 Docker 未运行，因此真实数据库验收在 G07 的 205 环境执行。

## 提交与部署

待执行。
