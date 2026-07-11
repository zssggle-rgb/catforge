# G02 详细设计、模型合同与测试计划进度

- Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`
- Goal 状态：`ready_to_close`
- 定时器：`catforge-v4-g02-10`
- 前置 G01 artifact commit：`26aaf84`
- 前置 G01 closure commit：`6c3525c`
- 允许修改：V4 详细设计、G02 schema/trace/test 合同及本目录 G02 回执
- 禁止事项：运行代码、数据库/205 写入、部署、路由切换、提前执行 G03

## 当前门禁

| 门禁 | 状态 |
| --- | --- |
| 读取 G01 真实版本/字段/cohort 边界 | completed |
| 复用现有实现模式并压缩运行文件预算 | completed |
| 详细数据流和 typed schema | completed |
| 反事实/选择贡献/WTP 识别状态机 | completed |
| 产品经理主表和下钻 DTO | completed |
| 需求追溯矩阵 | completed |
| 单元/集成/真实回放测试计划 | completed |
| 性能预算和查询计划 | completed |
| plan-eng-review 无 P0/P1 | completed |

## 当前设计约束

1. 首版只读，不新增迁移；
2. 不重建 M11C/M11D/M12D；
3. 一个薄编排器，模型尽量用纯函数；
4. M12C 只复用池/档位，不消费旧金额；
5. promotion 只有疑似标记，inventory 明确 unavailable；
6. 65E7Q 封顶为市场选择关联，不能在设计样例中出现卖点组合 WTP 金额；
7. 已发布 M12D 与最新上游冲突必须由版本线谱闸门显式处理。

## 工程评审结论

- Review mode：`SCOPE_REDUCED`；
- unresolved decisions：0；
- critical gaps：0；
- issues found：1，已修复；
- 修复项：将 Q5 的“两条独立 A 级 pair 且跨两个 model family”同步进 typed schema、测试 fixture 和需求追溯；
- 运行范围仍为 3 个新增文件、2 层新增业务能力、默认关闭的显式 V4 路由；
- 多 SKU 结构需求模型因当前数据无法处理价格内生性而退出首版，不作为静默待办。
