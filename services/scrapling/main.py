"""Datavault's Scrapling retrieval service.

This service deliberately delegates page retrieval and parsing to the real
D4Vinci/Scrapling project.  It does not decide source relevance and it does
not verify extracted records; those responsibilities remain in the
intelligence graph and grounding pipeline.
"""

import asyncio
import hashlib
import ipaddress
import json
import logging
import re
import socket
import os
import sys
from pathlib import Path
import httpx
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_policy import permission_decision
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from scrapling.fetchers import AsyncFetcher, DynamicFetcher
from search_provider import search as search_metadata
from trafilatura import extract as extract_main_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scrapling")

SCRAPLING_PORT = 8001
MAX_BYTES = 1_000_000
MAX_CONTENT_CHARS = 50_000
CONCURRENCY_LIMIT = 8
DYNAMIC_CONCURRENCY_LIMIT = 2
REQUEST_TIMEOUT = 10.0
VERIFY_TIMEOUT = 5.0


class ExtractRequest(BaseModel):
    urls: list[HttpUrl] = Field(..., min_length=1, max_length=25)
    source_policy: dict = Field(default_factory=dict)
    run_id: Optional[str] = None
    # Kept for API compatibility. Structured data is preserved without a
    # domain-specific schema allowlist; the graph filters fields by DataContract.
    schema_types: Optional[list[str]] = None
    selector_preset: Optional[str] = None
    custom_selectors: Optional[dict[str, list[str]]] = None
    follow_redirects: bool = True
    max_redirects: int = Field(5, ge=0, le=10)
    verify_ssl: bool = True
    render_js: bool = True
    render_wait_ms: int = Field(800, ge=0, le=5_000)


class VerifyRequest(BaseModel):
    urls: list[HttpUrl] = Field(..., min_length=1, max_length=100)
    source_policy: dict = Field(default_factory=dict)
    allow_root_fallback: bool = True
    max_redirects: int = Field(4, ge=0, le=10)


class ChunkRequest(BaseModel):
    text: str
    chunk_size: int = 500
    stride: int = 100
    url: str = ""
    source_metadata: dict = {}


class ExtractResponse(BaseModel):
    results: list[dict]
    total: int
    successful: int
    failed: int


class VerifyResponse(BaseModel):
    results: list[dict]
    reachable: int
    unreachable: int


class ChunkResponse(BaseModel):
    chunks: list[dict]
    total: int


app = FastAPI(title="Scrapling Service", version="2.0.0")
ACTIVE_EXTRACTIONS: dict[str, set] = {}


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1500)
    domain_filters: list[str] = Field(default_factory=list, max_length=25)
    max_results: int = Field(default=15, ge=1, le=30)


@app.post("/search")
async def search_endpoint(request: SearchRequest):
    domains = [d.strip().lower().rstrip(".") for d in request.domain_filters]
    if any(not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}", d) for d in domains):
        raise HTTPException(status_code=422, detail="Invalid hard domain restriction")
    try:
        return await search_metadata(request.query, domains, request.max_results)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Search engine request timed out") from None


