"""Fail-open, schema-driven chunk filtering through the real Laya API.

The intelligence service intentionally talks to the official ``laya-serve``
HTTP API instead of importing Laya into the Python 3.9 LangGraph process.
``laya-serve`` owns model loading and reuses its resident checkpoint across
requests.  This module only asks bounded yes/no questions; it never extracts
values or validates records.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Tuple

import httpx


LAYA_URL = os.getenv("LAYA_URL", "http://127.0.0.1:8002").rstrip("/")
LAYA_TIMEOUT_SECONDS = float(os.getenv("LAYA_TIMEOUT_SECONDS", "20"))
LAYA_BATCH_SIZE = max(1, min(int(os.getenv("LAYA_BATCH_SIZE", "32")), 64))
LAYA_THRESHOLD = min(max(float(os.getenv("LAYA_RELEVANCE_THRESHOLD", "0.20")), 0.0), 1.0)
LAYA_MODEL = os.getenv("LAYA_MODEL", "english").strip() or None
LAYA_MAX_LEN = max(1, int(os.getenv("LAYA_MAX_LEN", "512")))


def _enabled() -> bool:
    return os.getenv("LAYA_ENABLED", "0").strip().lower() not in {"0", "false", "no", "off"}


def build_questions(contract: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build one generic Laya decision from the generated DataContract.

    The contract is data, not a domain-specific branch.  Laya is asked only
    whether a chunk is potentially useful evidence for the downstream
    extractor; it is not asked to return an entity or field value.
    """
    fields = [
        {
            "name": field.get("name"),
            "description": field.get("description", ""),
            "required": bool(field.get("required", False)),
        }
        for field in contract.get("fields", [])
        if isinstance(field, dict) and field.get("name")
    ]
    context = {
        "entity_type": contract.get("entity_type", "entity"),
        "target_entity": contract.get("target_entity"),
        "business_goal": contract.get("business_goal"),
        "fields": fields,
        "constraints": contract.get("constraints", []),
        "relationships": contract.get("relationships", []),
        "required_evidence": (contract.get("evidence_policy") or {}).get("required_evidence", []),
    }
    return {
        "relevance": {
            "type": "noul",
            "instructions": (
                "Does this passage contain or directly support evidence that could satisfy "
                "at least one part of the supplied business requirement? Consider the "
                "requested entity, fields, constraints, relationships, and evidence "
                "requirements. Answer yes for potentially useful evidence, even when "
                "the passage is incomplete. Do not require the passage to prove the claim. "
                "Do not extract or invent any value. Requirement: "
                + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
            ),
        }
    }


def _score(result: Dict[str, Any]) -> float:
    answers = result.get("answers") if isinstance(result, dict) else None
    answer = answers.get("relevance") if isinstance(answers, dict) else None
    value = answer.get("noul") if isinstance(answer, dict) else None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise ValueError("Laya returned an out-of-range relevance score")
    return score


def _headers() -> Dict[str, str]:
    key = os.getenv("LAYA_API_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


async def filter_chunks(
    chunks: List[Dict[str, Any]],
    contract: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """Return chunks retained by Laya, metrics, and status.

    Status is ``active`` when Laya filtered successfully, ``disabled`` when
    explicitly disabled, and ``fallback`` when the existing path is retained.
    Any transport, model, timeout, or malformed-output error fails open so
    evidence is never discarded because the optimization is unavailable.
    """
    scores, metrics, status, evaluations = await score_chunks(chunks, contract)
    metrics["evaluations"] = evaluations
    if status in {"disabled", "fallback"}:
        return list(chunks), metrics, status

    kept = [
        {**chunk, "laya_score": round(scores[chunk["chunk_id"]], 6)}
        for chunk in chunks
        if scores[chunk["chunk_id"]] >= LAYA_THRESHOLD
    ]
    metrics["chunks_after"] = len(kept)
    metrics["chunks_filtered"] = len(chunks) - len(kept)
    metrics["score_by_chunk"] = scores
    # High recall is the governing policy. A valid but unexpectedly strict
    # model response must not erase every possible evidence unit.
    if not kept:
        metrics["fallback_reason"] = "no_chunks_above_threshold"
        metrics["chunks_after"] = len(chunks)
        metrics["chunks_filtered"] = 0
        return list(chunks), metrics, "fallback"
    return kept, metrics, "active"


async def score_chunks(
    chunks: List[Dict[str, Any]],
    contract: Dict[str, Any],
) -> Tuple[Dict[str, float], Dict[str, Any], str, List[Dict[str, Any]]]:
    """Run Laya once over each chunk and return reusable raw scores.

    Unlike ``filter_chunks``, this primitive does not fail open merely because
    every score is below the configured threshold.  That distinction is
    required by offline threshold experiments, where an empty retained set is
    a measurable result rather than a second inference or an implicit bypass.
    """
    before = len(chunks)
    metrics: Dict[str, Any] = {
        "chunks_before": before,
        "chunks_after": before,
        "chunks_filtered": 0,
        "latency_ms": 0.0,
        "batch_count": 0,
        "threshold": LAYA_THRESHOLD,
        "model": LAYA_MODEL,
    }
    evaluations = [
        {
            "chunk_id": chunk.get("chunk_id"),
            "source_url": chunk.get("url") or chunk.get("source_url"),
            "chunk_index": index,
            "score": None,
            "decision": "failed",
            "threshold": LAYA_THRESHOLD,
            "model": LAYA_MODEL,
            "status": "pending",
        }
        for index, chunk in enumerate(chunks)
    ]
    if not chunks or not _enabled():
        return {}, metrics, "disabled", evaluations

    questions = build_questions(contract)
    start = time.perf_counter()
    scores: Dict[str, float] = {}
    try:
        async with httpx.AsyncClient(timeout=LAYA_TIMEOUT_SECONDS, headers=_headers()) as client:
            for offset in range(0, before, LAYA_BATCH_SIZE):
                batch = chunks[offset:offset + LAYA_BATCH_SIZE]
                payload: Dict[str, Any] = {
                    "states": [{"body": str(chunk.get("text") or "")} for chunk in batch],
                    "questions": questions,
                    "max_len": LAYA_MAX_LEN,
                }
                if LAYA_MODEL:
                    payload["model"] = LAYA_MODEL
                response = await client.post(f"{LAYA_URL}/v1/systemone/batch", json=payload)
                response.raise_for_status()
                body = response.json()
                results = body.get("results") if isinstance(body, dict) else None
                if not isinstance(results, list) or len(results) != len(batch):
                    raise ValueError("Laya returned an invalid batch shape")
                for index, (chunk, result) in enumerate(zip(batch, results), start=offset):
                    score = _score(result)
                    scores[chunk["chunk_id"]] = score
                    evaluations[index].update({
                        "score": round(score, 6),
                        "decision": "retain" if score >= LAYA_THRESHOLD else "reject",
                        "status": "scored",
                    })
                metrics["batch_count"] += 1
    except Exception as exc:  # fail-open by design for the live pipeline
        metrics["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        metrics["error"] = type(exc).__name__
        metrics["failure_status"] = "unavailable"
        for item in evaluations:
            item["status"] = "failed"
            item["failure"] = type(exc).__name__
        return {}, metrics, "fallback", evaluations

    metrics["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
    metrics["average_decision_score"] = round(sum(scores.values()) / len(scores), 6) if scores else None
    return scores, metrics, "active", evaluations
