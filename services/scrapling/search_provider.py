"""Bounded metadata discovery using deedy5/ddgs; never fetch result pages."""
import asyncio
import ipaddress
import time
from urllib.parse import urlsplit
from ddgs import DDGS

_slots = asyncio.Semaphore(3)
_cache = {}
ENGINES = ("duckduckgo", "yahoo")


def allowed_url(url, domains):
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower().rstrip(".")
        if p.scheme not in {"http", "https"} or p.username or "." not in host or host.endswith((".local", ".localhost")):
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
        return not domains or any(host == d or host.endswith("." + d) for d in domains)
    except ValueError:
        return False


def _search(query, domains, limit):
    key = (query, tuple(domains), limit)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < 180:
        return cached[1]
    # Long OR-site expressions frequently return no engine results. With a large
    # scope search normally, then enforce every allowed domain on the returned URLs.
    scoped = query + (" (" + " OR ".join("site:" + d for d in domains) + ")" if 0 < len(domains) <= 3 else "")
    failures = []
    for engine in ENGINES:
        try:
            rows = DDGS(timeout=6).text(scoped, backend=engine, max_results=limit, region="wt-wt")
            results, seen = [], set()
            for row in rows:
                url = str(row.get("href") or row.get("url") or "")
                if not allowed_url(url, domains) or url in seen:
                    continue
                seen.add(url)
                results.append({"url": url, "title": str(row.get("title") or ""),
                                "snippet": str(row.get("body") or ""), "provider": "ddgs/" + engine,
                                "rank": len(results) + 1, "original_url": None,
                                "root_fallback": False, "redirected": False})
            if results:
                response = {"results": results, "failures": failures}
                if len(_cache) > 100:
                    _cache.clear()
                _cache[key] = (time.monotonic(), response)
                return response
            failures.append({"engine": engine, "reason": "no_results_in_scope"})
        except Exception as exc:
            # No CAPTCHA/proxy escalation and no upstream response bodies in logs.
            failures.append({"engine": engine, "reason": type(exc).__name__})
    return {"results": [], "failures": failures}


async def search(query, domains, limit):
    async with _slots:
        return await asyncio.wait_for(asyncio.to_thread(_search, query, domains, min(limit, 20)), timeout=15)
