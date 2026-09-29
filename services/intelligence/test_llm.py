"""Provider routing and latency guarantees; all model calls are fixtures."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from llm import LLMUnavailable, ModelGateway, provider_config, selected_model, validate_selection


class RateLimited(Exception):
    status_code = 429


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def gateway(self, env=None):
        self.clients = {}
        self.options = []
        def factory(**kwargs):
            client = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content='{"ok": true}')))
            client.bind = Mock(return_value=client)
            self.clients[kwargs["model"]] = client
            self.options.append(kwargs)
            return client
        return ModelGateway({"LLM_PROVIDER": "local", **(env or {})}, client_factory=factory)

    async def test_local_default_and_no_sdk_retries(self):
        gateway = self.gateway()
        await gateway.ainvoke([])
        self.assertEqual(gateway.status()["provider"], "local")
        self.assertEqual(self.options[0]["max_retries"], 0)
        self.assertEqual(self.options[0]["base_url"], "http://127.0.0.1:11434/v1")

    def test_nvidia_uses_only_official_endpoint_and_own_model(self):
        provider = provider_config("nvidia", {"NVIDIA_API_KEY": "fixture-secret", "MODEL_NAME": "old-groq-model"})
        self.assertEqual(provider.base_url, "https://integrate.api.nvidia.com/v1")
        self.assertEqual(provider.model, "meta/llama-3.3-70b-instruct")
        self.assertNotIn("fixture-secret", repr(provider))

    def test_provider_validation(self):
        for name, env in [("groq", {}), ("nvidia", {}), ("local", {"LOCAL_LLM_BASE_URL": "https://remote.example/v1"})]:
            with self.assertRaises(ValueError):
                provider_config(name, env)

    async def test_explicit_nvidia_rate_limit_cools_down_without_silent_switch(self):
        gateway = self.gateway({"NVIDIA_API_KEY": "fixture-secret"})
        selection = {"provider": "nvidia", "model": "meta/llama-3.3-70b-instruct", "allow_external": True}
        gateway._selection_client(selection)
        primary = self.clients[selection["model"]]
        primary.ainvoke.side_effect = RateLimited("secret provider response")
        token = selected_model.set(selection)
        try:
            for _ in range(2):
                with self.assertRaises(LLMUnavailable):
                    await gateway.ainvoke([])
        finally:
            selected_model.reset(token)
        self.assertEqual(primary.ainvoke.await_count, 1)
        self.clients["qwen2.5-coder:7b"].ainvoke.assert_not_called()

    def test_external_processing_requires_explicit_consent(self):
        with self.assertRaisesRegex(ValueError, "Approve sending"):
            validate_selection({"provider": "nvidia"}, {"NVIDIA_API_KEY": "fixture-secret"})
        with self.assertRaises(ValueError):
            validate_selection({"provider": "local", "model": "invalid\nmodel"}, {})

    async def test_new_hosted_model_does_not_require_code_allowlist_or_json_mode(self):
        gateway = self.gateway({"NVIDIA_API_KEY": "fixture-secret"})
        selection = {"provider": "nvidia", "model": "vendor/new-chat-model", "allow_external": True}
        token = selected_model.set(selection)
        try:
            await gateway.ainvoke([])
        finally:
            selected_model.reset(token)
        self.clients[selection["model"]].ainvoke.assert_awaited_once()
        self.clients[selection["model"]].bind.assert_not_called()

    async def test_parallel_collections_keep_separate_provider_contexts(self):
        gateway = self.gateway({"NVIDIA_API_KEY": "fixture-secret"})
        async def run(provider, model):
            selection = {"provider": provider, "model": model, "allow_external": provider == "nvidia"}
            token = selected_model.set(selection)
            try:
                await gateway.ainvoke([])
            finally:
                selected_model.reset(token)
        await asyncio.gather(run("local", "qwen2.5-coder:1.5b-instruct"), run("nvidia", "meta/llama-3.1-8b-instruct"))
        self.clients["qwen2.5-coder:1.5b-instruct"].ainvoke.assert_awaited_once()
        self.clients["meta/llama-3.1-8b-instruct"].ainvoke.assert_awaited_once()
        self.assertIsNone(selected_model.get())

    async def test_failure_is_sanitized_and_not_retried(self):
        gateway = self.gateway()
        client = self.clients["qwen2.5-coder:7b"]
        client.ainvoke.side_effect = RuntimeError("fixture-secret")
        with self.assertRaises(LLMUnavailable) as error:
            await gateway.ainvoke([])
        self.assertNotIn("fixture-secret", str(error.exception))
        client.ainvoke.assert_awaited_once()

    async def test_concurrency_is_shared_and_bounded(self):
        gateway = self.gateway({"LLM_MAX_CONCURRENCY": "1"})
        running = maximum = 0
        async def call(_):
            nonlocal running, maximum
            running += 1
            maximum = max(maximum, running)
            await asyncio.sleep(0.01)
            running -= 1
            return SimpleNamespace(content="{}")
        self.clients["qwen2.5-coder:7b"].ainvoke.side_effect = call
        await asyncio.gather(*(gateway.ainvoke([]) for _ in range(5)))
        self.assertEqual(maximum, 1)

    async def test_deadline_includes_time_waiting_for_slot(self):
        gateway = self.gateway({"LLM_MAX_CONCURRENCY": "1"})
        gateway.total_timeout = 0.01
        await gateway._semaphore.acquire()
        try:
            with self.assertRaisesRegex(LLMUnavailable, "queue wait"):
                await gateway.ainvoke([])
        finally:
            gateway._semaphore.release()

    async def test_truncated_json_is_not_returned_as_success(self):
        gateway = self.gateway()
        self.clients["qwen2.5-coder:7b"].ainvoke.return_value = SimpleNamespace(
            content='{"partial":', response_metadata={"finish_reason": "length"})
        with self.assertRaises(LLMUnavailable):
            await gateway.ainvoke([])


if __name__ == "__main__":
    unittest.main()
