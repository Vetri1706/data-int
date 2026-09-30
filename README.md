# Datavault

Hackathon prototype for turning a business prompt into a structured dataset with inspectable, field-level source evidence. The current verifier is conservative and extractive. This repository does **not** establish enterprise readiness or general web-fact accuracy.

## Current execution path

Next.js dashboard -> Rust API / PostgreSQL -> Python LangGraph workflow -> search providers -> permission gate -> Scrapling retrieval -> extraction -> typed verification -> entity resolution -> acceptance gate -> versioned dataset.

The LLM proposes queries, a data contract and candidate values. Only the verifier can accept candidate values. SearXNG and TF-IDF are discovery/ranking components, not truth estimators. The graph has fixed supported stages with dynamic queries and bounded replanning; it does not execute arbitrary generated scraper code.

## Trust and acceptance

Each requested field has `supported`, `contradicted` or `unknown`, with a reason. Supported claims retain the actual retrieved URL, chunk ID, normalized-text character offsets, quote, content hash and available timestamps. Model-generated quotes and fabricated chunk IDs cannot establish support.

The verifier recognizes explicit subject/field statements, numeric scales and units, URLs, ISO dates, booleans and exact list members. It abstains on unsupported paraphrases, ambiguous subjects and modal statements. This is a limited grammar, not a general natural-language entailment model. A supported claim means the retrieved passage explicitly states the value; it does not prove that the publisher is truthful.

Required fields and hard constraints must pass before a row enters an accepted dataset. Optional unsupported values are null. Review candidates and conflicts are retained separately in execution history. Freshness requires a publication date when requested; crawl time does not substitute for it. Minimum-source checks count distinct registered domains after exact-content mirror removal; different domains are not proof of independent ownership.

Confidence probabilities and invented authority/default scores are not assigned. Field coverage is the fraction of requested fields with supported values. Legacy datasets retain their historical values and are labelled as not verified by the new method.

## Workflow and identity

- `completed`: accepted count reaches the target and average accepted-row field coverage reaches `min_field_coverage` (default 1).
- `partial`: accepted rows exist but the completion conditions were not met within the execution budget.
- `exhausted`: no accepted rows were obtained within that budget. This does not mean no qualifying entities exist on the web.
- `failed` and `cancelled` are distinct terminal states.

Replanning considers unattempted candidates and receives missing fields, contradictions, policy/retrieval failures and evidence requirements. It cannot relax source permission or hard constraints. Raw drafts are never rescued into datasets on timeout.

Identity depends on entity type: jobs use posting URLs, people use profile URLs, products use manufacturer and model/SKU, companies use supported website domains or registry ID plus jurisdiction. Missing strong identifiers keep matches local to a source page. Complementary supported claims merge; conflicting values remain conflicts. Ambiguous cross-source duplicates may remain separate.

Cancellation persists first in PostgreSQL, interrupts the Python workflow and cancels active scraper tasks. Late callbacks cannot replace a cancelled result. Real stage transitions and events are stored in PostgreSQL. Execution is still in-process: crash recovery and durable resume are not implemented, and pause returns an explicit unsupported response.

Dataset routes load the requested dataset ID; history links to individual runs. Workflow templates pass actual prompts, fields, entity types and target counts into collection creation.

## Source permission

Collection creation starts with a prompt and optional domain restrictions. Continue discovers candidate domains using search engines and opens source review; it does not require users to know websites in advance. Discovery reads search-provider metadata, without fetching result pages or invoking an LLM fallback. A basic keyword filter removes generic off-topic hits; it is a discovery heuristic, not claim verification, and can miss relevant paraphrases. It does not create a collection or run. Empty results and discovery failures offer retry/edit actions, not invented source suggestions.

Before collection starts, users review the suggested domains and confirm permission for their selection. Explicit approved domains and that attestation are then recorded with user and time; this is not an automated determination of a site's legal terms. Suggested domains never grant permission by themselves. Optional hard domain restrictions remain enforced through discovery and retrieval.

Retrieval checks the approved scope, blocked/disabled sources, robots rules and public URLs. Redirect destinations are checked before retrieval. Hard domain filters fail closed even when search falls back to another provider. Unknown robots/control policy stops retrieval. Public availability by itself does not grant collection permission.

Normal browser rendering is allowed for permitted pages without usable static content. CAPTCHA, authentication errors, forbidden responses and rate limits do not trigger stealth/anti-bot escalation. Browser subrequests must remain within the approved domains. Keep backend and service ports private; the frontend bridge does not expose internal service callbacks.

## Local setup

Use the [cross-platform scripts](scripts/README.md) for setup, start, status and stop. Requires Docker with Compose, Rust, Python 3.11+ and Node.js 20.9+. Docker provides local PostgreSQL, Redis-compatible Valkey and SearXNG; application services run on the host. Setup preserves existing `.env` values, backs it up before changes, and fills missing settings/secrets.

