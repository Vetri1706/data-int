import asyncio
import copy
import hashlib
import unittest
from datetime import datetime, timedelta, timezone

import httpx
from grounding import (collect_sources, chunk_sources, retrieve_chunks,
                       validate_candidates, sanitize_query, fresh_score, constraint_passes)

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)
CONTRACT = {"entity_type": "company", "fields": [
    {"name": "name", "required": True}, {"name": "location", "required": True},
    {"name": "industry", "required": True}], "freshness_days": 90,
    "constraints": [{"field": "location", "operator": "eq", "target_value": "Chennai", "is_hard": True}],
    "evidence_policy": {"min_sources": 2, "require_date": True}}


def document(url="https://acme.example/about", text=None, **kwargs):
    text = text or "Acme Robotics is a robotics company based in Chennai. Acme Robotics builds robotics systems for factories."
    return {"url": url, "title": "Acme", "content": text,
            "content_sha256": hashlib.sha256(text.encode()).hexdigest(), "http_status": 200,
            "reachability": 1., "published_at": NOW.isoformat(), "fetched_at": NOW.isoformat(), **kwargs}


def candidate(chunk):
    return {"canonical_name": "Acme Robotics", "name": "Acme Robotics", "location": "Chennai",
            "industry": "robotics", "chunk_id": chunk["chunk_id"],
            "source_url": "https://fabricated.example/claim", "evidence_excerpt": "Invented text",
            "extraction_confidence": 1.0}


