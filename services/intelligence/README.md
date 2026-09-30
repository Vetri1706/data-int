# Evidence retrieval and validation

## Model providers

Choose **Provider** and **Model** in New collection, then review before running.
The selection is stored with that collection and applies to parsing, planning,
source suggestions, extraction, and replanning. Legacy collections default local.
Validation combines typed rules with a separate model review for prose and heading
relationships. Model-reviewed support requires an exact quotation from an HTTP 200
source, a matching value and a field relation cue. Invented quotes and citations,
historical/hypothetical statements and deterministic contradictions are rejected.
Each citation records its verification method. This is not a calibrated truth score.

Academic discovery now searches department facilities and research laboratories
separately, preserving the subject and region instead of relying on one rankings-heavy
query. The planner does not seed institution names or URLs. User-approved domains
remain hard limits; create a new collection to discover a new scope. Existing runs
and their approval records are not rewritten.
Model judgments on search snippets are advisory: a model cannot exclude a page
by inventing a location. The source-permission and robots checks still block access.
Generated contracts add fields referenced by hard constraints, and regional
constraints use geographic matching rather than requiring the literal words
"South India" in an address. Explicit academic subjects in "in X in Y" requests
are preserved as field constraints. Verification runs between extraction waves,
so later timeouts retain rows that have already passed the checks.

Scrapling retrieves pages; Trafilatura removes navigation boilerplate while contact
footers remain available. Retrieval uses 1,600-character passages, covers distinct
pages before repeating a directory, removes image-only name evidence, and reviews claims using context from
the same fetched page. Explicit South India scope is checked against known state/city
aliases; unknown locations fail closed. Other geographic scopes still depend on the
generated constraints. Institution type is optional unless the user requests it.

- Local: Ollama at `http://127.0.0.1:11434/v1`. The selector lists every installed
  model returned by `/api/tags`, including custom models. No automatic downloads.
  Cloud-relayed models remain visible but disabled to preserve local-only processing.
- NVIDIA: `https://integrate.api.nvidia.com/v1`. The selector lists the entire live
  `/models` catalog rather than a fixed shortlist. Embedding and reranking models
  remain visible but disabled because collection workflows need text generation.
  Requires `NVIDIA_API_KEY` in the server environment / `.env.llm.local`, and
  explicit per-collection consent to send prompts, fields, queries, and passages.
  Catalog access does not guarantee inference access or compatibility for every
  model; failures remain explicit and never silently switch to another model.
- No implicit Groq fallback, no browser credentials, and no silent provider switch.

**Refresh models** fetches both catalogs in parallel without sending prompts or
passages. Server-side selection validation uses the same catalog (cached up to
60 seconds); newly discovered text models are accepted without code changes.
Provider failures have bounded deadlines and a retry action, not fallback lists.

The private `.env.llm.local` file is gitignored and should be mode `600`. Python
loads it before legacy `.env`; explicit process variables take precedence. The
launcher also loads it. Never put model keys in `NEXT_PUBLIC_*` variables.

`LLM_MAX_CONCURRENCY`, `LLM_TIMEOUT_SECONDS`, `LLM_TOTAL_TIMEOUT_SECONDS`,
`LLM_MAX_TOKENS`, and `WORKFLOW_TIMEOUT_SECONDS` control limits. The total model
deadline includes queue wait. SDK retries are disabled; 429/5xx responses open a
30-second provider cooldown. Failed model calls stop the run, not more replanning.
`GET /health` shows non-secret defaults and limits; authenticated `/v1/me/models`
proxies `/models`. The Rust URL suggestion fallback uses the same gateway via
`/discover`, carrying the collection's provider selection. Both internal services
bind to loopback. Browser requests cannot reach internal workflow callbacks.

Run provider/workflow fixtures without spending hosted credits:
`services/intelligence/.venv/bin/python -B -m unittest discover -s services/intelligence -p 'test_*.py'`.

The five critical handoff fixes are implemented in `grounding.py`, the LangGraph
nodes in `graph.py`, the Rust search crate, and the frontend evidence adapters.

## Retrieval

- Search uses natural language keywords. Planner domain suggestions do not become
  mandatory `site:` restrictions. Explicit `domain_filters` remain hard filters.
