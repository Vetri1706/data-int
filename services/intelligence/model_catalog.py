"""Metadata-only discovery, configuration gates and evidence-based cost labels."""
import asyncio
from decimal import Decimal, InvalidOperation
import os
import re
import time

try:
    from asyncio import timeout as async_timeout
except ImportError:
    from async_timeout import timeout as async_timeout

import httpx
from llm import provider_config
from providers import (PROVIDERS, GLM_FREE_MODELS, GLM_PAID_MODELS,
                       GROQ_FREE_TIER, GEMINI_FREE_TIER, model_sort_key)


def unavailable_reason(provider, model, row):
    details = row.get("details") or {}
    if provider == "local" and (
        row.get("remote_host") or row.get("remote_model")
        or model.endswith(":cloud") or details.get("format") == "remote"
    ):
        return "Cloud-relayed Ollama models are not supported by local-only processing."
    if row.get("active") is False:
        return "Provider marks this model inactive."
    capabilities = row.get("capabilities")
    if isinstance(capabilities, list) and capabilities and not {"completion", "chat"}.intersection(capabilities):
        return "Not a text-generation model."
    architecture = row.get("architecture") or {}
    for field in ("input_modalities", "output_modalities"):
        modes = row.get(field, architecture.get(field))
        if isinstance(modes, list) and "text" not in modes:
            return "This workflow requires text input and text output."
    if provider == "gemini" and "generateContent" not in row.get("supportedGenerationMethods", []):
        return "Not a chat-generation model."
    if re.search(r"(?:^|[/_-])(?:embed(?:dings?|qa)?|rerank)(?:[/_-]|\d|$)", model.lower()):
        return "Embedding or reranking model; cannot run a collection."
    if re.search(r"(?:whisper|orpheus|prompt-guard|safeguard|llama-guard|flux|stable-diffusion|cogview|cogvideo|imagen|veo|tts|native-audio|image-generation|flash-image)", model.lower()):
        return "Specialized image, audio or safety model; cannot run this collection workflow."
    return None


def amount(value):
    try:
        value = Decimal(str(value))
        return value if value.is_finite() and value >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def zero_pricing(pricing, fields):
    return isinstance(pricing, dict) and all(amount(pricing.get(field)) == 0 for field in fields)


def model_cost(provider, model, row):
    spec = PROVIDERS[provider]
    kind, label, note = "unknown", "Pricing unknown", "Check provider pricing; account billing and quota are not verified by model discovery."
    if provider == "local":
        kind, label, note = "local", "Local / no API fee", "Runs on your hardware; compute and electricity costs still apply."
    elif provider == "glm" and model in GLM_FREE_MODELS:
        kind, label, note = "free", "Free", "Listed as free in Z.ai pricing. Provider rate limits still apply."
    elif provider == "glm" and model in GLM_PAID_MODELS:
        kind, label, note = "paid", "Paid", "Token charges apply; see Z.ai pricing."
    elif (provider == "groq" and model in GROQ_FREE_TIER) or (provider == "gemini" and model in GEMINI_FREE_TIER):
        kind, label, note = "free_tier", "Free tier available", "Limited free-tier quota exists. A billed account may incur charges; this app does not verify your account tier or remaining quota."
    elif provider == "openrouter":
        pricing = row.get("pricing") or {}
        fields = ("prompt", "completion", *[k for k in pricing if k not in {"prompt", "completion"}])
        if zero_pricing(pricing, fields):
            kind, label, note = "free", "Free", "Zero prices in the live OpenRouter catalog. Free-model rate limits still apply."
        elif any((amount(v) or 0) > 0 for v in pricing.values()):
            kind, label, note = "paid", "Paid", "Nonzero prices in the live OpenRouter catalog."
    elif provider == "huggingface":
        # Pin each route: one free destination does not make automatic routing free.
        if row.get("is_free") is True or ("is_free" not in row and zero_pricing(row.get("pricing"), ("input", "output"))):
            kind, label, note = "free", "Free", "This pinned route is free in the live Hugging Face catalog. Promotional pricing can change."
        else:
            kind, label, note = "credits", "Credits / paid", "Hugging Face monthly credits may cover usage; additional usage is billed. Remaining credits are not checked."
    return {"kind": kind, "label": label, "note": note, "source_url": spec.pricing_url}


def normalize_rows(provider, rows):
    if not isinstance(rows, list):
        raise ValueError("Invalid catalog")
    models = {}
    for original in rows:
        if not isinstance(original, dict):
            continue
        model_id = (original.get("name") or original.get("model")) if provider in {"local", "gemini"} else original.get("id")
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 256 or any(ord(c) < 32 for c in model_id):
            continue
        if provider == "gemini":
            model_id = model_id.removeprefix("models/")
        variants = [(model_id, original)]
        if provider == "huggingface":
            variants = []
            for route in original.get("providers", []):
                route_id = route.get("provider")
                if route.get("status") == "live" and isinstance(route_id, str) and re.fullmatch(r"[a-z0-9-]+", route_id):
                    variants.append((f"{model_id}:{route_id}", {**original, **route}))
        for model, row in variants:
            reason = unavailable_reason(provider, model, row)
            context = row.get("context_length") or row.get("context_window") or row.get("inputTokenLimit") or (row.get("details") or {}).get("context_length")
            if not isinstance(context, int) or isinstance(context, bool) or context <= 0:
                context = None
            # Only these public fields leave the intelligence service.
            models[model] = {"id": model, "label": model, "available": reason is None, "reason": reason,
                             "context_length": context, "cost": model_cost(provider, model, row),
                             "catalog_source": row.get("_catalog_source", "live")}
    return sorted(models.values(), key=model_sort_key)