```powershell
# Windows (from the repository root)
powershell -ExecutionPolicy Bypass -File scripts/windows/dev.ps1 setup
powershell -ExecutionPolicy Bypass -File scripts/windows/dev.ps1 start
powershell -ExecutionPolicy Bypass -File scripts/windows/dev.ps1 status
# Stop app processes; add --infra to also stop Docker services while keeping data
powershell -ExecutionPolicy Bypass -File scripts/windows/dev.ps1 stop
```

```sh
# macOS: use scripts/macos/dev.sh; Linux: use scripts/linux/dev.sh
bash scripts/macos/dev.sh setup
bash scripts/macos/dev.sh start
```

The old `bash start.sh` entry point forwards to the shared launcher. See the scripts guide for browser dependencies, logs, existing databases, changed ports, and optional flags. To run services manually instead:

1. Create a database and set `DATABASE_URL`. Apply `migrations/001_initial_schema.sql` **only for an empty database**, then `migrations/002_trust_and_workflow.sql`. Existing databases need only migration 002. The API and launcher also apply the idempotent migration 002 on startup. SQLx compilation needs the migrated database available.
2. Install Python dependencies from `services/intelligence/requirements.txt` and `services/scrapling/requirements.txt` in your virtual environment. Install Scrapling's browser dependencies if browser rendering is needed.
3. Start the configured search service and Redis. Configure local Ollama or a hosted provider as described below. Each hosted collection requires explicit external-processing consent.
4. Start the services in separate shells, with repository environment variables available:

```sh
# From services/intelligence
python -m uvicorn graph:app --host 127.0.0.1 --port 7000
# From services/scrapling
python -m uvicorn main:app --host 127.0.0.1 --port 8001
# From backend
cargo run -p api-server
# From frontend
npm ci
npm run dev -- --port 3001
```

Open the frontend at `http://localhost:3001`. On Windows use `npm.cmd` if PowerShell blocks npm scripts. Existing collections without a permission policy cannot be rerun; create a new collection with approved domains.

### Local SearXNG in Docker

From the repository root, with Docker Desktop running:

```sh
docker compose -f compose.search.yml up -d --wait
docker compose -f compose.search.yml ps
docker compose -f compose.search.yml logs --tail 30 searxng
```

Open `http://127.0.0.1:8888`. The root `.env` contains `SEARXNG_URL`, the host port, pinned official image digests and a private `SEARXNG_SECRET`. For a fresh setup, copy the example's settings and generate a random secret before starting Compose. Only search-specific variables enter the container; model API keys stay outside it. Settings are in `infra/searxng/settings.yml`; HTML and JSON responses are enabled. Valkey is a private search cache with no host port. It does not replace the application's separate Redis service.

The instance listens on host loopback only and restarts with Docker unless deliberately stopped. Its health check confirms the HTTP service, not upstream engine availability. To check an actual search in PowerShell:

```powershell
$result = Invoke-RestMethod 'http://127.0.0.1:8888/search?q=Python%20documentation&format=json'
$result.results | Select-Object -First 5 title, url, engines
$result.unresponsive_engines
```

Google, Bing and Wikipedia are enabled by default. The initial live check on this machine returned results from Google/Bing; DuckDuckGo returned a CAPTCHA and Brave returned HTTP 429, so those two engines are disabled by default in the settings file. Their access failures are not bypassed.

To exercise the app's actual Rust SearXNG adapter and hard domain filter, without a database, LLM or fallback provider:

```sh
cd backend
cargo run -p datavault-search --example searxng_smoke
# Optional arguments: search query, required domain
cargo run -p datavault-search --example searxng_smoke -- "Python documentation" python.org
```

