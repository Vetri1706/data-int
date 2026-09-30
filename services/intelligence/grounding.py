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
from claims import quantity, verify_claim, entity_key, exact, typed_equal, text_key, field_kind
from pathlib import Path
import sys
from urllib.robotparser import RobotFileParser
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_policy import permission_decision

MAX_BYTES = 1_000_000
DOMAIN_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)



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


async def fetch_source(client, result, url_guard=public_url, source_policy=None):
    """Fetch actual text, never a generated snippet. Failed candidates are discarded.

    A 404 may fall back to the root, but only that root's fetched content can
    provide evidence. A working home page does not validate the rejected deep URL.
    """
    original = result.get("original_url") or result.get("url", "")
    url = result.get("url", "")
    used_root = bool(result.get("root_fallback"))
    redirects = int(bool(result.get("redirected")))
    try:
        for _ in range(7):
            if not permission_decision(url, source_policy)[0] or not await url_guard(url):
                return None
            parsed = urlsplit(url)
            robots = await client.get(f"{parsed.scheme}://{parsed.netloc}/robots.txt", follow_redirects=False, timeout=1.5)
            if robots.status_code == 200:
                rules = RobotFileParser()
                rules.parse(robots.text.splitlines())
                if not rules.can_fetch("Datavault", url):
                    return None
            elif robots.status_code != 404:
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
                if status == 404 and not used_root:
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
                    "reachability": 1.,
                    "published_at": published,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
    except (httpx.HTTPError, ValueError, UnicodeError, asyncio.TimeoutError):
        return None
    return None


async def collect_sources(results, client=None, url_guard=public_url, source_policy=None):
    limit = asyncio.Semaphore(8)
    async def one(result):
        async with limit:
            try:
                return await asyncio.wait_for(fetch_source(client, result, url_guard, source_policy), timeout=8)
            except asyncio.TimeoutError:
                return None
    if client is None:
        async with httpx.AsyncClient(headers={"User-Agent": "Datavault/1.0 (source verification)"}) as shared:
            return await collect_sources(results, shared, url_guard, source_policy)
    fetched = await asyncio.gather(*(one(r) for r in results[:50]))
    unique = {}
    for source in fetched:
        if source:
            unique.setdefault(source["url"], source)
    return list(unique.values())


def chunk_sources(sources, size=1600, stride=1200):
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
    # Cover distinct pages before allocating extra passages to a long directory.
    best, rest = [], []
    seen_urls = set()
    for item in ranked:
        if item[0]["url"] not in seen_urls:
            best.append(item)
            seen_urls.add(item[0]["url"])
        else:
            rest.append(item)
    selected, per_source = [], {}
    for chunk, score in [*best, *rest]:
        if score <= 0 or per_source.get(chunk["url"], 0) >= 4:
            continue
        # Do not spend the context window repeating overlapping passages.
        if any(c["url"] == chunk["url"] and abs(c["char_start"] - chunk["char_start"]) < min(300, len(chunk["text"])) for c in selected):
            continue
        selected.append({**chunk, "retrieval_score": round(score, 6)})
        per_source[chunk["url"]] = per_source.get(chunk["url"], 0) + 1
        if len(selected) >= top_k:
            break
    return selected


def normalized(value):
    return " ".join(re.findall(r"\w+", str(value).casefold()))


def supported_name(name, text):
    return exact(name, text)


def supported(value, text):
    """Compatibility helper: exact occurrence only; never a claim verdict."""
    return value is not None and exact(value, text)


def fresh_score(source, freshness_days, require_date=False, now=None):
    """Only an actual publication date can establish freshness."""
    now = now or datetime.now(timezone.utc)
    try:
        date = datetime.fromisoformat(str(source.get("published_at")).replace("Z", "+00:00"))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        age = (now - date).total_seconds() / 86400
        if age < -1:
            return None, "invalid"
        return max(0., 1. - max(age, 0.) / max(float(freshness_days or 365), 1.)), "publication"
    except (TypeError, ValueError, OverflowError):
        return None, "unknown"


