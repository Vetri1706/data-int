# AI Data Intelligence & Search Grounding Platform

A high-performance, prompt-driven **Data Intelligence Platform** engineered in **Rust (Axum + Tokio)**. It replaces brittle, site-specific web scrapers with an intelligent, dynamic 5-stage **Search Grounding & Data Synthesis Pipeline**.

---

## 🏛️ Grounding Architecture Pipeline

```text
[ User Prompt ]
       │
       ▼
1. [ Classifier & Dynamic Thresholding ] (Scores 0.0 - 1.0; gates live web retrieval)
       │
       ▼
2. [ Query Rewriter & Expansion ]        (Translates natural language to search-optimized queries)
       │
       ▼
3. [ Multi-Source Web Retrieval ]        (Concurrent harvesting across DuckDuckGo, SearXNG & direct APIs)
       │
       ▼
4. [ Deduplication, Rerank & Blend ]     (Authority scoring, BM25 keyword overlap & context injection)
       │
       ▼
5. [ Cross-Referencing & Synthesis ]     (LLM synthesis with strict inline citation anchors [1], [2])
       │
       ▼
[ Structured Dataset & Grounding Metadata ] (CSV/JSON Export + Auditable Task History)
```

---

## ✨ Key Features & Problem Statement Alignment

| Problem Statement Requirement | Platform Feature |
|---|---|
| **Natural-Language Understanding** | Dynamic intent classification scoring prompts between $0.0$ and $1.0$. Detects business intelligence, hiring leads, commercial procurement, or static theoretical queries. |
| **Dynamic Workflow Execution** | Eliminates manual scrapers. Generates multi-angle keyword queries and executes concurrent search retrieval dynamically. |
| **Traceable & Source-Backed Data** | Every claim in the synthesized report maps directly to verified citation anchors `[1]`, `[2]` with direct source URLs. |
| **Dataset Export (CSV / JSON)** | 1-click **Export to CSV** and **Export to JSON** for all extracted structured records. |
| **Task Management & History** | Built-in in-memory Task Store tracking all executed workflows, stage latency metrics, and past datasets for instant inspection. |
| **Ultra-High Performance** | Built in **Rust 2024** on **Tokio + Axum** with zero-cost abstractions, sub-second pipeline execution, and rock-solid memory safety. |

---

## 🚀 Quickstart

### Prerequisites
* **Rust 1.80+** (`cargo`, `rustc`)

### 1. Build and Run
```bash
cargo run
```
The server will boot on `http://127.0.0.1:8080`.

### 2. Open the Interactive Dashboard
Navigate to `http://127.0.0.1:8080` in any modern web browser to access:
* **Interactive Prompt Interface** with pre-built business templates (Hiring Leads, Market Intel, Product Comparison, Offline Math).
* **Dynamic Threshold Slider** ($0.0$ to $1.0$).
* **Live 5-Stage Stepper** showing per-stage metrics in real time.
* **Grounded Markdown Report** with inline citation links.
* **Structured Dataset Explorer** with 1-click CSV & JSON downloads.
* **Workflow History Drawer** to reload and re-export previous runs.

---

## 🔌 API Endpoints

### 1. Execute Grounded Search & Extraction
* **Endpoint:** `POST /v1/grounded-search`
* **Payload:**
```json
{
  "prompt": "Find Rust backend developer job openings in Bangalore remote with salary",
  "grounding_threshold": 0.65,
  "max_sources": 8
}
```
* **Response:** Returns `GroundingResponse` containing the synthesized markdown, structured dataset records, grounding metadata, and stage duration metrics.

### 2. Task History & Export
* `GET /v1/tasks`: Returns list of all previous workflow executions.
* `GET /v1/tasks/{id}`: Returns the complete result of a past workflow.
* `GET /v1/tasks/{id}/export/csv`: Downloads dataset as CSV.
* `GET /v1/tasks/{id}/export/json`: Downloads dataset as JSON.
* `GET /health`: Healthcheck status.

---

## 📂 Project Structure
```
data-intelligence-platform/
├── Cargo.toml
├── .env.example
├── .env
├── README.md
├── src/
│   ├── main.rs                   # Axum routing, API endpoints & static dashboard serving
│   ├── config.rs                 # Environment configuration (LLM keys, thresholds)
│   ├── models.rs                 # Serde data transfer objects & domain models
│   ├── storage.rs                # Task Store & workflow history persistence
│   ├── export.rs                 # CSV & JSON dataset exporters
│   └── pipeline/
│       ├── mod.rs                # 5-stage pipeline orchestrator
│       ├── stage1_classifier.rs  # Intent detection & dynamic thresholding
│       ├── stage2_rewriter.rs    # Query rewriting & multi-angle expansion
│       ├── stage3_retriever.rs   # Concurrent multi-source retrieval (Tokio)
│       ├── stage4_reranker.rs    # Deduplication, relevance scoring & context blending
│       └── stage5_synthesizer.rs # Cross-referencing, LLM synthesis & citation mapping
└── static/
    ├── index.html                # Modern interactive dashboard
    ├── styles.css                # Sleek dark-mode aesthetic & design system
    └── app.js                   # Client-side reactivity, stepper & dataset export
```
