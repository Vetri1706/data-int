# Laya Before TF-IDF Threshold Sweep

Generated: `2026-09-30T10:03:46.823197+00:00`

This is an evaluation-only replay. Production defaults and extraction/grounding/validation behavior were not changed.

## Pipeline

`cached Scrapling normalized pages → complete chunks → Laya once → offline threshold → existing TF-IDF → existing extraction → grounding/validation`

## Aggregate results

| Configuration | Chunks | Laya retained | TF-IDF candidates | LLM tokens | Records | Verified | Evidence recall | Laya ms | Total ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 24 | 0 | 4 | 0 | 0 | 0 | N/A | 0.00 | 342.31 |
| 0.05 | 24 | 24 | 4 | 0 | 0 | 0 | N/A | 16158.47 | 16288.80 |
| 0.10 | 24 | 24 | 4 | 0 | 0 | 0 | N/A | 16158.47 | 16283.57 |
| 0.15 | 24 | 24 | 4 | 0 | 0 | 0 | N/A | 16158.47 | 16278.35 |
| 0.20 | 24 | 23 | 4 | 0 | 0 | 0 | N/A | 16158.47 | 16276.60 |
| 0.25 | 24 | 21 | 4 | 0 | 0 | 0 | N/A | 16158.47 | 16279.80 |
| 0.30 | 24 | 19 | 4 | 0 | 0 | 0 | N/A | 16158.47 | 16287.07 |

## Score distribution

```json
{
  "count": 24,
  "minimum": 0.1761,
  "maximum": 0.8042,
  "mean": 0.500508,
  "median": 0.5505,
  "p25": 0.323775,
  "p75": 0.677575,
  "p90": 0.73641,
  "p95": 0.763635,
  "bins": {
    "0.00-0.05": 0,
    "0.05-0.10": 0,
    "0.10-0.15": 0,
    "0.15-0.20": 1,
    "0.20-0.25": 2,
    "0.25-0.30": 2,
    "0.30+": 19
  }
}
```

## Fail-open checks

```json
{
  "service_unavailable": {
    "status": "fallback",
    "workflow_continues": true,
    "metrics": {
      "chunks_before": 10,
      "chunks_after": 10,
      "chunks_filtered": 0,
      "latency_ms": 9.54,
      "batch_count": 0,
      "threshold": 0.2,
      "model": "english",
      "error": "ConnectError",
      "failure_status": "unavailable",
      "evaluations": [
        {
          "chunk_id": "ab462b567750e4505af1",
          "source_url": "https://fixture.example/suppliers/example-components",
          "chunk_index": 0,
          "score": null,
          "decision": "failed",
          "threshold": 0.2,
          "model": "english",
          "status": "failed",
          "failure": "ConnectError"
        },
        {
          "chunk_id": "f76ae2dd3bc8b5857ffa",
          "source_url": "https://fixture.example/suppliers/example-components",
          "chunk_index": 1,
          "score": null,
          "decision": "failed",
          "threshold": 0.2,
          "model": "english",
          "status": "failed",
          "failure": "ConnectError"
        },
        {
          "chunk_id": "9823a0f3bbd79ae31d51",
          "source_url": "https://fixture.example/suppliers/example-components",
          "chunk_index": 2,
          "score": null,
          "decision": "failed",
          "threshold": 0.2,
          "model": "english",
          "status": "failed",
          "failure": "ConnectError"
        },
        {
          "chunk_id": "f25981f7b872b7e78712",
          "source_url": "https://fixture.example/suppliers/example-components",
          "chunk_index": 3,
          "score": null,
          "decision": "failed",
          "threshold": 0.2,
          "model": "english",
          "status": "failed",
          "failure": "ConnectError"
        },
        {
          "chunk_id": "2fd99b5b4ec9dc2450f2",
          "source_url": "https://fixture.example/suppliers/example-components",
          "chunk_index": 4,
          "score": null,
          "decision": "failed",
          "threshold": 0.2,
          "model": "english",
          "status": "failed",
          "failure": "ConnectError"
        },
        {
          "chunk_id": "119c2dfed84a57ecc389",
          "source_url": "https://fixture.example/suppliers/example-components",
          "chunk_index": 5,
          "score": null,
          "decision": "failed",
          "threshold": 0.2,
          "model": "english",
          "status": "failed",
          "failure": "ConnectError"
        },
        {
          "chunk_id": "f2959f501cc2a2d61345",
          "source_url": "https://fixture.example/suppliers/example-components",
          "chunk_index": 6,
          "score": null,
          "decision": "failed",
          "threshold": 0.2,
          "model": "english",
          "status": "failed",
          "failure": "ConnectError"
        },
        {
          "chunk_id": "3cafce05432c544a5746",
          "source_url": "https://fixture.example/suppliers/example-components",
          "chunk_index": 7,
          "score": null,
          "decision": "failed",
          "threshold": 0.2,
          "model": "english",
          "status": "failed",
          "failure": "ConnectError"
        },
        {
          "chunk_id": "44d1c3c31edb3fe6978c",
          "source_url": "https://fixture.example/suppliers/example-components",
          "chunk_index": 8,
          "score": null,
          "decision": "failed",
          "threshold": 0.2,
          "model": "english",
          "status": "failed",
          "failure": "ConnectError"
        },
        {
          "chunk_id": "2ef66c803f22b86ad47d",
          "source_url": "https://fixture.example/suppliers/example-components",
          "chunk_index": 9,
          "score": null,
          "decision": "failed",
          "threshold": 0.2,
          "model": "english",
          "status": "failed",
          "failure": "ConnectError"
        }
      ]
    }
  },
  "empty_input": {
    "status": "disabled",
    "workflow_continues": true,
    "chunks_before": 0
  },
  "high_threshold_offline": {
    "status": "measurable",
    "zero_retained_is_allowed": true
  }
}
```

## Notes

- Laya inference was executed once per chunk; all thresholds reuse the persisted scores.
- Evidence recall is a baseline-evidence proxy unless a manually reviewed gold chunk exists; this fixture also reports gold chunk precision/recall.
- No threshold was selected or applied to production.
