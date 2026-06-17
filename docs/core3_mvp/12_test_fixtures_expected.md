# 12 测试夹具与期望结果设计

## 1. 目标

Core3 MVP 需要确定性测试夹具，覆盖真实数据抽取、候选发现、任务/战场派生和三竞品选择。测试不能依赖外部 LLM。

建议新增：

```text
examples/core3/fixtures/tv_core3_sku_master.csv
examples/core3/fixtures/tv_core3_market_fact.csv
examples/core3/fixtures/tv_core3_sku_param.csv
examples/core3/fixtures/tv_core3_sku_claim.csv
examples/core3/fixtures/tv_core3_sku_comment.csv
examples/core3/expected/tv_core3_expected_min.json
```

测试可以通过 helper 将 CSV 导入现有 raw tables。

## 2. SKU 夹具矩阵

至少 10 个 SKU，覆盖三槽位和边界。

| sku_code | model | brand | 角色定位 | 目的 |
| --- | --- | --- | --- | --- |
| `TV00029115` | `85E7Q` | Hisense | 目标 SKU | 目标报告 |
| `TVCORE30001` | `85Q10K` | TCL | direct | 同尺寸、同价位、Mini LED、高刷 |
| `TVCORE30002` | `85X90L` | Sony | direct 备选 | 同尺寸高画质，价格略高 |
| `TVCORE30003` | `85U7N` | Hisense | pressure | 价格更低、销量更强 |
| `TVCORE30004` | `85C755` | TCL | pressure 备选 | 降价明显、销量强 |
| `TVCORE30005` | `85A95L` | Sony | benchmark_potential | OLED/高端标杆 |
| `TVCORE30006` | `85UX` | Hisense | benchmark 备选 | 更高亮度/更多分区 |
| `TVCORE30007` | `75GamePro` | BrandG | gaming strong | 游戏战场对比 |
| `TVCORE30008` | `85ValueMax` | BrandV | value large screen | 大屏性价比 |
| `TVCORE30009` | `65SimpleCare` | BrandS | senior/eye care | 长辈易用和护眼 |
| `TVCORE30010` | `85NoMarket` | BrandM | 缺量价 | 降级/不足原因 |
| `TVCORE30011` | `85NoComment` | BrandN | 缺评论 | 评论缺失不判 false |

## 3. 主数据 fixture

`tv_core3_sku_master.csv`

字段：

```text
sku_code,brand,model_name,series,category_name,launch_date,product_url
```

要求：

- `TV00029115.model_name=85E7Q`，用于型号解析。
- 至少两个型号包含 `85E7`，用于测试 409 多匹配时可构造额外行。
- `series` 用于同系列去重测试。

## 4. 市场事实 fixture

`tv_core3_market_fact.csv`

字段：

```text
sku_code,period,period_type,channel_group,channel_type,channel_name,sales_volume,sales_amount,avg_price,promotion_flag
```

每个关键 SKU 至少 6 个 period，最好 12 个 period。

期望市场关系：

- `TV00029115`：目标价位中高，销量中等。
- `TVCORE30001`：价格接近目标，销量略高。
- `TVCORE30003`：价格低 15%-25%，销量显著高，用于 pressure。
- `TVCORE30004`：近 3 个月价格下探明显，用于 pressure 备选。
- `TVCORE30005`：价格高 40% 以上，销额强，用于 benchmark。
- `TVCORE30010`：价格和销量为空，用于降级。

必须能验证：

- `price_wavg_12m`
- `price_latest`
- `sales_volume_12m`
- `channel_share`
- `price_drop_rate_3m`
- `sales_percentile`

## 5. 参数 fixture

`tv_core3_sku_param.csv`

字段：

```text
sku_code,raw_param_name,raw_param_value,raw_unit,source_channel,observed_at
```

必须覆盖的抽取样例：

| raw_param_name | raw_param_value | 期望 |
| --- | --- | --- |
| 屏幕尺寸 | 85英寸 | `screen_size_inch=85` |
| 峰值亮度 | 1600nits | `peak_brightness_nits=1600` |
| 控光分区 | 1296分区 | `dimming_zones=1296` |
| 原生刷新率 | 144Hz | `native_refresh_rate_hz=144` |
| HDMI2.1接口 | 2个 | `hdmi_2_1_ports=2` |
| 内存 | 4GB+64GB | `ram_gb=4`, `storage_gb=64` |
| 高频调光 | 3840Hz | `eye_dimming_freq_hz=3840` |
| 动态补偿 | 支持MEMC | candidate alias -> `motion_compensation_flag` |

