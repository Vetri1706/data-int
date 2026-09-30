"""Local Ollama adapter with explicit context, output and thinking budgets."""
import httpx
from langchain_core.messages import AIMessage


class OllamaClient:
    def __init__(self, *, model, base_url, timeout, max_tokens, num_ctx=8192):
        self.model = model
        self.url = base_url.rstrip('/').removesuffix('/v1') + '/api/chat'
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.num_ctx = num_ctx

    async def ainvoke(self, messages, *, response_schema=None):
        roles = {'human': 'user', 'ai': 'assistant', 'system': 'system'}
        payload = {
            'model': self.model,
            'messages': [{'role': roles.get(m.type, m.type), 'content': m.content} for m in messages],
            'stream': False, 'think': False, 'keep_alive': '10m',
            'format': response_schema or 'json',
            'options': {'temperature': 0, 'num_ctx': self.num_ctx, 'num_predict': self.max_tokens},
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            response = await client.post(self.url, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Gateway uses status only; never expose Ollama's response body.
                exc.status_code = response.status_code
                raise
            data = response.json()
        return AIMessage(content=data.get('message', {}).get('content', ''), response_metadata={
            'finish_reason': data.get('done_reason'),
            'input_tokens': data.get('prompt_eval_count'),
            'output_tokens': data.get('eval_count'),
            'load_duration_ns': data.get('load_duration'),
        })
