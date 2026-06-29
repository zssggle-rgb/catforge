# CatForge Analyst 用户卖点价值看板详细设计

## 1. 设计目标

本文承接 [CatForge Analyst 用户卖点价值看板需求](../sop_requirements/CATFORGE_ANALYST_claim_value_dashboard_requirements.md)，定义 `catforge_analyst` 用户卖点价值看板的工程实现方案。

设计目标：

1. 复用 M12C 已生成的 SKU 卖点价值量化结果，不重算量化逻辑。
2. 由 CLI 生成稳定的 `short_answer`、`dashboard_payload`、`feishu_card_payload` 和飞书详细报告链接。
3. 飞书会话主屏展示卡片式看板，用户不用先打开长文档也能看到关键结论。
4. 详细推导、完整卖点表和计算口径继续放在飞书 Markdown 报告中。
5. Skill 只负责路由和卡片发送，不解析大 JSON，不重新组织业务结论。
6. 默认业务展示不出现原始可比池组间差、内部字段名、批次号和调试信息。

## 2. 总体架构

```text
用户问题
  -> 小奥 Skill / OpenClaw 飞书入口
  -> catforge_analyst ask 或 sku-claim-value
       -> SKUResolver
       -> AnalystRepository.sku_claim_value()
       -> ClaimValueAnswerRenderer
       -> ClaimValueDashboardPayloadBuilder
       -> ClaimValueFeishuCardRenderer
       -> ClaimValueReportRenderer
       -> FeishuReportPublisher
       -> FeishuCardReplyPublisher
  -> short_answer + feishu_card_payload + report_url
```

模块职责：

| 模块 | 职责 |
| --- | --- |
| Skill | 识别“用户卖点价值/溢价卖点/卖点值多少钱”意图，调用 CLI，并在飞书入口传入 message_id |
| CLI | 参数解析、调用服务、输出 text/json、发送飞书卡片 |
| AnalystRepository | 读取 M12C SKU 层和战场层结果 |
| ClaimValueAnswerRenderer | 生成 600 字短答和 Markdown 报告 |
| ClaimValueDashboardPayloadBuilder | 把 M12C payload 裁剪成会话看板 payload |
| ClaimValueFeishuCardRenderer | 把 dashboard payload 渲染成飞书卡片 JSON |
| FeishuReportPublisher | 创建飞书详细报告并设置链接权限 |
| FeishuCardReplyPublisher | 回复飞书消息，发送卡片 |

## 3. 数据流

### 3.1 输入

`sku-claim-value` 已返回：

```json
{
  "target": {},
  "result": {
    "sku_claim_value": {
      "sku_level_claim_values": [],
      "claim_values": [],
      "attributions": [],
      "method_note_cn": ""
    },
    "claim_value_answer": {
      "short_answer": "",
      "report": {}
    }
  }
}
```

看板只消费 `sku_claim_value` 和 `claim_value_answer.report.url`。

### 3.2 输出

`claim_value_answer` 增加：

```json
{
  "short_answer": "600字以内短答",
  "dashboard_payload": {},
  "feishu_card_payload": {},
  "report": {
    "status": "created",
    "url": "https://..."
  },
  "report_title": "海信 65E7Q 用户卖点价值分析报告"
}
```

## 4. Dashboard Payload 设计

### 4.1 Schema

