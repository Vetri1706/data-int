"""Explicit user-approved scope. Model suggestions can never grant permission."""
from urllib.parse import urlsplit


def normalized_domain(value):
    if not isinstance(value, str) or any(c in value for c in "/:@?#* "):
        return None
    domain = value.strip().lower().rstrip(".")
    return domain if "." in domain and not domain.startswith(".") else None


def domain_matches(host, domains):
    return any((d := normalized_domain(item)) and (host == d or host.endswith("." + d)) for item in domains)


def permission_decision(url, policy):
    policy = policy if isinstance(policy, dict) else {}
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower().rstrip(".")
        if p.scheme not in {"http", "https"} or not host or p.username:
            return False, "Invalid public-web URL"
    except ValueError:
        return False, "Invalid URL"
    if policy.get("basis") != "user_confirmed_permission":
        return False, "No recorded collection permission"
    if domain_matches(host, policy.get("blocked_domains", [])):
        return False, "Source disabled or blocked"
    if not domain_matches(host, policy.get("approved_domains", [])):
        return False, "Domain outside approved collection scope"
    restrictions = policy.get("domain_filters", [])
    if restrictions and not domain_matches(host, restrictions):
        return False, "Domain outside hard restrictions"
    return True, "Within user-approved scope; robots policy still required"