def constraint_passes(value, operator, target, kind="string"):
    if value is None:
        return False
    op = str(operator).lower().strip()
    if op == "in_region":
        from geography import in_region
        return in_region(value, target)
    if op in {"is_not_empty", "not_empty", "exists", "not_null", "non_empty"}:
        return bool(str(value).strip())
    if op in {"is_empty", "empty", "null", "is_null"}:
        return not bool(str(value).strip())
    left = text_key(value)
    if not left:
        return False
    if op in {"eq", "equals", "=="}:
        right = text_key(target) if target is not None else ""
        return typed_equal(value, target, kind)
    if op in {"ne", "neq", "!=", "not_equals"}:
        right = text_key(target) if target is not None else ""
        return target is not None and not typed_equal(value, target, kind)
    if op in {"contains", "like"}:
        right = text_key(target) if target is not None else ""
        return f" {right} " in f" {left} " or (bool(right) and right in left)
    if op in {"not_contains", "not_like"}:
        right = text_key(target) if target is not None else ""
        return right not in left
    if op in {"in"}:
        targets = target if isinstance(target, (list, tuple, set)) else [target]
        return any(typed_equal(value, t, kind) for t in targets if t is not None)
    if op in {"not_in"}:
        targets = target if isinstance(target, (list, tuple, set)) else [target]
        return not any(typed_equal(value, t, kind) for t in targets if t is not None)
    if op in {"gte", "lte", "gt", "lt", ">=", "<=", ">", "<"}:
        qa, qb = quantity(value), quantity(target)
        if qa is not None and qb is not None:
            if qa[1:] != qb[1:]:
                return False  # no implicit currency / unit conversion
            a, b = qa[0], qb[0]
        else:
            try:
                a, b = datetime.fromisoformat(str(value)), datetime.fromisoformat(str(target))
            except (TypeError, ValueError):
                return False
        try:
            return {"gte": a >= b, ">=": a >= b, "lte": a <= b, "<=": a <= b,
                    "gt": a > b, ">": a > b, "lt": a < b, "<": a < b}[op]
        except TypeError:
            return False
    return False


def extract_canonical_name(record: dict, contract: dict = None) -> str:
    """Universally extract the canonical entity name from any record structure."""
    if not isinstance(record, dict):
        return ""
    identity_field = {"job":"job_title", "job_opening":"job_title", "job_posting":"job_title",
                      "person":"person_name", "product":"product_name", "company":"company_name", "supplier":"company_name"}.get((contract or {}).get("entity_type"))
    for key in ("canonical_name", identity_field):
        if key and isinstance(record.get(key), str) and record[key].strip():
            return record[key].strip()
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


