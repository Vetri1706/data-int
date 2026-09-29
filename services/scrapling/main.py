"""
Scrapling Service — Adaptive Extraction & Link Verification
============================================================

Standalone microservice for:
- JSON-LD structured data extraction (schema.org: JobPosting, Product, Hotel, Organization, etc.)
- DOM selector-based extraction with fallback strategies
- Concurrent HTTP verification with 404/410/5xx purging
- Text chunking for RAG retrieval

API:
  POST /extract        - Extract structured data from URLs
  POST /verify         - Verify URL reachability (batch)
  POST /chunk          - Chunk extracted content for RAG
  GET  /health         - Health check
"""

import asyncio
import hashlib
import json
import logging
import re
import socket
import ipaddress
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from extruct import extract as extruct_extract
from w3lib.html import get_base_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scrapling")

SCRAPLING_PORT = 8001
MAX_BYTES = 1_000_000
CONCURRENCY_LIMIT = 10
REQUEST_TIMEOUT = 10.0
VERIFY_TIMEOUT = 5.0

SCHEMA_TYPES = {
    "JobPosting": ["title", "hiringOrganization", "jobLocation", "baseSalary", "employmentType", "datePosted", "validThrough", "description", "identifier", "url"],
    "Product": ["name", "brand", "offers", "description", "sku", "gtin", "aggregateRating", "review", "url"],
    "Hotel": ["name", "brand", "address", "geo", "starRating", "description", "amenityFeature", "checkInTime", "checkOutTime", "url"],
    "Organization": ["name", "url", "logo", "address", "contactPoint", "sameAs", "foundingDate", "description"],
    "LocalBusiness": ["name", "address", "geo", "telephone", "openingHours", "priceRange", "currenciesAccepted", "paymentAccepted", "url"],
    "Event": ["name", "startDate", "endDate", "location", "description", "organizer", "performer", "offers", "url"],
    "Article": ["headline", "author", "datePublished", "dateModified", "publisher", "description", "articleBody", "url"],
    "Person": ["name", "jobTitle", "worksFor", "affiliation", "email", "telephone", "url", "sameAs"],
}

SELECTOR_PRESETS = {
    "job": {
        "title": ["h1.job-title", "h1.title", "[data-testid=job-title]", ".job-header h1", "h1"],
        "company": [".company-name", "[data-testid=company-name]", ".employer-name", ".company a"],
        "location": [".job-location", "[data-testid=location]", ".location", "[itemprop=jobLocation]"],
        "salary": [".salary", "[data-testid=salary]", ".compensation", "[itemprop=baseSalary]"],
        "description": [".job-description", "[data-testid=description]", ".description", "[itemprop=description]"],
        "type": [".employment-type", "[data-testid=job-type]", ".job-type", "[itemprop=employmentType]"],
    },
    "product": {
        "title": ["h1.product-title", "h1.title", "[data-testid=product-title]", ".product-name h1"],
        "price": [".price", "[data-testid=price]", ".product-price", "[itemprop=price]"],
        "description": [".product-description", "[data-testid=description]", ".description", "[itemprop=description]"],
        "brand": [".brand", "[data-testid=brand]", ".product-brand", "[itemprop=brand]"],
        "rating": [".rating", "[data-testid=rating]", "[itemprop=aggregateRating]"],
    },
    "hotel": {
        "name": ["h1.hotel-name", "h1.title", "[data-testid=hotel-name]", ".hotel-header h1"],
        "address": [".address", "[data-testid=address]", "[itemprop=address]"],
        "rating": [".star-rating", "[data-testid=rating]", "[itemprop=starRating]"],
        "description": [".hotel-description", "[data-testid=description]", ".description", "[itemprop=description]"],
        "amenities": [".amenities", "[data-testid=amenities]", ".facilities", "[itemprop=amenityFeature]"],
    },
    "company": {
        "name": ["h1.company-name", "h1.title", "[data-testid=company-name]", ".org-name"],
        "description": [".company-description", "[data-testid=description]", ".about-us", "[itemprop=description]"],
        "location": [".hq-location", "[data-testid=location]", ".headquarters", "[itemprop=address]"],
        "website": [".website a", "[data-testid=website]", "[itemprop=url]"],
        "size": [".company-size", "[data-testid=size]", "[itemprop=numberOfEmployees]"],
    },
    "generic": {
        "title": ["h1", "title", "[itemprop=name]", "[itemprop=headline]"],
        "description": ["[itemprop=description]", ".description", ".content", "main", "article"],
        "url": ["[itemprop=url]", "link[rel=canonical]"],
    },
}


