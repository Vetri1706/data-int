#!/usr/bin/env bash
# start.sh — Launch the full Datavault stack
# Usage: ./start.sh [--no-frontend]

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a
source "$ROOT/.env" 2>/dev/null || true
if [ -f "$ROOT/.env.llm.local" ]; then
    source "$ROOT/.env.llm.local"
fi
set +a

CYAN="\033[0;36m"; GREEN="\033[0;32m"; YELLOW="\033[1;33m"; NC="\033[0m"

log() { echo -e "${CYAN}[datavault]${NC} $1"; }
ok()  { echo -e "${GREEN}✓${NC} $1"; }
warn(){ echo -e "${YELLOW}⚠${NC} $1"; }

# ── 1. PostgreSQL ──────────────────────────────────────────────────────────────
log "Checking PostgreSQL..."
if ! pg_isready -q; then
    warn "PostgreSQL not running. Starting..."
    brew services start postgresql@15 2>/dev/null || true
    sleep 2
fi
if ! psql -d postgres -c "SELECT 1" -q >/dev/null 2>&1; then
    warn "Creating datavault database..."
    psql -d postgres -c "CREATE DATABASE datavault OWNER home;" 2>/dev/null || true
fi
# Run migrations (idempotent via IF NOT EXISTS guards)
psql -d datavault -f "$ROOT/migrations/001_initial_schema.sql" >/dev/null 2>&1 || true
ok "PostgreSQL ready (datavault)"

# ── 2. Redis ──────────────────────────────────────────────────────────────────
log "Checking Redis..."
if ! redis-cli ping >/dev/null 2>&1; then
    warn "Redis not running. Starting..."
    brew services start redis 2>/dev/null || true
    sleep 1
fi
ok "Redis ready"

# ── 3. SearXNG ───────────────────────────────────────────────────────────────
log "Checking SearXNG..."
if curl -s "http://127.0.0.1:8888/healthz" >/dev/null 2>&1; then
    ok "SearXNG already running"
elif command -v docker &>/dev/null; then
    log "Starting SearXNG via Docker..."
    docker run -d --name searxng -p 8888:8080 \
        -e "SEARXNG_SECRET=$(openssl rand -hex 32)" \
        searxng/searxng:latest >/dev/null 2>&1 || true
    ok "SearXNG started on :8888"
else
    warn "SearXNG not available — search will use DuckDuckGo / Wikipedia fallback"
fi

# ── Local model (only when explicitly selected, or the local-only default) ────
if [[ "${LLM_PROVIDER:-local}" == "local" || "${LLM_FALLBACK_PROVIDER:-}" == "local" ]]; then
    if ! curl -fsS "${LOCAL_LLM_BASE_URL:-http://127.0.0.1:11434/v1}/models" >/dev/null 2>&1; then
        if [[ "${LOCAL_LLM_BASE_URL:-http://127.0.0.1:11434/v1}" != "http://127.0.0.1:11434/v1" ]]; then
            warn "Start your configured local OpenAI-compatible model server before collecting."
        else
            OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 ollama serve &
        fi
    fi
fi

# ── 4. Intelligence Service (LangGraph) ──────────────────────────────────────
log "Starting Intelligence Service (port 7000)..."
cd "$ROOT/services/intelligence"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
fi
RUST_API_BASE="${RUST_API_BASE:-http://127.0.0.1:3000/v1}" \
SEARXNG_URL="${SEARXNG_URL:-http://127.0.0.1:8888}" \
INTELLIGENCE_PORT="${INTELLIGENCE_PORT:-7000}" \
.venv/bin/python graph.py &
INTEL_PID=$!
ok "Intelligence Service PID=$INTEL_PID"

# ── 5. Rust API Server ────────────────────────────────────────────────────────
log "Building & starting Rust API (backend workspace)..."
cd "$ROOT/backend"
if [ ! -f "Cargo.lock" ]; then
    cargo build --bin api-server 2>&1
fi

DATABASE_URL="$DATABASE_URL" \
REDIS_URL="$REDIS_URL" \
JWT_SECRET="$JWT_SECRET" \
INTELLIGENCE_URL="$INTELLIGENCE_URL" \
SEARXNG_URL="$SEARXNG_URL" \
HOST="${HOST:-127.0.0.1}" \
PORT="${PORT:-3000}" \
cargo run --bin api-server &
API_PID=$!
ok "Rust API PID=$API_PID on http://${HOST:-127.0.0.1}:${PORT:-3000}"

# ── 6. Next.js Frontend ───────────────────────────────────────────────────────
if [[ "$1" != "--no-frontend" ]]; then
    log "Starting Next.js frontend (port 3001)..."
    cd "$ROOT/frontend"
    NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" \
    npm run dev -- -p 3001 &
    FE_PID=$!
    ok "Frontend PID=$FE_PID on http://localhost:3001"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Datavault stack running${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Frontend:         ${CYAN}http://localhost:3001${NC}"
echo -e "  Rust API:         ${CYAN}http://127.0.0.1:3000/v1/health${NC}"
echo -e "  Intelligence:     ${CYAN}http://127.0.0.1:7000/health${NC}"
echo -e "  SearXNG:          ${CYAN}http://127.0.0.1:8888${NC}"
echo ""
echo "  Press Ctrl+C to stop all services"

wait
