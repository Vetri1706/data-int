"""Laya integration tests use a protocol fixture and never load model weights."""

import unittest
from unittest.mock import patch

import laya_filter


class FakeResponse:
    def __init__(self, scores):
        self._scores = scores

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "results": [
                {"answers": {"relevance": {"noul": score}}}
                for score in self._scores
            ]
        }


class FakeClient:
    def __init__(self, scores_by_call):
        self.scores_by_call = iter(scores_by_call)
        self.payloads = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, _url, json):
        self.payloads.append(json)
        return FakeResponse(next(self.scores_by_call))


class FailingClient(FakeClient):
    async def post(self, _url, json):
        raise OSError("Laya is unavailable")


CONTRACT = {
    "entity_type": "company",
    "business_goal": "Find component suppliers",
    "fields": [
        {"name": "company_name", "description": "Company name", "required": True},
        {"name": "location", "description": "Company location", "required": False},
    ],
    "constraints": [{"field": "location", "operator": "eq", "target_value": "India"}],
    "relationships": [],
    "evidence_policy": {"required_evidence": ["official source"]},
}


def chunk(index, text):
    return {"chunk_id": f"chunk-{index}", "url": "https://example.com", "text": text}


class LayaFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_relevant_and_irrelevant_chunks_are_filtered_in_batch(self):
        client = FakeClient([[0.91, 0.04]])
        chunks = [chunk(1, "Supplier location and company name"), chunk(2, "Unrelated weather report")]
        with patch.object(laya_filter.httpx, "AsyncClient", return_value=client):
            kept, metrics, status = await laya_filter.filter_chunks(chunks, CONTRACT)
        self.assertEqual(status, "active")
        self.assertEqual([item["chunk_id"] for item in kept], ["chunk-1"])
        self.assertEqual(kept[0]["text"], chunks[0]["text"])
        self.assertEqual(metrics["chunks_before"], 2)
        self.assertEqual(metrics["chunks_after"], 1)
        self.assertEqual(metrics["chunks_filtered"], 1)
        self.assertEqual(client.payloads[0]["states"][0]["body"], chunks[0]["text"])

    async def test_multiple_batches_are_used_without_reinitializing_client(self):
        client = FakeClient([[0.8, 0.7], [0.6]])
        chunks = [chunk(i, f"candidate {i}") for i in range(3)]
        with patch.object(laya_filter, "LAYA_BATCH_SIZE", 2), patch.object(
            laya_filter.httpx, "AsyncClient", return_value=client
        ):
            kept, metrics, status = await laya_filter.filter_chunks(chunks, CONTRACT)
        self.assertEqual(status, "active")
        self.assertEqual(len(kept), 3)
        self.assertEqual(metrics["batch_count"], 2)
        self.assertEqual(len(client.payloads), 2)

    async def test_contract_changes_the_decision_question(self):
        first = laya_filter.build_questions(CONTRACT)["relevance"]["instructions"]
        other = {**CONTRACT, "entity_type": "job", "fields": [{"name": "role", "description": "Role title"}]}
        second = laya_filter.build_questions(other)["relevance"]["instructions"]
        self.assertIn("company_name", first)
        self.assertIn("role", second)
        self.assertNotEqual(first, second)

    async def test_laya_failure_falls_back_without_changing_chunks(self):
        chunks = [chunk(1, "Keep this evidence")]
        with patch.object(laya_filter.httpx, "AsyncClient", return_value=FailingClient([])):
            kept, metrics, status = await laya_filter.filter_chunks(chunks, CONTRACT)
        self.assertEqual(status, "fallback")
        self.assertEqual(kept, chunks)
        self.assertEqual(metrics["chunks_after"], len(chunks))
        self.assertEqual(metrics["chunks_filtered"], 0)

    async def test_high_recall_fallback_prevents_empty_evidence_set(self):
        chunks = [chunk(1, "Possible evidence")]
        client = FakeClient([[0.01]])
        with patch.object(laya_filter.httpx, "AsyncClient", return_value=client):
            kept, metrics, status = await laya_filter.filter_chunks(chunks, CONTRACT)
        self.assertEqual(status, "fallback")
        self.assertEqual(kept, chunks)
        self.assertEqual(metrics["fallback_reason"], "no_chunks_above_threshold")


if __name__ == "__main__":
    unittest.main()