async def public_url(url: str) -> bool:
    """Reuse the service's existing public-address SSRF protection."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            return False
        loop = asyncio.get_running_loop()
        addresses = await loop.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (ValueError, OSError):
        return False


def _error_code(error: BaseException) -> str:
    message = str(error).lower()
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)) or "timeout" in message:
        return "timeout"
    if "ssl" in message or "certificate" in message:
        return "tls_error"
    if "redirect" in message:
        return "redirect_error"
    if "connection" in message or "network" in message or "dns" in message:
        return "connection_error"
    return "retrieval_error"


def _failed(url: str, error: str, code: str, status_code: Optional[int] = None) -> dict:
    result = {
        "url": url,
        "original_url": url,
        "source_url": url,
        "status": "failed",
        "success": False,
        "error": error[:500],
        "error_code": code,
    }
    if status_code is not None:
        result["http_status"] = status_code
    return result


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _element_value(element: Any) -> Any:
    """Read a Scrapling selector without assuming a page schema."""
    if hasattr(element, "attrib"):
        attributes = element.attrib
        for key in ("content", "datetime", "href", "src", "value"):
            value = attributes.get(key)
            if value:
                return _clean_text(value)
    if hasattr(element, "get_all_text"):
        value = _clean_text(element.get_all_text(separator=" ", strip=True))
        if value:
            return value
    return _clean_text(element)


def _json_ld(page: Any) -> list[dict]:
    values = []
    try:
        scripts = page.css("script[type='application/ld+json']::text").getall()
    except Exception:
        scripts = []
    for raw in scripts:
        try:
            parsed = json.loads(str(raw).strip())
        except (TypeError, json.JSONDecodeError):
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        values.extend(item for item in items if isinstance(item, dict))
    return values


def _microdata(page: Any) -> list[dict]:
    """Preserve generic microdata using Scrapling selectors."""
    results = []
    try:
        items = page.css("[itemscope][itemtype]")
    except Exception:
        return results
    for item in items:
        item_type = item.attrib.get("itemtype", "") if hasattr(item, "attrib") else ""
        props: dict[str, Any] = {}
        try:
            elements = item.css("[itemprop]")
        except Exception:
            elements = []
        for element in elements:
            name = element.attrib.get("itemprop") if hasattr(element, "attrib") else None
            value = _element_value(element)
            if not name or not value:
                continue
            if name in props:
                props[name] = props[name] if isinstance(props[name], list) else [props[name]]
                props[name].append(value)
            else:
                props[name] = value
        if props:
            props["@type"] = item_type.rsplit("/", 1)[-1] if item_type else "Thing"
            results.append(props)
    return results


def _rdfa(page: Any) -> list[dict]:
    """Preserve generic RDFa using Scrapling selectors."""
    results = []
    try:
        items = page.css("[typeof]")
    except Exception:
        return results
    for item in items:
        item_type = item.attrib.get("typeof", "") if hasattr(item, "attrib") else "Thing"
        props: dict[str, Any] = {}
        try:
            elements = item.css("[property]")
        except Exception:
            elements = []
        for element in elements:
            name = element.attrib.get("property") if hasattr(element, "attrib") else None
            value = _element_value(element)
            if not name or not value:
                continue
            if name in props:
                props[name] = props[name] if isinstance(props[name], list) else [props[name]]
                props[name].append(value)
            else:
                props[name] = value
        if props:
            props["@type"] = item_type.rsplit(":", 1)[-1]
            results.append(props)
    return results


def _selector_data(page: Any, selectors: Optional[dict[str, list[str]]]) -> dict[str, list[dict]]:
    """Apply only selectors supplied by the generated contract, if any."""
    if not selectors:
        return {}
    output: dict[str, list[dict]] = {}
    for field_name, selector_list in selectors.items():
        if not isinstance(field_name, str) or not isinstance(selector_list, list):
            continue
        for selector in selector_list:
            if not isinstance(selector, str) or not selector.strip():
                continue
            try:
                matches = page.css(selector)
            except Exception:
                continue
            values = []
            for match in matches:
                value = _element_value(match)
                if value:
                    values.append({"name": field_name, "value": value, "source": "scrapling_selector", "selector": selector})
            if values:
                output[field_name] = values
                break
    return output


def _page_title(page: Any, url: str) -> str:
    try:
        title = page.css("title::text").get()
        if title:
            return _clean_text(title)
    except Exception:
        pass
    return urlsplit(url).netloc


def _normalized_content(page: Any) -> str:
    """Scrapling fetches; Trafilatura removes menus before context selection."""
    content = None
    body = getattr(page, "body", b"")
    if body and (b"<" in body if isinstance(body, bytes) else "<" in body):
        try:
            content = extract_main_text(body, url=str(getattr(page, "url", "")),
                output_format="txt", include_formatting=True, include_links=True,
                include_tables=True, include_comments=False, favor_precision=True)
            if content:
                # Contact addresses are often in the footer, outside the article.
                # Preserve their original text; never create synthetic claims.
                for node in page.css("footer, address, [role='contentinfo']"):
                    footer = node.get_all_text(separator="\n", strip=True)
                    if footer and footer not in content:
                        content += "\n\n" + footer[:5000]
        except (ValueError, TypeError, AttributeError):
            content = None
    try:
        content = content or page.markdown(main_content_only=True)
    except Exception:
        content = page.get_all_text(separator="\n", strip=True, ignore_tags=("script", "style", "noscript", "svg", "iframe"))
    # Image alt text is not an entity assertion. Decorative Markdown dividers
    # must not consume the extraction window or become partial name evidence.
    content = re.sub(r"!\[[^\]]*\]\([^\n)]*\)", "", str(content or ""))
    content = re.sub(r"(?m)^\s*[-_=]{4,}\s*$", "", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()[:MAX_CONTENT_CHARS]


def _usable_content(content: str) -> bool:
    return len(content) >= 40 and not re.search(
        r"(?:access denied|verify you are human|captcha|page not found)", content[:250], re.I
    )


async def robots_allowed(url, policy):
    if not permission_decision(url, policy)[0] or not await public_url(url):
        return False
    p = urlsplit(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.get(robots_url, headers={"User-Agent": "Datavault/1.0"})
        if response.status_code == 404:
            return True  # explicit permission exists; the site publishes no robots rules
        if response.status_code != 200:
            return False
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser.can_fetch("Datavault", url)
    except httpx.HTTPError:
        return False


async def _fetch_static(url: str, request: ExtractRequest) -> Any:
    for _ in range(request.max_redirects + 1):
        if not permission_decision(url, request.source_policy)[0] or not await public_url(url) or not await robots_allowed(url, request.source_policy):
            raise PermissionError("Source permission or robots policy denied retrieval")
        page = await AsyncFetcher.get(url, follow_redirects=False, timeout=REQUEST_TIMEOUT,
            verify=request.verify_ssl, headers={"User-Agent": "Datavault/1.0"},
            selector_config={"keep_comments": False, "keep_cdata": False})
        if int(getattr(page, "status", 0)) not in {301,302,303,307,308}:
            return page
        headers = getattr(page,"headers",{}) or {}
        location = headers.get("location") or headers.get("Location")
        if not request.follow_redirects or not location:
            return page
        url = urljoin(url, location)
    raise PermissionError("Redirect limit exceeded")


async def _fetch_dynamic(url: str, request: ExtractRequest, stealth: bool = False) -> Any:
    if stealth:
        raise PermissionError("Anti-bot bypass is disabled")
    if not await robots_allowed(url, request.source_policy):
        raise PermissionError("Source permission or robots policy denied rendering")
    async def setup(page):
        async def guard(route):
            target = route.request.url
            scheme = urlsplit(target).scheme.lower()
            if scheme in {"about", "blob", "data"}:
                await route.continue_()
            elif permission_decision(target, request.source_policy)[0] and await public_url(target):
                if route.request.is_navigation_request() and not await robots_allowed(target, request.source_policy):
                    await route.abort()
                else:
                    await route.continue_()
            else:
                await route.abort()
        try:
            await page.route("**/*", guard)
        except Exception:
            # Scrapling catches setup errors; close the page before it can navigate.
            await page.close()
            raise
    return await DynamicFetcher.async_fetch(url, headless=True, load_dom=True, network_idle=False,
        wait=request.render_wait_ms, timeout=int(REQUEST_TIMEOUT*1000), google_search=False,
        page_setup=setup, retries=1, selector_config={"keep_comments":False,"keep_cdata":False})


def _response_result(page: Any, original_url: str, request: ExtractRequest, mode: str, root_fallback: bool = False) -> dict:
    final_url = str(getattr(page, "url", "") or original_url)
    status_code = int(getattr(page, "status", 0) or 0)
    content = _normalized_content(page)
    if len(getattr(page, "body", b"")) > MAX_BYTES:
        raise ValueError("response exceeded the maximum content size")
    if not _usable_content(content):
        raise ValueError("page returned no usable content")

    structured = _json_ld(page) + _microdata(page) + _rdfa(page)
    selectors = _selector_data(page, request.custom_selectors)
    history = getattr(page, "history", []) or []
    headers = getattr(page, "headers", {}) or {}
    content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    published_at = None
    for selector in ['meta[property="article:published_time"]::attr(content)', 'meta[name="date"]::attr(content)', 'time[datetime]::attr(datetime)']:
        try:
            published_at = page.css(selector).get()
            if published_at:
                break
        except (AttributeError, TypeError):
            continue
    logger.info("[SCRAPLING] Retrieval successful URL=%s status=%s mode=%s content_size=%d", final_url, status_code, mode, len(content))
    if structured:
        logger.info("[SCRAPLING] Structured data found URL=%s items=%d", final_url, len(structured))
    logger.info("[SCRAPLING] Normalized content generated URL=%s", final_url)
    return {
        "url": final_url,
        "original_url": original_url,
        "source_url": final_url,
        "title": _page_title(page, final_url),
        "schema_type": structured[0].get("@type") if structured else None,
        "schema_data": structured[0] if structured else {},
        "all_schemas": structured,
        "selector_data": selectors,
        "text_content": content,
        "text_hash": content_sha256,
        "content_sha256": content_sha256,
        "http_status": status_code,
        "reachability": 1.0 if status_code == 200 else 0.0,
        "redirect_count": len(history),
        "root_fallback": root_fallback,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "published_at": published_at,
        "content_type": headers.get("content-type", "text/html"),
        "rendered": mode != "static",
        "retrieval_mode": mode,
        "extraction_method": "structured_data_and_markdown" if structured else "markdown",
        "status": "success",
        "success": True,
    }


async def retrieve_page(url: str, request: ExtractRequest, allow_render: bool = True) -> dict:
    """Retrieve one page with Scrapling, escalating only when necessary."""
    logger.info("[SCRAPLING] Starting source retrieval URL=%s", url)
    if not await public_url(url):
        return _failed(url, "blocked non-public URL", "ssrf_blocked")
    if request.run_id:
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                response = await client.get(f"{os.getenv('RUST_API_BASE', 'http://127.0.0.1:3000/v1')}/internal/runs/{request.run_id}/control")
                response.raise_for_status()
                control = response.json()
            except (httpx.HTTPError, ValueError):
                return _failed(url, "Cannot confirm current source policy", "policy_unavailable")
        if control.get("status") == "cancelled":
            return _failed(url, "Run cancelled", "cancelled")
        request = request.model_copy(update={"source_policy": control.get("source_policy", {})})
    permitted, reason = permission_decision(url, request.source_policy)
    if not permitted:
        return _failed(url, reason, "permission_denied")
    if not await robots_allowed(url, request.source_policy):
        return _failed(url, "Robots policy denied or unavailable", "robots_denied")
    if not await public_url(url):
        logger.warning("[SCRAPLING] Retrieval failed URL=%s Error=blocked_non_public_url", url)
        return _failed(url, "blocked non-public URL", "ssrf_blocked")

    initial_error: Optional[BaseException] = None
    static_page = None
    static_status = 0
    try:
        static_page = await _fetch_static(url, request)
        static_status = int(getattr(static_page, "status", 0) or 0)
        final_url = str(getattr(static_page, "url", "") or url)
        if not await public_url(final_url):
            return _failed(url, "redirected to a non-public URL", "ssrf_blocked", static_status)
        static_content = _normalized_content(static_page)
        if static_status == 200 and _usable_content(static_content):
            return _response_result(static_page, url, request, "static")
        if static_status in {401,403,429} or re.search(r"captcha|verify you are human|access denied", static_content, re.I):
            return _failed(url, "Access restriction; anti-bot escalation disabled", "access_restricted", static_status)
        initial_error = RuntimeError(f"static retrieval returned HTTP {static_status} or unusable content")
        logger.info("[SCRAPLING] Static retrieval needs escalation URL=%s status=%s", url, static_status)
    except PermissionError as exc:
        return _failed(url, str(exc), "permission_denied")
    except Exception as exc:
        initial_error = exc
        logger.info("[SCRAPLING] Static retrieval failed; considering browser escalation URL=%s Error=%s", url, _error_code(exc))

    # Preserve the old root fallback behavior, but still retrieve the root via
    # Scrapling and keep its provenance explicit.
    parsed = urlsplit(url)
    root_url = f"{parsed.scheme}://{parsed.netloc}/"
    if parsed.path not in {"", "/"} and static_status == 404:
        try:
            root_page = await _fetch_static(root_url, request)
            if int(getattr(root_page, "status", 0) or 0) == 200 and await public_url(str(root_page.url)) and _usable_content(_normalized_content(root_page)):
                return _response_result(root_page, url, request, "static", root_fallback=True)
        except Exception:
            pass

    # Do not escalate binary files, documents, or PDFs to headless browser
    if parsed.path.lower().endswith((".pdf", ".doc", ".docx", ".zip", ".tar", ".gz", ".mp4", ".mp3", ".png", ".jpg", ".jpeg", ".svg")):
        allow_render = False

    if not allow_render:
        error = initial_error or RuntimeError("static retrieval failed")
        logger.warning("[SCRAPLING] Retrieval failed URL=%s Error=%s", url, _error_code(error))
        return _failed(url, str(error), _error_code(error), getattr(static_page, "status", None))

    async with DYNAMIC_SEMAPHORE:
        page = None
        try:
            page = await _fetch_dynamic(url, request)
            final_url = str(getattr(page, "url", "") or url)
            status_code = int(getattr(page, "status", 0) or 0)
            if not await public_url(final_url):
                return _failed(url, "redirected to a non-public URL", "ssrf_blocked", status_code)
            if status_code == 200:
                return _response_result(page, url, request, "dynamic")
            initial_error = RuntimeError(f"dynamic retrieval returned HTTP {status_code}")
        except Exception as exc:
            initial_error = exc

    logger.warning("[SCRAPLING] Retrieval failed URL=%s Error=%s", url, _error_code(initial_error))
    return _failed(url, str(initial_error), _error_code(initial_error), getattr(static_page, "status", None))


def chunk_text(text: str, chunk_size: int, stride: int, url: str, metadata: dict) -> list[dict]:
    if chunk_size <= 0 or stride <= 0 or stride > chunk_size:
        raise ValueError("Invalid chunk parameters")
    chunks = []
    for start in range(0, len(text), stride):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        chunk_id = hashlib.sha256(f"{url}:{metadata.get('text_hash', '')}:{start}".encode()).hexdigest()[:20]
        chunks.append({
            "chunk_id": chunk_id,
            "text": chunk,
            "char_start": start,
            "char_end": end,
            "url": url,
            **{k: v for k, v in metadata.items() if k != "text"},
        })
        if end == len(text):
            break
    return chunks


@app.get("/health")
async def health():
    return {"status": "ok", "service": "scrapling", "port": SCRAPLING_PORT}


@app.post("/extract", response_model=ExtractResponse)
async def extract_endpoint(req: ExtractRequest):
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def process_one(url: HttpUrl) -> dict:
        async with semaphore:
            try:
                return await retrieve_page(str(url), req, allow_render=req.render_js)
            except Exception as exc:
                logger.exception("[SCRAPLING] Retrieval failed URL=%s", url)
                return _failed(str(url), str(exc), _error_code(exc))

    tasks = [asyncio.create_task(process_one(url)) for url in req.urls]
    if req.run_id:
        ACTIVE_EXTRACTIONS.setdefault(req.run_id, set()).update(tasks)
    try:
        results = await asyncio.gather(*tasks)
    finally:
        if req.run_id:
            ACTIVE_EXTRACTIONS.get(req.run_id, set()).difference_update(tasks)
            if not ACTIVE_EXTRACTIONS.get(req.run_id):
                ACTIVE_EXTRACTIONS.pop(req.run_id, None)
    successful = sum(1 for result in results if result.get("success"))
    return ExtractResponse(results=results, total=len(results), successful=successful, failed=len(results) - successful)


@app.post("/verify", response_model=VerifyResponse)
async def verify_endpoint(req: VerifyRequest):
    request = ExtractRequest(
        urls=req.urls[:1],
        source_policy=req.source_policy,
        follow_redirects=True,
        max_redirects=req.max_redirects,
        render_js=False,
    )
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def verify_one(url: HttpUrl) -> dict:
        async with semaphore:
            result = await retrieve_page(str(url), request, allow_render=False)
            if result.get("success"):
                return {
                    "url": str(url),
                    "final_url": result["url"],
                    "reachable": True,
                    "http_status": result["http_status"],
                    "redirect_count": result["redirect_count"],
                    "root_fallback": result["root_fallback"],
                    "reachability": result["reachability"],
                }
            return {"url": str(url), "reachable": False, "error": result.get("error", "Unreachable or blocked")}

    results = await asyncio.gather(*(verify_one(url) for url in req.urls))
    reachable = sum(1 for result in results if result.get("reachable"))
    return VerifyResponse(results=results, reachable=reachable, unreachable=len(results) - reachable)


@app.post("/runs/{run_id}/cancel")
async def cancel_extraction(run_id: str):
    tasks = ACTIVE_EXTRACTIONS.pop(run_id, set())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    return {"cancelled_requests": len(tasks)}


@app.post("/chunk", response_model=ChunkResponse)
async def chunk_endpoint(req: ChunkRequest):
    chunks = chunk_text(req.text, req.chunk_size, req.stride, req.url, req.source_metadata)
    return ChunkResponse(chunks=chunks, total=len(chunks))


DYNAMIC_SEMAPHORE = asyncio.Semaphore(DYNAMIC_CONCURRENCY_LIMIT)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=SCRAPLING_PORT, log_level="info")
