# 04 分词、语义抽取与资产候选生成

## 1. 模块定位

这一层是 v2 设计的关键补充。它回答：

- 数据里有哪些真实参数字段。
- 数据里有哪些真实宣传卖点。
- 用户评论实际在说什么。
- 哪些字段、短语、主题是已知资产能解释的。
- 哪些内容是新候选，需要进入复核。

它不是最终竞品算法，但决定竞品报告是否可信。

## 2. 模块拆分

```text
semantic/
  tokenizer.py
  phrase_miner.py
  param_extractor.py
  claim_extractor.py
  comment_topic_extractor.py
  asset_candidate_generator.py
  mapping_candidate_generator.py
  semantic_evidence.py
```

## 3. 分词与短语抽取

### 3.1 首版策略

MVP 可采用确定性方法，不依赖外部 LLM：

1. 业务词典优先。
2. 正则识别数值实体。
3. 字符 n-gram 抽取高频短语。
4. 预制关键词匹配。
5. 共现统计。

如果引入 `jieba` 或其他中文分词库，应通过封装层接入，不让业务逻辑依赖具体分词实现。

### 3.2 业务词典来源

业务词典不等于 SKU 写死，来源包括：

- 已批准标准参数别名。
- 已批准标准卖点关键词。
- 已批准评论主题关键词。
- 彩电通用技术词：Mini LED、OLED、量子点、HDR、刷新率、HDMI、分区、峰值亮度、护眼、低蓝光、杜比、AI、语音、投屏。
- 从当前批次高频短语挖掘出的候选词。

### 3.3 数值实体

必须识别：

| 类型 | 示例 | 输出 |
| --- | --- | --- |
| 尺寸 | `85英寸`、`85寸` | `screen_size_inch=85` |
| 刷新率 | `120Hz`、`144Hz`、`300Hz` | `refresh_rate_hz` 或待判别 |
| 亮度 | `1600nits`、`5200尼特` | `peak_brightness_nits` 候选 |
| 分区 | `1296分区`、`千级分区` | `dimming_zones` |
| HDMI | `2个HDMI2.1` | `hdmi_2_1_ports` |
| 内存 | `4GB+64GB` | `ram_gb`、`rom_gb` |
| 色域 | `95% DCI-P3` | `color_gamut_percent` |
| 功率 | `60W` | `speaker_power_watt` |
| 延迟 | `8ms` | `input_lag_ms` |

## 4. 参数抽取

### 4.1 输入

- `core3_clean_param_fact`
- `core3_clean_claim_sentence` 中的数值实体。
- 型号名。
- 标准参数 seed。
- 参数候选别名。

### 4.2 字段匹配

匹配顺序：

```text
exact alias
  -> contains alias
  -> token synonym
  -> semantic phrase candidate
  -> unmapped candidate
```

输出必须保留：

- raw field。
- matched param。
- match type。
- confidence。
- examples。
- evidence。

### 4.3 值解析

每个标准参数绑定 parser：

```text
inch
hz
nits
zones
gb
ports
resolution
percentage
watt
ms
boolean_keyword
enum_keyword
```

### 4.4 冲突

冲突不直接丢弃：

- 原生刷新率和运动补偿刷新率应拆成不同参数。
- raw 参数和卖点文本冲突时进入冲突表。
- 冲突降低参数置信度，并进入复核队列。

## 5. 卖点抽取与标准卖点激活

### 5.1 卖点不是抽象战场

不能把“高端画质”“游戏体育”直接当卖点。卖点要可证据化：

- Mini LED 背光。
- 高亮 HDR。
- 精细分区控光。
- 高刷新率。
- HDMI 2.1 游戏连接。
- 低延迟。
- 护眼。
- 音画沉浸。
- 智能语音。

### 5.2 激活证据

每个卖点拆三类证据：

```text
param_score
promo_score
comment_score
```

技术型卖点权重：

```text
参数 0.55 + 宣传 0.35 + 评论 0.10
```

体验型卖点权重：

```text
参数 0.30 + 宣传 0.30 + 评论 0.40
```

市场型卖点权重：

```text
市场 0.50 + 宣传 0.20 + 评论 0.30
```

