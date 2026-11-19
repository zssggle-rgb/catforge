---
name: catforge-claim-value
description: 基于授权项目脑已验证的事实和冻结的上游结果推导卖点价值量化。
---

运行 value.py claim-value SNAPSHOT RESULTS。SNAPSHOT 为 sync.py 的原生回读目录，RESULTS 为该快照独享的结果目录。先构建 package_rules.py 规则包并将包的父目录加入 PYTHONPATH。从同一快照的服务批次卖点、参数、评论、市场、战场评分与分配结果生成可比池、量价和解释性归因。保留样本范围、样本限制和证据。 完成冻结后再打开工厂保存的历史输出进行对照。
