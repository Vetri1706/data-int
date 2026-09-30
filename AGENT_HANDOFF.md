# AGENT HANDOFF: Business Data Intelligence Platform (Datavault)

**Generated:** September 30, 2026  
**Repository:** `/Users/home/Downloads/data-intelligence-platform`  
**Remote Git:** `https://github.com/Vetri1706/data-int.git` (Branch: `master`)

---

## 1. Executive Summary & Architecture

Datavault is an autonomous business data intelligence and web extraction platform designed with a **Rust execution core** and an **adaptive LangGraph reasoning layer**. It accepts high-level natural language requirements, compiles them into structured schemas (`DataContract`), orchestrates web retrieval and multi-tier scraping, validates entity claims against verbatim source text chunks, and materializes structured, confidence-scored datasets.

### Architecture Topology

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Next.js 16 Web Dashboard (:3001)                     │
│  - Collection Builder & Review Wizard                                  │
│  - Live DagExecutionFeed & Evidence Drawer                             │
│  - Datasets, Records Table, Source Registry, Bulk Delete/Rename        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / JSON / SSE
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   Rust Axum Core API Server (:3000)                    │
│  - Workspace, Auth, Session Management (PostgreSQL 15)                 │
│  - Search Provider Cascade (SearXNG -> DuckDuckGo -> Discovery)        │
│  - Dataset & Provenance Materialization                                │
│  - Webhook endpoint: /v1/internal/intelligence/run                     │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │ /internal/search                │ /run, /parse
                   ▼                                 ▼
┌───────────────────────────────┐ ┌──────────────────────────────────────┐
│ Scrapling Stealth API (:8001) │ │ LangGraph Intelligence Layer (:7000) │
│ - Headless Chrome CDP         │ │ - parse_requirement -> build_plan    │
│ - Cloudflare bypass           │ │ - execute_search -> extract_normalize│
│ - SPA empty container check   │ │ - validate_records -> evaluate_cover │
│ - Fallback HTTP fetcher       │ │ - should_replan -> semantic_verify   │
└───────────────────────────────┘ └──────────────────────────────────────┘
                   │                                 │
                   └────────────────┬────────────────┘
                                    ▼
                 ┌──────────────────────────────────────┐
                 │ Storage: PostgreSQL (:5432)          │
                 │ Cache/Queue: Redis (:6379)           │
                 │ Local LLM: Ollama (:11434)           │
                 └──────────────────────────────────────┘
```

---

## 2. Port & Service Inventory

| Service | Port | Directory | Tech Stack | Health / Status Endpoint |
| :--- | :--- | :--- | :--- | :--- |
| **Rust API Server** | `3000` | `backend/apps/api-server` | Rust, Axum, SQLx, Tokio | `GET http://127.0.0.1:3000/v1/health` |
| **Intelligence Engine**| `7000` | `services/intelligence` | Python 3.12, FastAPI, LangGraph | `GET http://127.0.0.1:7000/health` |
| **Next.js Frontend** | `3001` | `frontend` | Next.js 16, React 19, Tailwind | `GET http://localhost:3001` |
| **Scrapling Stealth** | `8001` | `services/scrapling` | Python 3, FastAPI, Scrapling | `GET http://127.0.0.1:8001/health` |
| **PostgreSQL** | `5432` | System (`brew services`) | Postgres 15 (`datavault` DB) | `psql -d datavault -c "SELECT 1;"` |
| **Redis** | `6379` | System (`brew services`) | Redis Server | `redis-cli ping` |
| **Ollama LLM** | `11434`| System (`ollama serve`) | `qwen2.5-coder:1.5b-instruct` | `GET http://127.0.0.1:11434/api/tags` |
| **SearXNG (Optional)**| `8888` | Docker container | SearXNG meta-search | `GET http://127.0.0.1:8888/healthz` |

---

## 3. Major Bugs Resolved & Hardening Implemented