def validate_candidates(records, chunks, contract, now=None, reviewed_claims=None):
    """Keep review candidates separate; acceptance requires explicit supported claims.

    A missing field or conflicting claim is retained as a diagnostic, not promoted
    by a confidence average. Only supported values can populate accepted rows.
    """
    fields = [f for f in contract.get("fields", []) if isinstance(f, dict) and f.get("name")]
    policy = contract.get("evidence_policy") or {}
    by_id = {c["chunk_id"]: c for c in chunks if c.get("http_status") == 200}
    candidates = []
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            continue
        name = extract_canonical_name(raw, contract)
        if not name or len(name) > 160:
            continue
        # Explicit fabricated chunk identifiers cannot be repaired using another page.
        if raw.get("chunk_id") and raw["chunk_id"] not in by_id:
            continue
        anchor = by_id.get(raw.get("chunk_id"))
        url = anchor["url"] if anchor else raw.get("source_url")
        eligible = [c for c in by_id.values() if c.get("url") == url]
        identity_field = {"name": "canonical_name", "identity": True}
        reviews = (reviewed_claims or {}).get(index, {})
        identity = reviews.get("canonical_name", {})
        named = [c for c in eligible if verify_claim(name, identity_field, name, c)["state"] == "supported"]
        if not named and identity.get("state") != "supported":
            continue
        anchor = anchor or eligible[0]
        claims = {}
        for field in fields:
            value = raw.get(field["name"])
            if field["name"] in {"name", "canonical_name"} and value is None:
                value = name
            decisions = [verify_claim(name, field, value, c) for c in eligible]
            reviewed = reviews.get(field["name"])
            if reviewed:
                decisions.append(reviewed)
            elif field["name"] in {"name", "canonical_name"} and identity.get("state") == "supported":
                decisions.append({**identity, "field_name": field["name"]})
            states = {d["state"] for d in decisions}
            state = "contradicted" if "contradicted" in states else "supported" if "supported" in states else "unknown"
            evidence = [e for d in decisions for e in d["evidence"]]
            claims[field["name"]] = {"field_name": field["name"], "value": value, "state": state,
                                    "reason": next((d["reason"] for d in decisions if d["state"] == state), "Missing evidence"), "evidence": evidence}
        row = {f["name"]: claims[f["name"]]["value"] if claims[f["name"]]["state"] == "supported" else None for f in fields}
        row.update(canonical_name=name, source_url=anchor["url"], chunk_id=anchor["chunk_id"], claims=claims,
                   evidence_excerpt=anchor["text"], _sources=eligible)
        candidates.append(row)

    groups = {}
    for row in candidates:
        key = entity_key(row, contract)
        if key not in groups:
            groups[key] = row
            continue
        current = groups[key]
        current["_sources"].extend(row["_sources"])
        for field, incoming in row["claims"].items():
            existing = current["claims"][field]
            if existing["state"] == "unknown" and incoming["state"] == "supported":
                current["claims"][field] = incoming
            elif existing["state"] == "supported" and incoming["state"] == "supported":
                spec = next(f for f in fields if f["name"] == field)
                if not typed_equal(existing["value"], incoming["value"], spec.get("field_type", "string")):
                    existing.update(state="contradicted", reason="Conflicting values across records", alternatives=[existing["value"], incoming["value"]])
                existing["evidence"].extend(incoming["evidence"])
            elif incoming["state"] == "contradicted":
                existing.update(state="contradicted", reason=incoming["reason"])
                existing["evidence"].extend(incoming["evidence"])

    output = []
    for key, row in groups.items():
        sources = row.pop("_sources")
        claims = row["claims"]
        # Corroborate or contradict each field independently; exact mirrors do not vote twice.
        for field in fields:
            claim = claims[field["name"]]
            seen = {(e["source_url"], e["chunk_id"], e["char_start"]) for e in claim["evidence"]}
            for chunk in sources:
                decision = verify_claim(row["canonical_name"], field, claim["value"], chunk)
                for ev in decision["evidence"]:
                    ident = (ev["source_url"], ev["chunk_id"], ev["char_start"])
                    if ident not in seen:
                        claim["evidence"].append(ev)
                        seen.add(ident)
                if decision["state"] == "contradicted":
                    claim.update(state="contradicted", reason="Contradictory source evidence")
            row[field["name"]] = claim["value"] if claim["state"] == "supported" else None
        reasons = []
        required = {f["name"] for f in fields if f.get("required")}
        required.update(c["field"] for c in contract.get("constraints", []) if c.get("is_hard"))
        for name in required:
            claim = claims.get(name, {})
            if claim.get("state") != "supported":
                reasons.append({"field": name, "state": claim.get("state", "unknown"), "reason": claim.get("reason", "Missing field")})
        for constraint in contract.get("constraints", []):
            if constraint.get("is_hard") and not constraint_passes(row.get(constraint["field"]), constraint.get("operator"), constraint.get("target_value"), field_kind(next((f for f in fields if f["name"] == constraint["field"]), {"name":constraint["field"]}))):
                reasons.append({"field": constraint["field"], "state": "unknown" if row.get(constraint["field"]) is None else "contradicted", "reason": "Hard constraint not satisfied"})
        for name, claim in claims.items():
            independent = set()
            hashes = set()
            for ev in claim["evidence"]:
                if ev.get("state") != "supported" or ev.get("content_sha256") in hashes:
                    continue
                independent.add(independent_domain(ev["source_url"]))
                hashes.add(ev.get("content_sha256"))
            claim["distinct_source_domains"] = len(independent)
            if name in required and len(independent) < max(1, int(policy.get("min_sources", 1))):
                reasons.append({"field": name, "state": "unknown", "reason": "Insufficient distinct source domains"})
            if name in required and (policy.get("require_date") or contract.get("freshness_days")):
                dated = [fresh_score({"published_at": e.get("published_at")}, contract.get("freshness_days"), True, now)[0] for e in claim["evidence"] if e.get("state") == "supported"]
                if not any(d is not None and d > 0 for d in dated):
                    reasons.append({"field": name, "state": "unknown", "reason": "No evidence within required publication window"})
        supported_fields = sum(c["state"] == "supported" for c in claims.values())
        coverage = supported_fields / len(fields) if fields else 0.
        # Empty schemas and no supported business attributes never form accepted datasets.
        accepted = bool(fields) and supported_fields > 0 and not reasons
        citations = [{"field_name": n, "extracted_value": str(c["value"]), **e} for n, c in claims.items() if c["state"] == "supported" for e in c["evidence"] if e["state"] == "supported"]
        method = "typed-and-model-reviewed-quotes-v1" if any(e.get("verification_method") == "model-reviewed-quote-v1" for e in citations) else "typed-claims-v1"
        row.update(accepted=accepted, status="verified" if accepted else "needs_review", confidence_score=None,
                   confidence_breakdown={}, verification={"version": "typed-claims-v1", "accepted": accepted,
                   "method": method,
                   "field_coverage": coverage, "acceptance_failures": reasons},
                   provenance={"validation_method": method, "source_urls": sorted({e["source_url"] for e in citations}),
                               "field_evidence": citations, "http_status": sources[0].get("http_status"),
                               "fetched_at": sources[0].get("fetched_at"), "content_sha256": sources[0].get("content_sha256")})
        output.append(row)
    return output
