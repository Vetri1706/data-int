# Development scripts

Run these from any directory. Paths are resolved relative to the scripts, including paths with spaces. The wrappers share `dev.py`, so setup and service behavior stay consistent across operating systems.

## Prerequisites

- Python 3.11+ with `venv`/pip (Python 3.12 recommended for this checkout).
- Node.js 20.9+ and npm.
- Rust/Cargo and the platform's build tools: Visual Studio C++ Build Tools on Windows, Xcode Command Line Tools on macOS, a C compiler/linker on Linux.
- Docker with Compose v2+ and a running Linux container engine. Docker Desktop works on Windows/macOS. On Linux, the current user must have access to the Docker daemon. These scripts do not install system packages, change execution policy globally, or add Docker permissions.

## Commands

| Action | Windows PowerShell | macOS | Linux |
| --- | --- | --- | --- |
| First setup | `powershell -ExecutionPolicy Bypass -File scripts/windows/dev.ps1 setup` | `bash scripts/macos/dev.sh setup` | `bash scripts/linux/dev.sh setup` |
| Start | `powershell -ExecutionPolicy Bypass -File scripts/windows/dev.ps1 start` | `bash scripts/macos/dev.sh start` | `bash scripts/linux/dev.sh start` |
| Status | `powershell -ExecutionPolicy Bypass -File scripts/windows/dev.ps1 status` | `bash scripts/macos/dev.sh status` | `bash scripts/linux/dev.sh status` |
| Stop app | `powershell -ExecutionPolicy Bypass -File scripts/windows/dev.ps1 stop` | `bash scripts/macos/dev.sh stop` | `bash scripts/linux/dev.sh stop` |
| Start search only | `powershell -ExecutionPolicy Bypass -File scripts/windows/dev.ps1 search` | `bash scripts/macos/dev.sh search` | `bash scripts/linux/dev.sh search` |

`-ExecutionPolicy Bypass` applies to that PowerShell process only. If scripts are already permitted, use `./scripts/windows/dev.ps1 start` directly. PowerShell 7 users can substitute `pwsh` for `powershell`.

Options go after the action:

- `setup --with-browsers`: also run Scrapling's browser installer. On Linux its system dependencies may require elevated package installation. Without this option static retrieval works; browser rendering requires a separately installed compatible browser runtime.
- `setup --skip-install`: keep existing Python/npm packages, but verify imports, synchronize `.env`, start infrastructure, migrate and rebuild.
- `start --no-frontend`: launch only the application services.
- `start --no-build`: reuse the existing Rust binary. Normal `start` rebuilds if the API is not already running.
- `stop --infra`: also stop this project's PostgreSQL, Redis-compatible Valkey and SearXNG containers. Named data volumes are retained. External services and Ollama are untouched.

`bash start.sh` remains a compatibility shortcut for `start`, including `--no-frontend`. Run setup first. Use the scripts' stop command to shut down the background services.

## What setup and start do

Setup creates/reuses the root `.venv`, installs both Python services' requirements plus launcher requirements, and runs `npm ci` from the frontend lockfile. Existing nonempty `.env` values are preserved; missing settings are copied from `.env.example`. Missing PostgreSQL/JWT/search secrets are generated locally. Any `.env` change first creates an ignored `.env.backup-*.local` backup. Neither credentials nor database connection strings are printed.

The default Docker stacks bind only to `127.0.0.1`:

| Service | Default port | Management |
| --- | --- | --- |
| PostgreSQL 16 | 5432 | `compose.dev.yml`; persistent volume |
| Redis-compatible Valkey | 6379 | `compose.dev.yml`; separate from the search cache |
| SearXNG | 8888 | `compose.search.yml`; existing search configuration |
| Scrapling | 8001 | Root `.venv`, Uvicorn |
| Intelligence | 7000 | Root `.venv`, Uvicorn |
| Rust API | 3000 | Compiled `api-server` binary |
| Next.js dashboard | 3001 | Node/Next development server |