### Issue 1: "Workflow exceeded its 180s time limit" & Dropped Records
- **Symptoms**: Collection runs for complex queries (e.g. *EV battery suppliers in India*) failed with timeout, reporting 0 records found despite the LLM extracting 31-54 raw candidates.
- **Root Cause 1 (`constraint_passes`)**: Small models generated `operator: "is_not_empty"` for hard constraints. `constraint_passes` in `grounding.py` only supported `eq`, `contains`, `gte`, returning `False` for `is_not_empty` and discarding every candidate.
- **Root Cause 2 (`supported` & `eval_text`)**: `supported` required exact string containment; composite location strings like `"Bengaluru, Karnataka, India"` failed when text contained `"Bengaluru, Karnataka"`.
- **Root Cause 3 (Timeout Drop)**: LangGraph threw `TimeoutError` at 180s during replanning loops, executing `post_run_event("run.failed")` and discarding all extracted records.
- **Root Cause 4 (Infinite Replan)**: `evaluate_coverage` counted only strictly verified records, leading to coverage `0/10 = 0.0%`, keeping the graph looping on slow local CPU inference.
- **Fixes Applied**:
  1. Updated `constraint_passes` in `grounding.py` to support `is_not_empty`, `not_empty`, `exists`, `not_null`, `in`, `not_in`, `!=`, and case/whitespace tolerance.
  2. Implemented `extract_canonical_name` in `grounding.py` to dynamically resolve canonical entity identity across any schema (`company_name`, `supplier_name`, `name`, `title`, first required field).
  3. Added `ACTIVE_RUN_STATES` in `graph.py` to track workflow state in flight. On `TimeoutError`, if extracted records exist, they are salvaged as draft records with full provenance and materialized into the database via `run.completed`.
  4. Updated `should_replan` to exit early when sufficient records exist (`len(validated) >= 5` or `len(extracted) >= 10` on iteration >= 1).
  5. Capped `max_iterations = 1` for local models, and increased `WORKFLOW_TIMEOUT_SECONDS = 300` in `.env.llm.local`.

### Issue 2: GitHub Push Protection Rejection
- **Symptoms**: `git push -u origin master` failed with `remote: error: GH013: Repository rule violations ... Groq API Key / GCP API Key found in .env`.
- **Root Cause**: `.env` was committed in early prototype commits (`eb880eb`, `27361ed`).
- **Fixes Applied**:
  1. Added `.env` explicitly to `.gitignore`.
  2. Executed `git filter-branch` to rewrite commit history and remove `.env` across all past commits.
  3. Committed the full multi-crate platform (`backend/`, `frontend/`, `services/`, `migrations/`, `start.sh`).
  4. Successfully pushed clean tree to `https://github.com/Vetri1706/data-int.git`.

### Issue 3: macOS Disk Space Exhaustion (99.9% Full / 290MB free)
- **Symptoms**: Background tasks and processes intermittently exited with `Killed: 9` or `no space left on device`.
- **Root Cause**: `~/.npm` (8.8GB) and `~/Library/Caches/` (6GB) filled the 228GB disk.
- **Fixes Applied**: Cleared stale caches, freeing **11 GB** of disk space.

---

## 4. Key Files & Code Map

