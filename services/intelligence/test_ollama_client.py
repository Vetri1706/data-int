import json
import unittest
from unittest.mock import patch
import httpx
from langchain_core.messages import SystemMessage, HumanMessage
from ollama_client import OllamaClient


class OllamaTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_request_controls_and_usage(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'message': {'content': '{"records":[]}'},
                'done_reason': 'stop', 'prompt_eval_count': 100, 'eval_count': 8})
        factory = httpx.AsyncClient
        with patch('ollama_client.httpx.AsyncClient', side_effect=lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs)):
            client = OllamaClient(model='installed:latest', base_url='http://127.0.0.1:11434/v1', timeout=40, max_tokens=1024)
            schema = {'type': 'object'}
            result = await client.ainvoke([SystemMessage(content='Extract JSON'), HumanMessage(content='passage')], response_schema=schema)
        request = requests[0]
        self.assertEqual(str(request.url), 'http://127.0.0.1:11434/api/chat')
        self.assertNotIn('authorization', request.headers)
        body = json.loads(request.content)
        self.assertEqual(body['messages'][1], {'role': 'user', 'content': 'passage'})
        self.assertFalse(body['think'])
        self.assertFalse(body['stream'])
        self.assertEqual(body['format'], schema)
        self.assertEqual(body['options'], {'num_ctx': 8192, 'num_predict': 1024, 'temperature': 0})
        self.assertEqual(result.response_metadata['output_tokens'], 8)
        self.assertEqual(result.response_metadata['finish_reason'], 'stop')

    async def test_native_http_status_reaches_gateway_error_classifier(self):
        factory = httpx.AsyncClient
        with patch('ollama_client.httpx.AsyncClient', side_effect=lambda **kwargs: factory(transport=httpx.MockTransport(lambda _: httpx.Response(503)), **kwargs)):
            client = OllamaClient(model='installed:latest', base_url='http://127.0.0.1:11434/v1', timeout=40, max_tokens=1024)
            with self.assertRaises(httpx.HTTPStatusError) as error:
                await client.ainvoke([])
        self.assertEqual(error.exception.status_code, 503)
