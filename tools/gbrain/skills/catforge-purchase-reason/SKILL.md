---
name: catforge-purchase-reason
description: 基于授权项目脑已验证的事实和冻结的上游结果推导购买理由。
---

运行 reasons.py SNAPSHOT RESULTS。SNAPSHOT 为 sync.py 的原生回读目录，RESULTS 为该快照独享的结果目录。先构建 package_rules.py 规则包并将包的父目录加入 PYTHONPATH。默认计算目标 SKU，--all-members 可为候选全集生成输入。--without-claim-value 验证可选上游缺失的降级路径。理由成立、用户验证和阻力独立存储。 完成冻结后再打开工厂保存的历史输出进行对照。
