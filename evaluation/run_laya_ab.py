#!/usr/bin/env python3
"""Controlled A/B evaluation for the current Datavault Laya integration.

Capture phase (once): schema generation, SearXNG metadata, source relevance,
Scrapling retrieval, chunking, and the existing TF-IDF retrieval.

Replay phase (twice): the same captured chunks, existing extraction node, and
existing deterministic validation with Laya disabled/enabled. The output is a
JSON report containing raw per-query measurements and evidence-loss analysis.

This is an evaluation harness, not a production workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "intelligence"))

import graph  # noqa: E402
import laya_filter  # noqa: E402
from grounding import chunk_sources, constraint_passes, retrieve_chunks, validate_candidates  # noqa: E402
from relevance import evaluate_sources  # noqa: E402


QUERIES = [
    "Find AI startups in South India with founders, websites, locations, and funding evidence.",
    "Find EV battery and component suppliers in India with catalog links, locations, and certifications.",
    "Find currently open backend engineering roles from official company career pages in India.",
    "Find project management SaaS products with pricing tiers, billing cadence, and source links.",
    "Find robotics companies headquartered in Tamil Nadu with website and location evidence.",
    "Find companies that could sponsor a robotics hackathon with CSR evidence, previous sponsorships, contact information, and relevance.",
    "Find AI startups in Bengaluru founded after 2020 with funding in the last 18 months and at least one founder.",
    "Find hotels in Chennai with room prices, amenities, address, and current booking availability.",
    "Find Indian battery manufacturers with products, locations, certifications, and contact details.",
    "Find current backend engineering jobs where role details are on company career pages, including title, location, seniority, and application URL.",
]


class TimedLLM:
    """Proxy the existing ModelGateway without changing its prompts or model."""

    def __init__(self, delegate: Any):
        self.delegate = delegate
        self.calls: List[Dict[str, Any]] = []

    @staticmethod
    def _content(messages: list) -> str:
        parts = []
        for message in messages:
            content = getattr(message, "content", message)
            parts.append(str(content))
        return "\n".join(parts)

    async def ainvoke(self, messages: list):
        content = self._content(messages)
        started = time.perf_counter()
        response = await self.delegate.ainvoke(messages)
        elapsed = (time.perf_counter() - started) * 1000
        usage = getattr(response, "usage_metadata", None) or {}
        response_metadata = getattr(response, "response_metadata", None) or {}
        token_usage = response_metadata.get("token_usage", {}) if isinstance(response_metadata, dict) else {}
        actual = usage.get("input_tokens") or token_usage.get("prompt_tokens")
        self.calls.append({
            "latency_ms": round(elapsed, 2),
            "input_chars": len(content),
            "estimated_input_tokens": max(1, (len(content) + 3) // 4),
            "actual_input_tokens": actual,
        })
        return response


def selection_from_env() -> Dict[str, Any]:
    provider = os.getenv("LLM_PROVIDER", "local").strip().lower()
    default_model = "qwen2.5-coder:1.5b-instruct" if provider == "local" else "meta/llama-3.3-70b-instruct"
    return {
        "provider": provider,
        "model": os.getenv("LOCAL_LLM_MODEL" if provider == "local" else "NVIDIA_MODEL", default_model),
        "allow_external": provider == "nvidia",
    }


async def searxng_search(client: httpx.AsyncClient, query: str, limit: int) -> List[Dict[str, Any]]:
    response = await client.get(
        f"{os.getenv('SEARXNG_URL', 'http://127.0.0.1:8888').rstrip('/')}/search",
        params={"q": query, "format": "json", "language": "en", "safesearch": 0},
    )
    response.raise_for_status()
    rows = response.json().get("results", [])
    candidates = []
    for row in rows[:limit]:
        if not isinstance(row, dict) or not isinstance(row.get("url"), str):
            continue
        candidates.append({
            "url": row["url"],
            "title": str(row.get("title", "")),
            "snippet": str(row.get("content", row.get("snippet", ""))),
            "search_query": query,
            "provider": "searxng",
            "engine": row.get("engine"),
        })
    return candidates


def base_state(run_id: str, prompt: str, contract: Dict[str, Any], relevant: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "prompt": prompt,
        "data_contract": contract,
        "queries": [prompt],
        "candidate_sources": relevant,
        "source_relevance": [],
        "relevant_sources": relevant,
        "search_results": [],
        "retrieved_chunks": [],
        "processed_chunks": [],
        "extracted_records": [],
        "validated_records": [],
        "coverage_score": 0.0,
        "iteration": 0,
        "max_iterations": 0,
        "status": "PENDING",
        "messages": [],
    }


def source_without_content(source: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in source.items() if k != "content"}


async def parse_contract(prompt: str, selection: Dict[str, Any]) -> Dict[str, Any]:
    token = graph.selected_model.set(selection)
    try:
        return await graph.parse_endpoint(graph.ParseRequest(prompt=prompt, model_selection=selection))
    finally:
        graph.selected_model.reset(token)


async def capture_query(
    index: int,
    prompt: str,
    selection: Dict[str, Any],
    client: httpx.AsyncClient,
    max_candidates: int,
    fixed_keep: bool,
) -> Dict[str, Any]:
    started = time.perf_counter()
    captured: Dict[str, Any] = {"index": index, "query": prompt, "errors": []}
    try:
        contract = await parse_contract(prompt, selection)
        captured["data_contract"] = contract
        candidates = await searxng_search(client, prompt, max_candidates)
        captured["candidate_sources"] = candidates

        if fixed_keep:
            evaluations = [{
                "candidate_index": item,
                "url": candidate.get("url", ""),
                "decision": "KEEP",
                "relevance_score": 1.0,
                "source_type": "evaluation_fixture",
                "entity_relevance": True,
                "evidence_capability": ["captured for Laya isolation"],
                "constraint_relevance": True,
                "reason": "Fixed KEEP decision used only to isolate Laya from source-gate model quality.",
                "missing_information": [],
            } for item, candidate in enumerate(candidates)]
            captured["source_relevance_mode"] = "fixed_keep_fixture"
        else:
            token = graph.selected_model.set(selection)
            try:
                evaluations = await evaluate_sources(candidates, prompt, contract, graph.llm.ainvoke)
            finally:
                graph.selected_model.reset(token)
            captured["source_relevance_mode"] = "live_existing_gate"
        relevant = [
            {**candidates[item["candidate_index"]], "relevance": item}
            for item in evaluations
            if item.get("decision") == "KEEP"
            and isinstance(item.get("candidate_index"), int)
            and 0 <= item["candidate_index"] < len(candidates)
        ]
        captured["source_relevance"] = evaluations
        captured["relevant_sources"] = relevant

        # Reuse the actual graph Scrapling node and actual grounding retrieval.
        original_event = graph.post_run_event
        original_retrieve = graph.retrieve_chunks
        retrieval_timing: Dict[str, float] = {}

        async def no_event(*_args, **_kwargs):
            return None

        def timed_retrieve(*args, **kwargs):
            t0 = time.perf_counter()
            result = original_retrieve(*args, **kwargs)
            retrieval_timing["chunking_tfidf_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return result

        graph.post_run_event = no_event
        graph.retrieve_chunks = timed_retrieve
        try:
            state = base_state(f"laya-ab-{index}", prompt, contract, relevant)
            scrapling_started = time.perf_counter()
            state = await graph.scrapling_extraction(state)
            captured["scrapling_stage_ms"] = round((time.perf_counter() - scrapling_started) * 1000, 2)
        finally:
            graph.post_run_event = original_event
            graph.retrieve_chunks = original_retrieve

        fetched_sources = state.get("search_results", [])
        all_chunks = chunk_sources(fetched_sources)
        selected_chunks = state.get("retrieved_chunks", [])
        captured.update({
            "scrapling_retrieval_ms": captured.get("scrapling_stage_ms", 0),
            "chunking_tfidf_ms": retrieval_timing.get("chunking_tfidf_ms", 0),
            "search_results": [source_without_content(s) for s in fetched_sources],
            "retrieved_sources": [source_without_content(s) for s in fetched_sources],
            "retrieved_source_content": fetched_sources,
            "chunks_generated": len(all_chunks),
            "retrieved_chunks": selected_chunks,
            "scrapling_records": state.get("scrapling_records", []),
            "capture_latency_ms": round((time.perf_counter() - started) * 1000, 2),
        })
    except Exception as exc:  # Keep the suite running and report the failed query.
        captured["errors"].append(f"{type(exc).__name__}: {exc}")
        captured["capture_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return captured


async def laya_decisions(chunks: List[Dict[str, Any]], contract: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, float]]:
    """Call the official Laya batch endpoint once per bounded batch."""
    started = time.perf_counter()
    scores: Dict[str, float] = {}
    batch_size = laya_filter.LAYA_BATCH_SIZE
    questions = laya_filter.build_questions(contract)
    headers = laya_filter._headers()
    async with httpx.AsyncClient(timeout=laya_filter.LAYA_TIMEOUT_SECONDS, headers=headers) as client:
        for offset in range(0, len(chunks), batch_size):
            batch = chunks[offset:offset + batch_size]
            payload: Dict[str, Any] = {
                "states": [{"body": str(chunk.get("text") or "")} for chunk in batch],
                "questions": questions,
                "max_len": laya_filter.LAYA_MAX_LEN,
            }
            if laya_filter.LAYA_MODEL:
                payload["model"] = laya_filter.LAYA_MODEL
            response = await client.post(f"{laya_filter.LAYA_URL}/v1/systemone/batch", json=payload)
            response.raise_for_status()
            body = response.json()
            results = body.get("results") if isinstance(body, dict) else None
            if not isinstance(results, list) or len(results) != len(batch):
                raise ValueError("invalid Laya batch response")
            for chunk, result in zip(batch, results):
                score = laya_filter._score(result)
                scores[chunk["chunk_id"]] = score
    retained = [
        {**chunk, "laya_score": round(scores[chunk["chunk_id"]], 6)}
        for chunk in chunks
        if scores[chunk["chunk_id"]] >= laya_filter.LAYA_THRESHOLD
    ]
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    values = list(scores.values())
    metrics = {
        "chunks_before": len(chunks),
        "chunks_after": len(retained),
        "chunks_filtered": len(chunks) - len(retained),
        "retention_percentage": round((len(retained) / len(chunks) * 100) if chunks else 100.0, 2),
        "filtering_percentage": round((1 - len(retained) / len(chunks)) * 100 if chunks else 0.0, 2),
        "latency_ms": elapsed,
        "batch_size": batch_size,
        "batch_count": (len(chunks) + batch_size - 1) // batch_size if chunks else 0,
        "average_decision_score": round(sum(values) / len(values), 6) if values else None,
        "retained_chunks": len(retained),
        "rejected_chunks": len(chunks) - len(retained),
        "fallback_occurrences": 0,
        "threshold": laya_filter.LAYA_THRESHOLD,
    }
    return retained, metrics, scores


def record_key(record: Dict[str, Any]) -> str:
    value = record.get("canonical_name") or record.get("name") or ""
    return " ".join(str(value).casefold().split())


def evidence_units(record: Dict[str, Any]) -> List[Tuple[str, str]]:
    provenance = record.get("provenance") or {}
    fields = provenance.get("field_evidence") or []
    units = []
    for item in fields:
        if isinstance(item, dict) and item.get("field_name") and item.get("chunk_id"):
            units.append((str(item["field_name"]), str(item["chunk_id"])))
    if not units and record.get("chunk_id"):
        units.append(("record", str(record["chunk_id"])))
    return units


def status_counts(records: List[Dict[str, Any]]) -> Dict[str, int]:
    return dict(Counter(record.get("status", "unknown") for record in records))


def hard_constraint_count(records: List[Dict[str, Any]], contract: Dict[str, Any]) -> int:
    hard = [item for item in contract.get("constraints", []) if isinstance(item, dict) and item.get("is_hard")]
    if not hard:
        return 0
    total = 0
    for record in records:
        if all(constraint_passes(record.get(item.get("field")), item.get("operator"), item.get("target_value")) for item in hard):
            total += 1
    return total


async def run_mode(
    captured: Dict[str, Any],
    enabled: bool,
    selection: Dict[str, Any],
    delegate_llm: Any,
) -> Dict[str, Any]:
    chunks = copy.deepcopy(captured.get("retrieved_chunks", []))
    contract = captured["data_contract"]
    prompt = captured["query"]
    laya_metrics: Dict[str, Any] = {
        "chunks_before": len(chunks), "chunks_after": len(chunks),
        "chunks_filtered": 0, "latency_ms": 0.0, "fallback_occurrences": 0,
    }
    scores: Dict[str, float] = {}
    if enabled and chunks:
        try:
            filtered, laya_metrics, scores = await laya_decisions(chunks, contract)
        except Exception as exc:
            # Match the production fail-open behavior and keep this query in
            # the report as a measured fallback rather than dropping it.
            filtered = chunks
            laya_metrics = {
                "chunks_before": len(chunks),
                "chunks_after": len(chunks),
                "chunks_filtered": 0,
                "latency_ms": 0.0,
                "fallback_occurrences": 1,
                "fallback_error": f"{type(exc).__name__}: {exc}",
                "threshold": laya_filter.LAYA_THRESHOLD,
            }
    else:
        filtered = chunks

    state = {
        **base_state(captured["index"], prompt, contract, captured.get("relevant_sources", [])),
        "search_results": copy.deepcopy(captured.get("retrieved_source_content", [])),
        "retrieved_chunks": chunks,
        "scrapling_records": copy.deepcopy(captured.get("scrapling_records", [])),
        "extracted_records": [],
        "processed_chunks": [],
    }
    if enabled:
        state["laya_filtered_chunks"] = filtered

    timed_llm = TimedLLM(delegate_llm)
    original_llm = graph.llm
    original_event = graph.post_run_event

    async def no_event(*_args, **_kwargs):
        return None

    graph.llm = timed_llm
    graph.post_run_event = no_event
    selected_token = graph.selected_model.set(selection)
    extraction_started = time.perf_counter()
    extraction_error = None
    try:
        state = await graph.extract_and_normalize(state)
    except Exception as exc:  # Report rather than hiding provider failures.
        extraction_error = f"{type(exc).__name__}: {exc}"
    finally:
        graph.selected_model.reset(selected_token)
        graph.llm = original_llm
        graph.post_run_event = original_event

    extraction_latency = round((time.perf_counter() - extraction_started) * 1000, 2)
    extracted = state.get("extracted_records", [])
    validation_started = time.perf_counter()
    validated = validate_candidates(extracted, chunks, contract) if not extraction_error else []
    validation_latency = round((time.perf_counter() - validation_started) * 1000, 2)
    calls = timed_llm.calls
    actual_tokens = [item["actual_input_tokens"] for item in calls if item.get("actual_input_tokens") is not None]
    estimated_tokens = sum(item["estimated_input_tokens"] for item in calls)
    total_mode = captured.get("scrapling_stage_ms", 0) + laya_metrics.get("latency_ms", 0) + extraction_latency + validation_latency
    return {
        "enabled": enabled,
        "chunks_to_tfidf": captured.get("chunks_generated", 0),
        "chunks_entering_laya": len(chunks) if enabled else 0,
        "chunks_to_extraction": len(filtered),
        "laya_metrics": laya_metrics if enabled else {
            "chunks_before": 0, "chunks_after": 0, "chunks_filtered": 0,
            "latency_ms": 0.0, "fallback_occurrences": 0,
        },
        "laya_scores": scores,
        "llm_calls": len(calls),
        "llm_input_tokens": {
            "actual": sum(actual_tokens) if actual_tokens else None,
            "estimated": estimated_tokens,
            "basis": "provider_usage_metadata" if actual_tokens else "input_characters_divided_by_4",
        },
        "llm_call_details": calls,
        "extraction_latency_ms": extraction_latency,
        "validation_latency_ms": validation_latency,
        "scrapling_latency_ms": captured.get("scrapling_stage_ms", 0),
        "tfidf_latency_ms": captured.get("chunking_tfidf_ms", 0),
        "total_replay_latency_ms": round(total_mode, 2),
        "extraction_error": extraction_error,
        "extracted_records": extracted,
        "validated_records": validated,
        "status_counts": status_counts(validated),
        "records_extracted": len(extracted),
        "records_verified": sum(r.get("status") == "verified" for r in validated),
        "records_needs_review": sum(r.get("status") == "needs_review" for r in validated),
        "records_draft": sum(r.get("status") == "draft" for r in validated),
        "required_fields_grounded": sum(len((r.get("provenance") or {}).get("field_evidence") or []) for r in validated),
        "hard_constraints_satisfied": hard_constraint_count(validated, contract),
        "validation_failures": max(0, len(extracted) - len(validated)),
    }


def compare_records(baseline: Dict[str, Any], laya: Dict[str, Any], retained_ids: set[str]) -> Dict[str, Any]:
    baseline_records = {record_key(r): r for r in baseline.get("validated_records", []) if record_key(r)}
    laya_records = {record_key(r): r for r in laya.get("validated_records", []) if record_key(r)}
    comparisons = []
    baseline_units = []
    retained_units = []
    for key, base in baseline_records.items():
        units = evidence_units(base)
        baseline_units.extend(units)
        retained_units.extend(unit for unit in units if unit[1] in retained_ids)
        current = laya_records.get(key)
        field_differences = []
        for field in base.keys():
            if field in {"provenance", "confidence_breakdown", "evidence_excerpt", "status", "confidence_score", "grounding_score"}:
                continue
            if base.get(field) != (current or {}).get(field):
                field_differences.append({"field": field, "baseline": base.get(field), "laya": (current or {}).get(field)})
        if current is None:
            lost_units = [unit for unit in units if unit[1] not in retained_ids]
            classification = "lost_by_laya" if lost_units else "extraction_variation"
        elif field_differences:
            lost_fields = [item["field"] for item in field_differences if any(u[0] == item["field"] and u[1] not in retained_ids for u in units)]
            classification = "lost_by_laya" if lost_fields else "extraction_variation"
        elif base.get("status") != current.get("status"):
            classification = "validation_variation"
        else:
            classification = "retained_correctly"
        comparisons.append({
            "record": key,
            "baseline_status": base.get("status"),
            "laya_status": current.get("status") if current else None,
            "baseline_evidence": units,
            "evidence_retained": all(unit[1] in retained_ids for unit in units),
            "field_differences": field_differences,
            "classification": classification,
        })
    for key in sorted(set(laya_records) - set(baseline_records)):
        comparisons.append({"record": key, "classification": "newly_discovered"})
    total = len(baseline_units)
    return {
        "records": comparisons,
        "baseline_evidence_units": len(baseline_units),
        "retained_baseline_evidence_units": len(retained_units),
        "evidence_recall_baseline_proxy": (len(retained_units) / total) if total else None,
        "evidence_recall_label": "baseline verified-record evidence proxy; ground truth unavailable",
        "lost_evidence_units": [list(unit) for unit in baseline_units if unit[1] not in retained_ids],
        "records_lost_by_laya": sum(item.get("classification") == "lost_by_laya" for item in comparisons),
        "records_lost_or_changed": sum(item.get("classification") != "retained_correctly" for item in comparisons if item.get("baseline_status")),
    }


def threshold_analysis(captured_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    thresholds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
    output = []
    for threshold in thresholds:
        before = after = evidence_total = evidence_kept = 0
        for row in captured_rows:
            base = row.get("baseline", {})
            scores = row.get("laya", {}).get("laya_scores", {})
            chunks = row.get("captured", {}).get("retrieved_chunks", [])
            retained = {cid for cid, score in scores.items() if score >= threshold}
            before += len(chunks)
            after += len(retained)
            for record in base.get("validated_records", []):
                for _, cid in evidence_units(record):
                    evidence_total += 1
                    evidence_kept += cid in retained
        output.append({
            "threshold": threshold,
            "retention_percentage": round(after / before * 100, 2) if before else None,
            "chunk_reduction_percentage": round((before - after) / before * 100, 2) if before else None,
            "evidence_recall_baseline_proxy": round(evidence_kept / evidence_total, 4) if evidence_total else None,
            "false_negative_rate_baseline_proxy": round(1 - evidence_kept / evidence_total, 4) if evidence_total else None,
        })
    return output


async def fail_open_check(chunks: List[Dict[str, Any]], contract: Dict[str, Any]) -> Dict[str, Any]:
    original_url = laya_filter.LAYA_URL
    original_timeout = laya_filter.LAYA_TIMEOUT_SECONDS
    try:
        laya_filter.LAYA_URL = "http://127.0.0.1:1"
        laya_filter.LAYA_TIMEOUT_SECONDS = 0.5
        retained, metrics, status = await laya_filter.filter_chunks(chunks, contract)
        return {
            "status": status,
            "workflow_continues": status == "fallback" and [c["chunk_id"] for c in retained] == [c["chunk_id"] for c in chunks],
            "metrics": metrics,
        }
    finally:
        laya_filter.LAYA_URL = original_url
        laya_filter.LAYA_TIMEOUT_SECONDS = original_timeout


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [row for row in rows if not row.get("captured", {}).get("errors")]
    def total(mode: str, key: str) -> float:
        return sum((row.get(mode, {}).get(key) or 0) for row in valid)
    def avg(mode: str, key: str) -> Optional[float]:
        values = [row.get(mode, {}).get(key) for row in valid if row.get(mode, {}).get(key) is not None]
        return round(sum(values) / len(values), 2) if values else None

    def token_total(mode: str) -> int:
        total_tokens = 0
        for row in valid:
            token_info = row.get(mode, {}).get("llm_input_tokens") or {}
            total_tokens += token_info.get("actual") if token_info.get("actual") is not None else token_info.get("estimated", 0)
        return total_tokens

    def laya_latency_average() -> Optional[float]:
        values = [row.get("laya", {}).get("laya_metrics", {}).get("latency_ms") for row in valid]
        values = [value for value in values if value is not None]
        return round(sum(values) / len(values), 2) if values else None

    baseline_tokens = token_total("baseline")
    laya_tokens = token_total("laya")
    baseline_chunks = total("baseline", "chunks_to_extraction")
    laya_chunks = total("laya", "chunks_to_extraction")
    evidence_total = sum(row.get("comparison", {}).get("baseline_evidence_units", 0) for row in valid)
    evidence_kept = sum(row.get("comparison", {}).get("retained_baseline_evidence_units", 0) for row in valid)
    return {
        "queries_tested": len(valid),
        "queries_failed_capture": len(rows) - len(valid),
        "sources_processed": sum(len(row.get("captured", {}).get("retrieved_source_content", [])) for row in valid),
        "candidate_sources": sum(len(row.get("captured", {}).get("candidate_sources", [])) for row in valid),
        "relevant_sources": sum(len(row.get("captured", {}).get("relevant_sources", [])) for row in valid),
        "successfully_retrieved_sources": sum(len(row.get("captured", {}).get("retrieved_sources", [])) for row in valid),
        "failed_sources": sum(max(0, len(row.get("captured", {}).get("relevant_sources", [])) - len(row.get("captured", {}).get("retrieved_sources", []))) for row in valid),
        "chunks_generated": sum(row.get("captured", {}).get("chunks_generated", 0) for row in valid),
        "chunks_sent_to_extraction_baseline": baseline_chunks,
        "chunks_sent_to_extraction_laya": laya_chunks,
        "chunk_reduction_absolute": baseline_chunks - laya_chunks,
        "chunk_reduction_percentage": round((baseline_chunks - laya_chunks) / baseline_chunks * 100, 2) if baseline_chunks else None,
        "llm_calls_baseline": total("baseline", "llm_calls"),
        "llm_calls_laya": total("laya", "llm_calls"),
        "llm_input_tokens_baseline": baseline_tokens,
        "llm_input_tokens_laya": laya_tokens,
        "token_reduction_percentage": round((baseline_tokens - laya_tokens) / baseline_tokens * 100, 2) if baseline_tokens else None,
        "average_laya_latency_ms": laya_latency_average(),
        "average_workflow_latency_baseline_ms": avg("baseline", "total_replay_latency_ms"),
        "average_workflow_latency_laya_ms": avg("laya", "total_replay_latency_ms"),
        "latency_difference_ms_baseline_minus_laya": round(avg("baseline", "total_replay_latency_ms") - avg("laya", "total_replay_latency_ms"), 2) if avg("baseline", "total_replay_latency_ms") is not None and avg("laya", "total_replay_latency_ms") is not None else None,
        "latency_reduction_percentage": round((avg("baseline", "total_replay_latency_ms") - avg("laya", "total_replay_latency_ms")) / avg("baseline", "total_replay_latency_ms") * 100, 2) if avg("baseline", "total_replay_latency_ms") and avg("laya", "total_replay_latency_ms") is not None else None,
        "verified_records_baseline": total("baseline", "records_verified"),
        "verified_records_laya": total("laya", "records_verified"),
        "needs_review_baseline": total("baseline", "records_needs_review"),
        "needs_review_laya": total("laya", "records_needs_review"),
        "draft_records_baseline": total("baseline", "records_draft"),
        "draft_records_laya": total("laya", "records_draft"),
        "evidence_recall_baseline_proxy": round(evidence_kept / evidence_total, 4) if evidence_total else None,
        "baseline_evidence_units": evidence_total,
        "retained_baseline_evidence_units": evidence_kept,
        "false_negative_cases": sum(row.get("comparison", {}).get("records_lost_by_laya", 0) for row in valid),
        "laya_fallback_cases": sum(row.get("laya", {}).get("laya_metrics", {}).get("fallback_occurrences", 0) for row in valid),
        "ground_truth": "unavailable; baseline evidence is reported only as a clearly labeled proxy",
    }


async def main(args: argparse.Namespace) -> int:
    selection = selection_from_env()
    # The evaluation intentionally points at the actual local Laya server.
    if args.laya_url:
        laya_filter.LAYA_URL = args.laya_url.rstrip("/")
    if args.scrapling_url:
        graph.SCRAPLING_URL = args.scrapling_url.rstrip("/")
    rows = []
    async with httpx.AsyncClient(timeout=30) as client:
        for index, query in enumerate(QUERIES[:args.limit], 1):
            captured = await capture_query(index, query, selection, client, args.max_candidates, args.fixed_keep)
            if captured.get("errors"):
                rows.append({"captured": captured, "query": query})
                continue
            baseline = await run_mode(captured, False, selection, graph.llm)
            laya = await run_mode(captured, True, selection, graph.llm)
            if laya.get("laya_metrics", {}).get("fallback_occurrences"):
                retained_ids = {chunk["chunk_id"] for chunk in captured.get("retrieved_chunks", [])}
            else:
                retained_ids = {cid for cid, score in laya.get("laya_scores", {}).items() if score >= laya_filter.LAYA_THRESHOLD}
            comparison = compare_records(baseline, laya, retained_ids)
            rows.append({
                "query": query,
                "captured": captured,
                "baseline": baseline,
                "laya": laya,
                "comparison": comparison,
            })
            print(json.dumps({
                "query": query,
                "baseline_verified": baseline.get("records_verified"),
                "laya_verified": laya.get("records_verified"),
                "baseline_chunks": baseline.get("chunks_to_extraction"),
                "laya_chunks": laya.get("chunks_to_extraction"),
                "laya_ms": laya.get("laya_metrics", {}).get("latency_ms"),
            }, ensure_ascii=False), flush=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": {
            "selection": {"provider": selection.get("provider"), "model": selection.get("model")},
            "laya_url": laya_filter.LAYA_URL,
            "laya_model": laya_filter.LAYA_MODEL,
            "laya_threshold": laya_filter.LAYA_THRESHOLD,
            "laya_batch_size": laya_filter.LAYA_BATCH_SIZE,
            "fixed_inputs": True,
            "same_search_results_and_scrapling_capture": True,
            "source_relevance_mode": "fixed_keep_fixture" if args.fixed_keep else "live_existing_gate",
            "ground_truth": "unavailable",
            "current_pipeline_note": "retrieve_chunks currently performs chunking plus TF-IDF before the laya_filter node; both arms share that selected chunk set.",
        },
        "aggregate": aggregate(rows),
        "threshold_analysis": threshold_analysis(rows),
        "fail_open_check": await fail_open_check(
            next((row["captured"].get("retrieved_chunks", []) for row in rows
                  if not row.get("captured", {}).get("errors")
                  and row["captured"].get("retrieved_chunks")), []),
            next((row["captured"].get("data_contract", {}) for row in rows if not row.get("captured", {}).get("errors")), {}),
        ),
        "per_query": rows,
        "regression_tests": args.regression_tests,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output), "aggregate": report["aggregate"]}, indent=2), flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10, help="number of fixed evaluation queries")
    parser.add_argument("--max-candidates", type=int, default=6)
    parser.add_argument("--fixed-keep", action="store_true", help="evaluation-only fixed KEEP source gate to isolate Laya")
    parser.add_argument("--laya-url", default=os.getenv("LAYA_URL", "http://127.0.0.1:8002"))
    parser.add_argument("--scrapling-url", default=os.getenv("SCRAPLING_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--output", default=str(ROOT / "evaluation" / "results" / "laya_ab_latest.json"))
    parser.add_argument("--regression-tests", default="run separately; see final report")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(parse_args())))
