---
name: catforge-target-group
description: 从 GBrain 已验证的 SKU 事实快照独立推导目标客群画像和全部候选评分。
---

以 sync.py 回执指定的 readback 目录为输入。使用 package_rules.py 构建规则包，将其父目录加入 PYTHONPATH，运行 profiles.py SNAPSHOT OUTPUT --domain target-group。M10C 读取本领域定义、固定批次的参数和卖点、服务批次的评论以及同尺寸价格和共同周市场观测。保留完整评分分解、负面和缺失信号及复核状态。词表间引用描述定义关系。每次运行只加载指定领域的规则和共享事实，不读取其他领域的评分或工厂输出。结果冻结后运行对照。
