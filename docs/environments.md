# CatForge environment inventory

Last verified: 2026-06-09 23:55:55 CST

This file records non-secret environment metadata for CatForge. Full credentials are stored only in the local ignored file `.catforge/environment-access.local.md`.

## Environments

| Environment | Purpose | Public IP | SSH user | Hostname | Private IP | PostgreSQL endpoint |
| --- | --- | --- | --- | --- | --- | --- |
| Server A | Development | `123.56.42.205` | `root` | `iZ2ze28m4yoveztbjr69ywZ` | `192.168.20.34` | `123.56.42.205:5432` |
| Server B | Test | `123.56.43.191` | `root` | `iZ2ze28m4yoveztbjr69yvZ` | `192.168.20.33` | `123.56.43.191:5432` |

Shared SSH key path on this workstation:

```text
/Users/sjs/hxmvp/HX-ECS-海信.pem
```

The key file permission was set to `600` for OpenSSH compatibility.

## PostgreSQL

| Environment | Version | Cluster | Port | Service | Listen addresses | Data directory | Admin role |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Server A | `18.4 (Ubuntu 18.4-1.pgdg26.04+1)` | `main` | `5432` | `active`, `enabled` | `0.0.0.0`, `::` | `/var/lib/postgresql/18/main` | `admin` |
| Server B | `18.4 (Ubuntu 18.4-1.pgdg26.04+1)` | `main` | `5432` | `active`, `enabled` | `0.0.0.0`, `::` | `/var/lib/postgresql/18/main` | `admin` |

## Verification results

| Check | Server A | Server B | Notes |
| --- | --- | --- | --- |
| SSH login with key | Pass | Pass | Logged in as `root`. |
| PostgreSQL service on server | Pass | Pass | `systemctl is-active postgresql` returned `active`; `pg_isready -h 127.0.0.1 -p 5432` accepted connections. |
| Local PostgreSQL login on server | Pass | Pass | `admin` can query `postgres` through `127.0.0.1:5432`. |
| Direct PostgreSQL from workstation to public IP | Blocked | Blocked | TCP `5432` opens, but PostgreSQL protocol handshake is closed or times out before authentication. Host firewall is open, so this likely needs cloud security group or cloud firewall adjustment. |
| PostgreSQL through SSH tunnel | Pass | Pass | Workstation can query both databases through local SSH tunnels. |
| CatForge deployment baseline | Pass | Not started | Server A has `deploy`, Docker, Compose, `/opt/catforge`, `catforge_dev`, `catforge_app`, and running API/Web/Redis containers. |
| CatForge server-local health | Pass | Not started | Server A `127.0.0.1:8000/healthz` returns `{"status":"ok"}` and `127.0.0.1:8000/readyz` returns `{"status":"ready","database":"ok"}`. |
| CatForge public app ports | Blocked | Not started | Server A public `8000` and `5173` time out from this workstation. Use SSH tunnel until cloud security group or firewall rules are decided. |

## Server A development baseline

Server A is initialized as the CatForge development integration environment.

| Item | Value |
| --- | --- |
| Deploy user | `deploy` |
| App directory | `/opt/catforge` |
| Runtime env file | `/opt/catforge/.env` |
| Docker | `29.1.3` |
| Docker Compose | `2.40.3` |
| Docker registry mirror | `https://docker.m.daocloud.io` |
| Application database | `catforge_dev` |
| Application database user | `catforge_app` |
| API database target | `host.docker.internal:5432/catforge_dev` |
| Containers | `catforge-api-1`, `catforge-web-1`, `catforge-redis-1` |

Server-local checks:

```text
GET http://127.0.0.1:8000/healthz -> {"status":"ok"}
GET http://127.0.0.1:8000/readyz -> {"status":"ready","database":"ok"}
HEAD http://127.0.0.1:5173/ -> HTTP/1.1 200 OK
```

## Current access path for SKU import

Until public PostgreSQL access is fixed at the cloud network layer, use SSH tunneling from this workstation or from the import runner.

Development database tunnel:

```bash
ssh -i /Users/sjs/hxmvp/HX-ECS-海信.pem -N -L 25432:127.0.0.1:5432 root@123.56.42.205
```

Connect clients to:

```text
host=127.0.0.1 port=25432 dbname=postgres user=admin
```

Test database tunnel:

```bash
ssh -i /Users/sjs/hxmvp/HX-ECS-海信.pem -N -L 25433:127.0.0.1:5432 root@123.56.43.191
```

Connect clients to:

```text
host=127.0.0.1 port=25433 dbname=postgres user=admin
```

Server A application tunnel:

```bash
ssh -i /Users/sjs/hxmvp/HX-ECS-海信.pem \
  -N \
  -L 18000:127.0.0.1:8000 \
  -L 15173:127.0.0.1:5173 \
  deploy@123.56.42.205
```

After the tunnel is open:

```text
API health: http://127.0.0.1:18000/healthz
Web UI: http://127.0.0.1:15173
```

## Cloud network follow-up

To make the public PostgreSQL examples usable directly, check the cloud-side inbound rules for port `5432` on both ECS instances:

- Allow the import runner source IP or office/VPN egress IP only, not `0.0.0.0/0`.
- Include Server A and Server B private subnet rules if cross-environment access is required.
- Re-run the PostgreSQL SSL handshake check after changing the security group or cloud firewall policy.

For CatForge development access, decide whether public `8000` and `5173` should be opened. Prefer SSH tunnel, VPN, or fixed-source allow-listing over public `0.0.0.0/0` access.
