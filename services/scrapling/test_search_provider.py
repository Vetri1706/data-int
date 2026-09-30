import unittest
from unittest.mock import patch
import search_provider as search


class SearchTests(unittest.TestCase):
    def setUp(self):
        search._cache.clear()

    def test_fallback_deduplication_provenance_and_scope(self):
        rows = [{"href": "https://evil.example/a", "title": "Wrong scope"},
                {"href": "https://sub.allowed.example/a", "title": "Supplier", "body": "Battery catalogue"}]
        with patch.object(search, "DDGS") as client:
            client.return_value.text.side_effect = [RuntimeError("secret-body"), rows + rows]
            result = search._search("battery suppliers", ["allowed.example"], 10)
            self.assertEqual(len(result["results"]), 1)
            self.assertEqual(result["results"][0]["provider"], "ddgs/yahoo")
            self.assertEqual(result["results"][0]["snippet"], "Battery catalogue")
            self.assertNotIn("secret-body", str(result))
            self.assertIn("site:allowed.example", client.return_value.text.call_args.args[0])
            self.assertEqual(search._search("battery suppliers", ["allowed.example"], 10), result)
            self.assertEqual(client.return_value.text.call_count, 2)

    def test_unapproved_or_private_urls_never_become_candidates(self):
        for url in ["http://127.0.0.1/a", "http://10.1.2.3/a", "http://host.local/a", "file:///a", "https://u:p@example.com/a", "https://allowed.example.evil.com/a"]:
            self.assertFalse(search.allowed_url(url, ["allowed.example"]), url)
        self.assertTrue(search.allowed_url("https://sub.allowed.example/a", ["allowed.example"]))

    def test_engine_failures_do_not_invent_results(self):
        with patch.object(search, "DDGS", side_effect=RuntimeError("secret")):
            result = search._search("test", [], 10)
        self.assertEqual(result["results"], [])
        self.assertEqual(len(result["failures"]), 2)