边界：

- `TVCORE30010` 缺价格，但参数完整。
- `TVCORE30011` 参数完整，评论缺失。
- 某 SKU raw 参数字段为 `-`，必须 unknown。

## 6. 宣传卖点 fixture

`tv_core3_sku_claim.csv`

字段：

```text
sku_code,claim_title,claim_text,claim_order,source_channel,observed_at
```

必须覆盖：

- Mini LED / U+Mini。
- 高亮 HDR / XDR / nits。
- 分区控光 / 光晕控制。
- 高刷 / 144Hz / 120Hz。
- HDMI 2.1 / 满血接口。
- 护眼 / 低蓝光 / 无频闪。
- AI 画质芯片：未映射高频短语，进入 candidate claim。

否定测试：

- 文本 `不支持HDMI 2.1` 不得激活 `CLAIM_HDMI_2_1_GAMING`。

## 7. 评论 fixture

`tv_core3_sku_comment.csv`

字段：

```text
sku_code,platform,comment_id,comment_text,rating,comment_time,dimension_1,dimension_2,dimension_3
```

必须覆盖评论句：

- 画质清晰、亮度够、白天看也清楚。
- 看球不卡、运动画面流畅。
- 接游戏主机延迟低。
- 看久不刺眼。
- 爸妈操作简单。
- 音响效果不错。
- 安装师傅及时。
- 开机广告多：未映射或系统风险主题。

边界：

- `TVCORE30011` 无评论，用于验证评论缺失不判 false。
- 服务体验评论不能直接激活产品卖点。

## 8. Expected JSON

`tv_core3_expected_min.json`

结构：

```json
{
  "target_sku_code": "TV00029115",
  "target_model_query": "85E7Q",
  "must_extract_params": {
    "screen_size_inch": 85,
    "native_refresh_rate_hz": 144,
    "peak_brightness_nits": 1600,
    "dimming_zones": 1296,
    "hdmi_2_1_ports": 2
  },
  "must_activate_claims": [
    "CLAIM_MINI_LED_BACKLIGHT",
    "CLAIM_HIGH_BRIGHTNESS_HDR",
    "CLAIM_FINE_LOCAL_DIMMING",
    "CLAIM_HIGH_REFRESH_RATE",
    "CLAIM_HDMI_2_1_GAMING"
  ],
  "must_detect_topics": [
    "TOPIC_PICTURE_QUALITY",
    "TOPIC_GAMING_SMOOTHNESS",
    "TOPIC_SPORTS_WATCHING"
  ],
  "must_score_tasks": [
    "TASK_PREMIUM_PICTURE_AV",
    "TASK_GAMING_ENTERTAINMENT",
    "TASK_LIVING_ROOM_CINEMA"
  ],
  "must_enter_battlefields": [
    "BF_PREMIUM_PICTURE",
    "BF_GAMING_SPORTS",
    "BF_FAMILY_VIEWING_UPGRADE"
  ],
  "expected_core3_roles": {
    "direct": "TVCORE30001",
    "pressure": "TVCORE30003",
    "benchmark_potential": "TVCORE30005"
  },
  "must_have_candidate_diagnostics": [
    "candidate_param_alias",
    "candidate_claim",
    "candidate_comment_topic"
  ]
}
```

## 9. 后端测试命名

建议测试函数：

```text
test_core3_data_status_and_sku_resolution
test_core3_seed_v02_schema_and_references
test_core3_extracts_params_from_real_rows
test_core3_detects_claim_activation_components
test_core3_comment_topics_include_evidence_sentences
test_core3_candidate_assets_are_diagnostics_not_final_assets
test_core3_market_profile_changes_with_sales_and_price
test_core3_tasks_groups_battlefields_are_derived_from_signals
test_core3_selects_direct_pressure_benchmark_without_duplicates
test_core3_degrades_missing_market_or_comments_without_false_values
test_core3_exports_csv_and_jsonl
```

## 10. 验收

- fixture 能在 SQLite 测试库导入 raw tables。
- expected JSON 与 API 输出可自动比对。
- 所有抽取、派生、竞品选择测试不依赖网络和外部 LLM。
- 修改 fixture 中价格或销量时，pressure 或 market_score 测试会失败，证明量价真的参与。
- 删除评论时，评论主题为空但不会产生 false 结论。