@dataclass
class ExtractedField:
    name: str
    value: Any
    source: str
    selector: Optional[str] = None
    confidence: float = 0.0


@dataclass
class ExtractionResult:
    url: str
    final_url: str
    schema_type: Optional[str]
    schema_data: dict
    selector_data: dict
    text_content: str
    text_hash: str
    http_status: int
    reachability: float
    fetched_at: str
    content_type: str
    extraction_method: str


class ExtractRequest(BaseModel):
    urls: list[HttpUrl] = Field(..., min_length=1, max_length=50)
    schema_types: Optional[list[str]] = None
    selector_preset: Optional[str] = None
    custom_selectors: Optional[dict[str, list[str]]] = None
    follow_redirects: bool = True
    max_redirects: int = 5
    verify_ssl: bool = True


class VerifyRequest(BaseModel):
    urls: list[HttpUrl] = Field(..., min_length=1, max_length=100)
    allow_root_fallback: bool = True
    max_redirects: int = 4


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


app = FastAPI(title="Scrapling Service", version="1.0.0")


async def public_url(url: str) -> bool:
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
        return bool(addresses) and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    except (ValueError, OSError):
        return False


def build_client(verify_ssl: bool, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        follow_redirects=False,
        verify=verify_ssl,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Scrapling/1.0)"},
        limits=httpx.Limits(max_connections=CONCURRENCY_LIMIT, max_keepalive_connections=5),
    )


async def fetch_with_verification(
    client: httpx.AsyncClient,
    url: str,
    allow_root_fallback: bool,
    max_redirects: int,
) -> Optional[dict]:
    original_url = url
    used_root = False
    redirects = 0

    for _ in range(max_redirects + 2):
        if not await public_url(url):
            return None
        try:
            async with client.stream("GET", url, timeout=VERIFY_TIMEOUT) as response:
                status = response.status_code
                if status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location or redirects >= max_redirects:
                        return None
                    url = urljoin(url, location)
                    redirects += 1
                    continue
                if status in {403, 404} and not used_root and allow_root_fallback:
                    parsed = urlsplit(url)
                    root = f"{parsed.scheme}://{parsed.netloc}/"
                    if root == url:
                        return None
                    url, used_root = root, True
                    continue
                if status != 200:
                    return None
                content_type = response.headers.get("content-type", "").lower()
                if not any(t in content_type for t in ("text/html", "text/plain", "application/xhtml", "application/json")):
                    return None
                body = bytearray()
                async for block in response.aiter_bytes():
                    body.extend(block)
                    if len(body) > MAX_BYTES:
                        return None
                html = body.decode(response.encoding or "utf-8", errors="replace")
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup.select("script:not([type='application/ld+json']), style, nav, footer, header, noscript, form"):
                    tag.decompose()
                text = " ".join(soup.get_text(" ", strip=True).split())[:50000]
                if len(text) < 40 or re.search(r"(?:access denied|verify you are human|captcha|page not found)", text[:250], re.I):
                    return None
                title = soup.title.get_text(" ", strip=True) if soup.title else urlsplit(url).netloc
                return {
                    "url": url,
                    "original_url": original_url,
                    "title": title,
                    "html": html,
                    "soup": soup,
                    "text": text,
                    "text_hash": hashlib.sha256(text.encode()).hexdigest(),
                    "http_status": status,
                    "redirect_count": redirects,
                    "root_fallback": used_root,
                    "reachability": 0.7 if (redirects or used_root) else 1.0,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "content_type": content_type,
                }
        except (httpx.HTTPError, ValueError, UnicodeError, asyncio.TimeoutError):
            return None
    return None


