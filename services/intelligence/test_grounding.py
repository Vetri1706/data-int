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
    def contract(self, **changes):
        contract = copy.deepcopy(CONTRACT)
        contract.update(evidence_policy={"min_sources": 1}, freshness_days=None, target_count=1)
        contract.update(changes)
        return contract

    def verify(self, text=None, changes=None, contract=None):
        chunks = chunk_sources([document(text=text)])
        row = {**candidate(chunks[0]), **(changes or {})}
        return validate_candidates([row], chunks, contract or self.contract(), NOW)

    def test_query_sanitization(self):
        self.assertEqual(sanitize_query('"robotics" site:example.com AND (Chennai OR Bangalore) funding'), "robotics Chennai Bangalore funding")

    def test_exact_provenance_and_no_confidence_fabrications(self):
        row = self.verify()[0]
        self.assertTrue(row["accepted"])
        self.assertEqual(row["source_url"], document()["url"])
        self.assertIsNone(row["confidence_score"])
        self.assertEqual(row["confidence_breakdown"], {})
        text = document()["content"]
        for evidence in row["provenance"]["field_evidence"]:
            self.assertEqual(evidence["verbatim_quote"], text[evidence["char_start"]:evidence["char_end"]])
            self.assertNotIn("Invented", evidence["verbatim_quote"])

    def test_chunk_offsets_and_retrieval_preserved(self):
        source = document(text="Chennai robotics company. " * 80)
        for c in chunk_sources([source]):
            self.assertEqual(c["text"], source["content"][c["char_start"]:c["char_end"]])
        unrelated = document("https://cooking.example/", "Chocolate cake recipe butter flour eggs oven.")
        selected = retrieve_chunks([unrelated, document()], "Chennai robotics company", CONTRACT, top_k=1)
        self.assertEqual(selected[0]["url"], document()["url"])

    def test_forged_identity_or_chunk_cannot_be_repaired(self):
        self.assertEqual(self.verify(changes={"canonical_name":"Delhi Robotics"}), [])
        self.assertEqual(self.verify(changes={"chunk_id":"forged"}), [])

    def test_wrong_location_is_review_and_null_not_accepted(self):
        row=self.verify("Acme Robotics is a robotics company based in Mumbai.")[0]
        self.assertFalse(row["accepted"])
        self.assertIsNone(row["location"])
        self.assertEqual(row["claims"]["location"]["state"],"contradicted")
        self.assertTrue(row["verification"]["acceptance_failures"])

    def test_missing_required_field_abstains(self):
        row=self.verify(changes={"industry":"aerospace"})[0]
        self.assertFalse(row["accepted"])
        self.assertIsNone(row["industry"])
        self.assertEqual(row["claims"]["industry"]["state"],"unknown")

    def test_zero_is_supported_value(self):
        c=self.contract(fields=[{"name":"revenue","field_type":"number","required":True}],constraints=[])
        row=self.verify("Acme Robotics revenue is 0.",{"revenue":0},c)[0]
        self.assertTrue(row["accepted"])
        self.assertEqual(row["revenue"],0)

    def test_publication_freshness_is_a_gate_and_crawl_is_unknown(self):
        self.assertEqual(fresh_score(document(published_at=None),90,False,NOW),(None,"unknown"))
        c=self.contract(freshness_days=7)
        chunks=chunk_sources([document(published_at=(NOW-timedelta(days=30)).isoformat())])
        row=validate_candidates([candidate(chunks[0])],chunks,c,NOW)[0]
        self.assertFalse(row["accepted"])
        self.assertTrue(any("publication" in r["reason"] for r in row["verification"]["acceptance_failures"]))

    def test_mirrors_do_not_satisfy_two_source_policy(self):
        chunks=chunk_sources([document(),document("https://mirror.example/about")])
        rows=[candidate(c) for c in chunks]
        c=self.contract(evidence_policy={"min_sources":2})
        for row in validate_candidates(rows,chunks,c,NOW):
            self.assertFalse(row["accepted"])
            self.assertEqual(row["claims"]["location"]["distinct_source_domains"],1)

    def test_same_name_jobs_at_different_employers_remain_distinct(self):
        c=self.contract(entity_type="job",constraints=[],fields=[{"name":n,"required":True} for n in ["job_title","company_name","location"]])
        pages=[document("https://jobs.example/a", "Senior Engineer company name: Acme. Senior Engineer is based in Chennai."),document("https://jobs.example/b", "Senior Engineer company name: Beta. Senior Engineer is based in Chennai.")]
        chunks=chunk_sources(pages)
        rows=[{"canonical_name":"Senior Engineer","job_title":"Senior Engineer","company_name":employer,"location":"Chennai","chunk_id":chunk["chunk_id"]} for employer,chunk in zip(["Acme","Beta"],chunks)]
        output=validate_candidates(rows,chunks,c,NOW)
        self.assertEqual(len(output),2)
        self.assertTrue(all(r["accepted"] for r in output))

    def test_complementary_claims_merge_without_changing_evidence(self):
        pages=[document(text="Acme Robotics is based in Chennai. Acme Robotics website: https://acme.example/"), document("https://acme.example/products","Acme Robotics is a robotics company. Acme Robotics website: https://acme.example/")]
        chunks=chunk_sources(pages)
        rows=[{**candidate(chunks[0]),"industry":None},{**candidate(chunks[1]),"location":None}]
        contract=self.contract()
        contract["fields"].append({"name":"website","field_type":"url","required":False})
        rows=[{**row,"website":"https://acme.example/"} for row in rows]
        output=validate_candidates(rows,chunks,contract,NOW)
        self.assertEqual(len(output),1)
        self.assertTrue(output[0]["accepted"])
        self.assertEqual(len(output[0]["provenance"]["source_urls"]),2)

    def test_conflicting_claims_are_not_resolved_by_picking_one(self):
        chunks=chunk_sources([document(text=document()["content"]+" Acme Robotics website: https://acme.example/"),document("https://acme.example/contact","Acme Robotics is a robotics company based in Mumbai. Acme Robotics website: https://acme.example/")])
        rows=[candidate(chunks[0]),{**candidate(chunks[1]),"location":"Mumbai"}]
        contract=self.contract()
        contract["fields"].append({"name":"website","field_type":"url","required":False})
        rows=[{**row,"website":"https://acme.example/"} for row in rows]
        output=validate_candidates(rows,chunks,contract,NOW)
        self.assertEqual(len(output),1)
        row=output[0]
        self.assertFalse(row["accepted"])
        self.assertEqual(row["claims"]["location"]["state"],"contradicted")
        self.assertIsNone(row["location"])

    def test_neighbour_and_same_sentence_entity_attributes_are_not_borrowed(self):
        for text in ["Acme Robotics is a robotics company based in Mumbai. Other Industries is based in Chennai.",
                     "Acme Robotics is located in Mumbai, unlike Beta which is headquartered in Chennai."]:
            row=self.verify(text)[0]
            self.assertFalse(row["accepted"])
            self.assertNotEqual(row["claims"]["location"]["state"],"supported")

    def test_negation_is_contradiction(self):
        row=self.verify("Acme Robotics is a robotics company but it is not based in Chennai.")[0]
        self.assertFalse(row["accepted"])
        self.assertNotEqual(row["claims"]["location"]["state"],"supported")

    def test_numeric_and_date_constraints(self):
        self.assertTrue(constraint_passes("$1.5M","gte","$1.4M"))
        self.assertFalse(constraint_passes("$1.5M","gte",1400000))
        self.assertFalse(constraint_passes("Chennai","unsupported_operator",None))
        self.assertFalse(constraint_passes("$1.5M","gte",2000000))
        self.assertTrue(constraint_passes("2026-09-29","gte","2026-01-01"))
        self.assertFalse(constraint_passes("unknown","gte",5))
        self.assertTrue(constraint_passes(0,"eq",0))
        self.assertFalse(constraint_passes("C++","eq","C"))
        self.assertTrue(constraint_passes("1 million","eq",1000000,"number"))

    def test_attributes_outside_schema_are_not_persisted(self):
        row=self.verify(changes={"invented_revenue":"$100M"})[0]
        self.assertNotIn("invented_revenue",row)


class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def fetch(self, handler, url="https://source.example/deep"):
        async def guard(url):
            return not url.startswith("http://127.0.0.1")
        def permitted(request):
            return httpx.Response(404) if request.url.path == "/robots.txt" else handler(request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(permitted)) as client:
            return await collect_sources([{"url": url, "snippet": "A model's invented story"}], client, guard,
                {"basis":"user_confirmed_permission","approved_domains":["source.example"]})

    async def test_root_fallback_uses_only_root_content(self):
        def handler(request):
            if request.url.path == "/deep": return httpx.Response(404)
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<html><title>Home</title><p>Acme Robotics official website has a robotics research team in Chennai.</p></html>")
        rows = await self.fetch(handler)
        self.assertEqual(rows[0]["url"], "https://source.example/")
        self.assertTrue(rows[0]["root_fallback"])
        self.assertNotIn("invented", rows[0]["content"])
        self.assertEqual(rows[0]["reachability"], 1.)

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
