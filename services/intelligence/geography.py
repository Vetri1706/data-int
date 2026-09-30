"""Explicit regional scope, separate from model guesses about institutions."""
import re

# Administrative/city aliases are geographic normalization, never entity seeds.
REGIONS = {"south india": {
    "tamil nadu", "karnataka", "kerala", "andhra pradesh", "telangana", "puducherry",
    "chennai", "madras", "bengaluru", "bangalore", "coimbatore", "tiruchirappalli",
    "thiruvananthapuram", "trivandrum", "hyderabad", "tirupati", "visakhapatnam",
}}


def in_region(value, region):
    text = re.sub(r"[^\w ]", " ", str(value).casefold())
    text = " " + " ".join(text.split()) + " "
    return any(" " + place + " " in text for place in REGIONS.get(str(region).casefold(), set()))


def preserve_geographic_scope(contract, prompt):
    for region in REGIONS:
        if not re.search(r"\b" + re.escape(region) + r"\b", prompt, re.I):
            continue
        location = next((f for f in contract["fields"] if f["name"] in {"location", "city", "address"}), None)
        if not location:
            location = {"name": "location", "field_type": "location", "description": "City and state of the entity", "required": True}
            contract["fields"].append(location)
        location["required"] = True
        # "contains South India" rejects an actual Chennai/Kerala address.
        # Replace only the equivalent regional predicate, retaining other limits.
        contract['constraints'] = [c for c in contract['constraints'] if not (
            c.get('field') == location['name'] and c.get('operator') in {'eq', 'contains', 'in'}
            and str(c.get('target_value', '')).casefold() == region)]
        constraint = {"field": location["name"], "operator": "in_region", "target_value": region, "is_hard": True}
        if constraint not in contract["constraints"]:
            contract["constraints"].append(constraint)
    return contract