class GroundingTests(unittest.TestCase):
    def test_query_sanitization_preserves_terms_after_site_filter(self):
        self.assertEqual(sanitize_query('"robotics" site:example.com AND (Chennai OR Bangalore) funding'),
                         "robotics Chennai Bangalore funding")

    def test_chunk_offsets_reconstruct_exact_text_and_overlap(self):
        source = document(text="Chennai robotics company. " * 80)
        chunks = chunk_sources([source])
        self.assertGreater(len(chunks), 2)
        self.assertEqual(chunks[1]["char_start"], 100)
        for chunk in chunks:
            self.assertEqual(chunk["text"], source["content"][chunk["char_start"]:chunk["char_end"]])
        self.assertEqual(chunks[-1]["char_end"], len(source["content"]))

    def test_retrieval_ranks_relevant_source(self):
        irrelevant = document("https://cooking.example/", "Chocolate cake recipe butter flour eggs oven.")
        selected = retrieve_chunks([irrelevant, document()], "Chennai robotics company", CONTRACT, top_k=1)
        self.assertEqual(selected[0]["url"], document()["url"])
        self.assertGreater(selected[0]["retrieval_score"], 0)

    def test_provenance_overwrites_model_fabrications(self):
        chunks = chunk_sources([document()])
        row = validate_candidates([candidate(chunks[0])], chunks, CONTRACT, NOW)[0]
        self.assertEqual(row["source_url"], chunks[0]["url"])
        self.assertEqual(row["evidence_excerpt"], chunks[0]["text"])
        self.assertEqual(row["provenance"]["char_start"], 0)
        self.assertIn("ml_validation_score", row["confidence_breakdown"])
        self.assertEqual(row["confidence_breakdown"]["agreement"], 0)
        self.assertNotEqual(row["status"], "verified")

    def test_hallucinated_identity_chunk_and_unreachable_source_rejected(self):
        chunks = chunk_sources([document()])
        for changes in [{"canonical_name": "Invented Inc"}, {"chunk_id": "forged"},
                        {"canonical_name": "Top 10 robotics companies"}]:
            self.assertEqual(validate_candidates([{**candidate(chunks[0]), **changes}], chunks, CONTRACT, NOW), [])
        chunks[0]["http_status"] = 404
        self.assertEqual(validate_candidates([candidate(chunks[0])], chunks, CONTRACT, NOW), [])

    def test_unsupported_hard_constraint_not_filled_from_url(self):
        chunks = chunk_sources([document(text="Acme Robotics is a robotics company in Mumbai, with equipment for factories.")])
        row = candidate(chunks[0])
        row["source_url"] = "https://example.com/Chennai"
        self.assertEqual(validate_candidates([row], chunks, CONTRACT, NOW), [])

    def test_missing_and_zero_fields(self):
        chunks = chunk_sources([document()])
        row = candidate(chunks[0]); row["industry"] = "aerospace"
        output = validate_candidates([row], chunks, CONTRACT, NOW)[0]
        self.assertLess(output["confidence_breakdown"]["completeness"], 1)
        self.assertNotIn("industry", [f["field_name"] for f in output["provenance"]["field_evidence"]])
        self.assertTrue(constraint_passes(0, "eq", 0))

    def test_independent_agreement_and_duplicate_dedup(self):
        first = document()
        mirror = document("https://mirror.example/about")
        second = document("https://news.example/story", "Chennai company Acme Robotics develops robotics tools. The robotics products support local factories.")
        chunks = chunk_sources([first, mirror, second])
        row = candidate(chunks[0])
        output = validate_candidates([row, row], chunks, CONTRACT, NOW)
        self.assertEqual(len(output), 1)
        self.assertEqual(len(output[0]["provenance"]["source_urls"]), 2)
        self.assertEqual(output[0]["confidence_breakdown"]["agreement"], .5)

    def test_domain_repeats_and_conflicting_location_not_agreement(self):
        chunks = chunk_sources([document(), document("https://acme.example/team", "Acme Robotics robotics Chennai team."),
                               document("https://news.example/", "Acme Robotics robotics company based in Mumbai.")])
        row = validate_candidates([candidate(chunks[0])], chunks, CONTRACT, NOW)[0]
        self.assertEqual(row["confidence_breakdown"]["agreement"], 0)

    def test_freshness_changes_score_and_unknown_is_not_fresh(self):
        recent = document()
        old = document(published_at=(NOW - timedelta(days=120)).isoformat())
        self.assertGreater(fresh_score(recent, 90, True, NOW)[0], fresh_score(old, 90, True, NOW)[0])
        self.assertEqual(fresh_score(document(published_at=None), 90, True, NOW), (0., "unknown"))
        self.assertEqual(fresh_score(document(published_at=None), 90, False, NOW), (.5, "crawl"))
        chunks = chunk_sources([recent]); row = candidate(chunks[0])
        a = validate_candidates([row], chunks, CONTRACT, NOW)[0]
        chunks[0]["published_at"] = old["published_at"]
        b = validate_candidates([row], chunks, CONTRACT, NOW)[0]
        self.assertGreater(a["confidence_score"], b["confidence_score"])

    def test_redirect_penalty_and_contributions_match(self):
        chunks = chunk_sources([document()]); row = candidate(chunks[0])
        direct = validate_candidates([row], chunks, CONTRACT, NOW)[0]
        chunks[0]["reachability"] = .7
        redirected = validate_candidates([row], chunks, CONTRACT, NOW)[0]
        self.assertAlmostEqual(redirected["confidence_score"], direct["confidence_score"] * .7, places=3)
        self.assertAlmostEqual(sum(f["contribution"] for f in redirected["provenance"]["factors"]), redirected["confidence_score"], places=3)

    def test_numeric_and_date_constraints(self):
        self.assertTrue(constraint_passes("$1.5M", "gte", 1_400_000))
        self.assertFalse(constraint_passes("$1.5M", "gte", 2_000_000))
        self.assertTrue(constraint_passes("2026-09-29", "gte", "2026-01-01"))
        self.assertFalse(constraint_passes("unknown", "gte", 5))
        self.assertFalse(constraint_passes("Chennai office", "eq", "Chennai"))

    def test_negated_claim_and_accessory_are_rejected(self):
        chunks = chunk_sources([document(text="Acme Robotics is a robotics company, but it is not based in Chennai. It is headquartered in Mumbai.")])
        self.assertEqual(validate_candidates([candidate(chunks[0])], chunks, CONTRACT, NOW), [])
        chunks = chunk_sources([document(text="Acme Robotics phone case is a robotics accessory available in Chennai. This company sells phone cases.")])
        row = {**candidate(chunks[0]), "canonical_name": "Acme Robotics phone case", "name": "Acme Robotics phone case"}
        self.assertEqual(validate_candidates([row], chunks, CONTRACT, NOW), [])

    def test_publisher_subdomains_are_one_confirmation(self):
        chunks = chunk_sources([document("https://www.acme.com/"), document("https://news.acme.com/story", "Chennai company Acme Robotics develops robotics tools for industrial factories.")])
        row = validate_candidates([candidate(chunks[0])], chunks, CONTRACT, NOW)[0]
        self.assertEqual(row["confidence_breakdown"]["agreement"], 0)

    def test_neighbouring_entity_attributes_not_misattributed(self):
        chunks = chunk_sources([document(text="Acme Robotics is a robotics company in Mumbai. Other Industries is based in Chennai.")])
        self.assertEqual(validate_candidates([candidate(chunks[0])], chunks, CONTRACT, NOW), [])

    def test_unknown_schema_description_is_supported(self):
        contract = copy.deepcopy(CONTRACT)
        contract["fields"][0]["description"] = None
        self.assertTrue(retrieve_chunks([document()], "Chennai robotics company", contract))

    def test_model_attributes_outside_contract_not_persisted(self):
        chunks = chunk_sources([document()])
        row = {**candidate(chunks[0]), "invented_revenue": "$100M"}
        self.assertNotIn("invented_revenue", validate_candidates([row], chunks, CONTRACT, NOW)[0])


