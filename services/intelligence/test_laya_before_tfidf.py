"""Tests for the explicit evaluation-only Laya-before-TF-IDF path."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import graph
from grounding import chunk_sources


CONTRACT = {
    "entity_type": "company",
    "fields": [{"name": "company_name", "description": "Company name", "required": True}],
    "constraints": [],
    "relationships": [],
}


def state():
    source = {
        "url": "https://example.com/company",
        "content": "Navigation. Example Components makes battery systems in Chennai. " * 30,
        "content_sha256": "fixture-hash",
    }
    return {
        "run_id": "before-tfidf-test",
        "prompt": "Find component companies",
        "data_contract": CONTRACT,
        "relevant_sources": [{"url": source["url"], "title": "Example"}],
        "search_results": [source],
        "retrieved_chunks": [],
        "chunk_pool": chunk_sources([source]),
        "laya_filtered_chunks": [],
        "laya_metrics": {},
        "laya_status": "pending",
        "laya_scores": {},
        "laya_evaluations": [],
        "tfidf_metrics": {},
        "laya_before_tfidf": True,
        "laya_enabled": True,
    }


class LayaBeforeTfidfTests(unittest.IsolatedAsyncioTestCase):
    async def test_laya_before_tfidf_consumes_complete_chunk_pool(self):
        current = state()
        kept = current["chunk_pool"][:1]
        metrics = {
            "chunks_before": len(current["chunk_pool"]),
            "chunks_after": 1,
            "chunks_filtered": len(current["chunk_pool"]) - 1,
            "latency_ms": 2.0,
            "score_by_chunk": {kept[0]["chunk_id"]: 0.9},
            "evaluations": [],
        }
        with patch.object(graph, "post_run_event", AsyncMock()), patch.object(
            graph, "apply_laya_filter", AsyncMock(return_value=(kept, metrics, "active"))
        ):
            filtered = await graph.laya_filter(current)
        self.assertEqual(len(filtered["laya_filtered_chunks"]), 1)
        self.assertEqual(filtered["laya_scores"][kept[0]["chunk_id"]], 0.9)

    async def test_tfidf_ranks_only_laya_approved_chunks(self):
        current = state()
        current["laya_filtered_chunks"] = current["chunk_pool"][:1]
        with patch.object(graph, "post_run_event", AsyncMock()):
            ranked = await graph.rank_after_laya(current)
        self.assertLessEqual(len(ranked["retrieved_chunks"]), 1)
        self.assertEqual(ranked["tfidf_metrics"]["chunks_before"], 1)

    async def test_disabled_laya_passes_all_chunks_to_tfidf(self):
        current = state()
        current["laya_enabled"] = False
        with patch.object(graph, "post_run_event", AsyncMock()), patch.object(
            graph, "apply_laya_filter", AsyncMock()
        ) as mock_filter:
            disabled = await graph.laya_filter(current)
            mock_filter.assert_not_awaited()
        self.assertEqual(disabled["laya_status"], "disabled")
        self.assertEqual(disabled["laya_filtered_chunks"], current["chunk_pool"])


if __name__ == "__main__":
    unittest.main()
