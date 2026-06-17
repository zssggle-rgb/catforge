# 08 报告、页面工作流与导出模块

## 1. 模块目标

把核心三竞品结果组织成可演示、可复核、可导出的报告。这里不按前端/后端拆分，而按用户看到和使用的工作流设计数据契约。

## 2. 页面工作流

MVP 页面组只有三页：

1. 批量总览。
2. 单 SKU 竞品报告。
3. 竞品证据卡。

页面入口独立：

```text
彩电核心三竞品 MVP
```

不放进 Goal3 工作台子菜单。

## 3. 批量总览

### 3.1 用户目标

证明系统能对一批 SKU 产出核心三竞品组合，并能看出哪些结果可信、哪些需要复核。

### 3.2 数据契约

API：

```text
GET /api/mvp/core3/projects/{project_id}/overview
```

响应：

```json
{
  "project_id": "...",
  "latest_run_id": "...",
  "analyzed_sku_count": 1000,
  "confidence_distribution": {
    "high": 720,
    "medium": 210,
    "low": 70
  },
  "insufficient_reason_top5": [],
  "rows": []
}
```

行字段：

- `target_sku_code`
- `brand`
- `model_name`
- `primary_battlefield`
- `direct_competitor`
- `pressure_competitor`
- `benchmark_potential_competitor`
- `confidence_level`
- `review_flag`
- `insufficient_reasons`

### 3.3 操作

- 刷新数据状态。
- 运行批量生成。
- 导出 CSV。
- 导出 JSONL。

## 4. 单 SKU 竞品报告

### 4.1 用户目标

输入一个型号或 SKU，查看目标 SKU 为什么进入某些任务/战场，以及三个核心竞品是什么。

### 4.2 数据契约

API：

```text
GET /api/mvp/core3/projects/{project_id}/sku/{sku_or_model}/report
```

响应：

```json
{
  "target_sku": {},
  "market_profile": {},
  "standard_params": {},
  "activated_claims": [],
  "comment_topics": [],
  "tasks": [],
  "target_groups": [],
  "battlefields": [],
  "core_competitors": [],
  "confidence_level": "high",
  "review_flag": false,
  "insufficient_reasons": []
}
```

### 4.3 展示结构

从上到下：

1. 搜索区：输入 `sku_code` 或型号。
2. 目标 SKU 市场画像：价格、销量、渠道、趋势。
3. 核心参数：尺寸、Mini LED、刷新率、亮度、分区、HDMI。
4. 激活卖点：卖点名、激活分、证据数。
5. 用户任务、目标客群、价值战场。
6. 三竞品卡：direct / pressure / benchmark_potential。

三竞品卡字段：

- 角色中文名。
- 竞品品牌/型号/SKU。
- 分数。
- 置信度。
- 业务理由。
- 关键组件分。
- 查看证据按钮。

## 5. 竞品证据卡

### 5.1 用户目标

解释“为什么选它，而不是只输出列表”。

### 5.2 数据契约

API：

```text
GET /api/mvp/core3/projects/{project_id}/sku/{sku_or_model}/competitors/evidence
```

响应：

```json
{
  "target_sku_code": "TV00029115",
  "count": 3,
  "items": [
    {
      "role": "direct",
      "competitor_sku_code": "TV00030001",
      "evidence_card": {},
      "evidence_items": []
    }
  ]
}
```

### 5.3 展示结构

每个角色展示：

- 价格对比。
- 销量对比。
- 渠道重合。
- 参数对比。
- 标准卖点对比。
- 任务/战场相似度。
- 评论证据。
- evidence_id 表格。

无竞品时：

- 展示不足原因。
- 不渲染空白对比卡。

## 6. 导出

### 6.1 CSV

API：

```text
GET /api/mvp/core3/projects/{project_id}/export/core3.csv
```

文件名：

```text
sku_competitor_core3.csv
```

字段：

```text
target_sku_code,role,competitor_sku_code,score,reason,confidence,confidence_level,review_flag,insufficient_reasons
```

### 6.2 JSONL

API：

```text
GET /api/mvp/core3/projects/{project_id}/export/evidence-cards.jsonl
```

文件名：

```text
evidence_cards.jsonl
```

每行：

```json
{"target_sku_code":"...","role":"direct","competitor_sku_code":"...","evidence_card":{}}
```

## 7. 前端文件组织

```text
apps/factory-web/src/pages/core3/
  Core3Mvp.tsx
  core3Pages.ts
  core3Format.ts
  core3Pages.test.ts
```

`Core3Mvp.tsx` 内部按工作流拆组件：

- `Core3OverviewPanel`
- `Core3SkuReportPanel`
- `Core3EvidencePanel`
- `Core3CompetitorCard`
- `Core3EvidenceTable`

## 8. 错误处理

| API 状态 | 页面处理 |
| --- | --- |
| 404 SKU 不存在 | 提示未找到 SKU 或型号 |
| 409 多个型号匹配 | 展示候选选择表 |
| 422 数据不足 | 展示不足原因 |
| 500 未预期错误 | 展示生成失败，不暴露堆栈 |

## 9. 验收

- 首屏就是可操作工作台，不做营销落地页。
- 三页互相独立但共享当前项目和目标 SKU。
- 单 SKU 报告可从 `85E7Q` 搜索到结果。
- 证据卡能展开 evidence_id。
- 导出文件字段符合契约。

