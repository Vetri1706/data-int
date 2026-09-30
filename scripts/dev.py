#!/usr/bin/env python3
"""Local development lifecycle shared by Windows, macOS, and Linux wrappers."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import quote, unquote, urlparse
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
RUNTIME = ROOT / ".runtime"
STATE = RUNTIME / "services.json"
LOGS = ROOT / "logs"


def say(message):
    print(f"[datavault] {message}", flush=True)


def run(args, *, env=None, cwd=ROOT, capture=False):
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=env,
                            text=True, capture_output=capture, check=False)
    if result.returncode:
        # Do not echo command arguments, connection strings, or environment values.
        raise RuntimeError(f"{Path(str(args[0])).name} failed (exit {result.returncode}).")
    return result.stdout if capture else None


def values(path):
    from dotenv import dotenv_values
    return {k: v or "" for k, v in dotenv_values(path, interpolate=False).items()}


def derived(env):
    result = dict(env)
    for key in ("POSTGRES_PASSWORD", "JWT_SECRET", "SEARXNG_SECRET"):
        if not result.get(key):
            result[key] = secrets.token_hex(32)
    user = quote(result.get("POSTGRES_USER", "datavault"), safe="")
    password = quote(result["POSTGRES_PASSWORD"], safe="")
    database = quote(result.get("POSTGRES_DB", "datavault"), safe="")
    defaults = {
        "DATABASE_URL": f"postgres://{user}:{password}@127.0.0.1:{result.get('POSTGRES_PORT', '5432')}/{database}",
        "REDIS_URL": f"redis://127.0.0.1:{result.get('REDIS_PORT', '6379')}",
        "INTELLIGENCE_URL": f"http://127.0.0.1:{result.get('INTELLIGENCE_PORT', '7000')}",
        "SCRAPLING_URL": f"http://127.0.0.1:{result.get('SCRAPLING_PORT', '8001')}",
        "RUST_API_BASE": f"http://127.0.0.1:{result.get('PORT', '3000')}/v1",
    }
    for key, value in defaults.items():
        if not result.get(key):
            result[key] = value
    return result


def sync_env():
    """Append missing example settings, retaining existing keys/comments/values."""
    path = ROOT / ".env"
    original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    existing = values(path) if path.exists() else {}
    legacy = values(ROOT / ".env.llm.local")
    template = values(ROOT / ".env.example")
    merged = derived({**template, **legacy, **existing})
    updates = {k: v for k, v in merged.items() if k not in existing or v != existing[k]}
    if not updates:
        say(".env already contains all settings; existing values preserved.")
        return
    if path.exists():
        backup = ROOT / f".env.backup-{datetime.now():%Y%m%d-%H%M%S-%f}.local"
        shutil.copy2(path, backup)
        say(f"Saved {backup.name}")
    lines = original.splitlines()
    for key, value in updates.items():
        # Single quotes keep spaces, #, $, and URL punctuation literal for dotenv/Compose.
        encoded = "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
        replacement = f"{key}={encoded}"
        indices = [i for i, line in enumerate(lines)
                   if re.match(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=", line)]
        if indices:
            for i in indices:
                lines[i] = replacement
        else:
            lines.append(replacement)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    say(f"Updated {len(updates)} settings in .env; credential values are not printed.")


def environment():
    if not (ROOT / ".env").exists():
        raise RuntimeError("Missing .env. Run the setup command first.")
    env = {**values(ROOT / ".env.example"), **values(ROOT / ".env.llm.local"),
           **values(ROOT / ".env"), **os.environ}
    for key in ("DATABASE_URL", "REDIS_URL", "JWT_SECRET"):
        if not env.get(key):
            raise RuntimeError(f"Missing {key}. Run setup or set it in .env.")
    # URLs left blank in an external environment are derived from configured ports.
    env = derived(env)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    for key in ("LOCAL_INFRA", "LOCAL_SEARCH"):
        if env.get(key) not in ("docker", "external"):
            raise RuntimeError(f"{key} must be docker or external.")
    return env


def require_tools(env):
    for tool in ("node", "cargo"):
        if not shutil.which(tool):
            raise RuntimeError(f"Install {tool} and reopen the terminal before setup/start.")
    version = run(["node", "-p", "process.versions.node"], capture=True).strip()
    if tuple(map(int, version.split(".")[:2])) < (20, 9):
        raise RuntimeError("Next.js requires Node.js 20.9 or newer.")
    if env.get("LOCAL_INFRA") == "docker" or env.get("LOCAL_SEARCH") == "docker":
        if not shutil.which("docker"):
            raise RuntimeError("Install Docker with Compose v2+ and start its Linux engine.")
        try:
            run(["docker", "info", "--format", "{{.ServerVersion}}"], capture=True)
            run(["docker", "compose", "version"], capture=True)
        except RuntimeError:
            raise RuntimeError("Docker is unavailable. Start Docker Desktop / the Docker daemon.") from None


def compose(file, args, env):
    return run(["docker", "compose", "--project-directory", ROOT, "--env-file", ROOT / ".env",
                "-f", ROOT / file, *args], env=env)


def validate_local_config(env):
    """Never start/migrate a different database from the one the app will use."""
    if env["LOCAL_INFRA"] == "docker":
        db = urlparse(env["DATABASE_URL"])
        expected = (env["POSTGRES_USER"], env["POSTGRES_PASSWORD"], env["POSTGRES_DB"], int(env["POSTGRES_PORT"]))
        actual = (unquote(db.username or ""), unquote(db.password or ""), unquote(db.path.lstrip("/")), db.port or 5432)
        redis = urlparse(env["REDIS_URL"])
        if db.hostname not in ("localhost", "127.0.0.1") or actual != expected:
            raise RuntimeError("DATABASE_URL differs from the Docker POSTGRES_* settings. Align them or set LOCAL_INFRA=external.")
        if (redis.hostname not in ("localhost", "127.0.0.1") or redis.scheme != "redis"
                or (redis.port or 6379) != int(env["REDIS_PORT"]) or redis.password or redis.username):
            raise RuntimeError("REDIS_URL differs from Docker Redis settings. Align them or set LOCAL_INFRA=external.")
    if env["LOCAL_SEARCH"] == "docker":
        search = urlparse(env["SEARXNG_URL"])
        if (search.hostname not in ("localhost", "127.0.0.1") or search.scheme != "http"
                or search.port != int(env["SEARXNG_PORT"]) or search.path not in ("", "/")):
            raise RuntimeError("SEARXNG_URL differs from Docker search settings. Align them or set LOCAL_SEARCH=external.")


def infra(env):
    validate_local_config(env)
    for mode, file in (("LOCAL_INFRA", "compose.dev.yml"), ("LOCAL_SEARCH", "compose.search.yml")):
        if env[mode] == "docker":
            say(f"Starting {file} and waiting for health checks...")
            compose(file, ["up", "-d", "--wait", "--wait-timeout", "120"], env)


def migrate(env):
    import psycopg
    try:
        with psycopg.connect(env["DATABASE_URL"], connect_timeout=5) as conn:
            # Serializes concurrent setup processes that target the same database.
            conn.execute("SELECT pg_advisory_xact_lock(684701247)")
            exists = conn.execute("SELECT to_regclass('public.users')").fetchone()[0]
            if exists is None:
                count = conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]
                if count:
                    raise RuntimeError("The database has unrelated tables but no users table. Choose an empty Datavault database.")
                conn.execute((ROOT / "migrations/001_initial_schema.sql").read_text(encoding="utf-8"))
                say("Applied initial schema to empty database.")
            conn.execute((ROOT / "migrations/002_trust_and_workflow.sql").read_text(encoding="utf-8"))
    except psycopg.Error as exc:
        raise RuntimeError(f"Database connection/migration failed ({type(exc).__name__}); check DATABASE_URL and PostgreSQL logs.") from None
    say("Database migrations are current.")


def identity(pid):
    import psutil
    proc = psutil.Process(pid)
    return {"pid": pid, "created": proc.create_time()}


def owned(record):
    import psutil
    try:
        proc = psutil.Process(record["pid"])
        return proc if abs(proc.create_time() - record["created"]) < 0.01 and proc.is_running() else None
    except (psutil.NoSuchProcess, KeyError, TypeError):
        return None


@contextmanager
def lifecycle_lock():
    RUNTIME.mkdir(exist_ok=True)
    path = RUNTIME / "lifecycle.lock"
    for attempt in range(2):
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(identity(os.getpid()), handle)
            break
        except FileExistsError:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                raise RuntimeError("Launcher lock is being written or is damaged. Retry; inspect .runtime/lifecycle.lock if it persists.") from None
            if owned(record) or attempt:
                raise RuntimeError("Another setup/start/stop command is active. Wait for it to finish.")
            path.unlink()
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def records():
    if not STATE.exists():
        return {}
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_records(state):
    RUNTIME.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def terminate(record):
    import psutil
    parent = owned(record)
    if parent is None:
        return
    children = parent.children(recursive=True)
    processes = children + [parent]
    for proc in reversed(processes):
        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=8)
    for proc in alive:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=3)


def http_ready(url, expected=None):
    try:
        # Local checks must not be diverted through a system HTTP proxy.
        with build_opener(ProxyHandler({})).open(url, timeout=2) as response:
            if expected:
                data = json.load(response)
                return all(data.get(k) == v for k, v in expected.items())
            return response.status == 200
    except Exception:
        return False


def specs(env, frontend=True):
    python = str(PYTHON)
    target = Path(env.get("CARGO_TARGET_DIR") or ROOT / "backend/target")
    if not target.is_absolute():
        target = ROOT / "backend" / target
    api = target / "debug" / ("api-server.exe" if os.name == "nt" else "api-server")
    result = [
        ("scrapling", [python, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", env["SCRAPLING_PORT"]], ROOT / "services/scrapling", env["SCRAPLING_URL"].rstrip("/") + "/health", {"status": "ok", "service": "scrapling"}),
        ("intelligence", [python, "-m", "uvicorn", "graph:app", "--host", "127.0.0.1", "--port", env["INTELLIGENCE_PORT"]], ROOT / "services/intelligence", env["INTELLIGENCE_URL"].rstrip("/") + "/health", {"status": "ok", "service": "intelligence"}),
        ("api", [str(api)], ROOT / "backend", env["RUST_API_BASE"].rstrip("/") + "/health", {"status": "ok"}),
    ]
    if frontend:
        result.append(("frontend", [shutil.which("node") or "node", str(ROOT / "frontend/node_modules/next/dist/bin/next"), "dev", "--hostname", "127.0.0.1", "--port", env["FRONTEND_PORT"]], ROOT / "frontend", f"http://127.0.0.1:{env['FRONTEND_PORT']}", None))
    return result


def validate_app_endpoints(env):
    # This launcher owns local app processes. External DB/search are allowed separately.
    for name, port, path in (("SCRAPLING_URL", "SCRAPLING_PORT", ""),
                             ("INTELLIGENCE_URL", "INTELLIGENCE_PORT", ""),
                             ("RUST_API_BASE", "PORT", "/v1")):
        url = urlparse(env[name])
        if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost")
                or url.port != int(env[port]) or url.path.rstrip("/") != path):
            raise RuntimeError(f"{name} must match the local {port} setting for this launcher.")
    if env.get("HOST") != "127.0.0.1":
        raise RuntimeError("Set HOST=127.0.0.1 for this local development launcher.")
    ports = [int(env[k]) for k in ("PORT", "FRONTEND_PORT", "SCRAPLING_PORT", "INTELLIGENCE_PORT")]
    if len(set(ports)) != len(ports) or any(p < 1 or p > 65535 for p in ports):
        raise RuntimeError("Application ports must be distinct numbers from 1 to 65535.")


def check_python():
    run([PYTHON, "-c", "import fastapi, uvicorn, httpx, langgraph, langchain_openai, sklearn, bs4, tldextract, scrapling, ddgs, dotenv, psycopg, psutil"])


def build_api(env):
    say("Building Rust API against the migrated database...")
    run(["cargo", "build", "--locked", "--bin", "api-server"], env=env, cwd=ROOT / "backend")


def start(env, args):
    state = records()
    requested = specs(env, not args.no_frontend)
    validate_app_endpoints(env)
    for name, _, _, url, expected in requested:
        if name in state and owned(state[name]):
            if state[name].get("url") != url or not http_ready(url, expected):
                raise RuntimeError(f"Managed {name} is unhealthy or its configuration changed. Run stop, then start.")
        else:
            parsed = urlparse(url)
            with socket.socket() as sock:
                sock.settimeout(1)
                if sock.connect_ex((parsed.hostname, parsed.port)) == 0:
                    raise RuntimeError(f"{name} port {parsed.port} is already in use by an unmanaged process. Stop it or change the configured port.")
    require_tools(env)
    check_python()
    if not args.no_frontend and not (ROOT / "frontend/node_modules/next/dist/bin/next").exists():
        raise RuntimeError("Frontend dependencies are missing. Run setup.")
    infra(env)
    migrate(env)
    if not (state.get("api") and owned(state["api"])) and not args.no_build:
        build_api(env)
    LOGS.mkdir(exist_ok=True)
    added = []
    try:
        for name, command, cwd, url, expected in requested:
            if state.get(name) and owned(state[name]):
                say(f"{name}: already running")
                continue
            say(f"Starting {name}; log: logs/{name}.log")
            options = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            with (LOGS / f"{name}.log").open("ab") as log:
                proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=subprocess.STDOUT, **options)
            state[name] = {**identity(proc.pid), "url": url}
            added.append(name)
            save_records(state)
            deadline = time.monotonic() + 90
            while not http_ready(url, expected):
                if proc.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(f"{name} failed to become healthy. Inspect logs/{name}.log.")
                time.sleep(1)
            say(f"{name}: ready at {url}")
    except BaseException:
        for name in reversed(added):
            terminate(state.pop(name))
        save_records(state)
        raise
    say("Services run in the background. Use status to check them and stop to end them.")
    say("Laya stays disabled. Ollama is managed separately; only reachable installed models are selectable.")


def stop(env, include_infra=False):
    state = records()
    for name in reversed(list(state)):
        record = state[name]
        terminate(record)
        del state[name]
        save_records(state)
        say(f"{name}: stopped (only matching recorded processes are targeted)")
    if include_infra:
        for mode, file in (("LOCAL_SEARCH", "compose.search.yml"), ("LOCAL_INFRA", "compose.dev.yml")):
            if env[mode] == "docker":
                compose(file, ["stop"], env)
        say("Docker services stopped. Database/cache volumes retained.")
    else:
        say("App services stopped. Docker services remain running; use stop --infra to stop them too.")


def status(env):
    state = records()
    healthy = True
    for name, _, _, url, expected in specs(env):
        live = http_ready(url, expected)
        managed = bool(state.get(name) and owned(state[name]))
        label = "healthy" if live else "unavailable"
        if live and not managed:
            label += " (not managed by these scripts)"
        say(f"{name:13} {label:42} {url}")
        healthy = healthy and live
    search = env["SEARXNG_URL"].rstrip("/") + "/healthz"
    search_ok = http_ready(search)
    say(f"{'searxng':13} {'healthy' if search_ok else 'unavailable':42} {search}")
    say("Search health checks availability only, not upstream search results.")
    return 0 if healthy and search_ok else 1


def setup(args):
    if STATE.exists() and any(owned(record) for record in records().values()):
        raise RuntimeError("Stop the app services before setup changes their dependencies.")
    if not args.skip_install:
        say("Installing launcher and service dependencies into .venv...")
        run([PYTHON, "-m", "pip", "install", "-r", ROOT / "scripts/requirements.txt",
             "-r", ROOT / "services/intelligence/requirements.txt", "-r", ROOT / "services/scrapling/requirements.txt"])
    check_python()
    with lifecycle_lock():
        sync_env()
        env = environment()
        require_tools(env)
        validate_app_endpoints(env)
        if not args.skip_install:
            npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
            if not npm:
                raise RuntimeError("npm is missing; reinstall Node.js.")
            say("Installing frontend packages from package-lock.json...")
            run([npm, "ci", "--no-audit", "--no-fund"], cwd=ROOT / "frontend", env=env)
        if args.with_browsers:
            browser = VENV / ("Scripts/scrapling.exe" if os.name == "nt" else "bin/scrapling")
            run([browser, "install"], env=env)
        infra(env)
        migrate(env)
        build_api(env)
    say("Setup complete. Run start to launch the app.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    setup_parser = sub.add_parser("setup", help="Install dependencies, preserve/sync .env, start Docker, migrate and build")
    setup_parser.add_argument("--skip-install", action="store_true", help="Use already-installed Python/frontend packages")
    setup_parser.add_argument("--with-browsers", action="store_true", help="Also install Scrapling browser dependencies")
    start_parser = sub.add_parser("start", help="Start app services in the background")
    start_parser.add_argument("--no-frontend", action="store_true")
    start_parser.add_argument("--no-build", action="store_true", help="Use an existing Rust build")
    stop_parser = sub.add_parser("stop", help="Stop only app processes recorded by this checkout")
    stop_parser.add_argument("--infra", action="store_true", help="Also stop the project's Docker services, keeping data volumes")
    sub.add_parser("status", help="Check HTTP health; returns nonzero if a service is unavailable")
    sub.add_parser("search", help="Start/check the configured search service only")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required.")
    if not PYTHON.exists():
        if args.action != "setup":
            raise RuntimeError("Run setup first to create .venv.")
        run([sys.executable, "-m", "venv", VENV])
    if Path(sys.prefix).resolve() != VENV.resolve():
        return subprocess.call([str(PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])
    if args.action == "setup":
        setup(args)
        return 0
    env = environment()
    if args.action == "status":
        return status(env)
    with lifecycle_lock():
        if args.action == "start":
            start(env, args)
        elif args.action == "stop":
            stop(env, args.infra)
        elif args.action == "search":
            validate_local_config(env)
            if env["LOCAL_SEARCH"] == "docker":
                compose("compose.search.yml", ["up", "-d", "--wait", "--wait-timeout", "120"], env)
            if not http_ready(env["SEARXNG_URL"].rstrip("/") + "/healthz"):
                raise RuntimeError("SearXNG health check failed.")
            say("SearXNG is healthy; this does not test upstream engine availability.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        say("Interrupted.")
        raise SystemExit(130)
    except ImportError:
        say("ERROR: Launcher dependencies are missing. Run setup without --skip-install.")
        raise SystemExit(1)
    except (RuntimeError, OSError, ValueError) as error:
        say(f"ERROR: {error}")
        raise SystemExit(1)
