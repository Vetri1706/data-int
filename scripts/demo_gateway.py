"""Restricted temporary gateway for Vercel -> local Rust API demo traffic.

Bind to loopback and expose only this process via a tunnel. Never tunnel the
Rust server directly: its internal callbacks must remain private.
"""
import hmac
import os
import re
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

ALLOWED_ROOTS = {'auth', 'collections', 'datasets', 'sources', 'runs', 'workspaces', 'me', 'health'}
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.api_route('/v1/{path:path}', methods=['GET', 'POST', 'PATCH', 'DELETE'])
async def proxy(path: str, request: Request):
    secret = os.environ.get('DATAVAULT_GATEWAY_KEY', '')
    supplied = request.headers.get('x-datavault-gateway-key', '')
    if len(secret) < 32 or not hmac.compare_digest(secret.encode(), supplied.encode()):
        return JSONResponse({'error': 'Gateway authentication required.'}, status_code=401)
    parts = path.split('/')
    if parts[0] not in ALLOWED_ROOTS or any(not re.fullmatch(r'[a-zA-Z0-9_-]+', p) for p in parts):
        return JSONResponse({'error': 'Not found.'}, status_code=404)
    if parts[-1] == 'events':
        return JSONResponse({'error': 'This temporary demo uses run polling instead of streaming.'}, status_code=501)
    base = os.environ.get('RUST_API_BASE', 'http://127.0.0.1:3000/v1').rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.username or parsed.password:
        return JSONResponse({'error': 'Gateway backend is not configured.'}, status_code=503)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1_000_000:
            return JSONResponse({'error': 'Request is too large.'}, status_code=413)
    headers = {k: request.headers[k] for k in ('authorization', 'content-type') if k in request.headers}
    query = ('?' + request.url.query) if request.url.query else ''
    try:
        async with httpx.AsyncClient(timeout=58, follow_redirects=False) as client:
            upstream = await client.request(request.method, base + '/' + path + query, headers=headers, content=bytes(body))
        result_headers = {k: upstream.headers[k] for k in ('content-type', 'content-disposition') if k in upstream.headers}
        result_headers['cache-control'] = 'no-store'
        return Response(upstream.content, status_code=upstream.status_code, headers=result_headers)
    except httpx.HTTPError:
        return JSONResponse({'error': 'The local demo backend is unavailable.'}, status_code=503)
