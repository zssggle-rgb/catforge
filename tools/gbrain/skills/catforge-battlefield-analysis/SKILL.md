---
name: catforge-battlefield-analysis
description: 从冻结定位画像与市场分配解释 SKU 的领先战场、证据缺口和角色系数敏感度。
---

先冻结三类定位画像，运行 `value.py allocation SNAPSHOT RESULTS`，再运行 `battlefield_analysis.py SNAPSHOT RESULTS`。程序检查快照和上游内容哈希，输出 `battlefield-analysis.json`。每个快照使用独立的结果目录。

用 `value_graph.py SNAPSHOT RESULTS STAGE` 为目标 SKU 生成分配、卖点价值、购买理由与战场分析页面，再在同一实例导入并提取关系。先导入对应的事实与定位画像。每次成功计算都保留 `revisions/<结果名>/<内容哈希>.json`，可按历史判断记录中的哈希回放。用 `compare_value.py SNAPSHOT RESULTS HOLDOUT_JSONL RECEIPT` 核对冻结后的历史参考。只有规则、窗口、母体和上游版本一致的结果可作等值验收。

引用领先两项的适配分、角色、分差、参数支持、评论正负向、证据来源和市场限制。披露本批次卖点覆盖。对次级角色系数 0.60、0.70、0.80 分别用该 SKU 全部入围战场重新归一化。列出同一窗口内目标 SKU 和整个母体各维度的观测量额、模型分配、未分配和舍入差。遇到缺失价格、缺失卖点或无可分配候选应保留未知状态。小票和执行结果缺失时，真实购买动机、销量因果效应保持未知。