The discovery order is [DDGS](https://github.com/deedy5/ddgs) (DuckDuckGo, then Yahoo), SearXNG, then Wikipedia. Production discovery uses search-engine results only; model-generated URL fallback is disabled. DDGS runs inside the Scrapling service with bounded calls, deduplication and a short metadata cache. Reviewed URLs seed collection directly and still pass through relevance, permission and evidence validation. The source review shows real search titles, snippets and provider names, with coarse intent screening; these are not verified evidence. Each fallback must still satisfy hard domain restrictions. Permissions, robots rules, [Scrapling](https://github.com/D4Vinci/Scrapling) page retrieval and typed claim verification happen afterward. A search result or reachable URL alone is not evidence of a supported claim. Upstream engines may time out, return CAPTCHAs or rate-limit; no proxy or CAPTCHA escalation is enabled.

Manage only this search stack with `docker compose -f compose.search.yml stop` or `docker compose -f compose.search.yml up -d --wait`. `down` removes its containers/network while retaining named cache volumes. After changing `settings.yml`, use `docker compose -f compose.search.yml restart searxng`. The official [container guide](https://docs.searxng.org/admin/installation-docker.html) and [JSON search API documentation](https://docs.searxng.org/dev/search_api.html) describe the underlying configuration.

## Verification and evaluation

```sh
python -m unittest discover -s services/intelligence -p 'test_*.py'
# From services/scrapling
python -m unittest discover -v
# From backend, with DATABASE_URL and TEST_DATABASE_URL pointing to an isolated migrated database
cargo test --workspace
# From frontend
npm run build
# PLAYWRIGHT_MODULE can point to an installed Playwright package; requires Chrome and a local frontend
node scripts/verify-evidence.cjs
# From repository root
python evaluation/run_claim_benchmark.py
```

The Rust database integration test runs when `TEST_DATABASE_URL` is supplied. It creates UUID-scoped fixtures and removes only its own records. Browser tests explicitly mock API responses; they are not live data-collection measurements.

The labelled benchmark compares the frozen lexical baseline from commit `2981853` against typed verification on identical claim/source pairs. Labels are synthetic and author assigned, not independently adjudicated. See [evaluation details](evaluation/README.md) and [machine-readable results](evaluation/results/claim_benchmark.json).

Laya is disabled in production run initialization and by default in the filter/launcher. It remains available only for explicit offline experiments. Enabling it requires evidence of reduced extraction cost or latency without losing accepted records or increasing false support on an independently labelled, frozen evaluation set.


### LLM providers and model costs

Set credentials in the root, gitignored `.env`, then restart the intelligence service. Environment variables supplied by the process take precedence; `.env.llm.local` remains a legacy fallback. Credentials stay server-side.

| Provider | Server configuration | Discovery |
| --- | --- | --- |
| GLM / Z.ai | `GLM_API_KEY` | Live catalog plus the two documented free Flash models omitted by `/models` |
| Groq | `GROQ_API_KEY` | Live model catalog |
| NVIDIA | `NVIDIA_API_KEY` | Live model catalog |
| Gemini | `GEMINI_API_KEY` | Paginated Gemini model catalog |
| OpenRouter | `OPENROUTER_API_KEY` | Live model catalog and pricing |
| Hugging Face | `HUGGINGFACE_API_KEY` | Live chat catalog, pinned to each available inference provider |
| Local Ollama | `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL` | Installed models on a reachable loopback server; no API key |

A hosted provider without its key is disabled before any catalog request. Revoking a key in the running configuration also invalidates its cached availability. Restart after editing `.env`. Catalog success establishes discovery access, not sufficient inference quota or a tested collection run. No inference is triggered by opening or refreshing the picker. HTTP failures disable the provider and expose a sanitized reason.

The picker honors each provider's configured model when it is available, including when switching providers. Local inference uses Ollama's [native chat API](https://docs.ollama.com/api/chat) with [JSON schemas](https://docs.ollama.com/capabilities/structured-outputs), `think=false`, `LOCAL_LLM_NUM_CTX=8192` and `LOCAL_LLM_MAX_TOKENS=1024`. Extraction sends four passages and requests at most two records per local call. The existing request and workflow deadlines still apply; there is no automatic switch to a hosted model. `LOCAL_LLM_DISABLED_MODELS` optionally excludes a comma-separated list of installed models that fail deployment-specific checks. Metadata discovery alone does not prove structured-output compatibility.

On this installation, `deepseek-r1:1.5b` exhausted a 1,024-token structured extraction without valid JSON; `qwen2.5:3b` produced valid JSON on the same passages. The local configuration now selects Qwen and excludes that DeepSeek model. The [live smoke result](evaluation/results/local-inference-smoke.json) records the limitation: the full EV workflow ran without a model timeout, but no draft passed all evidence requirements. This is latency validation, not a data-quality success. Failed-run pages offer a new collection setup using the original prompt, original domain restrictions, and configured local model; historical runs are preserved.

Model order is **free / local, free tier, credits, paid, unknown**. Free-tier labels describe eligibility, not the account's billing plan or remaining allowance. Hugging Face routes are explicitly pinned (`model:provider`) so a free route cannot silently switch to a paid route. Unknown prices stay unknown; zero-looking HF prices accompanied by `is_free: false` are not advertised as free. Specialized image/audio/embedding/moderation models are not runnable collection models.

Pricing references (reviewed 2026-09-30): [Z.ai](https://docs.z.ai/guides/overview/pricing), [Groq free-plan limits](https://console.groq.com/docs/rate-limits), [Gemini](https://ai.google.dev/gemini-api/docs/pricing), [Hugging Face credits](https://huggingface.co/docs/inference-providers/en/pricing), [Hugging Face catalog metadata](https://huggingface.co/docs/inference-providers/en/hub-api), [OpenRouter catalog](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties). Static price classifications in `services/intelligence/providers.py` must be reviewed when these policies change; unknown new models are not automatically called free.

`LLM_PROVIDER` chooses a preferred provider, not permission to run hosted inference. The picker defaults to an available model with no external-processing consent. It never silently changes provider after a user selects a model or when inference fails.