Setup starts the Docker dependencies, applies migration 001 only to an empty database, applies idempotent migration 002 and builds the Rust API. Start repeats the infrastructure/migration checks and launches the app in the background. Logs go to ignored `logs/{service}.log`; ignored `.runtime/` stores process IDs and creation times. A port occupied by an unmanaged process causes startup to fail with a clear message. It is never killed or silently treated as this application.

Open **http://127.0.0.1:3001**. Status checks actual HTTP responses and exits with code 1 if a required service is unavailable (including a deliberately omitted frontend). The Rust health endpoint checks PostgreSQL and Redis. Search health confirms the server is reachable, not that upstream engines return results; see the root README for the live search smoke test.

Stop verifies recorded process creation times before terminating each app process and its children. It does not scan for and kill all Node/Python processes. App startup failures clean up only processes started by that invocation. Docker infrastructure stays available unless `stop --infra` is used. No command deletes data volumes.

## Existing infrastructure and changed ports

Set `LOCAL_INFRA=external` with your existing `DATABASE_URL` and `REDIS_URL` to skip Docker PostgreSQL/Valkey. The database must already exist; setup still applies the Datavault schema/migration. Use a dedicated database. Set `LOCAL_SEARCH=external` with `SEARXNG_URL` to use an existing search instance.

For Docker mode, `DATABASE_URL` must agree with the `POSTGRES_*` values and `REDIS_URL` with `REDIS_PORT`. Existing values are never silently rewritten. Changing a `POSTGRES_PASSWORD` setting does not change the password stored in an already initialized PostgreSQL volume; keep the original value or change it in PostgreSQL yourself.

When changing an app port, change its matching URL (`PORT` / `RUST_API_BASE`, `INTELLIGENCE_PORT` / `INTELLIGENCE_URL`, `SCRAPLING_PORT` / `SCRAPLING_URL`) too, or leave that URL blank and rerun setup to derive it. Restart running app services after changing `.env`. Process environment variables override `.env`; `.env.llm.local` is only a legacy fallback. Values are read as dotenv data, never sourced as shell commands.

Ollama remains separate: start it and install a model yourself, or configure a hosted provider key. The app exposes only reachable installed Ollama models and key-configured hosted providers. These scripts do not download models or trigger inference. Laya is not launched because it remains disabled for production workflows.

## Launcher checks

After setup, run `.venv/Scripts/python.exe -m unittest discover -s scripts -p 'test_*.py'` on Windows, or `.venv/bin/python -m unittest discover -s scripts -p 'test_*.py'` on macOS/Linux. These exercise environment preservation, configuration guards and process ownership. Platform wrappers can be syntax checked independently with PowerShell's parser and `bash -n`.

Implementation references: [Docker Compose readiness](https://docs.docker.com/reference/cli/docker/compose/up/) and [Psycopg connection transactions](https://www.psycopg.org/psycopg3/docs/basic/usage.html).

## Temporary Vercel demo connection (Windows)

The Vercel project builds `frontend/`. The Rust API, database, search and model services stay on this computer. For an explicitly approved temporary demo, place the official Windows `cloudflared.exe` in ignored `.runtime/`, start the normal app services, then run:

```powershell
.venv/Scripts/python.exe scripts/demo_connection.py start
.venv/Scripts/python.exe scripts/demo_connection.py status
# Stops only this demo connection; the local app and Docker stay running.
.venv/Scripts/python.exe scripts/demo_connection.py stop
```

The gateway binds to `127.0.0.1:8010`, requires a generated shared server key, and blocks internal callbacks. Set Vercel's server-only `DATAVAULT_GATEWAY_KEY` from `.runtime/demo-gateway-key` and `RUST_API_BASE` to the printed tunnel URL plus `/v1`, then deploy. Never upload the root `.env` or expose port 3000 directly. The deployment upload excludes local credentials, logs, services and runtime files through `.vercelignore`.

Keep this computer awake and its app/Docker services running during judging. Restarting the tunnel changes its URL, requiring a Vercel environment update and redeployment. This is temporary hosting, not an independent cloud deployment. Quick Tunnels do not support SSE; this dashboard uses polling. Details: [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
