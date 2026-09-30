#!/usr/bin/env bash
# Launch the complete Datavault development stack.
# Usage: ./start.sh [--no-frontend]

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Machine-specific secrets belong in the gitignored .env.llm.local file.
set -a
[ ! -f "$ROOT/.env" ] || source "$ROOT/.env"
[ ! -f "$ROOT/.env.llm.local" ] || source "$ROOT/.env.llm.local"
set +a

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-3000}"
INTELLIGENCE_PORT="${INTELLIGENCE_PORT:-7000}"
SCRAPLING_PORT="${SCRAPLING_PORT:-8001}"
LAYA_PORT="${LAYA_PORT:-8002}"
SEARXNG_URL="${SEARXNG_URL:-http://127.0.0.1:8888}"
SCRAPLING_URL="${SCRAPLING_URL:-http://127.0.0.1:${SCRAPLING_PORT}}"
LAYA_URL="${LAYA_URL:-http://127.0.0.1:${LAYA_PORT}}"
INTELLIGENCE_URL="${INTELLIGENCE_URL:-http://127.0.0.1:${INTELLIGENCE_PORT}}"
RUST_API_BASE="${RUST_API_BASE:-http://127.0.0.1:${PORT}/v1}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379}"
DB_NAME="${DB_NAME:-datavault}"
DB_USER="${DB_USER:-$(whoami)}"
DATABASE_URL="${DATABASE_URL:-postgres://${DB_USER}@127.0.0.1:5432/${DB_NAME}}"
JWT_SECRET="${JWT_SECRET:-datavault-dev-secret-change-me}"
NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:${PORT}/v1}"
LLM_PROVIDER="${LLM_PROVIDER:-local}"
LLM_FALLBACK_PROVIDER="${LLM_FALLBACK_PROVIDER:-}"
NVIDIA_MODEL="${NVIDIA_MODEL:-meta/llama-3.2-11b-vision-instruct}"
LAYA_ENABLED="${LAYA_ENABLED:-1}"