- The provider cascade is SearXNG → DuckDuckGo HTML search → Wikipedia → LLM
  discovery. Indexed links and LLM suggestions are verified before returning.
- Rust follows bounded redirects and checks HEAD, falling back to GET for servers
  that reject HEAD. Requests have a 1.5 second timeout. A dead deep URL can fall
  back to its checked root; the deep-page title/snippet is discarded.
- Python fetches actual source text with eight concurrent requests, a 1 MB body
  limit, an eight-second overall candidate deadline, and at most 24,000 normalized
  text characters per page. Generated snippets never become extraction evidence.
- Retrieval creates 500-character chunks at a 100-character stride, ranks them
  using scikit-learn TF-IDF cosine similarity, and chooses up to 24 relevant,
  diversified chunks. Each source contributes at most four non-repetitive chunks.
- Offsets refer to normalized fetched text, not raw HTML bytes. The stored SHA-256
  identifies that normalized source text. Chunk text and offsets persist on each
  field citation. Replanning preserves previous attributed chunks and records.

## Confidence

`reachability × (0.10 authority_prior + 0.25 grounding + 0.20 ml_validation
+ 0.15 agreement + 0.10 freshness + 0.20 completeness)`

Direct HTTP 200 retrieval has reachability 1; redirects and root fallback have
reachability 0.7. Failed retrieval is excluded. The authority component is an
explicit domain prior, not a measured probability. Unknown domains use 0.5.

Grounding uses claim-to-chunk TF-IDF similarity. `ml_validation_score` combines
lexical grounding, supported attributes, and entity-type coherence. It rejects
ungrounded names, fabricated chunk IDs, generic directory titles, obvious
accessories when companies/people were requested, and unsupported hard constraints.
Unsupported schema values become null. Only matching source text becomes evidence.

Agreement counts independent registrable domains supporting the same identity and
attributes. Subdomains, repeated citations, and identical mirrored text do not add
votes. One source scores 0, two score 0.5, and three or more score 1.

Freshness decays against the requested window using a publication timestamp. A
crawl timestamp is explicitly labelled and capped at 0.5; if publication dates are
required, unknown dates score zero. Completeness counts evidence-supported required
fields, including valid zero values, rather than merely nonempty model output.

Verified records require score ≥0.75, all required fields, the minimum independent
source count, and required publication dates. Scores ≥0.5 are marked for review;
lower retained candidates remain drafts. These scores are **not calibrated truth
probabilities** and lexical similarity does not constitute full semantic entailment.
A trained entailment classifier needs representative labelled evaluation data.

## Storage and UI

Completion commits the dataset, full record provenance, source health, collection
status, and run event in one transaction before publishing completion. Repeated
completion callbacks do not duplicate datasets. JSON and CSV downloads include the
stored attributes and confidence breakdown, including citation metadata.

The dashboard, collection results, history, datasets, and sources read `/v1/collections`,
`/v1/runs`, `/v1/datasets`, and `/v1/sources`. API errors are visible. They do not
substitute sample records for failed requests. Missing evidence metrics and HTTP
checks display as unknown, not 92% or 200 OK. Other prototype routes are outside
this engine-fix pass.

## Verification and rollout

```sh
cd services/intelligence
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m unittest test_grounding test_workflow -v
cd ../../backend
cargo test -p datavault-search
cargo check --bin api-server
cd ../frontend
npm run lint
npm run build
```

`frontend/scripts/verify-evidence.cjs` uses Playwright with local API fixtures to
check measured confidence, unknown health, exact citation offsets, tab interaction,
mobile width, and error states. Set `PLAYWRIGHT_MODULE` to an installed Playwright
module and `VERIFY_BASE_URL` to a running frontend (default port 3001).

Restart the Rust API and intelligence processes after updating. No schema migration
is required; existing source-health and JSONB columns are used. Historical records
retain their original stored scores; rerun a collection to obtain measured evidence.
The tests use HTTP/model fixtures and do not spend LLM credits or alter user datasets.

The separate handoff roadmap (worker/crate implementations, scheduling, alerts,
cloud exports, external integrations, and provenance graph) remains future work.
