"""Measured retrieval and evidence validation; no LLM-generated evidence is trusted.

TF-IDF scores are lexical similarity measures, not calibrated truth probabilities.
Offsets refer to the normalized, fetched text stored in each source document.
"""

import asyncio
import hashlib
import ipaddress
import re
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin

import httpx
import tldextract
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

MAX_BYTES = 1_000_000
DOMAIN_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
WEIGHTS = {"source_authority": .10, "grounding_score": .25,
           "ml_validation_score": .20, "agreement": .15,
           "freshness": .10, "completeness": .20}


def sanitize_query(query):
    query = re.sub(r"\b(?:site|filetype|intitle|inurl):\S+", " ", str(query), flags=re.I)
    query = re.sub(r"\b(?:AND|OR|NOT)\b", " ", query)
    return " ".join(re.sub(r'["“”(){}\[\]|]', " ", query).split())[:500]


def domain_of(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def independent_domain(url):
    host = domain_of(url)
    parsed = DOMAIN_EXTRACTOR(host)
    return parsed.top_domain_under_public_suffix or host


async def public_url(url):
    """Reject local/network-service URLs, including each redirect destination."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            return False
        addresses = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
        return bool(addresses) and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    except (ValueError, OSError):
        return False


async def fetch_source(client, result, url_guard=public_url):
    """Fetch actual text, never a generated snippet. Failed candidates are discarded.

    A 403/404 may fall back to the root, but only that root's fetched content can
    provide evidence. A working home page does not validate the rejected deep URL.
    """
    original = result.get("original_url") or result.get("url", "")
    url = result.get("url", "")
    used_root = bool(result.get("root_fallback"))
    redirects = int(bool(result.get("redirected")))
    try:
        for _ in range(7):
            if not await url_guard(url):
                return None
            async with client.stream("GET", url, follow_redirects=False, timeout=1.5) as response:
                status = response.status_code
                if status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location or redirects >= 4:
                        return None
                    url = urljoin(url, location)
                    redirects += 1
                    continue
                if status in {403, 404} and not used_root:
                    parsed = urlsplit(url)
                    root = f"{parsed.scheme}://{parsed.netloc}/"
                    if root == url:
                        return None
                    url, used_root = root, True
                    continue
                if status != 200:
                    return None
                content_type = response.headers.get("content-type", "").lower()
                if not any(t in content_type for t in ("text/html", "text/plain", "application/xhtml")):
                    return None
                body = bytearray()
                async for block in response.aiter_bytes():
                    body.extend(block)
                    if len(body) > MAX_BYTES:
                        return None
                html = body.decode(response.encoding or "utf-8", errors="replace")
                soup = BeautifulSoup(html, "html.parser")
                date_tag = soup.select_one('meta[property="article:published_time"], meta[name="date"], time[datetime]')
                published = (date_tag.get("content") or date_tag.get("datetime")) if date_tag else None
                title = soup.title.get_text(" ", strip=True) if soup.title else domain_of(url)
                for tag in soup.select("script, style, nav, footer, header, noscript, form"):
                    tag.decompose()
                text = " ".join(soup.get_text(" ", strip=True).split())[:24000]
                if len(text) < 40 or re.search(r"(?:access denied|verify you are human|captcha|page not found)", text[:250], re.I):
                    return None
                return {
                    "url": url, "original_url": original, "title": title,
                    "provider": result.get("provider", "unknown"), "content": text,
                    "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "http_status": status, "redirect_count": redirects,
                    "root_fallback": used_root,
                    "reachability": .7 if redirects or used_root else 1.,
                    "published_at": published,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
    except (httpx.HTTPError, ValueError, UnicodeError, asyncio.TimeoutError):
        return None
    return None


async def collect_sources(results, client=None, url_guard=public_url):
    limit = asyncio.Semaphore(8)
    async def one(result):
        async with limit:
            try:
                return await asyncio.wait_for(fetch_source(client, result, url_guard), timeout=8)
            except asyncio.TimeoutError:
                return None
    if client is None:
        async with httpx.AsyncClient(headers={"User-Agent": "Datavault/1.0 (source verification)"}) as shared:
            return await collect_sources(results, shared, url_guard)
    fetched = await asyncio.gather(*(one(r) for r in results[:50]))
    unique = {}
    for source in fetched:
        if source:
            unique.setdefault(source["url"], source)
    return list(unique.values())


def chunk_sources(sources, size=500, stride=100):
    if size <= 0 or stride <= 0 or stride > size:
        raise ValueError("Chunk stride must be between 1 and chunk size")
    chunks = []
    for source in sources:
        text = source["content"]
        for start in range(0, len(text), stride):
            end = min(start + size, len(text))
            chunks.append({**{k: v for k, v in source.items() if k != "content"},
                           "chunk_id": hashlib.sha256(f'{source["url"]}:{source["content_sha256"]}:{start}'.encode()).hexdigest()[:20],
                           "text": text[start:end], "char_start": start, "char_end": end})
            if end == len(text):
                break
    return chunks


def similarities(query, texts):
    if not texts or not query.strip():
        return [0.] * len(texts)
    try:
        matrix = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True,
                                 strip_accents="unicode", max_features=30000).fit_transform([query, *texts])
        return cosine_similarity(matrix[0], matrix[1:]).ravel().tolist()
    except ValueError:  # empty vocabulary
        return [0.] * len(texts)


def retrieve_chunks(sources, prompt, contract, top_k=24):
    return rank_chunks(chunk_sources(sources), prompt, contract, top_k=top_k)


def rank_chunks(chunks, prompt, contract, top_k=24):
    """Rank an existing chunk set with the unchanged Datavault TF-IDF policy.

    This additive entry point is used by the evaluation-only Laya-before-TFIDF
    path.  ``retrieve_chunks`` delegates to it after creating chunks, so the
    ranking and per-source de-duplication rules remain identical in both paths.
    """
    query = " ".join([prompt, contract.get("entity_type") or "",
                      *[str(f.get("description") or f["name"]) for f in contract.get("fields", [])]])
    scores = similarities(query, [c["text"] for c in chunks])
    ranked = sorted(zip(chunks, scores), key=lambda item: item[1], reverse=True)
    selected, per_source = [], {}
    for chunk, score in ranked:
        if score <= 0 or per_source.get(chunk["url"], 0) >= 4:
            continue
        # Do not spend the context window repeating overlapping passages.
        if any(c["url"] == chunk["url"] and abs(c["char_start"] - chunk["char_start"]) < 300 for c in selected):
            continue
        selected.append({**chunk, "retrieval_score": round(score, 6)})
        per_source[chunk["url"]] = per_source.get(chunk["url"], 0) + 1
        if len(selected) >= top_k:
            break
    return selected


def normalized(value):
    return " ".join(re.findall(r"\w+", str(value).casefold()))


COMMON_SUFFIXES = {
    "inc", "incorporated", "ltd", "limited", "corp", "corporation",
    "llc", "technologies", "technology", "solutions", "group", "labs", "ai", "co"
}


def supported_name(name, text):
    if supported(name, text):
        return True
    tokens = [t for t in re.findall(r"\w+", str(name).casefold()) if t not in COMMON_SUFFIXES]
    if tokens:
        haystack = f" {normalized(text)} "
        if all(f" {t} " in haystack for t in tokens):
            return True
    return False


def supported(value, text):
    if value is None or value == "":
        return False
    values = value if isinstance(value, list) else [value]
    haystack = f" {normalized(text)} "
    for v in values:
        if not v:
            return False
        norm_v = normalized(v)
        if not norm_v:
            return False
        # Exact multi-token match
        is_match = f" {norm_v} " in haystack
        if not is_match:
            tokens = [t for t in re.findall(r"\w+", str(v).casefold()) if len(t) >= 2]
            if not tokens:
                return False
            if len(tokens) == 1:
                t = tokens[0]
                is_match = (
                    f" {t} " in haystack
                    or (len(t) >= 4 and (f" {t}n " in haystack or f" {t}an " in haystack or f" {t[:-1]} " in haystack))
                )
            else:
                matched_count = sum(
                    1 for t in tokens
                    if f" {t} " in haystack or f" {t}s " in haystack or (len(t) >= 4 and f" {t}n " in haystack)
                )
                is_match = matched_count >= (len(tokens) + 1) // 2
        if not is_match:
            return False

        # A matching keyword in an explicitly negated claim is not support.
        for sentence in re.split(r"[.!?;]", text):
            clean = normalized(sentence)
            for token in re.findall(r"\w+", norm_v):
                position = clean.find(token)
                if position >= 0 and re.search(r"\b(?:not|never|without|no longer)\b", " ".join(clean[:position].split()[-5:])):
                    return False
    return True


def entity_coherence(name, text, entity_type):
    kind = normalized(entity_type)
    if any(token in kind for token in ("company", "startup", "business", "person")) and re.search(
        r"\b(?:phone case|replacement cable|accessory|accessories|search portal)\b", name, re.I
    ):
        return 0.
    descriptions = {
        "company": "company business firm startup corporation develops manufactures headquartered founded",
        "startup": "startup company business founded develops technology funding",
        "job": "job role position hiring employment responsibilities qualifications",
        "person": "person researcher founder engineer director biography",
        "product": "product model specifications manufacturer features price",
        "hotel": "hotel resort accommodation rooms hospitality located",
    }
    label = next((description for key, description in descriptions.items() if key in kind), None)
    return min(1., similarities(label, [text])[0] * 4) if label else .5


def entity_context(text, name):
    """Avoid attributing one company's nearby location to another company."""
    sentences = re.split(r"(?<=[.!?;])\s+(?=[A-Z])", text)
    selected = []
    pattern = r"(?:It|They|The company|The firm|Founded|Headquartered|Headquarters|Location|Based|Office|Address|Products?|Services?|Contact|Plant|Facility|Manufacturing)\b"
    for index, sentence in enumerate(sentences):
        if supported_name(name, sentence):
            selected.append(sentence)
            if index + 1 < len(sentences) and re.match(pattern, sentences[index + 1], re.I):
                selected.append(sentences[index + 1])
    return " ".join(selected)


def fresh_score(source, freshness_days, require_date=False, now=None):
    now = now or datetime.now(timezone.utc)
    timestamp = source.get("published_at")
    basis = "publication"
    if not timestamp:
        if require_date:
            return 0., "unknown"
        timestamp, basis = source.get("fetched_at"), "crawl"
    try:
        date = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        age = (now - date).total_seconds() / 86400
        if age < -1:
            return 0., "invalid"
        score = max(0., 1. - max(age, 0.) / max(float(freshness_days or 365), 1.))
        # A recent crawl says nothing about how recently the facts changed.
        return min(score, .5) if basis == "crawl" else score, basis
    except (TypeError, ValueError, OverflowError):
        return 0., "unknown"


def source_authority(url, allowed_domains):
    host = domain_of(url)
    if any(host == d or host.endswith("." + d) for d in (domain_of("https://" + d) for d in allowed_domains)):
        return .85
    if host.endswith((".gov", ".gov.in", ".edu", ".ac.in")):
        return .85
    return .5  # explicitly a prior, never a measured verification result


def constraint_passes(value, operator, target):
    if value is None:
        return False
    op = str(operator).lower().strip()
    if op in {"is_not_empty", "not_empty", "exists", "not_null", "non_empty"}:
        return bool(str(value).strip())
    if op in {"is_empty", "empty", "null", "is_null"}:
        return not bool(str(value).strip())
    left = normalized(value)
    if not left:
        return False
    if op in {"eq", "equals", "=="}:
        right = normalized(target) if target is not None else ""
        return left == right
    if op in {"ne", "neq", "!=", "not_equals"}:
        right = normalized(target) if target is not None else ""
        return left != right
    if op in {"contains", "like"}:
        right = normalized(target) if target is not None else ""
        return f" {right} " in f" {left} " or (bool(right) and right in left)
    if op in {"not_contains", "not_like"}:
        right = normalized(target) if target is not None else ""
        return right not in left
    if op in {"in"}:
        targets = target if isinstance(target, (list, tuple, set)) else [target]
        return any(left == normalized(t) or f" {normalized(t)} " in f" {left} " or (normalized(t) and normalized(t) in left) for t in targets if t is not None)
    if op in {"not_in"}:
        targets = target if isinstance(target, (list, tuple, set)) else [target]
        return not any(left == normalized(t) or f" {normalized(t)} " in f" {left} " or (normalized(t) and normalized(t) in left) for t in targets if t is not None)
    if op in {"gte", "lte", "gt", "lt", ">=", "<=", ">", "<"}:
        def numeric(v):
            match = re.fullmatch(r"[$₹€£]?\s*(-?\d+(?:\.\d+)?)\s*([kmb]?)", str(v).replace(",", ""), re.I)
            if not match:
                raise ValueError("not numeric")
            return float(match[1]) * {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[match[2].lower()]
        try:
            a, b = numeric(value), numeric(target)
        except ValueError:
            try:
                a, b = datetime.fromisoformat(str(value)), datetime.fromisoformat(str(target))
            except ValueError:
                return False
        try:
            return {"gte": a >= b, ">=": a >= b, "lte": a <= b, "<=": a <= b,
                    "gt": a > b, ">": a > b, "lt": a < b, "<": a < b}[op]
        except TypeError:
            return False
    if target is None:
        return bool(str(value).strip())
    return False


def extract_canonical_name(record: dict, contract: dict = None) -> str:
    """Universally extract the canonical entity name from any record structure."""
    if not isinstance(record, dict):
        return ""
    # 1. Direct standard keys
    for k in ("canonical_name", "name", "title", "entity_name", "company_name", "company", "supplier_name", "supplier", "label"):
        val = record.get(k)
        if val and isinstance(val, str) and len(val.strip()) > 1:
            return val.strip()
    # 2. Check contract fields (e.g. first required field or text field)
    if contract and isinstance(contract, dict):
        fields = contract.get("fields", [])
        for f in fields:
            if isinstance(f, dict):
                fname = f.get("name")
                val = record.get(fname)
                if val and isinstance(val, str) and len(val.strip()) > 1:
                    return val.strip()
    # 3. Fallback: first non-metadata string field
    meta_keys = {"chunk_id", "source_url", "url", "evidence_excerpt", "extraction_confidence",
                 "status", "id", "confidence_score", "confidence_breakdown", "provenance"}
    for k, v in record.items():
        if k not in meta_keys and isinstance(v, str) and len(v.strip()) > 1:
            return v.strip()
    return ""


def validate_candidates(records, chunks, contract, now=None):
    """Bind claims to retrieved chunks; reject ungrounded identity and constraints."""
    by_id = {c["chunk_id"]: c for c in chunks}
    chunks_by_url = {}
    for c in chunks:
        chunks_by_url.setdefault(c.get("url"), []).append(c)

    fields = contract.get("fields", [])
    required = [f["name"] for f in fields if isinstance(f, dict) and f.get("required")]
    policy = contract.get("evidence_policy") or {}
    output = {}
    for candidate in records:
        if not isinstance(candidate, dict):
            continue
        record = dict(candidate)
        name = extract_canonical_name(record, contract)
        if len(name) < 2 or len(name) > 160 or name.startswith("http") or re.search(
            r"\b(search results?|directory|listing|top \d+|best \d+|click here|access denied)\b", name, re.I
        ):
            continue

        raw_cid = record.get("chunk_id")
        chunk = by_id.get(raw_cid)
        if not chunk and raw_cid is not None:
            cid_str = str(raw_cid).strip().strip("[]").strip()
            if cid_str.isdigit() and 1 <= int(cid_str) <= len(chunks):
                chunk = chunks[int(cid_str) - 1]
        if not chunk and record.get("source_url"):
            for candidate_chunk in chunks_by_url.get(record.get("source_url"), []):
                if supported_name(name, candidate_chunk["text"]):
                    chunk = candidate_chunk
                    break
        if not chunk and (raw_cid is None or raw_cid == "") and record.get("source_url"):
            url_chunks = chunks_by_url.get(record.get("source_url"), [])
            if url_chunks:
                chunk = url_chunks[0]
        # If no explicit chunk_id was provided or was invalid format, check if any chunk supports the name
        if not chunk and (raw_cid is None or raw_cid == ""):
            for candidate_chunk in chunks:
                if candidate_chunk.get("http_status") == 200 and supported_name(name, candidate_chunk["text"]):
                    chunk = candidate_chunk
                    break

        if not chunk or chunk.get("http_status") != 200 or not supported_name(name, chunk["text"]):
            continue

        attributes = {f["name"]: record.get(f["name"]) for f in fields if isinstance(f, dict) and "name" in f}
        if "name" in attributes and not attributes["name"]:
            attributes["name"] = name
        if "canonical_name" in attributes and not attributes["canonical_name"]:
            attributes["canonical_name"] = name
        context = entity_context(chunk["text"], name)
        eval_text = context if context else chunk["text"]
        verified_fields = [
            f for f, value in attributes.items()
            if supported(value, eval_text)
        ]
        if any(c.get("is_hard") and (c["field"] not in verified_fields or not constraint_passes(
            attributes.get(c["field"]), str(c.get("operator", "eq")).lower(), c.get("target_value")
        )) for c in contract.get("constraints", [])):
            continue
        claim = " ".join([name, *[str(v) for v in attributes.values() if v is not None]])
        grounding = similarities(claim, [chunk["text"]])[0]
        completeness = sum(f in verified_fields for f in required) / len(required) if required else 1.
        field_ratio = len(verified_fields) / max(len(attributes), 1)
        coherence = entity_coherence(name, chunk["text"], contract.get("entity_type", "entity"))
        ml_score = .4 * grounding + .4 * field_ratio + .2 * coherence
        if grounding < .01 or coherence == 0:
            continue
        # Corroborate the same identity AND supported claims; mirrored pages do
        # not become independent confirmations merely through a different host.
        citations, seen_domains, seen_text = [], set(), set()
        for other in [chunk, *chunks]:
            host = independent_domain(other["url"])
            if (other.get("http_status") != 200 or host in seen_domains
                    or other.get("content_sha256") in seen_text or not supported_name(name, other["text"])):
                continue
            compared = [f for f in verified_fields if normalized(attributes[f]) != normalized(name)]
            other_context = entity_context(other["text"], name) or other["text"]
            if compared and not all(supported(attributes[f], other_context) for f in compared):
                continue
            seen_domains.add(host)
            seen_text.add(other.get("content_sha256"))
            citations.append(other)
        agreement = min(max(len(citations) - 1, 0) / 2, 1.)
        freshness, freshness_basis = fresh_score(chunk, contract.get("freshness_days"), policy.get("require_date", False), now)
        reachability = float(chunk.get("reachability", 0))
        scores = {"source_authority": source_authority(chunk["url"], contract.get("allowed_domains", [])),
                  "grounding_score": grounding, "ml_validation_score": ml_score,
                  "agreement": agreement, "freshness": freshness, "completeness": completeness}
        confidence = reachability * sum(scores[k] * weight for k, weight in WEIGHTS.items())
        enough_sources = len(citations) >= max(int(policy.get("min_sources", 1)), 1)
        status = "verified" if confidence >= .75 and completeness == 1 and enough_sources and (freshness_basis == "publication" or not policy.get("require_date")) else "needs_review" if confidence >= .5 else "draft"
        evidence = [{"field_name": field, "verbatim_quote": chunk["text"],
                     "source_url": chunk["url"], "extracted_value": str(attributes[field]),
                     "chunk_id": chunk["chunk_id"], "char_start": chunk["char_start"], "char_end": chunk["char_end"]}
                    for field in verified_fields]
        grounded_attributes = {field: value if field in verified_fields else None for field, value in attributes.items()}
        value = {**grounded_attributes, "canonical_name": name, "source_url": chunk["url"], "chunk_id": chunk["chunk_id"],
                 "evidence_excerpt": chunk["text"], "grounding_score": round(grounding, 6),
                 "confidence_score": round(confidence, 4), "status": status,
                 "confidence_breakdown": {**{k: round(v, 6) for k, v in scores.items()},
                                          "reachability": reachability, "extraction_certainty": round(field_ratio, 6)},
                 "provenance": {"authority_score": scores["source_authority"], "agreement_rate": agreement,
                    "source_urls": [c["url"] for c in citations], "field_evidence": evidence,
                    "http_status": chunk["http_status"], "reachability": reachability,
                    "freshness_basis": freshness_basis, "fetched_at": chunk.get("fetched_at"),
                    "published_at": chunk.get("published_at"), "content_sha256": chunk.get("content_sha256"),
                    "chunk_id": chunk["chunk_id"], "char_start": chunk["char_start"], "char_end": chunk["char_end"],
                    "retrieval_score": chunk.get("retrieval_score"), "validation_method": "tfidf-evidence-v1",
                    "factors": [{"factor_name": k, "score": round(scores[k], 6), "weight": weight,
                                 "contribution": round(scores[k] * weight * reachability, 6)} for k, weight in WEIGHTS.items()]}}
        key = normalized(name)
        if key not in output or value["confidence_score"] > output[key]["confidence_score"]:
            output[key] = value
    return sorted(output.values(), key=lambda r: r["confidence_score"], reverse=True)
