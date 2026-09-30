"""Conservative, typed extractive verification.

This is not a general entailment model. Unsupported relations, ambiguous subjects,
units and dates abstain. Retrieval similarity never determines claim support.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit


def normalize(value):
    return " ".join(re.findall(r"\w+", str(value).casefold()))


def exact(value, text):
    needle = text_key(value)
    return bool(needle) and bool(re.search(r"(?<![\w+#])" + re.escape(needle) + r"(?![\w+#])", text_key(text)))


def text_key(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def canonical_url(value):
    try:
        p = urlsplit(str(value).strip())
        if p.scheme not in {"http", "https"} or not p.hostname or p.username:
            return None
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", p.query, ""))
    except ValueError:
        return None


def quantity(value):
    if isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    match = re.fullmatch(r"(?:(USD|EUR|GBP|INR|[$€£₹])\s*)?(-?\d+(?:\.\d+)?)\s*(thousand|million|billion|[kmb])?\s*(%|[A-Za-z]+)?", text, re.I)
    if not match:
        return None
    try:
        scale = {None: 1, "k": 1000, "thousand": 1000, "m": 1000000,
                 "million": 1000000, "b": 1000000000, "billion": 1000000000}[match[3].lower() if match[3] else None]
        # '$' remains ambiguous; it is not silently converted to USD.
        currency = {"€": "EUR", "£": "GBP", "₹": "INR"}.get(match[1], (match[1] or "").upper())
        return Decimal(match[2]) * scale, currency, (match[4] or "").lower()
    except (InvalidOperation, KeyError):
        return None


def typed_equal(left, right, kind="string"):
    if kind in {"number", "integer", "float", "currency", "money", "percentage", "quantity"}:
        a, b = quantity(left), quantity(right)
        return a is not None and a == b and (kind != "integer" or a[0] == a[0].to_integral_value())
    if kind in {"date", "datetime"}:
        try:
            parser = datetime.fromisoformat if kind == "datetime" else date.fromisoformat
            return parser(str(left).replace("Z", "+00:00")) == parser(str(right).replace("Z", "+00:00"))
        except ValueError:
            return False
    if kind in {"url", "uri"}:
        return canonical_url(left) is not None and canonical_url(left) == canonical_url(right)
    if kind in {"boolean", "bool"}:
        mapping = {"true": True, "yes": True, "false": False, "no": False}
        return str(left).lower() in mapping and str(right).lower() in mapping and mapping[str(left).lower()] == mapping[str(right).lower()]
    return text_key(left) == text_key(right) and bool(text_key(left))


def comparable_value(value, kind):
    if kind in {"number", "integer", "float", "currency", "money", "percentage", "quantity"}:
        return quantity(value) is not None
    if kind in {"date", "datetime"}:
        try:
            parser = datetime.fromisoformat if kind == "datetime" else date.fromisoformat
            parser(str(value).replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    if kind in {"boolean", "bool"}:
        return str(value).lower() in {"true", "false", "yes", "no"}
    return kind == "location" and bool(normalize(value))


def subject_clauses(text, entity):
    """Return exact offsets; never borrow another subject's neighboring clause."""
    previous_subject = False
    # Do not split decimals or URL dots. Contrast clauses reset subject context.
    pattern = r"[^\n;]+?(?:(?<!\d)[.!?](?=\s|$)|;|\n|$)"
    for sentence in re.finditer(pattern, text):
        raw = sentence.group().strip(" ;\n")
        for part in re.finditer(r".+?(?=,?\s+\b(?:but|whereas|unlike|while|however)\b|$)", raw, re.I):
            clause = part.group().strip(" ,")
            if not clause:
                continue
            prefix = re.match(r"^(?:but|whereas|unlike|while|however)\s+", clause, re.I)
            if prefix:
                clause = clause[prefix.end():]
                previous_subject = False
            named = exact(entity, clause)
            # A name in an object/list does not establish the subject.
            subject = named and normalize(clause).startswith(normalize(entity) + " ")
            subject = subject or (named and normalize(clause) == normalize(entity))
            pronoun = previous_subject and bool(re.match(r"^(?:it|they|the company|the firm)\b", clause, re.I))
            previous_subject = subject or pronoun
            if previous_subject:
                start = text.find(clause, sentence.start())
                yield clause, start, start + len(clause)


