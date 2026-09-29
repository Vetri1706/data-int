"""Catalog discovery uses HTTP fixtures only; no inference or external requests."""
import asyncio
import json
import unittest

import httpx

from model_catalog import ProviderCatalog


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    def catalog(self, handler, env=None):
        self.requests = []

        async def respond(request):
            self.requests.append(request)
            return handler(request)

        transport = httpx.MockTransport(respond)
        return ProviderCatalog({"NVIDIA_API_KEY": "fixture-secret", **(env or {})},
                               client_factory=lambda **kwargs: httpx.AsyncClient(transport=transport, **kwargs))

    async def test_all_nvidia_models_sorted_deduplicated_and_sanitized(self):
        rows = [{"id": f"vendor/model-{i:03d}", "private": "fixture-secret"} for i in range(120, -1, -1)]
        catalog = self.catalog(lambda _: httpx.Response(200, json={"data": rows + [rows[0]]}))
        result = await catalog.get("nvidia")
        self.assertEqual(len(result["models"]), 121)
        self.assertEqual(result["models"][0]["id"], "vendor/model-000")
        self.assertNotIn("fixture-secret", json.dumps(result))
        request = self.requests[0]
        self.assertEqual(str(request.url), "https://integrate.api.nvidia.com/v1/models")
        self.assertEqual(request.headers["authorization"], "Bearer fixture-secret")
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.content, b"")
        await catalog.validate({"provider": "nvidia", "model": "vendor/model-099"})
        self.assertEqual(len(self.requests), 1)

    async def test_every_installed_ollama_model_including_custom_and_base(self):
        rows = [{"name": model, "capabilities": ["completion"]} for model in
                ["qwen2.5-coder:1.5b-base", "custom-research:latest", "qwen2.5-coder:7b"]]
        catalog = self.catalog(lambda _: httpx.Response(200, json={"models": rows}))
        result = await catalog.get("local")
        self.assertEqual(len(result["models"]), 3)
        self.assertTrue(all(model["available"] for model in result["models"]))
        self.assertEqual(str(self.requests[0].url), "http://127.0.0.1:11434/api/tags")
        self.assertNotIn("authorization", self.requests[0].headers)
        await catalog.validate({"provider": "local", "model": "custom-research:latest"})

    async def test_embeddings_visible_but_not_runnable(self):
        catalog = self.catalog(lambda _: httpx.Response(200, json={"data": [
            {"id": "nvidia/nv-embedqa-mistral-7b-v2"}, {"id": "vendor/new-chat"},
            {"id": "snowflake/arctic-embed-l"}, {"id": "vendor/rerank-model"},
        ]}))
        result = await catalog.get("nvidia")
        self.assertEqual(len(result["models"]), 4)
        self.assertEqual(sum(model["available"] for model in result["models"]), 1)
        with self.assertRaisesRegex(ValueError, "Embedding or reranking"):
            await catalog.validate({"provider": "nvidia", "model": "snowflake/arctic-embed-l"})

    async def test_ollama_remote_aliases_and_embeddings_cannot_bypass_local_privacy(self):
        rows = [{"name": "custom:cloud"}, {"name": "renamed:latest", "remote_host": "https://ollama.com"},
                {"name": "remote:latest", "details": {"format": "remote"}},
                {"name": "embed:latest", "capabilities": ["embedding"]},
                {"name": "local:latest", "capabilities": ["completion", "tools"]}]
        catalog = self.catalog(lambda _: httpx.Response(200, json={"models": rows}))
        result = await catalog.get("local")
        self.assertEqual(len(result["models"]), 5)
        self.assertEqual(sum(model["available"] for model in result["models"]), 1)
        with self.assertRaisesRegex(ValueError, "Cloud-relayed"):
            await catalog.validate({"provider": "local", "model": "renamed:latest"})

    async def test_refresh_discovers_new_models_and_rejects_removed_selection(self):
        rows = [{"name": "original:latest"}]
        catalog = self.catalog(lambda _: httpx.Response(200, json={"models": rows}))
        await catalog.get("local")
        rows[:] = [{"name": "new:latest"}]
        self.assertEqual((await catalog.get("local"))["models"][0]["id"], "original:latest")
        self.assertEqual((await catalog.get("local", refresh=True))["models"][0]["id"], "new:latest")
        await catalog.validate({"provider": "local", "model": "new:latest"})
        with self.assertRaisesRegex(ValueError, "no longer"):
            await catalog.validate({"provider": "local", "model": "original:latest"})

    async def test_follows_all_catalog_pages_on_fixed_official_host(self):
        def handler(request):
            if request.url.params.get("after") == "vendor/first":
                return httpx.Response(200, json={"data": [{"id": "vendor/second"}], "has_more": False})
            return httpx.Response(200, json={"data": [{"id": "vendor/first"}], "has_more": True,
                                            "last_id": "vendor/first", "next": "https://untrusted.example"})
        catalog = self.catalog(handler)
        result = await catalog.get("nvidia")
        self.assertEqual(len(result["models"]), 2)
        self.assertTrue(all(request.url.host == "integrate.api.nvidia.com" for request in self.requests))

    async def test_incomplete_or_invalid_catalog_is_not_reported_as_complete(self):
        for payload in ({"data": [{"id": "loop"}], "has_more": True}, {"data": "invalid"}, {}):
            catalog = self.catalog(lambda _: httpx.Response(200, json=payload))
            result = await catalog.get("nvidia")
            self.assertFalse(result["available"])
            self.assertEqual(result["models"], [])
            self.assertTrue(result["reason"])

    async def test_missing_key_does_not_make_a_request(self):
        catalog = self.catalog(lambda _: self.fail("Unexpected network call"), {"NVIDIA_API_KEY": ""})
        result = await catalog.get("nvidia")
        self.assertFalse(result["available"])
        self.assertIn("NVIDIA_API_KEY", result["reason"])

    async def test_provider_errors_are_sanitized_and_refresh_recovers(self):
        status = 401
        catalog = self.catalog(lambda _: httpx.Response(status, json={"data": [{"id": "vendor/chat"}], "error": "fixture-secret"}))
        result = await catalog.get("nvidia")
        self.assertFalse(result["available"])
        self.assertIn("401", result["reason"])
        self.assertNotIn("fixture-secret", json.dumps(result))
        status = 200
        self.assertTrue((await catalog.get("nvidia", refresh=True))["available"])

    async def test_one_provider_failure_does_not_hide_the_other(self):
        def handler(request):
            if request.url.host == "127.0.0.1":
                raise httpx.ConnectError("private transport detail", request=request)
            return httpx.Response(200, json={"data": [{"id": "vendor/chat"}]})
        catalog = self.catalog(handler)
        local, nvidia = await asyncio.gather(catalog.get("local"), catalog.get("nvidia"))
        self.assertFalse(local["available"])
        self.assertNotIn("private transport", local["reason"])
        self.assertTrue(nvidia["available"])

    async def test_empty_catalog_is_truthful_without_fake_defaults(self):
        catalog = self.catalog(lambda _: httpx.Response(200, json={"models": []}))
        result = await catalog.get("local")
        self.assertEqual(result["models"], [])
        self.assertFalse(result["available"])
        self.assertIn("No Ollama models installed", result["reason"])

    async def test_redirects_never_forward_nvidia_credentials(self):
        catalog = self.catalog(lambda _: httpx.Response(302, headers={"Location": "https://untrusted.example"}))
        result = await catalog.get("nvidia")
        self.assertFalse(result["available"])
        self.assertEqual(len(self.requests), 1)


if __name__ == "__main__":
    unittest.main()