class ProviderCatalog:
    def __init__(self, env=None, client_factory=httpx.AsyncClient):
        self.env = os.environ if env is None else env
        self.client_factory = client_factory
        self._cache = {}
        self._locks = {name: asyncio.Lock() for name in PROVIDERS}

    async def _rows(self, name, config, client):
        headers = {"Authorization": f"Bearer {config.api_key}"} if name != "local" else {}
        if name == "local":
            response = await client.get(config.base_url.removesuffix("/v1") + "/api/tags")
            response.raise_for_status()
            return response.json()["models"]
        url = config.base_url + "/models"
        if name == "gemini":
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            headers = {"x-goog-api-key": config.api_key}
        rows, params, cursors = [], {}, set()
        for _ in range(100):
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            page = data["models" if name == "gemini" else "data"]
            if not isinstance(page, list):
                raise ValueError("Invalid catalog")
            rows.extend(page)
            if name == "gemini":
                cursor = data.get("nextPageToken")
                more = bool(cursor)
            else:
                more = bool(data.get("has_more"))
                cursor = data.get("last_id") or (page[-1].get("id") if page else None)
            if not more:
                break
            if not isinstance(cursor, str) or not cursor or cursor in cursors:
                raise ValueError("Invalid catalog pagination")
            cursors.add(cursor)
            params = {"pageToken" if name == "gemini" else "after": cursor}
        else:
            raise ValueError("Incomplete catalog")
        if name == "glm":
            existing = {row.get("id") for row in rows if isinstance(row, dict)}
            rows.extend({"id": model, "_catalog_source": "documented"} for model in GLM_FREE_MODELS if model not in existing)
        return rows

    async def get(self, name, *, refresh=False):
        if name not in self._locks:
            raise ValueError("Unknown model provider")
        spec = PROVIDERS[name]
        result = {"id": name, "label": spec.label, "available": False, "configured": False,
                  "external": name != "local", "reason": None, "models": []}
        # Configuration gate precedes cache lookup: revocation applies immediately.
        try:
            config = provider_config(name, self.env)
        except ValueError as exc:
            self._cache.pop(name, None)
            result["reason"] = str(exc)
            return result
        result["configured"] = True
        requested_at = time.monotonic()
        previous_cache = self._cache.get(name)
        async with self._locks[name]:
            cached = self._cache.get(name)
            if cached and cached[2] == config and ((not refresh and requested_at - cached[0] < 60) or cached is not previous_cache):
                return cached[1]
            try:
                async with async_timeout(8):
                    async with self.client_factory(timeout=6, follow_redirects=False) as client:
                        rows = await self._rows(name, config, client)
                result["models"] = normalize_rows(name, rows)
                if name == "local":
                    disabled = {m.strip() for m in self.env.get("LOCAL_LLM_DISABLED_MODELS", "").split(",") if m.strip()}
                    for model in result["models"]:
                        if model["id"] in disabled:
                            model.update(available=False, reason="Disabled for collections in server configuration after failing structured-output checks. Choose another installed model.")
                result["available"] = any(model["available"] for model in result["models"])
                usable = [m for m in result["models"] if m["available"]]
                preferred = next((m for m in usable if m["id"] == config.model), None)
                result["default_model"] = (preferred or (usable[0] if usable else {})).get("id")
                if not result["available"]:
                    result["reason"] = ("No Ollama models installed. Pull a model, then refresh." if name == "local" and not rows else
                                        "No text-generation models are available for this workflow.")
            except httpx.HTTPStatusError as exc:
                result["reason"] = f"{spec.label} catalog returned HTTP {exc.response.status_code}. Check credentials and provider access, then refresh."
            except (httpx.HTTPError, TimeoutError):
                result["reason"] = ("Cannot reach Ollama. Start Ollama, then refresh models." if name == "local" else
                                    f"Cannot reach {spec.label}'s model catalog. Retry shortly.")
            except (ValueError, KeyError, TypeError, AttributeError):
                result["reason"] = "Could not read the provider's model catalog. Check its configuration, then refresh."
                result["models"] = []
            self._cache[name] = (time.monotonic(), result, config)
            return result

    async def list(self, *, refresh=False):
        providers = await asyncio.gather(*(self.get(name, refresh=refresh) for name in PROVIDERS))
        available = [p for p in providers if p["available"]]
        preferred = self.env.get("LLM_PROVIDER", "local")
        provider = next((p for p in available if p["id"] == preferred), None)
        if provider is None:
            provider = min(available, key=lambda p: model_sort_key(next(m for m in p["models"] if m["available"])), default=None)
        default = None
        if provider:
            # A default never constitutes permission to send collection inputs.
            default = {"provider": provider["id"], "model": provider["default_model"], "allow_external": False}
        return {"default": default, "providers": providers}

    async def validate(self, selection):
        provider = await self.get(selection["provider"])
        if not provider["available"]:
            raise ValueError(provider["reason"])
        model = next((model for model in provider["models"] if model["id"] == selection["model"]), None)
        if model is None:
            raise ValueError("This model is no longer in the provider catalog. Refresh models and choose again.")
        if not model["available"]:
            raise ValueError(model["reason"])


provider_catalog = ProviderCatalog()