unknown 信号重归一：

```text
activation_score = known_weighted_score / known_weight_sum
confidence = base_confidence * known_weight_sum / total_weight
```

### 5.3 候选卖点

从宣传短语中发现候选卖点：

进入条件：

- 覆盖 SKU 数达到阈值。
- 与现有卖点相似度低。
- 有样例句。
- 与参数、评论、价格或销量有共现。

候选卖点默认不参与高置信结论，只进入复核和低置信提示。

## 6. 评论主题抽取

### 6.1 先分类，再主题

先判断句子类型：

- 产品体验。
- 服务体验。
- 物流安装。
- 价格感知。
- 未知。

再判断主题：

- 画质清晰。
- 亮度和 HDR。
- 运动流畅。
- 游戏连接。
- 音响沉浸。
- 系统流畅。
- 操作易用。
- 护眼舒适。
- 安装服务。
- 价格划算。

服务体验可以支持“服务保障战场”，不能激活“画质”“游戏”等产品卖点。

### 6.2 情感判断

首版使用规则：

- 正向词：好、清晰、流畅、满意、舒服、方便、够用、专业、喜欢、爽。
- 负向词：卡、慢、刺眼、反光、漏光、拖影、麻烦、广告多、贵、故障、差、模糊。
- 否定窗口：不、没有、没、无。

输出：

- positive。
- negative。
- neutral。
- mixed。

### 6.3 评论主题汇总

SKU 级主题汇总：

```text
mention_count
mention_rate
positive_rate
negative_rate
sample_sentences
evidence_ids
confidence
```

评论数少时降低置信度，不能把缺失当负面。

## 7. 用户任务候选

用户任务不是直接从评论抽标签，而是从卖点、参数、评论和市场共现推导。

候选任务来源：

- seed 本体。
- 高频卖点组合。
- 高频评论主题组合。
- 同价格带/同渠道高销量 SKU 的共性。

示例：

```text
TASK_GAMING_ENTERTAINMENT
  参数：高刷、HDMI2.1、低延迟
  卖点：游戏连接、运动流畅
  评论：游戏流畅、看球不卡
  市场：线上渠道、高刷池销量表现
```

MVP 第一版建议 seed 中预制完整常用任务，数据只负责激活和校准；新任务只进入候选。

## 8. 目标客群候选

客群来自任务和市场位置，不直接从单句文本提取。

示例：

```text
游戏用户 =
  游戏娱乐任务
  + 线上渠道适配
  + 中高价位性能诉求
  + 游戏/体育评论验证
```

候选客群需要：

- 来源任务。
- 价格带信号。
- 渠道信号。
- 评论语言样例。
- 示例 SKU。

## 9. 价值战场候选

价值战场来自任务、客群、卖点组合和市场验证。

示例：

```text
游戏体育战场 =
  高刷 + HDMI2.1 + 低延迟 + 运动流畅评论
  + 线上渠道表现
  + 同战场可比 SKU 有销量密度
```

战场不是因为文档里写了“游戏体育”就成立。必须回答两个问题：

1. 目标 SKU 是否主要在这个战场竞争。
2. 候选 SKU 是否也主要在这个战场竞争。

只有双方战场重合，才支持“正面对打”解释。

## 10. 映射候选

生成以下映射候选：

- 参数 -> 卖点。
- 卖点 -> 任务。
- 评论主题 -> 卖点。
- 评论主题 -> 任务。
- 任务 -> 客群。
- 任务 -> 战场。
- 卖点 -> 战场。
- 战场 -> 竞品规则。

每条映射包含：

- source code。
- target code。
- weight。
- condition。
- evidence basis。
- confidence。
- review status。

## 11. 语义抽取验收

必须证明：

1. 参数不是按 SKU 写死，而是由字段和文本解析得到。
2. 卖点不是按型号写死，而是由参数、宣传和评论激活。
3. 评论主题有样例句和情感。
4. 新字段、新短语、新主题进入候选资产。
5. 用户任务、客群、战场由已抽取信号推导，不直接从原文贴标签。
6. 低置信候选不进入高置信业务结论。

