# 01 数据读取与源表适配

## 1. 模块目标

本模块只负责把 PostgreSQL 中的项目数据读成统一输入对象，不做竞品判断。

输入：

- `project_id`
- 可选 `sku_or_model`
- 读取范围：当前项目、`category_code=TV`

输出：

- `Core3InputBundle`
- `ResolvedTargetSku`
- `DataStatus`

## 2. 源表映射

| 文档源 | 当前 CatForge 表 | MVP 字段 |
| --- | --- | --- |
| `sku_master` | `raw_sku_master` | `sku_code`, `brand`, `model_name`, `series`, `category_name`, `source_file_id`, `raw_row_id` |
| `market_fact` | `raw_market_fact` | `sku_code`, `period`, `period_type`, `channel_type`, `channel_name`, `sales_volume`, `sales_amount`, `avg_price`, `source_file_id`, `raw_row_id` |
| `sku_param_raw` | `raw_sku_param` | `sku_code`, `raw_param_name`, `raw_param_value`, `raw_unit`, `source_channel`, `observed_at`, `source_file_id`, `raw_row_id` |
| `sku_claim_raw` | `raw_sku_claim` | `sku_code`, `claim_title`, `claim_text`, `source_channel`, `observed_at`, `source_file_id`, `raw_row_id` |
| `sku_comment_raw` | `raw_sku_comment` | `sku_code`, `platform`, `comment_id`, `comment_text`, `rating`, `comment_time`, `dimension_1..3`, `source_file_id`, `raw_row_id` |

生产库如果已有文档源表或视图，只在 `data_access.py` 增加 adapter，不改变下游模块。

## 3. 统一数据结构

`Core3InputBundle`：

```python
@dataclass
class Core3InputBundle:
    project_id: str
    category_code: str
    sku_master: list[SkuMasterInput]
    market_facts: list[MarketFactInput]
    params: list[ParamInput]
    claims: list[ClaimInput]
    comments: list[CommentInput]
    evidence_index: dict[str, list[str]]
```

每个 input row 必须保留：

- `source_file_id`
- `raw_row_id`
- `source_table`
- `category_code`
- `project_id`

## 4. Unknown 规则

统一函数：

```python
UNKNOWN_STRINGS = {"", "-", "null", "NULL", "None", "none", "unknown", "UNKNOWN"}

def is_unknown(value: Any) -> bool:
    return value is None or str(value).strip() in UNKNOWN_STRINGS
```

规则：

- unknown 不等于 false。
- `mini_led_flag` 等布尔参数必须由明确证据推出 true 或 false。
- 空评论表示评论证据缺失，不表示用户没有对应诉求。
- 空销量或空价格进入数据健康和置信度降级，不直接过滤整行。

## 5. SKU / 型号解析

函数：

```python
resolve_sku_code(db, project_id: str, sku_or_model: str) -> ResolvedTargetSku
```

解析顺序：

1. 精确匹配 `sku_code`。
2. 精确匹配 `model_name`。
3. 大小写无关包含匹配 `model_name`。
4. 多个候选返回 `MultipleSkuMatches`，API 转为 409。
5. 无候选返回 `SkuNotFound`，API 转为 404。

返回：

```json
{
  "input": "85E7Q",
  "sku_code": "TV00029115",
  "brand": "Hisense",
  "model_name": "85E7Q",
  "match_type": "model_contains",
  "candidates": []
}
```

## 6. 读取函数

### `load_project_input`

```python
def load_project_input(db: Session, project_id: str) -> Core3InputBundle:
    project = require_project(db, project_id)
    masters = select RawSkuMaster where project_id
    markets = select RawMarketFact where project_id
    params = select RawSkuParam where project_id
    claims = select RawSkuClaim where project_id
    comments = select RawSkuComment where project_id
    return bundle
```

要求：

- 不因部分数据缺失而失败。
- 所有行按 `sku_code` 建索引，下游避免重复扫描。
- 只在项目不存在时失败。

### `data_status`

输出数据覆盖：

- SKU 数。
- 品牌数。
- 渠道数。
- 量价行数。
- 参数行数。
- 卖点行数。
- 评论行数。
- 缺价格 SKU 数。
- 缺销量 SKU 数。
- 缺核心参数 SKU 数。
- 缺评论 SKU 数。

## 7. Evidence 生成策略

读取阶段不急着为所有 raw row 生成 evidence，避免无用膨胀。

读取阶段只建立可追溯引用：

```text
raw_ref = source_table + ":" + raw_row_id
```

后续模块真正使用某条数据作为参数、市场画像、卖点或评论证据时，调用：

```python
get_or_create_evidence(raw_ref, source_type, field_name, raw_value, normalized_value)
```

这样保证 evidence 只覆盖参与结论的事实。

## 8. 失败处理

| 场景 | 处理 |
| --- | --- |
| 项目不存在 | 404 |
| 项目下无 SKU | 422，`no_sku_master` |
| 目标 SKU 不存在 | 404 |
| 型号匹配多个 | 409，返回候选 |
| 量价全空 | 不阻断读取，在健康检查标记 `no_market_fact` |
| 评论全空 | 不阻断读取，在健康检查标记 `no_comment_data` |

## 9. 验收

- 输入已有项目，`data_status` 能返回 5 类数据计数。
- 输入 `TV00029115` 能精确匹配 SKU。
- 输入 `85E7Q` 能匹配型号。
- 空值不会被转成 false。
- 读取阶段不调用竞品算法。