def extract_json_ld(soup: BeautifulSoup, target_types: Optional[list[str]] = None) -> list[dict]:
    results = []
    for script in soup.select("script[type='application/ld+json']"):
        try:
            data = json.loads(script.string or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                schema_type = item.get("@type")
                types = schema_type if isinstance(schema_type, list) else [schema_type] if schema_type else []
                if target_types and not any(t in target_types for t in types):
                    continue
                results.append(item)
        except (json.JSONDecodeError, TypeError):
            continue
    return results


def extract_microdata(soup: BeautifulSoup) -> list[dict]:
    results = []
    for item in soup.select("[itemscope][itemtype]"):
        item_type = item.get("itemtype", "")
        props = {}
        for prop in item.select("[itemprop]"):
            name = prop.get("itemprop")
            value = prop.get("content") or prop.get("datetime") or prop.get("href") or prop.get_text(" ", strip=True)
            if name and value:
                if name in props:
                    if not isinstance(props[name], list):
                        props[name] = [props[name]]
                    props[name].append(value)
                else:
                    props[name] = value
        if props:
            props["@type"] = item_type.split("/")[-1] if item_type else "Thing"
            results.append(props)
    return results


def extract_rdfa(soup: BeautifulSoup) -> list[dict]:
    results = []
    for item in soup.select("[typeof]"):
        props = {}
        for prop in item.select("[property]"):
            name = prop.get("property")
            value = prop.get("content") or prop.get("datetime") or prop.get("href") or prop.get_text(" ", strip=True)
            if name and value:
                if name in props:
                    if not isinstance(props[name], list):
                        props[name] = [props[name]]
                    props[name].append(value)
                else:
                    props[name] = value
        if props:
            props["@type"] = item.get("typeof", "").split(":")[-1] if item.get("typeof") else "Thing"
            results.append(props)
    return results


def extract_with_selectors(soup: BeautifulSoup, selectors: dict[str, list[str]]) -> dict[str, list[ExtractedField]]:
    results = {}
    for field_name, selector_list in selectors.items():
        for selector in selector_list:
            try:
                elements = soup.select(selector)
                if elements:
                    values = []
                    for el in elements:
                        val = el.get("content") or el.get("datetime") or el.get("href") or el.get_text(" ", strip=True)
                        if val:
                            values.append(ExtractedField(
                                name=field_name,
                                value=val,
                                source="selector",
                                selector=selector,
                                confidence=0.8,
                            ))
                    if values:
                        results[field_name] = values
                        break
            except Exception:
                continue
    return results


def normalize_schema_data(raw: dict, schema_type: str) -> dict:
    fields_of_interest = SCHEMA_TYPES.get(schema_type, [])
    normalized = {"@type": schema_type}
    for field in fields_of_interest:
        if field in raw:
            val = raw[field]
            if isinstance(val, dict) and "@type" in val:
                normalized[field] = normalize_schema_data(val, val["@type"])
            elif isinstance(val, list):
                normalized[field] = [normalize_schema_data(v, schema_type) if isinstance(v, dict) and "@type" in v else v for v in val]
            else:
                normalized[field] = val
    for k, v in raw.items():
        if k not in normalized:
            normalized[k] = v
    return normalized


def chunk_text(text: str, chunk_size: int, stride: int, url: str, metadata: dict) -> list[dict]:
    if chunk_size <= 0 or stride <= 0 or stride > chunk_size:
        raise ValueError("Invalid chunk parameters")
    chunks = []
    for start in range(0, len(text), stride):
        end = min(start + chunk_size, len(text))
        chunk_text = text[start:end]
        chunk_id = hashlib.sha256(f"{url}:{metadata.get('text_hash', '')}:{start}".encode()).hexdigest()[:20]
        chunks.append({
            "chunk_id": chunk_id,
            "text": chunk_text,
            "char_start": start,
            "char_end": end,
            "url": url,
            **{k: v for k, v in metadata.items() if k != "text"},
        })
        if end == len(text):
            break
    return chunks


async def process_url(
    client: httpx.AsyncClient,
    url: str,
    schema_types: Optional[list[str]],
    selector_preset: Optional[str],
    custom_selectors: Optional[dict],
    follow_redirects: bool,
    max_redirects: int,
    verify_ssl: bool,
) -> dict:
    fetched = await fetch_with_verification(client, url, True, max_redirects)
    if not fetched:
        return {"url": url, "error": "Failed to fetch or verify", "success": False}

    soup = fetched["soup"]
    schema_results = extract_json_ld(soup, schema_types)
    schema_results.extend(extract_microdata(soup))
    schema_results.extend(extract_rdfa(soup))

    normalized_schemas = []
    for item in schema_results:
        schema_type = item.get("@type", "Thing")
        normalized_schemas.append(normalize_schema_data(item, schema_type))

    selector_map = {}
    if custom_selectors:
        selector_map.update(custom_selectors)
    if selector_preset and selector_preset in SELECTOR_PRESETS:
        for k, v in SELECTOR_PRESETS[selector_preset].items():
            selector_map.setdefault(k, []).extend(v)

    selector_data = extract_with_selectors(soup, selector_map) if selector_map else {}

    primary_schema = normalized_schemas[0] if normalized_schemas else {}
    primary_type = primary_schema.get("@type") if primary_schema else None

    return {
        "url": fetched["url"],
        "original_url": fetched["original_url"],
        "title": fetched["title"],
        "schema_type": primary_type,
        "schema_data": primary_schema,
        "all_schemas": normalized_schemas,
        "selector_data": {k: [asdict(f) for f in v] for k, v in selector_data.items()},
        "text_content": fetched["text"],
        "text_hash": fetched["text_hash"],
        "http_status": fetched["http_status"],
        "reachability": fetched["reachability"],
        "fetched_at": fetched["fetched_at"],
        "content_type": fetched["content_type"],
        "extraction_method": "json_ld" if normalized_schemas else ("selector" if selector_data else "text_only"),
        "success": True,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "scrapling", "port": SCRAPLING_PORT}


@app.post("/extract", response_model=ExtractResponse)
async def extract_endpoint(req: ExtractRequest):
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    client = build_client(req.verify_ssl, REQUEST_TIMEOUT)

    async def process_one(url: HttpUrl):
        async with semaphore:
            return await process_url(
                client, str(url), req.schema_types, req.selector_preset,
                req.custom_selectors, req.follow_redirects, req.max_redirects, req.verify_ssl
            )

    results = await asyncio.gather(*(process_one(u) for u in req.urls))
    await client.aclose()

    successful = sum(1 for r in results if r.get("success"))
    return ExtractResponse(
        results=results,
        total=len(results),
        successful=successful,
        failed=len(results) - successful,
    )


@app.post("/verify", response_model=VerifyResponse)
async def verify_endpoint(req: VerifyRequest):
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    client = build_client(True, VERIFY_TIMEOUT)

    async def verify_one(url: HttpUrl):
        async with semaphore:
            fetched = await fetch_with_verification(client, str(url), req.allow_root_fallback, req.max_redirects)
            if fetched:
                return {
                    "url": str(url),
                    "final_url": fetched["url"],
                    "reachable": True,
                    "http_status": fetched["http_status"],
                    "redirect_count": fetched["redirect_count"],
                    "root_fallback": fetched["root_fallback"],
                    "reachability": fetched["reachability"],
                }
            return {"url": str(url), "reachable": False, "error": "Unreachable or blocked"}

    results = await asyncio.gather(*(verify_one(u) for u in req.urls))
    await client.aclose()

    reachable = sum(1 for r in results if r.get("reachable"))
    return VerifyResponse(results=results, reachable=reachable, unreachable=len(results) - reachable)


@app.post("/chunk", response_model=ChunkResponse)
async def chunk_endpoint(req: ChunkRequest):
    chunks = chunk_text(req.text, req.chunk_size, req.stride, req.url, req.source_metadata)
    return ChunkResponse(chunks=chunks, total=len(chunks))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=SCRAPLING_PORT, log_level="info")