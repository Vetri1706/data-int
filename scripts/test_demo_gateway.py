import os
import unittest
from unittest.mock import patch
import httpx
import demo_gateway


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_proxy_keeps_user_auth_but_does_not_forward_gateway_key(self):
        factory=httpx.AsyncClient
        received=[]
        def upstream(request):
            received.append(request)
            return httpx.Response(200,json={'ok':True})
        async with factory(transport=httpx.ASGITransport(app=demo_gateway.app),base_url='http://test') as client:
            with patch.dict(os.environ,{'DATAVAULT_GATEWAY_KEY':'test-only-'*4,'RUST_API_BASE':'http://127.0.0.1:3000/v1'}), patch('demo_gateway.httpx.AsyncClient',side_effect=lambda **kwargs:factory(transport=httpx.MockTransport(upstream),**kwargs)):
                response=await client.post('/v1/collections?page=2',headers={'x-datavault-gateway-key':'test-only-'*4,'authorization':'Bearer fixture-session'},json={'prompt':'fixture'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(str(received[0].url),'http://127.0.0.1:3000/v1/collections?page=2')
        self.assertEqual(received[0].headers['authorization'],'Bearer fixture-session')
        self.assertNotIn('x-datavault-gateway-key',received[0].headers)
        self.assertEqual(received[0].content,b'{"prompt":"fixture"}')

    async def test_requires_gateway_secret_and_blocks_private_paths(self):
        with patch.dict(os.environ, {'DATAVAULT_GATEWAY_KEY': 'test-only-' * 4}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=demo_gateway.app), base_url='http://test') as client:
                self.assertEqual((await client.get('/v1/health')).status_code, 401)
                headers = {'x-datavault-gateway-key': 'test-only-' * 4}
                for path in ['/v1/internal/search', '/v1/internal/intelligence/run', '/v1/auth/%2e%2e/internal']:
                    self.assertEqual((await client.get(path, headers=headers)).status_code, 404)
                self.assertEqual((await client.get('/v1/runs/test/events', headers=headers)).status_code, 501)

    async def test_missing_or_short_server_key_fails_closed(self):
        for secret in ['', 'short']:
            with patch.dict(os.environ, {'DATAVAULT_GATEWAY_KEY': secret}):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=demo_gateway.app), base_url='http://test') as client:
                    self.assertEqual((await client.get('/v1/health', headers={'x-datavault-gateway-key': secret})).status_code, 401)
