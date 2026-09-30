"""Schema-aware source relevance gating for search candidates.

The gate sees only search-result metadata. It never fetches pages and never
provides evidence to downstream validation. KEEP candidates are fetched later
by Scrapling; UNCERTAIN and REJECT candidates are not fetched.
"""

import json
import logging
from typing import Any, Awaitable, Callable

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger("datavault.relevance")

DECISIONS = {"KEEP", "REJECT", "UNCERTAIN"}


def _parse_json(content: str) -> Any:
    """Parse a JSON response, tolerating a fenced or surrounding text block."""
    try:
        return json.loads(content)
    except (TypeError, json.JSONDecodeError):
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
        start = content.find("[")
        end = content.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    raise ValueError("source relevance response was not valid JSON")


def _score(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def normalize_evaluation(raw: Any, candidate: dict, index: int) -> dict:
    """Normalize one model decision without trusting model-supplied URLs."""
    raw = raw if isinstance(raw, dict) else {}
    decision = str(raw.get("decision", "UNCERTAIN")).upper().strip()
    if decision not in DECISIONS:
        decision = "UNCERTAIN"
    capability = raw.get("evidence_capability", [])
    if not isinstance(capability, list):
        capability = []
    capability = [str(item).strip() for item in capability if str(item).strip()]
    reason = str(raw.get("reason", "Insufficient source metadata for a confident decision")).strip()
    return {
        "candidate_index": index,
        "url": candidate.get("url", ""),
        "decision": decision,
        "relevance_score": _score(raw.get("relevance_score")),
        "source_type": str(raw.get("source_type", "unknown")).strip() or "unknown",
        "entity_relevance": bool(raw.get("entity_relevance", False)),
        "evidence_capability": capability,
        "constraint_relevance": bool(raw.get("constraint_relevance", False)),
        "reason": reason[:1000],
        "missing_information": [str(item).strip() for item in raw.get("missing_information", [])
                                 if str(item).strip()] if isinstance(raw.get("missing_information", []), list) else [],
    }


def _system_prompt() -> str:
    return """You are the Source Relevance Gate for a business data intelligence system.

Your job is only to decide whether retrieving a search result is worthwhile for the
provided structured business requirement. Do not extract records and do not invent
facts. Evaluate entity relevance, evidence capability, hard-constraint relevance,
source type, and usefulness to the business goal. Textual keyword overlap alone is
not enough. A source may be relevant without containing every field.

Return ONLY valid JSON in this shape:
{"evaluations":[{"candidate_index":0,"decision":"KEEP | REJECT | UNCERTAIN",
"relevance_score":0.0,"source_type":"","entity_relevance":true,
"evidence_capability":[],"constraint_relevance":true,"reason":"",
"missing_information":[]}]}

KEEP means retrieval is strongly worthwhile. UNCERTAIN means retrieval may be
worthwhile but the metadata is insufficient. REJECT means the source is clearly
unlikely to provide the requested business evidence.
"""


async def evaluate_sources(
    candidates: list[dict],
    prompt: str,
    contract: dict,
    invoke: Callable[[list], Awaitable[Any]],
) -> list[dict]:
    """Evaluate candidates in one bounded metadata-only model request."""
    if not candidates:
        return []
    metadata = []
    for index, candidate in enumerate(candidates[:50]):
        metadata.append({
            "candidate_index": index,
            "title": str(candidate.get("title", ""))[:500],
            "url": str(candidate.get("url", ""))[:2000],
            "snippet": str(candidate.get("snippet", ""))[:1500],
            "search_query": str(candidate.get("search_query", ""))[:500],
            "provider": candidate.get("provider"),
        })
    requirement = {
        "user_request": prompt,
        "business_goal": contract.get("business_goal"),
        "target_entity": contract.get("entity_type"),
        "required_fields": contract.get("fields", []),
        "hard_constraints": [c for c in contract.get("constraints", []) if c.get("is_hard")],
        "required_evidence": contract.get("evidence_policy", {}),
        "relationships": contract.get("relationships", []),
    }
    response = await invoke([
        SystemMessage(content=_system_prompt()),
        HumanMessage(content=json.dumps({"business_requirement": requirement, "search_results": metadata})),
    ])
    payload = _parse_json(response.content)
    raw_evaluations = payload.get("evaluations", []) if isinstance(payload, dict) else payload
    by_index = {}
    if isinstance(raw_evaluations, list):
        for item in raw_evaluations:
            if isinstance(item, dict):
                try:
                    by_index[int(item.get("candidate_index"))] = item
                except (TypeError, ValueError):
                    continue
    return [normalize_evaluation(by_index.get(index, {}), candidate, index)
            for index, candidate in enumerate(candidates[:50])]
