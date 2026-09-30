"""Bounded output shapes for local structured generation; evidence still needs verification."""


def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


TEXT = {'type': 'string'}
STRINGS = {'type': 'array', 'items': TEXT}
QUERY_SCHEMA = object_schema({'queries': {'type': 'array', 'maxItems': 5, 'items': TEXT}})
CONTRACT_SCHEMA = object_schema({
    'entity_type': TEXT, 'business_goal': TEXT,
    'fields': {'type': 'array', 'minItems': 1, 'maxItems': 16, 'items': object_schema({
        'name': TEXT, 'field_type': TEXT, 'description': TEXT, 'required': {'type': 'boolean'},
    })},
    'constraints': {'type': 'array', 'items': object_schema({
        'field': TEXT, 'operator': {'type': 'string', 'enum': ['eq', 'contains', 'gte', 'lte', 'in']},
        'target_value': {'type': ['string', 'number', 'boolean', 'array'], 'items': TEXT},
        'is_hard': {'type': 'boolean'},
    })},
    'relationships': {'type': 'array', 'items': object_schema({'source': TEXT, 'relationship': TEXT, 'target': TEXT})},
    'target_count': {'type': 'integer'}, 'freshness_days': {'type': ['integer', 'null']},
    'evidence_policy': object_schema({'min_sources': {'type': 'integer'}, 'prefer_official': {'type': 'boolean'},
                                     'require_date': {'type': 'boolean'}, 'required_evidence': STRINGS}),
    'allowed_domains': STRINGS,
})
RELEVANCE_SCHEMA = object_schema({'evaluations': {'type': 'array', 'items': object_schema({
    'candidate_index': {'type': 'integer'},
    'decision': {'type': 'string', 'enum': ['KEEP', 'REJECT', 'UNCERTAIN']}, 'reason': TEXT,
})}})


def extraction_schema(fields, limit):
    types = {'integer': 'integer', 'number': 'number', 'float': 'number', 'boolean': 'boolean', 'array': 'array', 'list': 'array'}
    properties = {}
    for field in fields:
        kind = types.get(field.get('field_type'), 'string')
        properties[field['name']] = {'type': [kind, 'null']}
        if kind == 'string':
            properties[field['name']]['maxLength'] = 300
        if kind == 'array':
            properties[field['name']]['items'] = TEXT
    properties.update({key: {'type': 'string', 'maxLength': length} for key, length in
                       [('canonical_name', 160), ('chunk_id', 80), ('source_url', 2048), ('evidence_excerpt', 250)]})
    return object_schema({'records': {'type': 'array', 'maxItems': limit, 'items': object_schema(properties)}})