class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def fetch(self, handler, url="https://source.example/deep"):
        async def guard(url):
            return not url.startswith("http://127.0.0.1")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await collect_sources([{"url": url, "snippet": "A model's invented story"}], client, guard)

    async def test_root_fallback_uses_only_root_content(self):
        def handler(request):
            if request.url.path == "/deep": return httpx.Response(404)
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<html><title>Home</title><p>Acme Robotics official website has a robotics research team in Chennai.</p></html>")
        rows = await self.fetch(handler)
        self.assertEqual(rows[0]["url"], "https://source.example/")
        self.assertTrue(rows[0]["root_fallback"])
        self.assertNotIn("invented", rows[0]["content"])
        self.assertEqual(rows[0]["reachability"], .7)

    async def test_blocked_and_timeout_dropped(self):
        self.assertEqual(await self.fetch(lambda req: httpx.Response(403)), [])
        def timeout(request): raise httpx.ReadTimeout("timeout", request=request)
        self.assertEqual(await self.fetch(timeout), [])

    async def test_redirect_success_and_private_redirect_rejected(self):
        def handler(request):
            if request.url.path == "/deep": return httpx.Response(302, headers={"location": "/about"})
            return httpx.Response(200, headers={"content-type": "text/plain"}, text="Acme Robotics develops robotics and is headquartered in Chennai.")
        rows = await self.fetch(handler)
        self.assertEqual(rows[0]["redirect_count"], 1)
        self.assertEqual(rows[0]["url"], "https://source.example/about")
        self.assertEqual(await self.fetch(lambda req: httpx.Response(302, headers={"location": "http://127.0.0.1/private"})), [])

    async def test_soft_404_and_scripts_not_evidence(self):
        self.assertEqual(await self.fetch(lambda req: httpx.Response(200, headers={"content-type": "text/html"}, text="<h1>Page not found</h1><p>We could not find the requested resource.</p>")), [])
        rows = await self.fetch(lambda req: httpx.Response(200, headers={"content-type": "text/html"}, text="<script>Invented Inc in Chennai</script><p>Acme Robotics manufactures robotics equipment for industrial customers.</p>"))
        self.assertNotIn("Invented", rows[0]["content"])


if __name__ == "__main__":
    unittest.main()