```json
{
  "schema_version": "claim_value_dashboard_v1",
  "title": "海信 65E7Q 用户卖点价值看板",
  "target": {
    "sku_code": "TV00029112",
    "brand_name": "海信",
    "model_name": "65E7Q",
    "display_name": "海信 65E7Q",
    "market_summary": "65寸高价带，均价约5949元，周均约251台"
  },
  "summary_cn": "正向支付价值集中在...",
  "claim_structure": [
    {
      "category": "高溢价卖点",
      "count": 4,
      "amount_sum": 506,
      "sales_lift_sum": 14.9
    }
  ],
  "top_claims": [
    {
      "rank": 1,
      "claim_code": "tv_claim_hdr_high_brightness",
      "claim_name": "5200nits 高亮档位",
      "business_type": "高溢价卖点",
      "main_contexts": ["高端画质升级战场"],
      "explainable_amount_cn": "约60元",
      "explainable_sales_cn": "约5.4台/周",
      "parameter_strength_cn": "领先优势",
      "evidence_cn": "亮度参数领先、评论正向、市场承接成立"
    }
  ],
  "battlefield_sources": [
    {
      "battlefield_name": "高端画质升级战场",
      "positive_claims": ["5200nits 高亮档位", "98% 色彩表现", "1920 分区控光"],
      "amount_sum_cn": "约168元",
      "sales_lift_sum_cn": "约15台/周"
    }
  ],
  "activation_and_risk": [
    {
      "category": "门槛卖点",
      "claims": ["HDMI2.1 连接", "MiniLED 显示/背光", "杜比/影音认证"],
      "meaning_cn": "有助于入围，不单独解释加价"
    }
  ],
  "report_evidence_links": [
    {
      "label": "查看完整报告",
      "url": "https://...",
      "type": "report"
    }
  ],
  "display_policy": {
    "main_answer": "feishu_card",
    "report_as_evidence": true,
    "card_delivery_stdout": true,
    "fallback_to_short_answer": true,
    "hide_internal_fields": true
  }
}
```

### 4.2 字段生成规则

| 字段 | 生成规则 |
| --- | --- |
| `summary_cn` | 由目标名、Top 正向卖点、主要战场和门槛/待激活提醒拼接 |
| `claim_structure` | 按 M12C 业务分类统计本品已成立卖点和竞品拦截项 |
| `top_claims` | 优先正向分类；默认最多 5 条；人无我有显示潜力等级，不显示金额 |
| `battlefield_sources` | 从 `claim_values` 中聚合正向卖点的 `context_name` |
| `activation_and_risk` | 从门槛、待激活、厂家主张、竞品拦截、价格压力中各取重点项 |
| `report_evidence_links` | 使用本次 `with_report` 生成的飞书文档 URL |

## 5. Top 卖点选择算法

### 5.1 分类优先级

```text
高溢价卖点
-> 份额转化卖点
-> 客户获得价值卖点
-> 人无我有型支付价值卖点
-> 门槛卖点
-> 待激活卖点
```

卡片 Top 表默认只展示前四类。门槛和待激活进入“待激活/风险提示”区，不与正向 Top 混排。

### 5.2 排序字段

对同一分类内部排序：

```text
可解释金额 desc
-> 可解释销量 desc
-> 参数竞争力分 desc
-> 评论感知强度 desc
-> 卖点名称
```

人无我有型支付价值卖点使用：

```text
潜力分 desc
-> 参数竞争力分 desc
-> 评论感知强度 desc
```

### 5.3 金额展示

金额只允许来自最终分摊字段：

- `sku_level_user_payment_value_abs`
- `sku_excess_price_explained_abs`
- `price_premium_abs`，仅在其语义已经是本品可解释分摊时使用

禁止展示：

- `pool_claim_price_delta_abs`
- `_pool_claim_price_delta_abs`
- `pool_claim_weekly_sales_delta_abs`
- 任何“有卖点组 vs 对照组”的原始组间差

## 6. 飞书卡片设计

### 6.1 卡片结构

飞书卡片使用 JSON 2.0，结构如下：

```text
header: 海信 65E7Q 用户卖点价值看板
body:
  1. Markdown 结论
  2. 卖点价值结构图
  3. Top 卖点表
  4. 价值战场来源图/表
  5. 待激活与风险提示
  6. 查看完整报告按钮
```

### 6.2 结论区

```markdown
**结论：正向支付价值集中在 300Hz 高刷、5200nits 高亮、98% 色彩和 1920 分区控光**
高亮、色彩和分区控光主要支撑高端画质升级；300Hz 高刷主要支撑游戏体育流畅。HDMI2.1、MiniLED 和杜比当前更偏入围门槛，不单独解释加价。
```

### 6.3 卖点价值结构图

优先使用 `chart` 横向堆叠条：

```json
{
  "type": "bar",
  "direction": "horizontal",
  "xField": "count",
  "yField": "target",
  "seriesField": "category",
  "stack": true
}
```

维度：

