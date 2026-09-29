# AI-Powered Data Intelligence & Search Grounding Platform

An enterprise-grade, prompt-driven data intelligence platform built with **Rust (Axum + Tokio)** as the high-performance execution core and a **Contract-Driven Workflow DAG** with field-level evidence provenance and multi-factor confidence scoring.

---

## 🏛️ Architecture Overview

The platform bridges natural-language business requests to deterministic, auditable, source-backed datasets through a structured contract-driven pipeline:

```text
                           USER PROMPT
                                │
                                ▼
                 ┌─────────────────────────────┐
                 │    Requirement Compiler     │ ──► [Data Requirement Contract]
                 └──────────────┬──────────────┘
                                │
                                ▼
                 ┌─────────────────────────────┐
                 │     Workflow DAG Planner    │ ──► [DRAFT → PLANNING → DISCOVERY → ...]
                 └──────────────┬──────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
   │   SearXNG    │      │  Wikipedia   │      │ Source Intel │
   │  Discovery   │      │  OpenSearch  │      │   Registry   │
   └──────┬───────┘      └──────┬───────┘      └──────┬───────┘
          └─────────────────────┼─────────────────────┘
                                ▼
                 ┌─────────────────────────────┐
                 │  Adaptive Extraction (RAG)  │ ──► [JSON-LD + DOM + Live Text Chunks]
                 │       & 404 Link Purge      │
                 └──────────────┬──────────────┘
                                │
                                ▼
                 ┌─────────────────────────────┐
                 │  ML / Rule Verifier & Multi-│ ──► [Structural, Constraint, & Semantic Checks]
                 │   Factor Confidence Engine  │
                 └──────────────┬──────────────┘
                                │
                                ▼
                 ┌─────────────────────────────┐
                 │  Entity Resolution & Graph  │ ──► [Canonical Naming, Cross-Source Merging]
                 └──────────────┬──────────────┘
                                │
                                ▼
                 ┌─────────────────────────────┐
                 │    Interactive Dashboard    │ ──► [Clickable Field Evidence & Provenance Quotes]
                 └─────────────────────────────┘
```

---

## 🚀 Key Architectural Pillars

### 1. Data Requirement Contract
Instead of unconstrained searching, incoming prompts are compiled into a deterministic schema contract:
```json
{
  "entity": "job_opening",
  "fields": {
    "job_title": "string",
    "company_name": "string",
    "location": "string",
    "salary": "currency",
    "employment_type": "string",
    "job_url": "url"
  },
  "constraints": [
    "location ~= Bangalore",
    "role related_to Rust",
    "employment_type in [\"remote\", \"hybrid\"]"
  ],
  "critical_fields": ["job_title", "company_name", "location", "salary", "job_url"],
  "target_count": 25,
  "freshness": "7 days"
}
```

### 2. Pluggable `SearchProvider` Abstraction
SearXNG is isolated behind a clean trait interface (`src/pipeline/search_provider.rs`):
```rust
pub trait SearchProvider: Send + Sync {
    async fn search(&self, query: &str, limit: usize) -> Vec<SearchResultItem>;
}
```
Implementations include:
- `SearxngSearchProvider` (Local SearXNG instance on `http://127.0.0.1:8888`)
- `WikipediaSearchProvider` (Authoritative OpenSearch documentation)
- `LlmFallbackSearchProvider` (Grounded query generator)

### 3. Source Intelligence Engine (`src/pipeline/source_registry.rs`)
Maintains dynamic domain reliability and trust profiles:
- **Primary Official Portals** (`0.95 - 0.98` authority): Direct company careers, verified documentation.
- **Secondary Trusted Platforms** (`0.82 - 0.88` authority): LinkedIn, Indeed, Glassdoor, TripAdvisor, Booking.com.
- **Tertiary General Web** (`0.65 - 0.75` authority): Blogs, discussion forums.

### 4. Adaptive RAG Extraction & 404 Purge (`src/pipeline/scrapler.rs`)
- Traverses `<script type="application/ld+json">` schemas (`JobPosting`, `Hotel`, `Product`) first before falling back to DOM text chunks.
- Performs concurrent live HTTP availability checks; links returning `404`, `410`, or `5xx` are discarded.

### 5. Explainable Multi-Factor Confidence Scoring (`src/pipeline/validator_engine.rs`)
Replaces static single numbers with a multi-factor mathematical score:
$$\text{Record Confidence} = 0.30 \cdot \text{Authority} + 0.25 \cdot \text{Certainty} + 0.20 \cdot \text{Agreement} + 0.15 \cdot \text{Freshness} + 0.10 \cdot \text{Completeness}$$

### 6. Field-Level Evidence & Provenance Modal
Every extracted field records:
- **Exact quoted text excerpt** from the live web page.
- **Source URL** and **Page Title**.
- **Source Type badge** (e.g. `Official Company Page`, `Primary Job Board`).
- **Retrieval timestamp** and **Field-level confidence**.

### 7. Entity Resolution & Deduplication (`src/pipeline/entity_resolver.rs`)
- Normalizes corporate suffixes (`Zoho Corp`, `ZOHO`, `Zoho Corporation` $\to$ `Zoho Corporation`).
- Merges multiple occurrences across search hits, boosting `cross_source_agreement`.

### 8. Python LangGraph Intelligence Bridge (`services/intelligence/graph.py`)
Provides an optional stateful LangGraph intelligence bridge that interfaces directly with the Rust execution engine:
```text
START ──► parse_requirement ──► plan_collection ──► search_sources (Rust API) ──► evaluate_coverage
                                                            ▲                           │
                                                            └── replan_search (Loop) ◄──┘ (insufficient)
                                                                                        │ (sufficient)
                                                                                        ▼
                                                                                 finalize_dataset ──► END
```

---

## 🛠️ Getting Started

### Prerequisites
- **Rust 1.80+ / Cargo**
- **Docker** (for SearXNG meta-search engine)
- **Python 3.10+** (optional, for LangGraph bridge)

### 1. Launch SearXNG Meta-Search Engine
```bash
docker run -d --name searxng -p 8888:8080 \
  -v $(pwd)/searxng:/etc/searxng \
  searxng/searxng:latest
```

### 2. Configure Environment (`.env`)
```ini
HOST=127.0.0.1
PORT=3000
SEARXNG_URL=http://127.0.0.1:8888
GROUNDING_THRESHOLD=0.65
GROQ_API_KEY=your_groq_api_key
MODEL_NAME=openai/gpt-oss-120b
```

### 3. Run the Rust Engine
```bash
cargo run
```
The server will boot on `http://127.0.0.1:3000`.

### 4. Access the Dashboard
Open your browser to:
```text
http://127.0.0.1:3000
```
- Execute natural-language prompts (e.g., Tech Hiring, Hospitality Procurement, B2B Intel).
- View the real-time **8-Stage Workflow Stepper**.
- Inspect the **Data Requirement Contract**.
- Review the **Validated Dataset** with field-level quotes and multi-factor confidence ratings.
- Download **1-Click CSV / JSON Exports**.

### 5. Optional: Run the LangGraph Bridge
```bash
python3 services/intelligence/graph.py "Find Rust backend developer job openings in Bangalore"
```
