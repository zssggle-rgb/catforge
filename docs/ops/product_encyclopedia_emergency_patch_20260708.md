# 产品百科对比入口应急补丁记录

日期：2026-07-08

## 背景

竞品分析飞书卡片新增“查看详细对比结果”，需要把本品和 3 个竞品传给产品百科做横向对比。产品百科原线上站点 `https://hisense2.avc-mr.com/` 真实解析到 `120.46.25.87`，但现有 SSH 密钥无法登录该机器，不能直接改原站源码或静态文件。

因此采用应急方案：在可控的 205 服务器临时托管一份 patched 产品百科静态包，并让 CatForge 后端生成的产品百科链接指向 205 临时入口。

## 当前生效入口

- 临时产品百科入口：`http://123.56.42.205/encyclopedia`
- 产品百科 API 代理：`http://123.56.42.205/product-api/`
- 原产品百科 API 上游：`https://120.46.25.87/api/`
- CatForge API 环境变量：`CATFORGE_PRODUCT_ENCYCLOPEDIA_URL=http://123.56.42.205/`
- 飞书卡片按钮外层：`https://applink.feishu.cn/client/web_url/open?mode=sidebar-semi&max_width=1200&reload=false&url=<encoded 产品百科 URL>`，用于在飞书内置浏览器打开。

新生成的飞书卡片内层产品百科 URL 类似：

```text
http://123.56.42.205/encyclopedia?source=catforge_competitor_card&view=compare&category=tv&model=海信 65E7Q&model=65A7H PRO&model=65Q9L PRO&model=65A6F ULTRA&model_names=65E7Q,65A7H PRO,65Q9L PRO,65A6F ULTRA&brands=海信,创维,TCL,创维
```

产品百科 patched 前端会读取：

- `model`：重复参数，最多取 4 个。
- `model_names`：用于搜索接口的精确型号名。
- `brands`：与 `model` 同序对应的品牌。

## 205 服务器改动

服务器：`deploy@123.56.42.205`

静态文件：

- 当前静态目录：`/var/www/hisense2`
- 应急静态包：`/home/deploy/hisense-patched.tgz`
- patched 页面文件：`/var/www/hisense2/assets/Page1View-D343IxNv.js`
  - 增加 `URLSearchParams` 读取 query。
  - 有 query 时覆盖接口 `defaultSelection`。
- patched API 文件：`/var/www/hisense2/assets/LineChart-Nuna-ORo.js`
  - API base 从 `/api` 改为 `/product-api`。

Nginx：

- 配置文件：`/etc/nginx/sites-available/catforge.conf`
- 生效文件：`/etc/nginx/sites-enabled/catforge.conf`
- 新增 `location /product-api/`，HTTP 和 HTTPS server block 都有：

```nginx
location /product-api/ {
    proxy_pass https://120.46.25.87/api/;
    proxy_ssl_server_name on;
    proxy_ssl_name hisense2.avc-mr.com;
    proxy_set_header Host hisense2.avc-mr.com;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
}
```

后端运行配置：

- 当前运行 compose：`/opt/catforge/docker-compose.cloud.yml`
- 当前运行 env：`/opt/catforge/.env`
- 安全端口 compose 副本：`/opt/catforge/docker-compose.yml`
- 应急配置副本：`/home/deploy/docker-compose.safe-ports.yml`
- `/opt/catforge/.env` 增加：

```dotenv
CATFORGE_PRODUCT_ENCYCLOPEDIA_URL=http://123.56.42.205/
```

- 端口约束：
  - API：`127.0.0.1:8000:8000`
  - Web：`127.0.0.1:5173:5173`
  - Postgres/Redis 不对宿主机公开端口，仅容器网络内使用。

## 备份位置

原 205 静态页和 Nginx 配置备份：

```text
/var/backups/catforge-hisense2/20260708_093325/
  hisense2/index.html
  catforge.conf.sites-available
  catforge.conf.sites-enabled
```

Compose 备份候选：

```text
/var/backups/catforge-compose/docker-compose.yml.
/var/backups/catforge-compose/docker-compose.yml.no-pg-port.
/var/backups/catforge-compose/docker-compose.yml.safe-ports.20260708_174117
/home/deploy/catforge.env.bak.20260708_product_encyclopedia_url
/home/deploy/competitor_answer.py.bak.20260708_feishu_applink
```

注意：部分 compose 备份文件名缺少时间戳，是因为首次远端脚本中本地 shell 提前展开了变量。恢复时优先使用当前记录中的 `/home/deploy/docker-compose.safe-ports.yml` 重新应用应急状态。

## 重新应用应急状态

如果后续同步、部署或手工操作把 205 临时入口冲掉，可执行：

