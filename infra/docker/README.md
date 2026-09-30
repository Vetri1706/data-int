# Full Datavault Docker deployment

The root `compose.yml` runs the production Next.js server, Rust API, Python
intelligence service, Scrapling with browsers, SearXNG, PostgreSQL and two private
Valkey caches. A one-shot migration service initializes an empty database or
applies the idempotent migration to an existing Datavault schema.

## Start and stop

Docker Desktop must use Linux containers. Allow at least 20 GB of free disk space
for the first build's downloaded toolchains, browser packages and temporary layers.
Use the existing root `.env`; it must
contain nonempty `POSTGRES_PASSWORD`, `JWT_SECRET` and `SEARXNG_SECRET`. On a new
machine, copy `.env.example` and set those to separate randomly generated secrets.
Never commit `.env` or pass it as a Docker build argument.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/docker.ps1 start
powershell -ExecutionPolicy Bypass -File scripts/windows/docker.ps1 status
powershell -ExecutionPolicy Bypass -File scripts/windows/docker.ps1 logs intelligence
powershell -ExecutionPolicy Bypass -File scripts/windows/docker.ps1 stop
```

```sh
bash scripts/linux/docker.sh start
# macOS: bash scripts/macos/docker.sh start
bash scripts/linux/docker.sh status
bash scripts/linux/docker.sh stop
```

Equivalent: `docker compose -f compose.yml up -d --build --wait`.
Open **http://localhost:3003**. Only the dashboard is published, on loopback.
The database and internal callbacks have no host ports. Set
`DOCKER_FRONTEND_PORT` to choose another port. This is a local deployment; it
does not publish the app on Vercel or create a public tunnel.

`stop` keeps all data. The `datavault` project has separate volumes from
`datavault-dev` and `datavault-search`. A fresh deployment has an empty database;
it does not automatically import or share a development database. Never attach
the same PostgreSQL volume to two running database containers. Do not use
`docker compose down -v` unless you intend to delete this deployment's data.

## Models and secrets

Only intelligence receives hosted model keys. API receives the database password
and session signing secret. SearXNG receives its own search secret. The frontend
has no provider/database credentials. Docker build contexts exclude `.env`,
backups, logs, local tooling, and runtime files.

Local Ollama remains managed by the host. Docker Desktop uses
`http://host.docker.internal:11434/v1`; the explicit server-side
`LOCAL_LLM_ALLOW_DOCKER_HOST=1` permits only this host bridge in addition to
loopback. Reachable installed models are discovered normally. On native Linux,
the host-gateway mapping alone does not make a loopback-only Ollama listener
reachable: bind Ollama to a firewall-restricted Docker bridge address, or use a
configured hosted provider with collection consent. Do not expose Ollama publicly.
`DOCKER_OLLAMA_URL` can override the bridge URL's scheme/port/path; arbitrary
external hostnames are still rejected by the local-provider policy.

## Rebuilding the API

The API builds with SQLx offline query metadata in `backend/.sqlx`. No database
password or database connection is needed during image builds. After changing
SQL queries/schema, regenerate the cache against a migrated development database:

```sh
cargo install sqlx-cli --version 0.8.6 --no-default-features --features rustls,postgres --locked
cd backend
# Supply DATABASE_URL securely in the process environment, not in command history.
cargo sqlx prepare --workspace -- --bin api-server
```

Runtime schema migrations are separate from that compile-time query cache.

## Deployment boundaries

Use one intelligence container and one Uvicorn worker. Runs are currently
in-process and cannot resume after a crash/redeployment; Redis does not yet
provide a durable workflow worker. Stop starting new collections and let active
runs finish before restarting. Health checks establish service connectivity,
not extraction accuracy, upstream search availability or model quota.

For a public Linux server, place an HTTPS reverse proxy in front of the dashboard,
set up off-server PostgreSQL backups and test a restore. Keep API, database,
scraper and intelligence ports private. A small hosted-LLM deployment can start
with 4 vCPUs and 8 GB RAM, then be sized from actual load. No GPU or Ollama model
is bundled or downloaded by this Compose stack.
