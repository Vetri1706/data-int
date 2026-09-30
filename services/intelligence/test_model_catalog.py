"""Catalog discovery uses HTTP fixtures only; no inference or external requests."""
import asyncio
import json
import unittest

import httpx

from model_catalog import ProviderCatalog, normalize_rows
from providers import PROVIDERS


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_configured_local_default_and_disabled_model(self):
        rows = [{"name": "a-reasoning"}, {"name": "z-instruction", "details": {"context_length": 32768}}]
        catalog = self.catalog(lambda _: httpx.Response(200, json={"models": rows}), {
            "NVIDIA_API_KEY": "", "LOCAL_LLM_MODEL": "z-instruction", "LOCAL_LLM_DISABLED_MODELS": "a-reasoning"})
        result = await catalog.get("local")
        self.assertEqual(result["default_model"], "z-instruction")
        self.assertEqual((await catalog.list())["default"]["model"], "z-instruction")
        self.assertEqual(next(m for m in result["models"] if m["id"] == "z-instruction")["context_length"], 32768)
        with self.assertRaisesRegex(ValueError, "Disabled for collections"):
            await catalog.validate({"provider": "local", "model": "a-reasoning"})

    async def test_configured_default_overrides_alphabetical_order_but_not_cost_sort(self):
        catalog = self.catalog(lambda _: httpx.Response(200, json={"models": [{"name": "a-first"}, {"name": "z-configured"}]}),
                               {"LOCAL_LLM_MODEL": "z-configured"})
        result = await catalog.get("local")
        self.assertEqual(result["default_model"], "z-configured")
        self.assertEqual([m["id"] for m in result["models"]], ["a-first", "z-configured"])

    async def test_each_hosted_provider_fails_closed_without_key(self):
        env = {spec.key_env: " " for spec in PROVIDERS.values() if spec.key_env}
        catalog = self.catalog(lambda _: self.fail("Unexpected network call"), env)
        for name, spec in PROVIDERS.items():
            if name != "local":
                result = await catalog.get(name)
                self.assertFalse(result["available"])
                self.assertFalse(result["configured"])
                self.assertEqual(result["models"], [])
                self.assertIn(spec.key_env, result["reason"])

    async def test_cached_availability_is_revoked_and_rotated_keys_refetch(self):
        catalog = self.catalog(lambda _: httpx.Response(200, json={"data": [{"id": "chat"}]}))
        self.assertTrue((await catalog.get("nvidia"))["available"])
        catalog.env["NVIDIA_API_KEY"] = "rotated-secret"
        await catalog.get("nvidia")
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[-1].headers["authorization"], "Bearer rotated-secret")
        catalog.env["NVIDIA_API_KEY"] = ""
        self.assertFalse((await catalog.get("nvidia"))["available"])
        self.assertEqual(len(self.requests), 2)

    async def test_glm_documented_free_models_lead_live_paid_catalog(self):
        catalog = self.catalog(lambda _: httpx.Response(200, json={"data": [{"id": "glm-5"}]}), {"GLM_API_KEY": "fixture-secret"})
        result = await catalog.get("glm")
        self.assertEqual([m["id"] for m in result["models"]], ["glm-4.5-flash", "glm-4.7-flash", "glm-5"])
        self.assertEqual(result["models"][0]["catalog_source"], "documented")
        self.assertIsNone(result["models"][0]["context_length"])
        self.assertEqual([m["cost"]["kind"] for m in result["models"]], ["free", "free", "paid"])

    def test_openrouter_free_requires_explicit_valid_zero_prices(self):
        rows = [{"id": "z-free", "pricing": {"prompt": "0", "completion": "0", "request": "0"}},
                {"id": "a-paid", "pricing": {"prompt": "0", "completion": "0.5"}},
                {"id": "b-request-fee", "pricing": {"prompt": "0", "completion": "0", "request": "1"}},
                {"id": "unknown:free"}, {"id": "missing-output", "pricing": {"prompt": "0"}},
                {"id": "invalid", "pricing": {"prompt": "NaN", "completion": "0"}},
                {"id": "negative", "pricing": {"prompt": "-1", "completion": "0"}}]
        result = normalize_rows("openrouter", rows)
        self.assertEqual(result[0]["id"], "z-free")
        self.assertEqual(sum(m["cost"]["kind"] == "free" for m in result), 1)
        self.assertEqual(sum(m["cost"]["kind"] == "paid" for m in result), 2)

    def test_huggingface_free_route_is_pinned_and_other_routes_are_not_free(self):
        rows = [{"id": "org/chat", "providers": [
            {"provider": "free-host", "status": "live", "is_free": True, "context_length": 8192},
            {"provider": "paid-host", "status": "live", "pricing": {"input": 1, "output": 2}},
            {"provider": "zero-rounded", "status": "live", "is_free": False, "pricing": {"input": 0, "output": 0}},
            {"provider": "down", "status": "error", "is_free": True}]}]
        result = normalize_rows("huggingface", rows)
        self.assertEqual(result[0]["id"], "org/chat:free-host")
        self.assertEqual(result[0]["context_length"], 8192)
        self.assertEqual([m["cost"]["kind"] for m in result], ["free", "credits", "credits"])
        self.assertNotIn("org/chat", [m["id"] for m in result])

    def test_groq_free_tier_and_unsupported_models_are_honest(self):
        result = normalize_rows("groq", [{"id": "allam-2-7b"}, {"id": "openai/gpt-oss-20b"},
            {"id": "image-maker", "output_modalities": ["image"]}, {"id": "whisper-large-v3"},
            {"id": "meta-llama/llama-prompt-guard-2-86m"}, {"id": "inactive", "active": False}])
        self.assertEqual(result[0]["id"], "openai/gpt-oss-20b")
        self.assertEqual(result[0]["cost"]["kind"], "free_tier")
        self.assertEqual(sum(m["available"] for m in result), 2)
        self.assertFalse(any(m["cost"]["kind"] == "free" for m in result))

    async def test_gemini_pagination_and_key_never_in_url(self):
        def handler(request):
            self.assertEqual(request.headers["x-goog-api-key"], "fixture-secret")
            self.assertNotIn("fixture-secret", str(request.url))
            self.assertNotIn("authorization", request.headers)
            if request.url.params.get("pageToken") == "next":
                return httpx.Response(200, json={"models": [{"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]}]})
            return httpx.Response(200, json={"models": [{"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"], "inputTokenLimit": 1000000}], "nextPageToken": "next"})
        catalog = self.catalog(handler, {"GEMINI_API_KEY": "fixture-secret"})
        result = await catalog.get("gemini")
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(result["models"][0]["id"], "gemini-2.5-flash")
        self.assertEqual(result["models"][0]["cost"]["kind"], "free_tier")
        self.assertFalse(result["models"][1]["available"])

    async def test_catalog_default_is_available_and_never_approves_hosted_processing(self):
        def handler(request):
            if request.url.host == "127.0.0.1":
                raise httpx.ConnectError("unreachable")
            return httpx.Response(200, json={"data": [{"id": "glm-5"}]})
        catalog = self.catalog(handler, {"GLM_API_KEY": "fixture-secret", "NVIDIA_API_KEY": ""})
        result = await catalog.list()
        self.assertEqual(result["default"], {"provider": "glm", "model": "glm-4.5-flash", "allow_external": False})
        self.assertEqual(len(result["providers"]), 7)
        self.assertEqual(len(self.requests), 2)

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