- 高溢价
- 份额转化
- 人无我有
- 门槛
- 待激活
- 竞品拦截
- 价格压力

如果飞书卡片图表不可用，降级为 Markdown：

```text
高溢价 4 个｜门槛 3 个｜待激活 3 个｜竞品拦截 3 个
```

### 6.4 Top 卖点表

使用飞书 `table`：

| 列 | 宽度 | 说明 |
| --- | --- | --- |
| 卖点 | auto | 卖点业务名 |
| 分类 | 120px | 高溢价/份额转化/人无我有 |
| 战场 | auto | 主要成立战场 |
| 价值 | 120px | 金额或潜力等级 |
| 证据 | auto | 参数/评论/市场摘要 |

示例：

| 卖点 | 分类 | 战场 | 价值 | 证据 |
| --- | --- | --- | --- | --- |
| 5200nits 高亮 | 高溢价 | 高端画质 | 约60元 | 亮度领先、评论正向 |
| 300Hz 高刷 | 高溢价 | 游戏流畅 | 约339元 | 刷新率领先 |

### 6.5 价值战场来源

使用 `bar` 或短表：

| 战场 | 正向卖点 | 可解释价值 |
| --- | --- | --- |
| 高端画质升级 | 高亮、色彩、分区控光 | 约168元 |
| 游戏体育流畅 | 300Hz 高刷 | 约339元 |

### 6.6 待激活与风险提示

展示不超过 3 组：

```markdown
**待激活/风险**
- 门槛卖点：HDMI2.1、MiniLED、杜比，有助于入围，不单独加价。
- 待激活卖点：芯片、AI 画质、游戏低延迟，产品基础存在，但用户感知和市场验证仍需加强。
- 竞品拦截：若有，展示竞品侧已形成优势、本品需要补强的方向。
```

### 6.7 完整报告按钮

复用竞品卡片的按钮样式：

```json
{
  "tag": "button",
  "type": "primary",
  "text": {"tag": "plain_text", "content": "查看完整报告"},
  "behaviors": [{"type": "open_url", "default_url": "{report_url}"}]
}
```

## 7. CLI 设计

### 7.1 新增输出

在 `build_claim_value_answer()` 中新增：

```python
dashboard_payload = build_claim_value_dashboard_payload(
    target=target,
    payload=payload,
    report_url=publish_result.url,
)
feishu_card_payload = render_claim_value_feishu_card_payload(dashboard_payload)
```

返回：

```python
return {
    "short_answer": short_answer,
    "dashboard_payload": dashboard_payload,
    "feishu_card_payload": feishu_card_payload,
    "report": report,
    "markdown": ...,
    "report_title": title,
}
```

### 7.2 卡片发送

当前 `attach_feishu_card_delivery()` 只读取 `competitor_answer.feishu_card_payload`。需要扩展为：

```python
card = (
    result["result"].get("competitor_answer", {}).get("feishu_card_payload")
    or result["result"].get("claim_value_answer", {}).get("feishu_card_payload")
)
```

发送结果写回对应 answer：

```json
{
  "claim_value_answer": {
    "feishu_card_delivery": {
      "status": "sent",
      "message_cn": "已发送飞书用户卖点价值看板卡片。"
    }
  }
}
```

`format_feishu_card_delivery_text()` 也要识别 `claim_value_answer.feishu_card_delivery`。

## 8. Markdown 报告联动

`render_claim_value_report()` 顶部新增：

```markdown
## 用户卖点价值看板

{dashboard markdown}
```

`render_claim_value_dashboard_markdown()` 输出：

1. 看板结论。
2. 卖点价值结构。
3. Top 卖点表。
4. 价值战场来源表。
5. 待激活和风险提示。

报告中的看板内容必须与飞书卡片使用同一个 `dashboard_payload`，避免卡片和报告口径不一致。

## 9. Skill 设计

小奥 Skill 中新增固定 SOP：

```text
当用户问题包含：
用户卖点价值 / 卖点支付价值 / 溢价卖点 / 哪些卖点值钱 / 卖点能支撑多少钱

调用：
python -m app.cli.catforge_analyst ask \
  --query "{sku_or_model}" \
  --answer-style xiaoao \
  --with-report feishu-doc \
  --format text \
  --feishu-reply-message-id "{message_id}" \
  --feishu-card-only \
  "{原始问题}"
```

