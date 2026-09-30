#!/usr/bin/env python3
"""Controlled, replayable Laya-before-TF-IDF threshold evaluation.

The fixture contains cached normalized Scrapling output and contracts.  The
script scores every generated chunk exactly once, then replays the unchanged
TF-IDF, extraction, and validation stages for each offline threshold.
Production defaults are never changed by this script.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "intelligence"))

import graph  # noqa: E402
import laya_filter  # noqa: E402
from grounding import chunk_sources, rank_chunks, validate_candidates  # noqa: E402
from llm import ModelGateway  # noqa: E402
from run_laya_ab import (  # noqa: E402
    TimedLLM,
    base_state,
    compare_records,
    evidence_units,
    selection_from_env,
    status_counts,
)


THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]


def load_fixture(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("fixture must contain a non-empty cases list")
    for case in cases:
        if not isinstance(case, dict) or not case.get("sources") or not case.get("data_contract"):
            raise ValueError("each fixture case needs sources and data_contract")
    return cases


def make_chunks(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources = []
    for source in case["sources"]:
        item = {**source, "provider": "cached_scrapling_fixture"}
        if source.get("content_prefix"):
            item["content"] = f"{source['content_prefix']}\n{source.get('content', '')}"
        sources.append(item)
    return chunk_sources(sources)


def gold_chunk_ids(case: Dict[str, Any], chunks: List[Dict[str, Any]]) -> set[str]:
    markers = [str(item).casefold() for item in case.get("gold_relevant_markers", [])]
    return {
        chunk["chunk_id"]
        for chunk in chunks
        if any(marker in str(chunk.get("text", "")).casefold() for marker in markers)
    }


def score_distribution(scores: List[float]) -> Dict[str, Any]:
    if not scores:
        return {"count": 0, "minimum": None, "maximum": None, "mean": None,
                "median": None, "p25": None, "p75": None, "p90": None, "p95": None,
                "bins": {"0.00-0.05": 0, "0.05-0.10": 0, "0.10-0.15": 0,
                         "0.15-0.20": 0, "0.20-0.25": 0, "0.25-0.30": 0, "0.30+": 0}}
    values = sorted(scores)
    bins = Counter()
    for value in values:
        if value < 0.05:
            bins["0.00-0.05"] += 1
        elif value < 0.10:
            bins["0.05-0.10"] += 1
        elif value < 0.15:
            bins["0.10-0.15"] += 1
        elif value < 0.20:
            bins["0.15-0.20"] += 1
        elif value < 0.25:
            bins["0.20-0.25"] += 1
        elif value < 0.30:
            bins["0.25-0.30"] += 1
        else:
            bins["0.30+"] += 1

    def percentile(p: float) -> float:
        index = (len(values) - 1) * p
        lower, upper = int(index), min(int(index) + 1, len(values) - 1)
        fraction = index - lower
        return round(values[lower] + (values[upper] - values[lower]) * fraction, 6)

    return {
        "count": len(values),
        "minimum": round(values[0], 6),
        "maximum": round(values[-1], 6),
        "mean": round(statistics.mean(values), 6),
        "median": round(statistics.median(values), 6),
        "p25": percentile(0.25), "p75": percentile(0.75),
        "p90": percentile(0.90), "p95": percentile(0.95),
        "bins": {key: bins[key] for key in ["0.00-0.05", "0.05-0.10", "0.10-0.15",
                                             "0.15-0.20", "0.20-0.25", "0.25-0.30", "0.30+"]},
    }


async def score_fixture_cases(cases: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    scored = []
    all_scores: List[float] = []
    for case in cases:
        chunks = make_chunks(case)
        scores, metrics, status, evaluations = await laya_filter.score_chunks(chunks, case["data_contract"])
        all_scores.extend(scores.values())
        scored.append({
            **case,
            "chunks": chunks,
            "gold_chunk_ids": sorted(gold_chunk_ids(case, chunks)),
            "laya_scores": scores,
            "laya_metrics": metrics,
            "laya_status": status,
            "laya_evaluations": evaluations,
        })
    return scored, {"latency_ms": round(sum(x["laya_metrics"].get("latency_ms", 0) for x in scored), 2),
                    "scores": score_distribution(all_scores)}


async def replay_configuration(case: Dict[str, Any], retained: List[Dict[str, Any]],
                               selection: Dict[str, Any], include_laya_ms: float) -> Dict[str, Any]:
    started = time.perf_counter()
    tfidf_started = time.perf_counter()
    ranked = rank_chunks(retained, case["query"], case["data_contract"])
    tfidf_ms = round((time.perf_counter() - tfidf_started) * 1000, 2)
    state = {
        **base_state(case["case_id"], case["query"], case["data_contract"], case.get("sources", [])),
        "search_results": copy.deepcopy(case["sources"]),
        "retrieved_chunks": ranked,
        "laya_filtered_chunks": ranked,
        "chunk_pool": copy.deepcopy(case["chunks"]),
        "scrapling_records": [],
        "extracted_records": [],
        "processed_chunks": [],
        "laya_before_tfidf": True,
        "laya_enabled": False,
    }
    # Isolate provider cooldown/error state between replay arms. The selected
    # provider, model, prompts, and inputs remain identical for every arm.
    timed_llm = TimedLLM(ModelGateway())
    original_llm, original_event = graph.llm, graph.post_run_event

    async def no_event(*_args, **_kwargs):
        return None

    graph.llm, graph.post_run_event = timed_llm, no_event
    token = graph.selected_model.set(selection)
    extraction_error = None
    extraction_started = time.perf_counter()
    try:
        state = await graph.extract_and_normalize(state)
    except Exception as exc:
        extraction_error = f"{type(exc).__name__}: {exc}"
    finally:
        graph.selected_model.reset(token)
        graph.llm, graph.post_run_event = original_llm, original_event
    extraction_ms = round((time.perf_counter() - extraction_started) * 1000, 2)
    extracted = state.get("extracted_records", [])
    validation_started = time.perf_counter()
    validated = validate_candidates(extracted, ranked, case["data_contract"]) if not extraction_error else []
    validation_ms = round((time.perf_counter() - validation_started) * 1000, 2)
    actual = [call["actual_input_tokens"] for call in timed_llm.calls if call.get("actual_input_tokens") is not None]
    estimated = sum(call["estimated_input_tokens"] for call in timed_llm.calls)
    input_chars = sum(call["input_chars"] for call in timed_llm.calls)
    return {
        "chunks_entering_tfidf": len(retained),
        "tfidf_candidates": len(ranked),
        "chunks_to_extraction": len(ranked),
        "extraction_llm_calls": len(timed_llm.calls),
        "extraction_input_chars": input_chars,
        "extraction_input_tokens": sum(actual) if actual else estimated,
        "token_basis": "provider_usage_metadata" if actual else "input_characters_divided_by_4",
        "extraction_latency_ms": extraction_ms,
        "tfidf_latency_ms": tfidf_ms,
        "grounding_validation_latency_ms": validation_ms,
        "laya_latency_ms": include_laya_ms,
        "total_pipeline_latency_ms": round((time.perf_counter() - started) * 1000 + include_laya_ms, 2),
        "extraction_error": extraction_error,
        "records_extracted": len(extracted),
        "records": extracted,
        "validated_records": validated,
        "records_verified": sum(r.get("status") == "verified" for r in validated),
        "records_draft": sum(r.get("status") == "draft" for r in validated),
        "records_needs_review": sum(r.get("status") == "needs_review" for r in validated),
        "fields_grounded": sum(len((r.get("provenance") or {}).get("field_evidence") or []) for r in validated),
        "validation_failures": max(0, len(extracted) - len(validated)),
        "status_counts": status_counts(validated),
        "llm_call_details": timed_llm.calls,
    }


def evidence_metrics(baseline: Dict[str, Any], current: Dict[str, Any], retained_ids: set[str],
                     gold_ids: set[str], total_chunks: int) -> Dict[str, Any]:
    baseline_units = [unit for record in baseline["validated_records"] for unit in evidence_units(record)]
    retained_units = [unit for unit in baseline_units if unit[1] in retained_ids]
    gold_relevant = len(gold_ids)
    gold_retained = len(gold_ids & retained_ids)
    return {
        "baseline_evidence_units": len(baseline_units),
        "retained_baseline_evidence_units": len(retained_units),
        "evidence_recall_proxy": round(len(retained_units) / len(baseline_units), 4) if baseline_units else None,
        "lost_evidence_units": [list(unit) for unit in baseline_units if unit[1] not in retained_ids],
        "gold_relevant_chunks": gold_relevant,
        "gold_relevant_chunks_retained": gold_retained,
        "gold_chunk_recall": round(gold_retained / gold_relevant, 4) if gold_relevant else None,
        "gold_chunk_precision": round(gold_retained / len(retained_ids), 4) if retained_ids else None,
        "false_negative_chunks": len(gold_ids - retained_ids),
        "total_chunks": total_chunks,
        "record_comparison": compare_records(baseline, current, retained_ids),
    }


async def fail_open_checks(chunks: List[Dict[str, Any]], contract: Dict[str, Any]) -> Dict[str, Any]:
    original_url, original_timeout = laya_filter.LAYA_URL, laya_filter.LAYA_TIMEOUT_SECONDS
    try:
        laya_filter.LAYA_URL, laya_filter.LAYA_TIMEOUT_SECONDS = "http://127.0.0.1:1", 0.5
        retained, metrics, status = await laya_filter.filter_chunks(chunks, contract)
        return {"service_unavailable": {"status": status, "workflow_continues": status == "fallback" and len(retained) == len(chunks), "metrics": metrics},
                "empty_input": await _empty_check(contract),
                "high_threshold_offline": {"status": "measurable", "zero_retained_is_allowed": True}}
    finally:
        laya_filter.LAYA_URL, laya_filter.LAYA_TIMEOUT_SECONDS = original_url, original_timeout


async def _empty_check(contract: Dict[str, Any]) -> Dict[str, Any]:
    retained, metrics, status = await laya_filter.filter_chunks([], contract)
    return {"status": status, "workflow_continues": retained == [], "chunks_before": metrics["chunks_before"]}


def aggregate(config_rows: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    output = {}
    for name, rows in config_rows.items():
        def total(key: str) -> float:
            return sum(row.get(key) or 0 for row in rows)
        output[name] = {
            "chunks_generated": total("chunks_generated"),
            "laya_retained": total("laya_retained"),
            "laya_rejected": total("laya_rejected"),
            "tfidf_candidates": total("tfidf_candidates"),
            "llm_calls": total("extraction_llm_calls"),
            "llm_input_tokens": total("extraction_input_tokens"),
            "llm_input_chars": total("extraction_input_chars"),
            "records": total("records_extracted"),
            "verified": total("records_verified"),
            "draft": total("records_draft"),
            "needs_review": total("records_needs_review"),
            "fields_grounded": total("fields_grounded"),
            "validation_failures": total("validation_failures"),
            "laya_latency_ms": total("laya_latency_ms"),
            "tfidf_latency_ms": total("tfidf_latency_ms"),
            "extraction_latency_ms": total("extraction_latency_ms"),
            "grounding_validation_latency_ms": total("grounding_validation_latency_ms"),
            "total_pipeline_latency_ms": total("total_pipeline_latency_ms"),
        }
    return output


def markdown_report(report: Dict[str, Any]) -> str:
    rows = report["aggregate"]
    lines = ["# Laya Before TF-IDF Threshold Sweep", "",
             f"Generated: `{report['generated_at']}`", "",
             "This is an evaluation-only replay. Production defaults and extraction/grounding/validation behavior were not changed.", "",
             "## Pipeline", "",
             "`cached Scrapling normalized pages → complete chunks → Laya once → offline threshold → existing TF-IDF → existing extraction → grounding/validation`", "",
             "## Aggregate results", "",
             "| Configuration | Chunks | Laya retained | TF-IDF candidates | LLM tokens | Records | Verified | Evidence recall | Laya ms | Total ms |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, value in rows.items():
        evidence = report["evidence_by_configuration"].get(name, {}).get("evidence_recall_proxy")
        evidence_text = "N/A" if evidence is None else f"{evidence:.2%}"
        lines.append(f"| {name} | {value['chunks_generated']} | {value['laya_retained']} | {value['tfidf_candidates']} | {value['llm_input_tokens']} | {value['records']} | {value['verified']} | {evidence_text} | {value['laya_latency_ms']:.2f} | {value['total_pipeline_latency_ms']:.2f} |")
    lines += ["", "## Retrieval", "",
              f"Candidates: **{report['retrieval']['candidate_sources']}**, relevant sources: **{report['retrieval']['relevant_sources']}**, retrieved sources: **{report['retrieval']['retrieved_sources']}**.", "",
              "## Score distribution", "", "```json", json.dumps(report["score_distribution"], indent=2), "```", "",
              "## Fail-open checks", "", "```json", json.dumps(report["fail_open_checks"], indent=2), "```", "",
              "## Notes", "",
              "- Laya inference was executed once per chunk; all thresholds reuse the persisted scores.",
              "- Evidence recall is a baseline-evidence proxy unless a manually reviewed gold chunk exists; this fixture also reports gold chunk precision/recall.",
              "- No threshold was selected or applied to production.", ""]
    return "\n".join(lines)


async def main(args: argparse.Namespace) -> int:
    cases = load_fixture(Path(args.fixture))
    selection = selection_from_env()
    if args.laya_url:
        laya_filter.LAYA_URL = args.laya_url.rstrip("/")
    scored_cases, laya_summary = await score_fixture_cases(cases)
    configurations = ["baseline"] + [f"{threshold:.2f}" for threshold in THRESHOLDS]
    per_case: Dict[str, Dict[str, Any]] = {}
    config_rows: Dict[str, List[Dict[str, Any]]] = {name: [] for name in configurations}
    evidence_by_configuration: Dict[str, Dict[str, Any]] = {name: {"baseline_evidence_units": 0, "retained_baseline_evidence_units": 0, "lost_evidence_units": [], "gold_relevant_chunks": 0, "gold_relevant_chunks_retained": 0, "false_negative_chunks": 0} for name in configurations}

    for case in scored_cases:
        baseline_retained = case["chunks"]
        baseline = await replay_configuration(case, baseline_retained, selection, 0.0)
        per_case[case["case_id"]] = {"query": case["query"], "chunks_generated": len(case["chunks"]), "laya_evaluations": case["laya_evaluations"], "gold_chunk_ids": case["gold_chunk_ids"], "configurations": {"baseline": baseline}}
        config_rows["baseline"].append({"chunks_generated": len(case["chunks"]), "laya_retained": 0, "laya_rejected": 0, **baseline})
        evidence_by_configuration["baseline"]["baseline_evidence_units"] += sum(len(evidence_units(r)) for r in baseline["validated_records"])

        for threshold in THRESHOLDS:
            name = f"{threshold:.2f}"
            retained_ids = {cid for cid, score in case["laya_scores"].items() if score >= threshold}
            retained = [chunk for chunk in case["chunks"] if chunk["chunk_id"] in retained_ids]
            current = await replay_configuration(case, retained, selection, case["laya_metrics"].get("latency_ms", 0.0))
            evidence = evidence_metrics(baseline, current, retained_ids, set(case["gold_chunk_ids"]), len(case["chunks"]))
            per_case[case["case_id"]]["configurations"][name] = {**current, "laya_retained": len(retained), "laya_rejected": len(case["chunks"]) - len(retained), "evidence": evidence}
            config_rows[name].append({"chunks_generated": len(case["chunks"]), "laya_retained": len(retained), "laya_rejected": len(case["chunks"]) - len(retained), **current})
            summary = evidence_by_configuration[name]
            summary["baseline_evidence_units"] += evidence["baseline_evidence_units"]
            summary["retained_baseline_evidence_units"] += evidence["retained_baseline_evidence_units"]
            summary["lost_evidence_units"].extend(evidence["lost_evidence_units"])
            summary["gold_relevant_chunks"] += evidence["gold_relevant_chunks"]
            summary["gold_relevant_chunks_retained"] += evidence["gold_relevant_chunks_retained"]
            summary["false_negative_chunks"] += evidence["false_negative_chunks"]

    for name, summary in evidence_by_configuration.items():
        total = summary["baseline_evidence_units"]
        summary["evidence_recall_proxy"] = round(summary["retained_baseline_evidence_units"] / total, 4) if total else None
        gold_total = summary["gold_relevant_chunks"]
        summary["gold_chunk_recall"] = round(summary["gold_relevant_chunks_retained"] / gold_total, 4) if gold_total else None
        summary["gold_chunk_precision"] = None

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation": {
            "fixture": str(Path(args.fixture)),
            "replay": True,
            "production_behavior_changed": False,
            "pipeline_order": "cached Scrapling -> complete chunks -> Laya -> offline threshold -> existing TF-IDF -> extraction -> validation",
            "laya_model": laya_filter.LAYA_MODEL,
            "laya_runtime": laya_summary,
            "thresholds": THRESHOLDS,
        },
        "aggregate": aggregate(config_rows),
        "retrieval": {
            "candidate_sources": sum(len(case.get("sources", [])) for case in scored_cases),
            "relevant_sources": sum(1 for case in scored_cases if case.get("source_relevance") == "KEEP"),
            "retrieved_sources": sum(len(case.get("sources", [])) for case in scored_cases),
        },
        "evidence_by_configuration": evidence_by_configuration,
        "score_distribution": laya_summary["scores"],
        "raw_laya_evaluations": [item for case in scored_cases for item in case["laya_evaluations"]],
        "per_case": per_case,
        "fail_open_checks": await fail_open_checks(scored_cases[0]["chunks"], scored_cases[0]["data_contract"]),
        "regression_tests": "run separately; see final handoff",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown = output.with_suffix(".md")
    markdown.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({"json": str(output), "markdown": str(markdown), "aggregate": report["aggregate"]}, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(ROOT / "evaluation" / "fixtures" / "laya_threshold_cases.json"))
    parser.add_argument("--laya-url", default=os.getenv("LAYA_URL", "http://127.0.0.1:8002"))
    parser.add_argument("--output", default=str(ROOT / "evaluation" / "results" / f"laya_threshold_sweep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"))
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(parse_args())))
