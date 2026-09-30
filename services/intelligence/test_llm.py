"""Provider routing and latency guarantees; all model calls are fixtures."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from llm import LLMUnavailable, ModelGateway, provider_config, selected_model, validate_selection
from providers import PROVIDERS


class RateLimited(Exception):
    status_code = 429


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def test_all_hosted_providers_require_their_own_key_and_consent(self):
        for name, spec in PROVIDERS.items():
            if name == "local":
                continue
            with self.subTest(provider=name):
                with self.assertRaisesRegex(ValueError, spec.key_env):
                    provider_config(name, {})
                env = {spec.key_env: "fixture-secret"}
                config = provider_config(name, env)
                self.assertEqual(config.base_url, spec.base_url)
                self.assertNotIn("fixture-secret", repr(config))
                with self.assertRaisesRegex(ValueError, "Approve sending"):
                    validate_selection({"provider": name, "model": "model"}, env)
                self.assertTrue(validate_selection({"provider": name, "model": "model", "allow_external": True}, env)["allow_external"])

    async def test_all_hosted_clients_receive_selected_model_and_provider_key(self):
        for name, spec in PROVIDERS.items():
            if name == "local":
                continue
            gateway = self.gateway({spec.key_env: "fixture-secret"})
            token = selected_model.set({"provider": name, "model": "selected/model", "allow_external": True})
            try:
                await gateway.ainvoke([])
            finally:
                selected_model.reset(token)
            self.assertEqual(self.options[-1]["base_url"], spec.base_url)
            self.assertEqual(self.options[-1]["api_key"], "fixture-secret")
            self.assertEqual(self.options[-1]["model"], "selected/model")
            self.clients["qwen2.5-coder:7b"].ainvoke.assert_not_called()

    def test_key_rotation_rebuilds_client_and_revocation_blocks_cached_client(self):
        gateway = self.gateway({"GROQ_API_KEY": "first"})
        choice = {"provider": "groq", "model": "fixture-chat", "allow_external": True}
        _, first = gateway._selection_client(choice)
        gateway.env["GROQ_API_KEY"] = "second"
        _, second = gateway._selection_client(choice)
        self.assertIsNot(first, second)
        self.assertEqual(self.options[-1]["api_key"], "second")
        gateway.env["GROQ_API_KEY"] = ""
        with self.assertRaisesRegex(ValueError, "GROQ_API_KEY"):
            gateway._selection_client(choice)

    def test_glm_requests_documented_json_output_with_thinking_disabled(self):
        gateway = self.gateway({"GLM_API_KEY": "fixture-secret"})
        gateway._selection_client({"provider": "glm", "model": "glm-4.5-flash", "allow_external": True})
        self.clients["glm-4.5-flash"].bind.assert_called_once_with(response_format={"type": "json_object"})
        self.assertEqual(self.options[-1]["extra_body"], {"thinking": {"type": "disabled"}})

    def test_groq_oss_uses_bounded_reasoning(self):
        gateway = self.gateway({"GROQ_API_KEY": "fixture-secret"})
        gateway._selection_client({"provider": "groq", "model": "openai/gpt-oss-120b", "allow_external": True})
        self.assertEqual(self.options[-1]["reasoning_effort"], "low")

    async def test_missing_default_key_does_not_disable_other_configured_providers(self):
        gateway = self.gateway({"LLM_PROVIDER": "glm", "GROQ_API_KEY": "fixture-secret"})
        self.assertIsNone(gateway.status()["provider"])
        with self.assertRaises(LLMUnavailable):
            await gateway.ainvoke([])
        token = selected_model.set({"provider": "groq", "model": "fixture-chat", "allow_external": True})
        try:
            await gateway.ainvoke([])
        finally:
            selected_model.reset(token)
        self.clients["fixture-chat"].ainvoke.assert_awaited_once()

    def gateway(self, env=None):
        self.clients = {}
        self.options = []
        def factory(**kwargs):
            client = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content='{"ok": true}')))
            client.bind = Mock(return_value=client)
            self.clients[kwargs["model"]] = client
            self.options.append(kwargs)
            return client
        return ModelGateway({"LLM_PROVIDER": "local", **(env or {})}, client_factory=factory, local_client_factory=factory)

    async def test_local_default_and_no_sdk_retries(self):
        gateway = self.gateway()
        await gateway.ainvoke([])
        self.assertEqual(gateway.status()["provider"], "local")
        self.assertEqual(self.options[0]["max_tokens"], 1024)
        self.assertEqual(self.options[0]["num_ctx"], 8192)
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
        with self.assertRaisesRegex(LLMUnavailable, "truncated"):
            await gateway.ainvoke([])

    async def test_local_timeout_is_not_reported_as_rate_limit(self):
        gateway = self.gateway()
        self.clients["qwen2.5-coder:7b"].ainvoke.side_effect = TimeoutError()
        with self.assertRaisesRegex(LLMUnavailable, "inference timed out") as result:
            await gateway.ainvoke([])
        self.assertNotIn("rate", str(result.exception))

    async def test_local_schema_is_forwarded_without_changing_selected_model(self):
        gateway = self.gateway()
        schema = {"type": "object", "properties": {"records": {"type": "array"}}}
        await gateway.ainvoke([], response_schema=schema)
        self.clients["qwen2.5-coder:7b"].ainvoke.assert_awaited_once_with([], response_schema=schema)

    async def test_quota_cooldown_keeps_actual_reason_without_provider_body(self):
        gateway = self.gateway()
        self.clients["qwen2.5-coder:7b"].ainvoke.side_effect = RateLimited("secret-body")
        for _ in range(2):
            with self.assertRaisesRegex(LLMUnavailable, "HTTP 429") as result:
                await gateway.ainvoke([])
            self.assertNotIn("secret-body", str(result.exception))
        self.assertEqual(self.clients["qwen2.5-coder:7b"].ainvoke.await_count, 1)

    async def test_short_provider_retry_after_is_honored_once(self):
        gateway = self.gateway()
        failure = RateLimited("secret")
        failure.response = SimpleNamespace(headers={"retry-after": "0.01"})
        client = self.clients["qwen2.5-coder:7b"]
        client.ainvoke.side_effect = [failure, SimpleNamespace(content='{}')]
        self.assertEqual((await gateway.ainvoke([])).content, '{}')
        self.assertEqual(client.ainvoke.await_count, 2)


if __name__ == "__main__":
    unittest.main()