CYAN="\033[0;36m"; GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
log()  { echo -e "${CYAN}[datavault]${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
die()  { echo -e "${RED}✗${NC} $1" >&2; exit 1; }

PIDS=()
cleanup() {
    trap - EXIT INT TERM
    for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
    for pid in "${PIDS[@]:-}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

wait_http() {
    local url="$1" name="$2" attempts="${3:-30}" i
    for ((i=1; i<=attempts; i++)); do
        if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
            ok "$name ready"
            return 0
        fi
        sleep 1
    done
    return 1
}

start_background() {
    "$@" &
    PIDS+=("$!")
}

ensure_python_env() {
    local python="$1" venv="$2" requirements="$3"
    if [ ! -d "$venv" ]; then "$python" -m venv "$venv"; fi
    if ! "$venv/bin/python" -c 'import fastapi, httpx' >/dev/null 2>&1; then
        "$venv/bin/pip" install -q -r "$requirements"
    fi
}

# PostgreSQL
log "Checking PostgreSQL..."
if ! pg_isready -h 127.0.0.1 -p 5432 -q; then
    brew services start postgresql@15 2>/dev/null || brew services start postgresql 2>/dev/null || true
    remaining=30
    until pg_isready -h 127.0.0.1 -p 5432 -q || [ "$remaining" -le 0 ]; do
        sleep 1; remaining=$((remaining - 1))
    done
fi
pg_isready -h 127.0.0.1 -p 5432 -q || die "PostgreSQL is unavailable"
if ! psql "$DATABASE_URL" -c "SELECT 1" -q >/dev/null 2>&1; then
    if ! psql -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" 2>/dev/null | grep -q 1; then
        createdb "$DB_NAME" 2>/dev/null || psql -d postgres -c "CREATE DATABASE $DB_NAME" >/dev/null
    fi
fi
if ! psql "$DATABASE_URL" -tAc "SELECT to_regclass('public.users')" 2>/dev/null | grep -q '^users$'; then
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$ROOT/migrations/001_initial_schema.sql" >/dev/null
fi
ok "PostgreSQL ready: $DB_NAME"

# Redis
log "Checking Redis..."
if ! redis-cli -h 127.0.0.1 -p 6379 ping >/dev/null 2>&1; then
    brew services start redis 2>/dev/null || true
    sleep 2
fi
redis-cli -h 127.0.0.1 -p 6379 ping >/dev/null 2>&1 || die "Redis is unavailable"
ok "Redis ready"

# SearXNG
log "Checking SearXNG..."
if ! curl -fsS --max-time 2 http://127.0.0.1:8888/healthz >/dev/null 2>&1; then
    command -v docker >/dev/null 2>&1 || die "SearXNG is unavailable and Docker is not installed"
    if docker ps -a --format '{{.Names}}' | grep -qx searxng; then
        docker start searxng >/dev/null 2>&1 || true
    else
        docker run -d --name searxng -p 8888:8080 \
            -e "SEARXNG_SECRET=$(openssl rand -hex 32)" searxng/searxng:latest >/dev/null
    fi
    wait_http http://127.0.0.1:8888/healthz "SearXNG" 45 || die "SearXNG did not become ready"
else
    ok "SearXNG already ready"
fi

# LLM provider
if [[ "$LLM_PROVIDER" == "local" || "$LLM_FALLBACK_PROVIDER" == "local" ]]; then
    command -v ollama >/dev/null 2>&1 || die "LLM_PROVIDER=local requires the Ollama binary"
    if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 \
            OLLAMA_MAX_LOADED_MODELS=1 ollama serve &
        PIDS+=("$!")
        wait_http http://127.0.0.1:11434/api/tags "Ollama" 30 || die "Ollama did not become ready"
    else
        ok "Ollama already ready"
    fi
    if [ "${OLLAMA_AUTO_PULL:-0}" = "1" ]; then
        ollama pull "${LOCAL_LLM_MODEL:-qwen2.5-coder:1.5b-instruct}"
    fi
elif [ "$LLM_PROVIDER" = "nvidia" ]; then
    [ -n "${NVIDIA_API_KEY:-}" ] || die "LLM_PROVIDER=nvidia requires NVIDIA_API_KEY in .env.llm.local"
    ok "NVIDIA provider configured: $NVIDIA_MODEL"
fi

# D4Vinci/Scrapling
log "Starting D4Vinci/Scrapling..."
SCRAPLING_PYTHON="${SCRAPLING_PYTHON:-$(command -v python3.12 || command -v python3.11 || command -v python3.10 || true)}"
[ -n "$SCRAPLING_PYTHON" ] || die "Scrapling requires Python 3.10+"
SCRAPLING_DIR="$ROOT/services/scrapling"
SCRAPLING_VENV="$SCRAPLING_DIR/.venv-scrapling"
if ! curl -fsS --max-time 2 "$SCRAPLING_URL/health" >/dev/null 2>&1; then
    ensure_python_env "$SCRAPLING_PYTHON" "$SCRAPLING_VENV" "$SCRAPLING_DIR/requirements.txt"
    "$SCRAPLING_VENV/bin/scrapling" install >/dev/null 2>&1 || warn "Scrapling browser install incomplete; static retrieval remains available"
    start_background bash -c "cd '$SCRAPLING_DIR' && exec env SCRAPLING_PORT='$SCRAPLING_PORT' '$SCRAPLING_VENV/bin/python' main.py"
    wait_http "$SCRAPLING_URL/health" "Scrapling" 45 || die "Scrapling did not become ready"
else
    ok "Scrapling already ready"
fi

# Official Laya service
if [[ "$LAYA_ENABLED" != "0" && "$LAYA_ENABLED" != "false" && "$LAYA_ENABLED" != "off" ]]; then
    log "Starting official Laya service..."
    LAYA_PYTHON="${LAYA_PYTHON:-$(command -v python3.12 || command -v python3.11 || command -v python3.10 || true)}"
    [ -n "$LAYA_PYTHON" ] || die "Laya requires Python 3.10+"
    LAYA_DIR="$ROOT/services/laya"
    LAYA_VENV="$LAYA_DIR/.venv"
    if ! curl -fsS --max-time 2 "$LAYA_URL/health" >/dev/null 2>&1; then
        if [ ! -d "$LAYA_VENV" ]; then "$LAYA_PYTHON" -m venv "$LAYA_VENV"; fi
        if ! "$LAYA_VENV/bin/python" -c 'import laya' >/dev/null 2>&1; then
            "$LAYA_VENV/bin/pip" install -q -r "$LAYA_DIR/requirements.txt"
        fi
        start_background bash -c "cd '$LAYA_DIR' && exec env LAYA_HOST=127.0.0.1 LAYA_PORT='$LAYA_PORT' LAYA_PRELOAD='${LAYA_PRELOAD:-1}' LAYA_MODELS='${LAYA_MODELS:-english}' LAYA_DEVICE='${LAYA_DEVICE:-}' '$LAYA_VENV/bin/laya-serve'"
        wait_http "$LAYA_URL/health" "Laya" 90 || die "Laya did not become ready"
    else
        ok "Laya already ready"
    fi
else
    warn "Laya disabled; intelligence will use its fail-open path"
fi

# Intelligence
log "Starting Intelligence service..."
INTEL_DIR="$ROOT/services/intelligence"
INTELLIGENCE_PYTHON="${INTELLIGENCE_PYTHON:-$(command -v python3.12 || command -v python3.11 || true)}"
[ -n "$INTELLIGENCE_PYTHON" ] || die "Intelligence requires Python 3.11+"
INTELLIGENCE_VENV="${INTELLIGENCE_VENV:-$INTEL_DIR/.venv-runtime}"
if [ -d "$INTELLIGENCE_VENV" ] && ! "$INTELLIGENCE_VENV/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    INTELLIGENCE_VENV="$INTEL_DIR/.venv-runtime"
fi
ensure_python_env "$INTELLIGENCE_PYTHON" "$INTELLIGENCE_VENV" "$INTEL_DIR/requirements.txt"
if ! curl -fsS --max-time 2 "$INTELLIGENCE_URL/health" >/dev/null 2>&1; then
    start_background bash -c "cd '$INTEL_DIR' && exec env RUST_API_BASE='$RUST_API_BASE' SEARXNG_URL='$SEARXNG_URL' SCRAPLING_URL='$SCRAPLING_URL' LAYA_URL='$LAYA_URL' LAYA_ENABLED='$LAYA_ENABLED' INTELLIGENCE_PORT='$INTELLIGENCE_PORT' LLM_PROVIDER='$LLM_PROVIDER' NVIDIA_MODEL='$NVIDIA_MODEL' '$INTELLIGENCE_VENV/bin/python' graph.py"
    wait_http "$INTELLIGENCE_URL/health" "Intelligence" 45 || die "Intelligence did not become ready"
else
    ok "Intelligence already ready"
fi

# Rust API
log "Building and starting Rust API..."
API_DIR="$ROOT/backend"
(cd "$API_DIR" && DATABASE_URL="$DATABASE_URL" cargo build --quiet --bin api-server)
if ! curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/v1/health" >/dev/null 2>&1; then
    start_background bash -c "cd '$API_DIR' && exec env DATABASE_URL='$DATABASE_URL' REDIS_URL='$REDIS_URL' JWT_SECRET='$JWT_SECRET' INTELLIGENCE_URL='$INTELLIGENCE_URL' SEARXNG_URL='$SEARXNG_URL' HOST='$HOST' PORT='$PORT' cargo run --quiet --bin api-server"
    wait_http "http://127.0.0.1:${PORT}/v1/health" "Rust API" 45 || die "Rust API did not become ready"
else
    ok "Rust API already ready"
fi

# Next.js frontend
if [[ "${1:-}" != "--no-frontend" ]]; then
    log "Starting Next.js frontend..."
    FRONTEND_DIR="$ROOT/frontend"
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then (cd "$FRONTEND_DIR" && npm install); fi
    if ! curl -fsS --max-time 2 http://127.0.0.1:3001 >/dev/null 2>&1; then
        start_background bash -c "cd '$FRONTEND_DIR' && exec env NEXT_PUBLIC_API_URL='$NEXT_PUBLIC_API_URL' npm run dev -- -p 3001"
        wait_http http://127.0.0.1:3001 "Frontend" 45 || die "Frontend did not become ready"
    else
        ok "Frontend already ready"
    fi
fi

echo
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Datavault stack running${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Frontend:      ${CYAN}http://localhost:3001${NC}"
echo -e "  Rust API:      ${CYAN}http://127.0.0.1:${PORT}/v1/health${NC}"
echo -e "  Intelligence:  ${CYAN}${INTELLIGENCE_URL}/health${NC}"
echo -e "  Scrapling:     ${CYAN}${SCRAPLING_URL}/health${NC}"
echo -e "  Laya:          ${CYAN}${LAYA_URL}/health${NC}"
echo -e "  SearXNG:       ${CYAN}${SEARXNG_URL}${NC}"
echo -e "  LLM provider:  ${CYAN}${LLM_PROVIDER}${NC}"
echo
echo "Press Ctrl+C to stop services started by this command."

if [ "${#PIDS[@]}" -gt 0 ]; then wait "${PIDS[0]}"; fi
