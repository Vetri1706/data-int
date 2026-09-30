import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, ".")
from relevance import evaluate_sources, normalize_evaluation


class RelevanceGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.candidates = [
            {"url": "https://acme.example/", "title": "Acme Robotics", "snippet": "Industrial robotics supplier", "search_query": "robotics suppliers"},
            {"url": "https://recipes.example/", "title": "Robotics cake recipe", "snippet": "A recipe with robotics decorations", "search_query": "robotics suppliers"},
        ]
        self.contract = {
            "business_goal": "Find robotics suppliers",
            "entity_type": "company",
            "fields": [{"name": "name", "field_type": "string", "required": True}],
            "constraints": [],
            "relationships": [],
            "evidence_policy": {"required_evidence": ["supplier identity"]},
        }

    async def test_evaluates_metadata_without_fetching_pages(self):
        invoke = AsyncMock(return_value=SimpleNamespace(content=json.dumps({"evaluations": [
            {"candidate_index": 0, "decision": "KEEP", "relevance_score": .91,
             "source_type": "company website", "entity_relevance": True,
             "evidence_capability": ["supplier identity"], "constraint_relevance": True,
             "reason": "Potential supplier page", "missing_information": []},
            {"candidate_index": 1, "decision": "REJECT", "relevance_score": .05,
             "source_type": "recipe page", "entity_relevance": False,
             "evidence_capability": [], "constraint_relevance": False,
             "reason": "No business evidence", "missing_information": ["supplier identity"]},
        ]})))
        results = await evaluate_sources(self.candidates, "Find robotics suppliers", self.contract, invoke)
        self.assertEqual([result["decision"] for result in results], ["KEEP", "REJECT"])
        self.assertEqual(results[0]["url"], self.candidates[0]["url"])
        request = json.loads(invoke.await_args.args[0][1].content)
        self.assertEqual(request["search_results"][0]["url"], self.candidates[0]["url"])
        self.assertNotIn("content", request["search_results"][0])

    def test_invalid_model_decision_is_uncertain_and_url_is_candidate_owned(self):
        result = normalize_evaluation({"decision": "maybe", "url": "https://forged.example"}, self.candidates[0], 0)
        self.assertEqual(result["decision"], "UNCERTAIN")
        self.assertEqual(result["url"], self.candidates[0]["url"])


if __name__ == "__main__":
    unittest.main()
