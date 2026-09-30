"""Frozen lexical support baseline from commit 2981853; evaluation only."""
import re

def normalized(value):
    return " ".join(re.findall(r"\w+", str(value).casefold()))

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
