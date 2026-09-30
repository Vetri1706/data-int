"""Shared, bounded model gateway. Hosted processing requires explicit consent."""
import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlparse

try:
    from asyncio import timeout as async_timeout
except ImportError:
    from async_timeout import timeout as async_timeout

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import httpx
from ollama_client import OllamaClient
from providers import PROVIDERS

ROOT = Path(__file__).resolve().parents[2]
# Process variables win; .env is the primary server configuration.
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.llm.local")
logger = logging.getLogger("datavault.llm")
selected_model = ContextVar("selected_model", default=None)


def validate_selection(value=None, env=None):
    env = os.environ if env is None else env
    value = {} if value is None else value
    if not isinstance(value, dict):
        raise ValueError("Choose a provider and model")
    provider = value.get("provider", "local")
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise ValueError("Choose a supported model provider")
    spec = PROVIDERS[provider]
    model = value.get("model") or env.get(spec.model_env, spec.default_model)
    if not isinstance(model, str) or not model.strip() or len(model) > 256 or any(ord(c) < 32 for c in model):
        raise ValueError("Choose a valid model ID")
    if provider != "local" and value.get("allow_external") is not True:
        raise ValueError(f"Approve sending this collection's inputs to {spec.label} before running")
    provider_config(provider, env)
    return {"provider": provider, "model": model.strip(), "allow_external": provider != "local"}


class LLMUnavailable(RuntimeError):
    """Safe user-visible error without credentials or provider response bodies."""


def failure_message(provider, exc):
    label = f"{PROVIDERS[provider.name].label} ({provider.model})"
    status = getattr(exc, "status_code", None)
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)) or type(exc).__name__ == "APITimeoutError":
        hint = " Try an installed instruction model or increase the local inference timeout." if provider.name == "local" else " Retry when the provider responds faster."
        return f"{label}: inference timed out.{hint}"
    if status == 429:
        return f"{label}: HTTP 429, request or token quota exceeded. Wait for the provider limit to reset or choose another model."
    if status in (401, 403):
        return f"{label}: access rejected (HTTP {status}). Check this provider's API key and model access."
    if status == 503 and provider.name == "local":
        return f"{label}: Ollama is overloaded (HTTP 503). Wait for other local requests to finish."
    if status == 404:
        return f"{label}: model or endpoint not found (HTTP 404). Refresh the model list."
    if isinstance(exc, LLMUnavailable):
        return f"{label}: {exc}"
    return f"{label}: model request failed" + (f" (HTTP {status})." if isinstance(status, int) else ". Check the provider connection and server logs.")


@dataclass(frozen=True)
class Provider:
    name: str
    model: str
    base_url: str
    api_key: str = field(repr=False)


def provider_config(name, env):
    if name not in PROVIDERS:
        raise ValueError("Unknown model provider")
    spec = PROVIDERS[name]
    if name == "local":
        base = env.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
        url = urlparse(base)
        allowed_hosts = {"localhost", "127.0.0.1", "::1"}
        # Opt-in for Docker Desktop's host bridge; never allow arbitrary hosted URLs.
        if env.get("LOCAL_LLM_ALLOW_DOCKER_HOST") == "1":
            allowed_hosts.add("host.docker.internal")
        if url.scheme not in {"http", "https"} or url.hostname not in allowed_hosts or url.username or url.password or url.query or url.fragment:
            raise ValueError("LOCAL_LLM_BASE_URL must point to loopback or an explicitly enabled Docker host bridge")
        return Provider(name, env.get("LOCAL_LLM_MODEL", "qwen2.5-coder:7b"), base, "local-no-key")
    key = env.get(spec.key_env, "").strip()
    if not key:
        raise ValueError(f"Add {spec.key_env} to the server's .env and restart intelligence.")
    return Provider(name, env.get(spec.model_env, spec.default_model), spec.base_url, key)


