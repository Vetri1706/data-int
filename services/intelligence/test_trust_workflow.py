"""Adversarial regression tests for acceptance, replanning and cancellation."""
import asyncio
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import graph
from claims import verify_claim, entity_key, typed_equal
from source_policy import permission_decision
from test_grounding import document, chunk_sources, candidate


class TrustTests(unittest.TestCase):
    def test_typed_values_do_not_erase_datetime_or_integer_precision(self):
        self.assertFalse(typed_equal("2026-09-30T12:00:00Z","2026-09-30T13:00:00Z","datetime"))
        self.assertTrue(typed_equal("2026-09-30T12:00:00Z","2026-09-30T14:00:00+02:00","datetime"))
        self.assertFalse(typed_equal("2026-09-30 invented","2026-09-30","date"))
        self.assertFalse(typed_equal(2.5,2.5,"integer"))
        self.assertFalse(typed_equal("C++","C","string"))
        self.assertFalse(typed_equal("C#","C","string"))
    def test_company_namesakes_on_directory_are_not_merged(self):
        left={"canonical_name":"Acme","source_url":"https://directory.example/a"}
        right={"canonical_name":"Acme","source_url":"https://directory.example/b"}
        self.assertNotEqual(entity_key(left,{"entity_type":"company"}),entity_key(right,{"entity_type":"company"}))

    def test_product_and_person_identity_rules(self):
        a={"canonical_name":"Pro","manufacturer":"Alpha","sku":"V2","source_url":"https://example.com/a"}
        b={**a,"manufacturer":"Beta"}
        self.assertNotEqual(entity_key(a,{"entity_type":"product"}),entity_key(b,{"entity_type":"product"}))
        a={"canonical_name":"Alex Lee","profile_url":"https://example.com/alex-1"}
        b={**a,"profile_url":"https://example.com/alex-2"}
        self.assertNotEqual(entity_key(a,{"entity_type":"person"}),entity_key(b,{"entity_type":"person"}))

    def test_embedded_subjects_cannot_lend_support(self):
        for text in ["Acme Robotics employs Bob who is based in Chennai.",
                     "Acme Robotics competes with Beta based in Chennai.",
                     "Acme Robotics acquired a company based in Chennai."]:
            chunk=chunk_sources([document(text=text)])[0]
            claim=verify_claim("Acme Robotics",{"name":"location"},"Chennai",chunk)
            self.assertEqual(claim["state"],"unknown",text)

    def test_model_cannot_designate_arbitrary_fields_as_identity(self):
        chunk=chunk_sources([document(text="Acme Robotics discussed Chennai at a conference.")])[0]
        claim=verify_claim("Acme Robotics",{"name":"location","identity":True},"Chennai",chunk)
        self.assertEqual(claim["state"],"unknown")
    def test_false_support_examples(self):
        for field, value, text in [
            ({"name":"location", "field_type":"location"}, "New Delhi", "Acme Robotics is based in New York."),
            ({"name":"certification", "field_type":"certification"}, "ISO 27001", "Acme Robotics holds ISO 9001 certification."),
            ({"name":"revenue", "field_type":"number"}, "500 million", "Acme Robotics revenue is 10 million."),
            ({"name":"name", "identity":True}, "Delhi Robotics", "Acme Robotics is headquartered in Chennai."),
        ]:
            c=chunk_sources([document(text=text)])[0]
            with self.subTest(value=value):
                self.assertNotEqual(verify_claim("Acme Robotics",field,value,c)["state"],"supported")

    def test_permission_is_explicit_and_fail_closed(self):
        policy={"basis":"user_confirmed_permission","approved_domains":["example.com"]}
        self.assertFalse(permission_decision("https://example.com",{})[0])
        self.assertTrue(permission_decision("https://news.example.com/a",policy)[0])
        self.assertFalse(permission_decision("https://example.com.attacker.org/a",policy)[0])
        self.assertFalse(permission_decision("https://example.com/a",{**policy,"blocked_domains":["example.com"]})[0])
        self.assertFalse(permission_decision("https://example.com/a",{**policy,"domain_filters":["another.com"]})[0])

    def test_drafts_do_not_satisfy_target(self):
        state={"data_contract":{"target_count":100},"validated_records":[{"accepted":False}]*10,"iteration":0,"max_iterations":2}
        self.assertEqual(graph.should_replan(state),"replan")
        self.assertEqual(graph.completion(state)[2],"exhausted")

    def test_completion_requires_field_coverage(self):
        state={"data_contract":{"target_count":1,"min_field_coverage":1},"validated_records":[{"accepted":True,"verification":{"field_coverage":.5}}]}
        self.assertEqual(graph.completion(state)[2],"partial")
        state["validated_records"][0]["verification"]["field_coverage"]=1
        self.assertEqual(graph.completion(state)[2],"completed")


class WorkflowTrustTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_timeout_is_failed_and_keeps_sources_and_review(self):
        state={"run_id":"timeout-review","data_contract":{"target_count":1},"extracted_records":[],
               "validated_records":[{"canonical_name":"Draft","accepted":False}],
               "search_results":[{"url":"https://example.com/a","http_status":200,"content":"private page body"}],
               "stop_kind":"model_error","stop_reason":"Local Ollama: inference timed out."}
        with patch.object(graph,"post_run_event",AsyncMock()) as events:
            result=await graph.semantic_verify(state)
        self.assertEqual(result["status"],"FAILED")
        self.assertEqual(events.call_args.args[1],"run.failed")
        payload=events.call_args.kwargs["payload"]
        self.assertEqual(payload["records"],[])
        self.assertEqual(len(payload["review_candidates"]),1)
        self.assertEqual(len(payload["sources"]),1)
        self.assertNotIn("content",payload["sources"][0])
        self.assertIn("timed out",events.call_args.kwargs["error"])

    async def test_reviewed_sources_are_reused_without_model_or_search_calls(self):
        seed={"url":"https://example.com/a","title":"Supplier","provider":"ddgs/duckduckgo"}
        state={"run_id":"trust","prompt":"suppliers","iteration":0,"data_contract":{"_discovery_sources":[seed]}}
        with patch.object(graph,"post_run_event",AsyncMock()),patch.object(graph,"rust_post",AsyncMock()) as search,patch.object(graph.llm,"ainvoke",AsyncMock()) as model:
            state=await graph.build_plan(state)
            result=await graph.execute_search(state)
        search.assert_not_awaited()
        model.assert_not_awaited()
        self.assertEqual(result["candidate_sources"],[seed])

    async def test_quota_failure_preserves_only_already_accepted_records(self):
        req=graph.RunRequest(run_id="quota-test",prompt="test",data_contract={"target_count":2})
        async def fail(state):
            graph.ACTIVE_RUN_STATES[req.run_id]={**state,"validated_records":[{"canonical_name":"Accepted","accepted":True,"verification":{"field_coverage":1.}},{"canonical_name":"Draft","accepted":False}]}
            raise graph.LLMUnavailable("Groq: HTTP 429")
        with patch.object(graph,"checked_selection",AsyncMock(return_value={"provider":"local"})),patch.object(graph,"rust_get",AsyncMock(return_value={"status":"running"})),patch.object(graph,"graph",SimpleNamespace(ainvoke=fail)),patch.object(graph,"post_run_event",AsyncMock()) as events:
            await graph._execute_run(req)
        self.assertEqual(events.call_args.args[1],"run.partial")
        self.assertEqual([r["canonical_name"] for r in events.call_args.kwargs["payload"]["records"]],["Accepted"])
        self.assertIn("429",events.call_args.kwargs["payload"]["reason"])

    async def test_rejected_raw_output_never_salvaged(self):
        state={"run_id":"trust","data_contract":{"target_count":1},"extracted_records":[{"canonical_name":"Invented","chunk_id":"fake","evidence_excerpt":"invented"}],"validated_records":[],"search_results":[]}
        with patch.object(graph,"post_run_event",AsyncMock()) as events:
            result=await graph.semantic_verify(state)
        self.assertEqual(result["status"],"EXHAUSTED")
        self.assertEqual(events.call_args.kwargs["payload"]["records"],[])

    async def test_replan_considers_unvisited_urls_after_cap(self):
        old=[{"url":f"https://example.com/{i}"} for i in range(25)]
        new={"url":"https://example.com/new"}
        state={"run_id":"trust","prompt":"test","data_contract":{"source_policy":{"basis":"user_confirmed_permission","approved_domains":["example.com"]}},
               "candidate_sources":old+[new],"attempted_urls":[c["url"] for c in old]}
        async def evaluate(candidates,*_):
            self.assertEqual(candidates,[new])
            return [{"candidate_index":0,"decision":"KEEP"}]
        with patch.object(graph,"post_run_event",AsyncMock()),patch.object(graph,"evaluate_sources",evaluate):
            result=await graph.source_relevance_gate(state)
        self.assertEqual(result["relevant_sources"][0]["url"],new["url"])

    async def test_source_failures_survive_retrieval_and_inform_replanning(self):
        state={"run_id":"trust","prompt":"test","data_contract":{"target_count":1,"fields":[{"name":"salary"}]},
               "relevant_sources":[{"url":"https://example.com/a"}],"retrieved_chunks":[],"search_results":[],
               "validated_records":[],"queries":[],"iteration":0}
        failure={"url":"https://example.com/a","success":False,"error":"Robots denied","error_code":"robots_denied"}
        model=SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content='{"queries":[]}')))
        with patch.object(graph,"post_run_event",AsyncMock()),patch.object(graph,"scrapling_extract",AsyncMock(return_value=[failure])),patch.object(graph,"llm",model):
            result=await graph.scrapling_extraction(state)
            result=await graph.evaluate_coverage(result)
            await graph.replan(result)
        self.assertEqual(result["source_failures"][0]["code"],"robots_denied")
        self.assertIn("search_results",graph.ACTIVE_RUN_STATES["trust"])
        self.assertIn("salary",model.ainvoke.call_args.args[0][0].content)
        self.assertIn("Robots denied",model.ainvoke.call_args.args[0][0].content)

    async def test_replanner_gets_missing_fields_and_reasons(self):
        state={"run_id":"trust","prompt":"test","data_contract":{"target_count":5},"queries":[],"iteration":0,"validated_records":[],"evidence_gaps":[{"entity":"Acme","fields":[{"field":"salary","state":"unknown","reason":"Missing publication date"}]}]}
        model=SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content='{"queries":[]}')))
        with patch.object(graph,"llm",model),patch.object(graph,"post_run_event",AsyncMock()):
            await graph.replan(state)
        prompt=model.ainvoke.call_args.args[0][0].content
        self.assertIn("salary",prompt)
        self.assertIn("Missing publication date",prompt)

    async def test_cancellation_interrupts_active_work(self):
        started=asyncio.Event()
        stopped=asyncio.Event()
        async def work(_):
            started.set()
            try: await asyncio.sleep(30)
            finally: stopped.set()
        req=graph.RunRequest(run_id="cancel-test",prompt="test",data_contract={})
        with patch.object(graph.httpx,"AsyncClient",return_value=AsyncMock()),patch.object(graph,"checked_selection",AsyncMock(return_value={"provider":"local"})),patch.object(graph,"rust_get",AsyncMock(return_value={"status":"running"})),patch.object(graph,"graph",SimpleNamespace(ainvoke=work)),patch.object(graph,"post_run_event",AsyncMock()) as events:
            task=asyncio.create_task(graph._execute_run(req))
            graph.ACTIVE_TASKS[req.run_id]=task
            await asyncio.wait_for(started.wait(),1)
            task.cancel()
            await asyncio.wait_for(task,1)
            self.assertTrue(stopped.is_set())
            self.assertEqual(events.call_args.args[1],"run.cancelled")
            self.assertNotIn(req.run_id,graph.ACTIVE_TASKS)

    async def test_production_laya_is_disabled_without_touching_service(self):
        with patch.object(graph,"post_run_event",AsyncMock()),patch.object(graph,"apply_laya_filter",AsyncMock()) as service:
            result=await graph.laya_filter({"run_id":"trust","retrieved_chunks":[],"data_contract":{}})
        service.assert_not_awaited()
        self.assertEqual(result["laya_status"],"disabled")
