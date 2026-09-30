"""Workflow integration uses deterministic source and model fixtures, never API keys."""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("LLM_PROVIDER", "local")
import graph as workflow
from grounding import chunk_sources
from test_grounding import CONTRACT, document, candidate


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Catalog HTTP behavior is covered separately; workflow tests never use keys.
        patcher = patch.object(workflow.provider_catalog, "validate", AsyncMock())
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_parse_checks_live_catalog_before_sending_collection_inputs(self):
        model = SimpleNamespace(ainvoke=AsyncMock())
        workflow.provider_catalog.validate.side_effect = ValueError("Model removed; refresh models")
        with patch.object(workflow, "llm", model):
            with self.assertRaises(workflow.HTTPException) as error:
                await workflow.parse_endpoint(workflow.ParseRequest(prompt="private"))
        self.assertEqual(error.exception.status_code, 422)
        model.ainvoke.assert_not_called()

    async def test_parse_persists_user_choice_not_model_invented_settings(self):
        contract = {"fields": [{"name": "name"}], "_model_config": {"provider": "nvidia", "allow_external": True}}
        model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=json.dumps(contract))))
        with patch.object(workflow, "llm", model):
            result = await workflow.parse_endpoint(workflow.ParseRequest(prompt="test"))
        self.assertEqual(result["_model_config"]["provider"], "local")
        self.assertFalse(result["_model_config"]["allow_external"])
        self.assertIsNone(workflow.selected_model.get())

    async def test_parse_rejects_nvidia_without_consent_before_model_call(self):
        model = SimpleNamespace(ainvoke=AsyncMock())
        with patch.object(workflow, "llm", model):
            with self.assertRaises(workflow.HTTPException) as error:
                await workflow.parse_endpoint(workflow.ParseRequest(prompt="private", model_selection={"provider": "nvidia"}))
        self.assertEqual(error.exception.status_code, 422)
        model.ainvoke.assert_not_called()

    async def test_model_failure_is_not_swallowed_and_replanned(self):
        state = self.state()
        state["retrieved_chunks"] = chunk_sources([document()])
        with patch.object(workflow, "post_run_event", AsyncMock()), patch.object(
            workflow, "llm", SimpleNamespace(ainvoke=AsyncMock(side_effect=workflow.LLMUnavailable("unavailable")))):
            with self.assertRaises(workflow.LLMUnavailable):
                await workflow.extract_and_normalize(state)

    async def test_replanning_does_not_pay_to_extract_old_chunks_again(self):
        state = self.state()
        state["retrieved_chunks"] = chunk_sources([document()])
        state["processed_chunks"] = [c["chunk_id"] for c in state["retrieved_chunks"]]
        state["extracted_records"] = [{"canonical_name": "Acme"}]
        model = SimpleNamespace(ainvoke=AsyncMock())
        with patch.object(workflow, "post_run_event", AsyncMock()), patch.object(workflow, "llm", model):
            result = await workflow.extract_and_normalize(state)
        model.ainvoke.assert_not_called()
        self.assertEqual(result["extracted_records"], state["extracted_records"])

    async def test_workflow_deadline_persists_a_terminal_failure(self):
        import asyncio
        async def slow(_):
            await asyncio.sleep(1)
        with patch.object(workflow, "WORKFLOW_TIMEOUT", 0.01), patch.object(
            workflow, "graph", SimpleNamespace(ainvoke=slow)), patch.object(
            workflow, "post_run_event", AsyncMock()) as events:
            await workflow._execute_run(workflow.RunRequest(run_id="test", prompt="test"))
        self.assertEqual(events.call_args.args[1], "run.failed")
        self.assertIn("time limit", events.call_args.kwargs["error"])

    async def test_discovery_uses_shared_model_and_caps_suggestions(self):
        model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=json.dumps({"results": [
            {"title": "Acme", "url": "https://example.com"} for _ in range(10)]}))))
        with patch.object(workflow, "llm", model):
            result = await workflow.discover_endpoint(workflow.DiscoveryRequest(query="Acme", max_results=2))
        self.assertEqual(len(result["results"]), 2)
        model.ainvoke.assert_awaited_once()

    def state(self):
        return {"run_id": "test-run", "prompt": "robotics companies in Chennai", "data_contract": CONTRACT,
                "queries": ["robotics Chennai"], "candidate_sources": [], "source_relevance": [],
                "relevant_sources": [], "search_results": [], "retrieved_chunks": [],
                "extracted_records": [], "validated_records": [], "iteration": 0, "max_iterations": 1}

    async def test_extraction_validation_and_terminal_event_preserve_attribution(self):
        state = self.state()
        source = document()
        state["search_results"] = [source]
        state["retrieved_chunks"] = chunk_sources([source])
        row = candidate(state["retrieved_chunks"][0])
        with patch.object(workflow, "post_run_event", new_callable=AsyncMock) as events, patch.object(
            workflow, "llm", SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=json.dumps({"records": [row]}))))
        ):
            extracted = await workflow.extract_and_normalize(state)
            validated = await workflow.validate_records(extracted)
            final = await workflow.semantic_verify(validated)
        self.assertEqual(final["status"], "COMPLETED")
        payload = events.call_args.kwargs["payload"]
        self.assertEqual(payload["records"][0]["source_url"], source["url"])
        self.assertEqual(payload["records"][0]["evidence_excerpt"], source["content"])
        self.assertEqual(payload["sources"][0]["content_sha256"], source["content_sha256"])
        self.assertNotIn("content", payload["sources"][0])

    async def test_no_evidence_means_failed_run_not_successful_mock_output(self):
        with patch.object(workflow, "post_run_event", new_callable=AsyncMock) as events:
            state = await workflow.extract_and_normalize(self.state())
            state = await workflow.validate_records(state)
            state = await workflow.semantic_verify(state)
        self.assertEqual(state["status"], "FAILED")
        self.assertEqual(events.call_args.args[1], "run.failed")

    async def test_terminal_storage_failure_is_not_reported_as_success(self):
        with patch.object(workflow, "rust_post", AsyncMock(return_value={})):
            with self.assertRaisesRegex(RuntimeError, "did not persist"):
                await workflow.post_run_event("test-run", "run.completed", payload={"records": []})

    async def test_replanning_preserves_existing_sources_and_chunks(self):
        state = self.state()
        old = document()
        state["candidate_sources"] = [old]
        state["retrieved_chunks"] = chunk_sources([old])
        fresh = document("https://news.example/story", "Acme Robotics is a robotics company in Chennai, building robots for factories.")
        with patch.object(workflow, "post_run_event", new_callable=AsyncMock), patch.object(
            workflow, "rust_post", AsyncMock(return_value={"results": [{"url": fresh["url"], "title": "Fresh", "snippet": "Robotics"}]})) as search:
            state = await workflow.execute_search(state)
        self.assertEqual(len(state["candidate_sources"]), 2)
        self.assertEqual(state["retrieved_chunks"], chunk_sources([old]))
        self.assertEqual(search.call_args.args[1]["domain_filters"], [])

    async def test_source_relevance_gate_only_passes_keep_sources(self):
        state = self.state()
        state["candidate_sources"] = [
            {"url": "https://keep.example/", "title": "Keep", "snippet": "robotics company"},
            {"url": "https://reject.example/", "title": "Reject", "snippet": "unrelated"},
        ]
        model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=json.dumps({"evaluations": [
            {"candidate_index": 0, "decision": "KEEP", "relevance_score": .9},
            {"candidate_index": 1, "decision": "REJECT", "relevance_score": .1},
        ]}))))
        with patch.object(workflow, "post_run_event", new_callable=AsyncMock), patch.object(workflow, "llm", model):
            result = await workflow.source_relevance_gate(state)
        self.assertEqual([s["url"] for s in result["relevant_sources"]], ["https://keep.example/"])
        self.assertEqual([e["decision"] for e in result["source_relevance"]], ["KEEP", "REJECT"])

    async def test_scrapling_receives_only_keep_sources(self):
        state = self.state()
        state["relevant_sources"] = [{"url": "https://keep.example/", "title": "Keep"}]
        result = {"url": "https://keep.example/", "original_url": "https://keep.example/",
                  "title": "Keep", "text_content": "Keep Robotics is based in Chennai.",
                  "text_hash": "hash", "http_status": 200, "reachability": 1.0,
                  "fetched_at": "2026-09-30T00:00:00+00:00", "schema_data": {},
                  "selector_data": {}, "extraction_method": "text_only", "success": True}
        with patch.object(workflow, "post_run_event", new_callable=AsyncMock), patch.object(
            workflow, "scrapling_extract", AsyncMock(return_value=[result])) as scrapling:
            await workflow.scrapling_extraction(state)
        scrapling.assert_awaited_once_with(["https://keep.example/"], state["data_contract"])


if __name__ == "__main__":
    unittest.main()
