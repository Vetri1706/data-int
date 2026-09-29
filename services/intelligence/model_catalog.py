"""Live provider catalogs. Metadata only: no collection inputs or inference calls."""
import asyncio
import os
import re
import time

import httpx

from llm import provider_config


def unavailable_reason(provider, model, row):
    details = row.get("details") or {}
    if provider == "local" and (
        row.get("remote_host") or row.get("remote_model")
        or model.endswith(":cloud") or details.get("format") == "remote"
    ):
        return "Cloud-relayed Ollama models are not supported by local-only processing."
    capabilities = row.get("capabilities")
    if isinstance(capabilities, list) and capabilities and not {"completion", "chat"}.intersection(capabilities):
        return "Not a text-generation model."
    if re.search(r"(?:^|[/_-])(?:embed(?:dings?|qa)?|rerank)(?:[/_-]|\d|$)", model.lower()):
        return "Embedding or reranking model; cannot run a collection."
    return None


class ProviderCatalog:
    def __init__(self, env=None, client_factory=httpx.AsyncClient):
        self.env = os.environ if env is None else env
        self.client_factory = client_factory
        self._cache = {}
        self._locks = {name: asyncio.Lock() for name in ("local", "nvidia")}

    async def get(self, name, *, refresh=False):
        if name not in self._locks:
            raise ValueError("Unknown model provider")
        requested_at = time.monotonic()
        async with self._locks[name]:
            cached = self._cache.get(name)
            if cached and ((not refresh and requested_at - cached[0] < 60) or cached[0] >= requested_at):
                return cached[1]
            result = {"id": name, "label": "Local · Ollama" if name == "local" else "NVIDIA · hosted",
                      "available": False, "reason": None, "models": []}
            try:
                config = provider_config(name, self.env)
                async with asyncio.timeout(8):
                    async with self.client_factory(timeout=6, follow_redirects=False) as client:
                        if name == "local":
                            response = await client.get(config.base_url.removesuffix("/v1") + "/api/tags")
                            response.raise_for_status()
                            rows = response.json()["models"]
                        else:
                            rows = []
                            params = {}
                            cursors = set()
                            # Current NVIDIA responses are unpaginated. Also honor
                            # OpenAI-style pagination without following arbitrary URLs.
                            for _ in range(100):
                                response = await client.get(config.base_url + "/models", params=params,
                                                            headers={"Authorization": f"Bearer {config.api_key}"})
                                response.raise_for_status()
                                data = response.json()
                                page = data["data"]
                                if not isinstance(page, list):
                                    raise ValueError("Invalid catalog")
                                rows.extend(page)
                                if not data.get("has_more"):
                                    break
                                cursor = data.get("last_id") or (page[-1].get("id") if page else None)
                                if not isinstance(cursor, str) or not cursor or cursor in cursors:
                                    raise ValueError("Invalid catalog pagination")
                                cursors.add(cursor)
                                params = {"after": cursor}
                            else:
                                raise ValueError("Incomplete catalog")
                if not isinstance(rows, list):
                    raise ValueError("Invalid catalog")
                models = {}
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    model = (row.get("name") or row.get("model")) if name == "local" else row.get("id")
                    if not isinstance(model, str) or not model.strip():
                        continue
                    reason = unavailable_reason(name, model, row)
                    # Only these public fields leave the intelligence service.
                    models[model] = {"id": model, "label": model, "available": reason is None, "reason": reason}
                result["models"] = sorted(models.values(), key=lambda model: model["id"].casefold())
                result["available"] = any(model["available"] for model in result["models"])
                if not result["available"]:
                    result["reason"] = ("No text-generation models are available for this workflow." if models else
                                        "No Ollama models installed. Pull a model, then refresh." if name == "local" else
                                        "NVIDIA returned an empty model catalog.")
            except httpx.HTTPStatusError as exc:
                result["reason"] = f"{result['label']} catalog returned HTTP {exc.response.status_code}. Check the provider configuration, then refresh."
            except (httpx.HTTPError, TimeoutError):
                result["reason"] = ("Cannot reach Ollama. Start Ollama, then refresh models." if name == "local" else
                                    "Cannot reach NVIDIA's model catalog. Retry shortly.")
            except (ValueError, KeyError, TypeError, AttributeError):
                result["reason"] = ("Add NVIDIA_API_KEY to the server's private .env.llm.local file." if name == "nvidia" and not self.env.get("NVIDIA_API_KEY", "").strip()
                                    else "Could not read the provider's model catalog. Check its configuration, then refresh.")
            self._cache[name] = (time.monotonic(), result)
            return result

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
