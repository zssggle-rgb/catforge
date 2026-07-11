# V5-G01 进度

- Goal：205 真实数据只读覆盖基准、Gold Set 和可重放 manifest；
- active timer：`catforge-v5-g01-10`；
- 允许路径：本目录 G01 文档、fixture 和只读探针；
- 运行代码修改：0；
- 数据库/205 写入：0/0；
- 已完成：表结构和版本实时探针、M14 可用性、M11C/M11D、价格曲线、多层反事实覆盖、C01-C08 cohort 和 65E7Q 快照；
- 确定性：完整 stdout 双跑 SHA-256 均为 `d6c0bd60d9c35cef56cfb275c1a0d0d5375cf400b85b22dcd2f39e2bf1f468d6`；
- 关键修正：288 是 excluded 可召回候选，不是已通过尺寸/价格门槛的可拓展战场；
- 待完成：JSON/脚本校验、精确提交、manifest/关闭回执、删除定时器并关闭 Goal。