def field_kind(field):
    kind = str(field.get("field_type") or "string").lower()
    if kind != "string":
        return kind
    name = field["name"].lower()
    if name.endswith(("_url", "_link")) or name == "url":
        return "url"
    if name in {"location", "headquarters", "city", "country"}:
        return "location"
    if name in {"certification", "certifications"}:
        return "certification"
    return kind


def slot_patterns(field):
    """Explicit field labels and a small grammar of relation types, not topic keywords."""
    name = field["name"].replace("_", " ")
    labels = [name, *(field.get("evidence_labels") or [])]
    patterns = [rf"\b{re.escape(label)}\s*(?::|=|\bis\b|\bare\b)\s*" for label in labels if isinstance(label, str) and label]
    kind = field_kind(field)
    if kind == "location" or name in {"location", "headquarters", "city", "country"}:
        patterns += [r"\b(?:based|located|headquartered)\s+in\s+", r"\bheadquarters\s*(?:is|are|:)\s*"]
    if kind == "certification":
        patterns += [r"\b(?:holds|certified\s+(?:to|under)|certifications?\s*:)\s*"]
    if name == "industry":
        patterns += [r"\bis\s+(?:a|an)\s+"]
    return patterns


def verify_claim(entity, field, value, chunk):
    result = {"field_name": field["name"], "value": value, "state": "unknown", "reason": "No unambiguous subject-field evidence", "evidence": []}
    if value is None or value == "" or value == []:
        result["reason"] = "Missing value"
        return result
    if chunk.get("http_status") != 200:
        result["reason"] = "No successful source retrieval"
        return result
    if isinstance(value, list):
        parts = [verify_claim(entity, field, item, chunk) for item in value]
        result["state"] = "contradicted" if any(p["state"] == "contradicted" for p in parts) else "supported" if all(p["state"] == "supported" for p in parts) else "unknown"
        result["reason"] = "All list members must be supported"
        result["evidence"] = [e for p in parts for e in p["evidence"]]
        return result
    text, kind = chunk.get("text", ""), field_kind(field)
    identity = field["name"] in {"name", "canonical_name", "company_name", "job_title", "person_name", "product_name"} and typed_equal(value, entity)
    findings = []
    for clause, start, end in subject_clauses(text, entity):
        verdict, reason = None, None
        if identity and "![" in clause:
            continue  # image alt text alone is not an entity assertion
        if identity and exact(value, clause):
            verdict, reason = "supported", "Exact subject identity"
        else:
            # Past, hypothetical, quoted and attributed statements do not establish
            # an unqualified current claim. Abstain instead of guessing a relation.
            if re.search(r"\b(?:was|were|formerly|previously|will|would|could|might|may|if|allegedly|reportedly|plans?|expects?|claims?|said|says)\b", clause, re.I):
                continue
            for pattern in slot_patterns(field):
                match = re.search(pattern, clause, re.I)
                if not match:
                    continue
                prefix = re.sub(rf"^(?:{re.escape(entity)}|it|they|the company|the firm)(?:'s|\u2019s)?\s*", "", clause[:match.start()], count=1, flags=re.I).strip()
                # A relation belonging to an embedded subject cannot be borrowed.
                # Permit only simple copulas and a direct company-type predicate.
                simple = re.fullmatch(r"(?:(?:is|are|has|have)\s*)?(?:not\s*)?", prefix, re.I)
                company = re.fullmatch(r"(?:is|are)\s+(?:a|an)\s+[\w -]{1,80}\s+(?:company|firm|business|startup)", prefix, re.I)
                if not simple and not company:
                    continue
                tail = clause[match.end():].strip().rstrip(".!?;")
                tail = re.split(r",\s*(?:with|and|which)|\s+\b(?:but|whereas|unlike)\b", tail, maxsplit=1, flags=re.I)[0]
                negated = bool(re.search(r"\b(?:not|never|without|no longer)\b", clause[max(0, match.start()-16):match.start()]))
                comparison = tail
                if field["name"] == "industry":
                    comparison = re.split(r"\s+(?:company|business|firm|startup)\b", tail, maxsplit=1, flags=re.I)[0]
                elif kind == "certification":
                    comparison = re.split(r"\s+certifications?\b", tail, maxsplit=1, flags=re.I)[0]
                elif kind in {"number", "integer", "float", "currency", "money", "percentage", "quantity"}:
                    comparison = re.split(r"\s+(?:as of|in|for|during)\b", tail, maxsplit=1, flags=re.I)[0]
                comparison = comparison.strip()
                if re.match(r"(?:not|never|without|no longer)\b", comparison, re.I):
                    negated = True
                    comparison = re.sub(r"^(?:not|never|without|no longer)\s+", "", comparison, flags=re.I)
                if typed_equal(value, comparison, kind):
                    verdict = "contradicted" if negated else "supported"
                    reason = "Explicit negation" if negated else "Typed value in subject-field statement"
                elif not negated and (kind in {"location", "date", "datetime", "number", "integer", "float", "currency", "money", "percentage", "quantity", "boolean", "bool"}):
                    # Contradiction only for explicit, comparable values of a single-valued field.
                    comparable = comparable_value(comparison, kind) and comparable_value(value, kind)
                    if comparable:
                        verdict, reason = "contradicted", "Different explicit value for the same subject and field"
                if verdict:
                    break
        if verdict:
            evidence = {"source_url": chunk["url"], "chunk_id": chunk["chunk_id"], "verbatim_quote": text[start:end],
                        "char_start": chunk.get("char_start", 0) + start, "char_end": chunk.get("char_start", 0) + end,
                        "content_sha256": chunk.get("content_sha256"), "fetched_at": chunk.get("fetched_at"),
                        "published_at": chunk.get("published_at"), "state": verdict, "observed_value": comparison if not identity else entity}
            findings.append((verdict, reason, evidence))
    if findings:
        states = {f[0] for f in findings}
        result.update(state="contradicted" if "contradicted" in states else "supported",
                      reason="Conflicting evidence" if len(states) > 1 else findings[0][1], evidence=[f[2] for f in findings])
    return result


