import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, ".")
import main


class Values(list):
    def get(self, default=None):
        return self[0] if self else default

    def getall(self):
        return list(self)


class Element:
    def __init__(self, text="", attrib=None):
        self._text = text
        self.attrib = attrib or {}

    def get_all_text(self, separator=" ", strip=True, **_):
        return self._text.strip() if strip else self._text

    def __str__(self):
        return self._text


class Page:
    def __init__(self, content, structured=None, status=200, url="https://example.com/page"):
        self.url = url
        self.status = status
        self.reason = "OK"
        self.history = []
        self.headers = {"content-type": "text/html"}
        self.body = content.encode()
        self._content = content
        self._structured = structured or []

    def css(self, selector):
        if selector == "title::text":
            return Values(["Example Company"])
        if selector == "script[type='application/ld+json']::text":
            return Values([json.dumps(item) for item in self._structured])
        if selector == ".custom":
            return [Element("custom value")]
        return []

    def markdown(self, main_content_only=False):
        return self._content

    def get_all_text(self, **_):
        return self._content


class ScraplingServiceTests(unittest.IsolatedAsyncioTestCase):
    def request(self, **kwargs):
        return main.ExtractRequest(urls=["https://example.com/page"], **kwargs)

    async def test_static_scrapling_page_is_normalized_with_structured_data(self):
        page = Page(
            "# Example Company\n\nExample Company operates in Chennai.",
            [{"@type": "Organization", "name": "Example Company", "address": "Chennai"}],
        )
        with patch.object(main, "public_url", AsyncMock(return_value=True)), patch.object(
            main, "_fetch_static", AsyncMock(return_value=page)
        ):
            result = await main.retrieve_page("https://example.com/page", self.request(), allow_render=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["retrieval_mode"], "static")
        self.assertEqual(result["schema_data"]["name"], "Example Company")
        self.assertIn("Chennai", result["text_content"])
        self.assertEqual(result["source_url"], "https://example.com/page")

    async def test_empty_static_page_escalates_to_scrapling_dynamic_fetcher(self):
        empty = Page("", status=200)
        dynamic = Page("Example Company is headquartered in Chennai and supplies industrial robotics.")
        with patch.object(main, "public_url", AsyncMock(return_value=True)), patch.object(
            main, "_fetch_static", AsyncMock(return_value=empty)
        ), patch.object(main, "_fetch_dynamic", AsyncMock(return_value=dynamic)) as fetch:
            result = await main.retrieve_page("https://example.com/page", self.request(), allow_render=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["retrieval_mode"], "dynamic")
        self.assertEqual(fetch.await_count, 1)

    async def test_one_failed_source_does_not_cancel_other_sources(self):
        request = main.ExtractRequest(urls=["https://example.com/a", "https://example.com/b"])

        async def retrieve(url, *_args, **_kwargs):
            if url.endswith("/b"):
                return main._failed(url, "timeout", "timeout")
            return {"url": url, "status": "success", "success": True}

        with patch.object(main, "retrieve_page", side_effect=retrieve):
            response = await main.extract_endpoint(request)
        self.assertEqual(response.total, 2)
        self.assertEqual(response.successful, 1)
        self.assertEqual(response.results[1]["error_code"], "timeout")

    async def test_non_public_url_is_rejected_before_scrapling(self):
        request = self.request()
        with patch.object(main, "public_url", AsyncMock(return_value=False)), patch.object(
            main, "_fetch_static", AsyncMock()
        ) as fetch:
            result = await main.retrieve_page("http://127.0.0.1:3000/private", request)
        self.assertEqual(result["error_code"], "ssrf_blocked")
        fetch.assert_not_awaited()

    def test_contract_selectors_are_dynamic(self):
        page = Page("Example Company")
        result = main._selector_data(page, {"certification": [".custom"]})
        self.assertEqual(result["certification"][0]["value"], "custom value")


if __name__ == "__main__":
    unittest.main()
