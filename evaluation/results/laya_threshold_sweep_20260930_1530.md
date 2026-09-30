# Laya Before TF-IDF Threshold Sweep

Generated: `2026-09-30T10:00:35.380874+00:00`

This is an evaluation-only replay. Production defaults and extraction/grounding/validation behavior were not changed.

## Pipeline

`cached Scrapling normalized pages → complete chunks → Laya once → offline threshold → existing TF-IDF → existing extraction → grounding/validation`

## Aggregate results

| Configuration | Chunks | Laya retained | TF-IDF candidates | LLM tokens | Records | Verified | Evidence recall | Laya ms | Total ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 3 | 0 | 3 | 1284 | 3 | 0 | N/A | 0.00 | 14335.44 |
| 0.05 | 3 | 3 | 3 | 1284 | 3 | 0 | N/A | 11714.65 | 19795.94 |
| 0.10 | 3 | 3 | 3 | 1284 | 3 | 0 | N/A | 11714.65 | 19725.82 |
| 0.15 | 3 | 3 | 3 | 1284 | 3 | 0 | N/A | 11714.65 | 18633.11 |
| 0.20 | 3 | 3 | 3 | 1284 | 3 | 0 | N/A | 11714.65 | 19562.34 |
| 0.25 | 3 | 3 | 3 | 1284 | 3 | 0 | N/A | 11714.65 | 20269.27 |
| 0.30 | 3 | 3 | 3 | 1284 | 3 | 0 | N/A | 11714.65 | 19342.26 |

## Score distribution

```json
{
  "count": 3,
  "minimum": 0.5715,
  "maximum": 0.8368,
  "mean": 0.6851,
  "median": 0.647,
  "p25": 0.60925,
  "p75": 0.7419,
  "p90": 0.79884,
  "p95": 0.81782,
  "bins": {
    "0.00-0.05": 0,
    "0.05-0.10": 0,
    "0.10-0.15": 0,
    "0.15-0.20": 0,
    "0.20-0.25": 0,
    "0.25-0.30": 0,
    "0.30+": 3
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
      "chunks_before": 1,
      "chunks_after": 1,
      "chunks_filtered": 0,
      "latency_ms": 24.71,
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
