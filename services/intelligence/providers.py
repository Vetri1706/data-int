"""Server-owned provider registry. Credentials never form part of public metadata."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    label: str
    key_env: str
    base_url: str
    model_env: str
    default_model: str
    pricing_url: str


PROVIDERS = {
    "glm": ProviderSpec("GLM (Z.ai)", "GLM_API_KEY", "https://api.z.ai/api/paas/v4", "GLM_MODEL", "glm-4.5-flash", "https://docs.z.ai/guides/overview/pricing"),
    "groq": ProviderSpec("Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", "GROQ_MODEL", "openai/gpt-oss-20b", "https://console.groq.com/docs/rate-limits"),
    "nvidia": ProviderSpec("NVIDIA", "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1", "NVIDIA_MODEL", "meta/llama-3.3-70b-instruct", "https://build.nvidia.com"),
    "local": ProviderSpec("Local Ollama", "", "http://127.0.0.1:11434/v1", "LOCAL_LLM_MODEL", "qwen2.5-coder:7b", "https://docs.ollama.com/api/openai-compatibility"),
    "gemini": ProviderSpec("Gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_MODEL", "gemini-2.5-flash", "https://ai.google.dev/gemini-api/docs/pricing"),
    "openrouter": ProviderSpec("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "OPENROUTER_MODEL", "openrouter/free", "https://openrouter.ai/models?max_price=0"),
    "huggingface": ProviderSpec("Hugging Face", "HUGGINGFACE_API_KEY", "https://router.huggingface.co/v1", "HUGGINGFACE_MODEL", "openai/gpt-oss-20b", "https://huggingface.co/docs/inference-providers/en/pricing"),
}

# Z.ai's live /models omits these documented, working free models.
# Pricing reviewed 2026-09-30 against the official pages linked above.
GLM_FREE_MODELS = ("glm-4.5-flash", "glm-4.7-flash")
GLM_PAID_MODELS = {"glm-5.3-flash", "glm-5.3-flashx", "glm-5.3", "glm-5.2", "glm-5.1", "glm-5", "glm-4.7", "glm-4.7-flashx", "glm-4.6", "glm-4.5", "glm-4.5-x", "glm-4.5-air", "glm-4.5-airx", "glm-4-32b-0414-128k"}
# Only exact IDs with documented free tiers receive that label. Unknown/new
# model IDs remain unclassified until pricing is verified; never infer by name.
GROQ_FREE_TIER = {"openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"}
GEMINI_FREE_TIER = {"gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash"}
COST_ORDER = {"free": 0, "local": 0, "free_tier": 1, "credits": 2, "paid": 3, "unknown": 4}


def model_sort_key(model):
    return (COST_ORDER.get(model.get("cost", {}).get("kind"), 4), not model["available"], model["id"].casefold())
