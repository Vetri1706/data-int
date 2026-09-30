"""Shared, bounded local Ollama / opt-in NVIDIA gateway. No implicit Groq fallback."""
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

ROOT = Path(__file__).resolve().parents[2]
# Process variables win; private local overrides win over legacy .env.
load_dotenv(ROOT / ".env.llm.local")
load_dotenv(ROOT / ".env")
logger = logging.getLogger("datavault.llm")
selected_model = ContextVar("selected_model", default=None)


def validate_selection(value=None, env=None):
    env = os.environ if env is None else env
    value = {} if value is None else value
    if not isinstance(value, dict):
        raise ValueError("Choose a provider and model")
    provider = value.get("provider", "local")
    if provider not in {"local", "nvidia"}:
        raise ValueError("Choose Ollama or NVIDIA as the provider")
    model = value.get("model") or (env.get("LOCAL_LLM_MODEL", "qwen2.5-coder:1.5b-instruct")
                                  if provider == "local" else env.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct"))
    if not isinstance(model, str) or not model.strip() or len(model) > 256 or any(ord(c) < 32 for c in model):
        raise ValueError("Choose a valid model ID")
    if provider == "nvidia" and value.get("allow_external") is not True:
        raise ValueError("Approve sending this collection's inputs to NVIDIA before running")
    provider_config(provider, env)
    return {"provider": provider, "model": model, "allow_external": provider == "nvidia"}


class LLMUnavailable(RuntimeError):
    """Safe user-visible error without credentials or provider response bodies."""


@dataclass(frozen=True)
class Provider:
    name: str
    model: str
    base_url: str
    api_key: str = field(repr=False)


def provider_config(name, env):
    if name == "nvidia":
        key = env.get("NVIDIA_API_KEY", "").strip()
        if not key:
            raise ValueError("NVIDIA_API_KEY is required for the NVIDIA provider")
        return Provider(name, env.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct"),
                        "https://integrate.api.nvidia.com/v1", key)
    if name == "local":
        base = env.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
        url = urlparse(base)
        if url.scheme not in {"http", "https"} or url.hostname not in {"localhost", "127.0.0.1", "::1"} or url.username or url.password:
            raise ValueError("LOCAL_LLM_BASE_URL must point to a loopback OpenAI-compatible server")
        return Provider(name, env.get("LOCAL_LLM_MODEL", "qwen2.5-coder:7b"), base, "local-no-key")
    raise ValueError("LLM_PROVIDER must be nvidia or local; no implicit Groq fallback")


class ModelGateway:
    def __init__(self, env=None, client_factory=ChatOpenAI):
        env = os.environ if env is None else env
        self.env = env
        self.client_factory = client_factory
        primary = env.get("LLM_PROVIDER", "local").lower()
        fallback = env.get("LLM_FALLBACK_PROVIDER", "").lower()
        names = [primary] + ([fallback] if fallback and fallback != primary else [])
        self.providers = [provider_config(name, env) for name in names]
        self.concurrency = max(1, min(4, int(env.get("LLM_MAX_CONCURRENCY", "2"))))
        self.timeout = max(1.0, float(env.get("LLM_TIMEOUT_SECONDS", "30")))
        self.total_timeout = max(self.timeout, float(env.get("LLM_TOTAL_TIMEOUT_SECONDS", "55")))
        self.max_tokens = max(256, min(4096, int(env.get("LLM_MAX_TOKENS", "4096"))))
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._cooldown = {}
        self._clients = {
            p.name: client_factory(model=p.model, api_key=p.api_key, base_url=p.base_url,
                                   temperature=0.1, max_tokens=self.max_tokens,
                                   timeout=self.timeout, max_retries=0).bind(
                                       response_format={"type": "json_object"})
            for p in self.providers
        }

    def _selection_client(self, selection):
        config = validate_selection(selection, self.env)
        base = provider_config(config["provider"], self.env)
        provider = Provider(base.name, config["model"], base.base_url, base.api_key)
        key = (provider.name, provider.model)
        if key not in self._clients:
            client = self.client_factory(
                model=provider.model, api_key=provider.api_key, base_url=provider.base_url,
                temperature=0.1, max_tokens=self.max_tokens, timeout=self.timeout, max_retries=0,
            )
            # NVIDIA's catalog spans models with different structured-output support.
            # The workflow prompts and validates JSON without forcing an unsupported
            # response_format parameter on every hosted model.
            self._clients[key] = client.bind(response_format={"type": "json_object"}) if provider.name == "local" else client
        return provider, self._clients[key]

    def status(self):
        return {"provider": self.providers[0].name, "model": self.providers[0].model,
                "fallback": self.providers[1].name if len(self.providers) > 1 else None,
                "max_concurrency": self.concurrency, "request_timeout_seconds": self.timeout,
                "total_timeout_seconds": self.total_timeout}

    async def ainvoke(self, messages):
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
                        if self._cooldown.get(provider.name, 0) > time.monotonic():
                            continue
                        started = time.monotonic()
                        try:
                            async with async_timeout(self.timeout):
                                response = await client.ainvoke(messages)
                            if not isinstance(response.content, str) or not response.content.strip():
                                raise ValueError("empty model output")
                            if getattr(response, "response_metadata", {}).get("finish_reason") == "length":
                                raise ValueError("model output truncated by token limit")
                            logger.info("LLM provider=%s model=%s elapsed=%.2fs", provider.name,
                                        provider.model, time.monotonic() - started)
                            return response
                        except Exception as exc:
                            status = getattr(exc, "status_code", None)
                            if status == 429 or (isinstance(status, int) and status >= 500):
                                self._cooldown[provider.name] = time.monotonic() + 30
                            logger.warning("LLM provider=%s failure=%s status=%s", provider.name,
                                           type(exc).__name__, status)
                    raise LLMUnavailable("Model provider unavailable or rate-limited. Please retry shortly.")
        except (TimeoutError, asyncio.TimeoutError):
            raise LLMUnavailable("Model request timed out, including queue wait. Please retry.") from None
