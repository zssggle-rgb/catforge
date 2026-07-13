# 用户卖点价值画像 G08：205 部署与回滚 SOP

本文件记录命令模板。G08 不执行任何 205 操作。

## 部署前只读检查

1. 记录本地 RC commit SHA、远端分支 SHA和 205 当前代码 SHA。
2. 确认 205 工作树没有未归属修改；若存在，停止部署并先归属处理。
3. 记录 Alembic 当前版本、数据库表是否已存在及四张画像表行数。
4. 对四张画像表执行 schema/data 备份；即使当前不存在，也保存检查回执。
5. 记录 API `healthz`、`readyz` 和容器 restart count。

推荐的 205 只读命令：

```bash
cd /opt/catforge
git rev-parse HEAD
git status --short
docker compose -f docker-compose.cloud.yml --env-file .env run --rm -T api python -m alembic current
docker compose -f docker-compose.cloud.yml --env-file .env ps
```

数据库检查 SQL：

```sql
select to_regclass('public.core3_sellpoint_value_profile_version');
select to_regclass('public.core3_sku_sellpoint_value_profile');
select to_regclass('public.core3_sku_sellpoint_value_candidate');
select to_regclass('public.core3_sku_sellpoint_value_item');
```

## G09 部署

从本地使用已推送 RC 分支执行完整部署；部署前将 `<G08_RC_SHA>` 与远端分支 SHA核对一致：

```bash
CATFORGE_GIT_REF=new/base-publish-workbench-design scripts/full-deploy-205.sh dev
```

部署脚本会构建镜像、执行 `alembic upgrade head`、重建服务并检查健康。部署后必须再次确认：

```bash
cd /opt/catforge
git rev-parse HEAD
docker compose -f docker-compose.cloud.yml --env-file .env run --rm -T api python -m alembic current
docker compose -f docker-compose.cloud.yml --env-file .env ps
```

通过条件：远端 HEAD 等于 `<G08_RC_SHA>`；Alembic 为 `0045_core3_sellpoint_value_profile (head)`；API healthy/ready；四张表存在。

## G09：只生成 65E7Q 草稿

先生成唯一版本名，例如 `<PROFILE_VERSION>=spv-profile-v1-20260713-65e7q`。命令中不含 review/publish/current 操作：

```bash
docker compose -f docker-compose.cloud.yml --env-file .env exec -T api \
  python -m app.cli.catforge_analyst sellpoint-value-profile-generate \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id latest \
  --product-category tv \
  --sku-code TV00029112 \
  --profile-version <PROFILE_VERSION> \
  --generated-by codex-g09 \
  --enable-profile-write \
  --format json
```

读取保存画像生成产品经理报告：

```bash
docker compose -f docker-compose.cloud.yml --env-file .env exec -T api \
  python -m app.cli.catforge_analyst sellpoint-value-pm-v5 \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id latest \
  --product-category tv \
  --sku-code TV00029112 \
  --preview-profile-version <PROFILE_VERSION> \
  --enable-v5 \
  --format json
```

G09 验收至少核对：

- 65E7Q 命中唯一 SKU，来源批次范围和持久化锚点均为真实值；
- M12D 为当前已发布画像，关键来源没有占位 hash；
- 候选池完整，没有 12 款上限，M14 只标记不裁剪；
- 每项候选比较保存 eligible/selected/rejected 及原因；
- 门槛配置、保留投入、未转化投入、不必跟进和竞争缺口使用产品经理业务语言；
- 当前价格、销量及价值战场结论只引用画像已保存结果；
- profile hash、报告 hash、问答 expected hash 完全一致；
- 版本仍为 draft、`is_current=false`；
- 只存在 65E7Q 一条 SKU 画像，发布完整性门禁明确拒绝该单 SKU版本。

验收 SQL：

```sql
select profile_version, batch_id, source_batch_ids_json, source_scope_json,
       sku_count, ready_count, review_required_count, blocked_count, failed_count,
       processing_status, release_status, release_quality_status, is_current,
       input_fingerprint, candidate_universe_fingerprint, result_hash
from core3_sellpoint_value_profile_version
where profile_version = '<PROFILE_VERSION>';

select sku_code, analysis_state, freshness_status, profile_confidence,
       review_required, review_status, release_status, is_current,
       input_fingerprint, result_hash
from core3_sku_sellpoint_value_profile
where profile_version = '<PROFILE_VERSION>';

select pool_type, count(*)
from core3_sku_sellpoint_value_candidate
where profile_version = '<PROFILE_VERSION>'
group by pool_type;

select count(*) as value_item_count
from core3_sku_sellpoint_value_item
where profile_version = '<PROFILE_VERSION>';
```

## G10：G09 通过后续跑全部 SKU

TV 使用 G09 的同一 `<PROFILE_VERSION>` 续跑，已验证的 65E7Q 会被跳过并复用不可变结果：

```bash
docker compose -f docker-compose.cloud.yml --env-file .env exec -T api \
  python -m app.cli.catforge_analyst sellpoint-value-profile-batch-generate \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id latest \
  --product-category tv \
  --profile-version <PROFILE_VERSION> \
  --generated-by codex-g10-tv \
  --page-size 25 \
  --enable-profile-write \
  --format json
```

AC 使用独立版本名和 AC 的 latest 权威范围：

```bash
docker compose -f docker-compose.cloud.yml --env-file .env exec -T api \
  python -m app.cli.catforge_analyst sellpoint-value-profile-batch-generate \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id latest \
  --product-category ac \
  --profile-version <AC_PROFILE_VERSION> \
  --generated-by codex-g10-ac \
  --page-size 25 \
  --enable-profile-write \
  --format json
```

G10 只生成 draft；不调用 review/publish/current。完成后按权威 SKU 清单逐项核对不存在遗漏、重复、失败和非权威 SKU。

## 回滚

优先采用代码回滚并保留 0045 的加法型空表；旧代码不会消费这些表。若 G09 已生成草稿，先按精确 `profile_version` 备份和删除四张表中的该版本数据，不能使用无条件删除。

仅在明确批准“同时回滚 schema”后，才在 RC 代码仍可用时执行：

```bash
docker compose -f docker-compose.cloud.yml --env-file .env run --rm -T api \
  python -m alembic downgrade 0044_core3_m12d_reason_pressure
```

随后部署记录的部署前 commit。回滚验收必须确认：健康检查通过、旧业务接口回归通过、画像版本/current 没有误切换、其他任务数据行数不变。