边界：

- Skill 不自行改写 Top 卖点。
- Skill 不解释“价值分”。
- Skill 不展示本地 Markdown 路径。
- Skill 如果拿不到 message_id，降级为文本短答 + 飞书报告链接。

## 10. 错误与降级

| 错误 | 处理 |
| --- | --- |
| SKU 未找到 | 返回候选列表，要求二次选择 |
| M12C 结果为空 | 提示需要先执行 M12C 卖点价值量化 |
| 飞书报告创建失败 | 卡片仍展示，按钮不显示或显示“报告暂未生成” |
| 飞书卡片发送失败 | stdout 返回“飞书看板卡片发送失败：{业务原因}” |
| 卡片内容超长 | 裁剪 Top 卖点为 5 条，风险提示每类最多 3 条 |
| 图表渲染不支持 | 降级为 Markdown 结构条和普通表格 |

## 11. 测试设计

### 11.1 单元测试

新增测试文件或扩展 `test_claim_value_answer.py`：

1. `test_build_claim_value_dashboard_payload_groups_claims`
   - 输入包含高溢价、门槛、待激活、竞品拦截。
   - 断言 `claim_structure` 统计正确。

2. `test_claim_value_dashboard_top_claims_excludes_threshold_from_premium`
   - HDMI2.1、MiniLED、杜比不得出现在正向 Top 高溢价中。

3. `test_claim_value_dashboard_hides_raw_pool_delta`
   - payload 中有 `pool_claim_price_delta_abs=1964`。
   - 卡片和 dashboard markdown 不得包含 `1964元` 或 `可比池价格差异`。

4. `test_render_claim_value_feishu_card_payload_contains_report_button`
   - 有 report_url 时卡片包含 `查看完整报告` 按钮。

5. `test_attach_feishu_card_delivery_supports_claim_value_answer`
   - mock 飞书发送函数，确认 `claim_value_answer.feishu_card_payload` 可被发送。

### 11.2 CLI 测试

1. `sku-claim-value --answer-style xiaoao --with-report markdown --format json`
   - 返回 `dashboard_payload` 和 `feishu_card_payload`。

2. `ask --answer-style xiaoao --with-report markdown --format text`
   - 输出短答，不输出 JSON。

3. `--feishu-card-only` 缺少 message_id
   - 输出卡片未发送原因，不回退大段 JSON。

### 11.3 205 验收

以海信 65E7Q：

```bash
python -m app.cli.catforge_analyst ask \
  --answer-style xiaoao \
  --with-report feishu-doc \
  --format text \
  "海信 65E7Q 的用户卖点价值是什么"
```

验收：

- 输出飞书报告链接。
- 飞书卡片可在飞书会话中展示。
- 卡片不出现上千元原始可比池差。
- 卡片 Top 卖点与 M12C 当前结果一致。

## 12. 实现顺序

1. 新增 `build_claim_value_dashboard_payload()`。
2. 新增 `render_claim_value_feishu_card_payload()`。
3. 新增 `render_claim_value_dashboard_markdown()`。
4. 在 `build_claim_value_answer()` 中接入 dashboard 和 card payload。
5. 扩展 `catforge_analyst.attach_feishu_card_delivery()` 支持 `claim_value_answer`。
6. 扩展 text 输出中卡片发送状态格式化。
7. 更新小奥 Skill 的用户卖点价值 SOP。
8. 增加单元测试。
9. 部署 205，用海信 65E7Q 生成飞书卡片和报告验收。

## 13. 不变式

1. 看板只展示最终业务解释结果，不展示原始组间差。
2. 正向 Top 卖点只来自本品已成立卖点或 M12C 明确可展示的参数档位价值理由。
3. 竞品拦截项单独展示，不混入本品正向 Top。
4. 人无我有型支付价值卖点不展示金额，只展示潜力等级和验证条件。
5. 所有金额和销量都必须是解释性分摊，不写成严格因果收益。
6. 飞书卡片和 Markdown 报告必须共用同一个 dashboard payload。
7. Skill 不参与计算和改写，只调用 CLI。
