# 02 运行上下文、数据健康与落库骨架

## 1. 模块目标

在读取数据后，创建一次可追踪的 Core3 运行，并在运行开始前完成数据健康检查。后续每个模块都依赖同一个 `run_id` 写入结果。

## 2. 输入输出

输入：

- `Core3InputBundle`
- `RunRequest`
- `rule_version`

输出：

- `Core3RunContext`
- `DataQualitySummary`
- `core3_pipeline_run` 行

## 3. RunRequest

```json
{
  "target_sku_code": "TV00029115",
  "target_model": "85E7Q",
  "batch": false,
  "force_recompute": false
}
```

约束：

- `batch=false` 时，`target_sku_code` 和 `target_model` 至少一个必填。
- `batch=true` 时，对项目内全部 SKU 运行。
- 第一版同步执行，不进入异步 job。

## 4. Core3RunContext

```python
@dataclass
class Core3RunContext:
    run_id: str
    project_id: str
    category_code: str
    scope: Literal["single", "batch"]
    target_sku_codes: list[str]
    rule_version: str
    input_fingerprint: str
    warnings: list[str]
```

`target_sku_codes`：

- 单 SKU：长度 1。
- 批量：项目内所有 `sku_code` 非 unknown 的 SKU。

## 5. 输入指纹

用于判断是否复用最近结果。

指纹字段：

- SKU 数。
- 5 类源表行数。
- 每类源表最大 `updated_at`。
- 规则版本。
- 运行范围。
- 目标 SKU 列表 hash。

伪代码：

```python
fingerprint = sha256(json.dumps({
  "project_id": project_id,
  "category_code": category_code,
  "rule_version": rule_version,
  "scope": scope,
  "target_sku_codes_hash": hash_list(target_sku_codes),
  "source_counts": source_counts,
  "source_max_updated_at": source_max_updated_at,
}, sort_keys=True).encode()).hexdigest()
```

## 6. 数据健康检查

健康检查分两层。

### 6.1 项目级健康

输出：

- `sku_count`
- `brand_count`
- `channel_count`
- `market_fact_count`
- `param_row_count`
- `claim_row_count`
- `comment_row_count`
- `period_count`
- `latest_period`

### 6.2 SKU 级健康

每个 SKU 输出：

- 是否有主数据。
- 是否有价格。
- 是否有销量。
- 是否有渠道。
- 是否有核心参数候选。
- 是否有卖点文本。
- 是否有评论。

健康状态：

- `ready`：价格或销量、核心参数或卖点至少一类存在。
- `degraded`：可分析但置信度会降级。
- `blocked`：没有足够数据生成候选。

## 7. core3_pipeline_run 表

字段：

- `run_id`
- `project_id`
- `category_code`
- `status`
- `scope`
- `target_sku_code`
- `input_fingerprint`
- `rule_version`
- `counts`
- `warnings`
- `diagnostics`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

状态流：

```text
created -> running -> completed
                   -> failed
```

第一版可以创建时直接 `running`，结束后更新为 `completed`。

## 8. 复用策略

当 `force_recompute=false`：

1. 查找同项目、同 scope、同 target、同 fingerprint 的最新 completed run。
2. 如果存在，直接返回该 run 的报告引用。
3. 如果不存在，创建新 run。

当 `force_recompute=true`：

- 总是创建新 run。

## 9. 失败处理

| 场景 | 状态 | 说明 |
| --- | --- | --- |
| 项目无 SKU | failed | `no_sku_master` |
| 单 SKU 目标不存在 | 不创建 run | 404 |
| 批量无有效 sku_code | failed | `no_valid_sku_code` |
| 源数据读取异常 | failed | diagnostics 记录模块名 |
| 下游模块异常 | failed | 已产生的中间结果保留，便于排查 |

API 不暴露数据库连接串、堆栈和本地路径。

## 10. 验收

- 每次运行都有 `run_id`。
- 所有下游结果都带同一 `run_id`。
- 相同输入和规则版本可以复用结果。
- `force_recompute=true` 能创建新结果。
- 数据健康摘要可用于页面展示和置信度降级。

