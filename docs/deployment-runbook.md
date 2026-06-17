# CatForge deployment runbook

This runbook defines the first development chain for CatForge:

- Local workstation: code, unit tests, frontend iteration, and small deterministic fixtures.
- Server A: development integration environment for frequent deploys and later small-batch SKU import.
- Server B: test acceptance environment for stable commits only. Do not use it for day-to-day development.

Secrets must stay out of git. Use `.env.example` as the template, keep real local deployment values under `.catforge/`, and keep server runtime values in `/opt/catforge/.env`.

## Deployment model

Cloud servers use:

- Host PostgreSQL 18 on `127.0.0.1:5432`.
- Docker Compose for CatForge API, web, and Redis.
- API containers connect to host PostgreSQL through `host.docker.internal:5432`.
- Alembic migrations run inside the API image before services are started.
- Docker builds default to China-friendly PyPI/npm mirrors, and Server A also uses a Docker registry mirror because direct Docker Hub access timed out.

Local development can continue using the original `docker-compose.yml` or the backend SQLite fallback.

## Server A baseline

Server A is the development environment:

```text
host: 123.56.42.205
ssh user: deploy
app dir: /opt/catforge
database: catforge_dev
database owner/app user: catforge_app
```

PostgreSQL public access is currently not required for deployment. Use SSH for deploy and host-local PostgreSQL for the running API.

## Required local files

Create one ignored deployment file per target:

```bash
cp .env.example .catforge/deploy-dev.env
```

The local deployment file should include only deployment settings:

```bash
CATFORGE_ENV=dev
CATFORGE_DEPLOY_HOST=123.56.42.205
CATFORGE_DEPLOY_USER=deploy
CATFORGE_SSH_KEY=/Users/sjs/hxmvp/HX-ECS-海信.pem
CATFORGE_APP_DIR=/opt/catforge
CATFORGE_COMPOSE_FILE=docker-compose.cloud.yml
CATFORGE_RUNTIME_ENV_FILE=.catforge/server-a.runtime.env
CATFORGE_APP_URL=http://123.56.42.205:8000
```

Create the ignored runtime env file referenced by `CATFORGE_RUNTIME_ENV_FILE`:

```bash
CATFORGE_ENV=dev
CATFORGE_DATABASE_URL=postgresql+psycopg://catforge_app:<password>@host.docker.internal:5432/catforge_dev
CATFORGE_REDIS_URL=redis://redis:6379/0
CATFORGE_UPLOAD_DIR=/data/uploads
CATFORGE_EXPORT_DIR=/data/exports
CATFORGE_SYNC_JOBS=true
CATFORGE_API_PORT=8000
CATFORGE_WEB_PORT=5173
VITE_PROXY_TARGET=http://api:8000
```

## Database bootstrap

Run the SQL as a PostgreSQL superuser. For Server A this was run through SSH against local PostgreSQL:

```bash
psql -h 127.0.0.1 -U admin -d postgres \
  -v catforge_db_name=catforge_dev \
  -v catforge_app_user=catforge_app \
  -v catforge_app_password='<password>' \
  -f scripts/db-bootstrap.sql
```

The application user owns `catforge_dev`, so Alembic can create and migrate CatForge tables without using a superuser.

## Check environment

```bash
scripts/check-env.sh dev
```

The check verifies SSH, Docker, Git, rsync, PostgreSQL service readiness, `/opt/catforge/.env`, and the API health endpoints when the app is deployed.

## Deploy

```bash
scripts/deploy.sh dev
```

Server A dev should deploy from GitHub:

```bash
CATFORGE_SYNC_STRATEGY=github
CATFORGE_GIT_REPO=https://github.com/zssggle-rgb/catforge.git
CATFORGE_GIT_REF=main
```

With `CATFORGE_SYNC_STRATEGY=github`, the deploy script fetches `CATFORGE_GIT_REF` on the server and deploys that committed revision. The old rsync mode remains available by setting `CATFORGE_SYNC_STRATEGY=rsync`, but it should only be used for local debugging because it can deploy uncommitted workstation state.

The deploy script:

1. Syncs code into `/opt/catforge` from GitHub or rsync, depending on `CATFORGE_SYNC_STRATEGY`.
2. Uploads the runtime `.env` when `CATFORGE_RUNTIME_ENV_FILE` is set.
3. Builds the API and web images.
4. Runs `alembic upgrade head`.
5. Starts API, web, and Redis.
6. Checks `/healthz` and `/readyz` when `CATFORGE_APP_URL` is configured.

## Server B policy

Apply the same scripts to Server B after Server A is stable, but keep `deploy-test.env` and the runtime `.env` separate:

- `CATFORGE_DEPLOY_HOST=123.56.43.191`
- database name `catforge_test`
- deployment should be manually triggered from a stable commit or tag
- back up the database before deploying schema-changing revisions

Do not import experimental SKU batches into Server B until Server A import mapping and data-quality checks pass.
