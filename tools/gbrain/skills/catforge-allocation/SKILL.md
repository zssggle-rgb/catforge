---
name: catforge-allocation
description: 基于授权项目脑已验证的事实和冻结的上游结果推导语义市场分配。
---

运行 value.py allocation SNAPSHOT RESULTS。SNAPSHOT 为 sync.py 的原生回读目录，RESULTS 为该快照独享的结果目录。先构建 package_rules.py 规则包并将包的父目录加入 PYTHONPATH。分别对每个 SKU、窗口、母体和维度检查分配权重、量额和未分配量。保存三份画像的内容哈希。 完成冻结后再打开工厂保存的历史输出进行对照。