def entity_key(record, contract):
    """Never merge on a common display name without a type-specific discriminator."""
    kind = contract.get("entity_type", "entity").lower()
    name = normalize(record.get("canonical_name", ""))
    def first(*names):
        return next((normalize(record[n]) for n in names if record.get(n) not in (None, "")), None)
    if kind in {"job", "job_opening", "job_posting"}:
        url = record.get("job_url") or record.get("application_url")
        if canonical_url(url):
            return ("job", canonical_url(url))
        employer, location = first("company_name", "company", "employer"), first("location", "city")
        return ("job", name, employer, location, record.get("source_url")) if employer and location else ("unresolved", record.get("source_url"), record.get("chunk_id"), name)
    if kind in {"person", "people"}:
        profile = record.get("profile_url") or record.get("linkedin_url")
        return ("person", canonical_url(profile)) if canonical_url(profile) else ("person", name, first("employer", "company", "organization"), record.get("source_url"))
    if kind in {"product", "products"}:
        maker, model = first("manufacturer", "brand"), first("sku", "model", "model_number")
        return ("product", maker, model) if maker and model else ("product", name, record.get("source_url"))
    if kind in {"company", "startup", "business", "supplier"}:
        registry = first("registration_id", "company_number")
        if registry and first("country", "jurisdiction"):
            return ("company", registry, first("country", "jurisdiction"))
        website = record.get("website") or record.get("company_url")
        if canonical_url(website):
            return ("company", urlsplit(website).hostname.lower().removeprefix("www."))
        # Directory publishers can list namesakes; weak identities stay page-local.
        return ("company-local", name, record.get("source_url"))
    return (kind, name, record.get("source_url"))