```bash
ssh -i /Users/sjs/hxmvp/HX-ECS-海信.pem deploy@123.56.42.205
```

在 205 上执行：

```bash
docker run --rm --privileged --pid=host -v /:/host redis:7 sh -euxc '
  find /host/var/www/hisense2 -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  tar -xzf /host/home/deploy/hisense-patched.tgz -C /host/var/www/hisense2
  cp /host/home/deploy/catforge.conf.patched /host/etc/nginx/sites-available/catforge.conf
  cp /host/home/deploy/catforge.conf.patched /host/etc/nginx/sites-enabled/catforge.conf
  cp /host/home/deploy/docker-compose.safe-ports.yml /host/opt/catforge/docker-compose.yml
  chown -R root:root /host/var/www/hisense2
  find /host/var/www/hisense2 -type d -exec chmod 755 {} +
  find /host/var/www/hisense2 -type f -exec chmod 644 {} +
  chroot /host /usr/sbin/nginx -t
  chroot /host /usr/sbin/nginx -s reload
'

cd /opt/catforge
grep -q '^CATFORGE_PRODUCT_ENCYCLOPEDIA_URL=' .env \
  || printf '\nCATFORGE_PRODUCT_ENCYCLOPEDIA_URL=http://123.56.42.205/\n' >> .env
docker compose -f docker-compose.cloud.yml up -d --build api
```

验证：

```bash
curl -sS http://123.56.42.205/readyz
curl -sS 'http://123.56.42.205/product-api/dict/page-config?category=tv&requestId=recovery-check'
curl -sS -I http://123.56.42.205/assets/Page1View-D343IxNv.js
docker exec catforge-api-1 env | grep CATFORGE_PRODUCT_ENCYCLOPEDIA_URL
docker exec catforge-api-1 python - <<'PY'
from urllib.parse import parse_qs, urlsplit
from app.services.core3_real_data.analyst import competitor_answer
print(urlsplit(competitor_answer._feishu_web_url_open_applink("http://123.56.42.205/encyclopedia")).netloc)
PY
```

期望：

```text
{"status":"ready","database":"ok"}
CATFORGE_PRODUCT_ENCYCLOPEDIA_URL=http://123.56.42.205/
applink.feishu.cn
```

## 回滚到应急前状态

如果要撤销 205 临时产品百科入口，恢复旧静态页和旧 Nginx：

```bash
docker run --rm --privileged --pid=host -v /:/host redis:7 sh -euxc '
  find /host/var/www/hisense2 -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  cp -a /host/var/backups/catforge-hisense2/20260708_093325/hisense2/. /host/var/www/hisense2/
  cp /host/var/backups/catforge-hisense2/20260708_093325/catforge.conf.sites-available /host/etc/nginx/sites-available/catforge.conf
  cp /host/var/backups/catforge-hisense2/20260708_093325/catforge.conf.sites-enabled /host/etc/nginx/sites-enabled/catforge.conf
  chroot /host /usr/sbin/nginx -t
  chroot /host /usr/sbin/nginx -s reload
'
```

如需同时撤销后端链接临时入口，需要从 `/opt/catforge/.env` 删除：

```dotenv
CATFORGE_PRODUCT_ENCYCLOPEDIA_URL=http://123.56.42.205/
```

然后重启 API：

```bash
cd /opt/catforge
docker compose -f docker-compose.cloud.yml up -d api
```

## 已完成验证

- `http://123.56.42.205/readyz` 返回 `{"status":"ready","database":"ok"}`。
- `http://123.56.42.205/product-api/dict/page-config?category=tv` 正常返回 `maxModels: 4`。
- API 容器内生成的“查看详细对比结果”按钮外层为 `applink.feishu.cn/client/web_url/open`，参数为 `mode=sidebar-semi`、`max_width=1200`、`reload=false`。
- 该 AppLink 内层 URL 为 `http://123.56.42.205/encyclopedia`，并保留本品 + 3 个竞品的 `model` 参数。
- 浏览器打开实际后端生成 URL，页面渲染了 4 个型号：
  - 海信 65E7Q
  - 创维 65A7H PRO
  - TCL 65Q9L PRO
  - 创维 65A6F ULTRA
- 页面包含“销售对比”，浏览器 console 无错误。

## 相关后端版本

CatForge 后端功能提交：

```text
510ee3d3 Add product encyclopedia compare link to competitor cards
本次提交 Wrap product compare card button with Feishu AppLink for in-client browser
```

`510ee3d3` 新增飞书卡片按钮“查看详细对比结果”，并生成本品 + 3 个竞品的产品百科 query；后续补丁将按钮 URL 包装为飞书 AppLink，使其在飞书内置浏览器打开。