```
/Users/home/Downloads/data-intelligence-platform/
├── start.sh                              # Complete stack launcher with dependency checks
├── .env                                  # Core environment (gitignored)
├── .env.example                          # Safe environment template
├── .env.llm.local                        # Machine-specific LLM config (gitignored)
├── migrations/
│   └── 001_initial_schema.sql            # Postgres DDL: collections, datasets, runs, sources
├── backend/                              # Rust Cargo Workspace
│   ├── Cargo.toml
│   ├── apps/
│   │   ├── api-server/                   # Axum HTTP Server (:3000)
│   │   │   └── src/handlers/             # collections.rs, datasets.rs, runs.rs, internal.rs
│   │   └── worker/                       # Background task worker
│   └── crates/
│       ├── auth/                         # JWT authentication & session token hashing
│       ├── domain/                       # Core domain types (DataContract, SearchRequest)
│       ├── search/                       # SearXNG, DuckDuckGo, LLM Grounded discovery
│       └── storage/                      # SQLx PostgreSQL repository layer
├── services/
│   ├── intelligence/                     # LangGraph Reasoning Engine (:7000)
│   │   ├── graph.py                      # LangGraph StateGraph, nodes, routing, salvage logic
│   │   ├── grounding.py                  # Chunking, TF-IDF lexical validation, constraint check
│   │   ├── llm.py                        # ModelGateway (Ollama / NVIDIA fallback)
│   │   └── test_*.py                     # 55 unit tests (all passing)
│   └── scrapling/                        # Adaptive Scraping Microservice (:8001)
│       └── main.py                       # 3-tier fetcher: Static, Dynamic, Stealthy CDP
└── frontend/                             # Next.js 16 Web Dashboard (:3001)
    ├── app/                              # Collections, Datasets, Sources, Workflows
    └── components/                       # DagExecutionFeed, EvidenceDrawer, MetricCards
```

---

## 5. Invariants & Architecture Rules (MANDATORY)

1. **Zero Hardcoded Domain Keywords**:
   - **NEVER** introduce domain-specific hardcoded keywords, manual category word lists, brand/model dictionaries, or ad-hoc regex whitelists/blacklists (e.g. vehicle terms, job terms, electronics terms).
   - Domain knowledge must originate dynamically from the LLM Planner / Intent engine via `queryContext.extractionSchema` and structured `constraints`.
2. **Strict Constraint Contracts**:
   - Any candidate that violates an active hard constraint (`is_hard: true` where `passes === false`) must **NEVER** be promoted to `verified`.
3. **Evidence Attributed Provenance**:
   - Candidates must have an exact `source_url`, `chunk_id`, and `evidence_excerpt` grounded in real web text fetched by the system.
4. **Terminal Storage Reliability**:
   - Every completed run must write its entities to `dataset_records` in PostgreSQL. If timeout occurs, salvage candidate records into `draft` records rather than failing the run.

---

## 6. How to Run & Verify

### Starting the Services
```bash
cd /Users/home/Downloads/data-intelligence-platform
./start.sh
```

### Health Verification Commands
```bash
curl -s http://127.0.0.1:3000/v1/health   # Rust API
curl -s http://127.0.0.1:7000/health      # LangGraph Intelligence
curl -s http://127.0.0.1:8001/health      # Scrapling Service
curl -s http://127.0.0.1:11434/api/tags   # Ollama Models
```

### Running Intelligence Unit Tests
```bash
cd /Users/home/Downloads/data-intelligence-platform
services/intelligence/.venv/bin/python -m unittest discover -s services/intelligence
# Expect: Ran 55 tests in ~0.2s - OK
```

### Running Rust Backend Tests
```bash
cd /Users/home/Downloads/data-intelligence-platform/backend
cargo test --workspace
```

---

## 7. Immediate Next Steps for the Next Agent

1. **Live Smoke Test in Web UI**:
   - Boot `./start.sh`, visit `http://localhost:3001/collections/new`.
   - Submit: *"List EV battery and component suppliers in India with direct catalog links, locations, and certifications"*.
   - Confirm the run transitions through stages and materializes records into the dataset.

2. **Milestone A — Connect Scrapling Stealth to Intelligence Grounding**:
   - In `services/intelligence/grounding.py`, when static HTTP fetching in `fetch_source` returns an empty container (e.g., length < 1,500 chars or `<div id="root"></div>`), delegate the fetch to `http://127.0.0.1:8001/extract` to invoke Scrapling's headless Chrome CDP tier.

3. **Milestone B — Real-Time SSE DAG Stepper**:
   - Connect `frontend/components/collection/DagExecutionFeed.tsx` to `GET /v1/runs/{id}/events` (SSE) so users see live step progress without polling.

4. **Milestone C — Scheduled Workflows**:
   - Enable recurring runs in `backend/apps/worker` for periodic monitoring of datasets.