class ModelGateway:
    def __init__(self, env=None, client_factory=ChatOpenAI, local_client_factory=OllamaClient):
        env = os.environ if env is None else env
        self.env = env
        self.client_factory = client_factory
        self.local_client_factory = local_client_factory
        primary = env.get("LLM_PROVIDER", "local").lower()
        fallback = env.get("LLM_FALLBACK_PROVIDER", "").lower()
        names = [primary] + ([fallback] if fallback and fallback != primary else [])
        self.providers = []
        for name in names:
            if name not in PROVIDERS:
                raise ValueError("Unknown configured LLM provider")
            try:
                self.providers.append(provider_config(name, env))
            except ValueError:
                # Removing the preferred provider's key must not take down the
                # catalog or prevent choosing a different configured provider.
                logger.warning("LLM provider=%s is not configured", name)
        self.concurrency = max(1, min(4, int(env.get("LLM_MAX_CONCURRENCY", "2"))))
        self.timeout = max(1.0, float(env.get("LLM_TIMEOUT_SECONDS", "30")))
        self.total_timeout = max(self.timeout, float(env.get("LLM_TOTAL_TIMEOUT_SECONDS", "55")))
        self.max_tokens = max(256, min(4096, int(env.get("LLM_MAX_TOKENS", "4096"))))
        self.local_max_tokens = max(256, min(self.max_tokens, int(env.get("LOCAL_LLM_MAX_TOKENS", "1024"))))
        self.local_num_ctx = max(2048, min(32768, int(env.get("LOCAL_LLM_NUM_CTX", "8192"))))
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._cooldown = {}
        self._clients = {
            p.name: self._local_client(p)
            for p in self.providers if p.name == "local"
        }

    def _local_client(self, provider):
        return self.local_client_factory(model=provider.model, base_url=provider.base_url,
                                         timeout=self.timeout, max_tokens=self.local_max_tokens,
                                         num_ctx=self.local_num_ctx)

    def _selection_client(self, selection):
        config = validate_selection(selection, self.env)
        base = provider_config(config["provider"], self.env)
        provider = Provider(base.name, config["model"], base.base_url, base.api_key)
        # A rotated credential or changed local URL must not reuse an old client.
        key = (provider.name, provider.model, provider.base_url, provider.api_key)
        if provider.name == "local":
            if key not in self._clients:
                self._clients[key] = self._local_client(provider)
            return provider, self._clients[key]
        if key not in self._clients:
            options = {"extra_body": {"thinking": {"type": "disabled"}}} if provider.name == "glm" else {}
            if provider.name == "groq" and provider.model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
                options["reasoning_effort"] = "low"
            client = self.client_factory(
                model=provider.model, api_key=provider.api_key, base_url=provider.base_url,
                temperature=0.1, max_tokens=self.max_tokens, timeout=self.timeout, max_retries=0,
                **options,
            )
            # GLM supports JSON mode. Other catalogs span models with
            # different capabilities, so do not force it on every hosted model.
            self._clients[key] = client.bind(response_format={"type": "json_object"}) if provider.name == "glm" else client
        return provider, self._clients[key]

    def status(self):
        return {"provider": self.providers[0].name if self.providers else None,
                "model": self.providers[0].model if self.providers else None,
                "fallback": self.providers[1].name if len(self.providers) > 1 else None,
                "max_concurrency": self.concurrency, "request_timeout_seconds": self.timeout,
                "total_timeout_seconds": self.total_timeout}

    async def _invoke(self, client, messages, options):
        # Retry only a short, explicit provider Retry-After. The caller's total
        # deadline still covers this wait; quota exhaustion never switches models.
        for attempt in range(2):
            try:
                async with async_timeout(self.timeout):
                    return await client.ainvoke(messages, **options)
            except Exception as exc:
                headers = getattr(getattr(exc, "response", None), "headers", {})
                try:
                    delay = float(headers.get("retry-after", "nan"))
                except (ValueError, TypeError):
                    delay = float("nan")
                if attempt == 0 and getattr(exc, "status_code", None) == 429 and 0 <= delay <= 15:
                    logger.info("Provider requested a %.2fs quota wait; retrying once", delay)
                    await asyncio.sleep(delay)
                    continue
                raise

    async def ainvoke(self, messages, *, response_schema=None):
        selection = selected_model.get()
        if selection is not None:
            provider, client = self._selection_client(selection)
            attempts = [(provider, client)]
        else:
            # Only test fixtures / server-selected local defaults use this path.
            # Never escalate local work to an external provider without consent.
            attempts = [(p, self._clients[p.name]) for p in self.providers if p.name == "local"]
        if not attempts:
            raise LLMUnavailable("Choose a model and approve external processing before running")
        try:
            # Deadline includes queueing and fallback, not just network time.
            async with async_timeout(self.total_timeout):
                async with self._semaphore:
                    for provider, client in attempts:
                        cooldown_until, cooldown_reason = self._cooldown.get(provider.name, (0, ""))
                        if cooldown_until > time.monotonic():
                            raise LLMUnavailable(cooldown_reason)
                        started = time.monotonic()
                        try:
                            options = {"response_schema": response_schema} if provider.name == "local" and response_schema else {}
                            response = await self._invoke(client, messages, options)
                            if getattr(response, "response_metadata", {}).get("finish_reason") == "length":
                                raise LLMUnavailable("output was truncated at the token limit; choose an instruction model or increase the output budget.")
                            if not isinstance(response.content, str) or not response.content.strip():
                                raise LLMUnavailable("returned empty output; this model did not produce a usable structured response.")
                            logger.info("LLM provider=%s model=%s elapsed=%.2fs input_tokens=%s output_tokens=%s", provider.name,
                                        provider.model, time.monotonic() - started,
                                        getattr(response, "response_metadata", {}).get("input_tokens"),
                                        getattr(response, "response_metadata", {}).get("output_tokens"))
                            return response
                        except Exception as exc:
                            status = getattr(exc, "status_code", None)
                            reason = failure_message(provider, exc)
                            if status == 429 or (isinstance(status, int) and status >= 500):
                                self._cooldown[provider.name] = (time.monotonic() + 30, reason)
                            logger.warning("LLM provider=%s failure=%s status=%s", provider.name,
                                           type(exc).__name__, status)
                            raise LLMUnavailable(reason) from None
        except (TimeoutError, asyncio.TimeoutError):
            raise LLMUnavailable("Model request timed out, including queue wait. Please retry.") from None
