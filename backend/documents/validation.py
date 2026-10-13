"""
Validation of user-edited document content.

Walks the same JSON schema the writer uses (RESUME_CONTENT_SCHEMA) so the two
stay in sync. Checks types, the schema's own `required` keys and unknown keys.
"Required" means the key is present: empty strings and empty lists are valid, so
autosave of partly filled editor entries keeps working.
"""
from pipeline.llm.schemas import RESUME_CONTENT_SCHEMA

_COVER_LETTER_SCHEMA = {
    'type': 'object',
    'properties': {'header': RESUME_CONTENT_SCHEMA['properties']['header']},
    'required': ['header'],
}


def _type_ok(value, expected: str) -> bool:
    if expected == 'object':
        return isinstance(value, dict)
    if expected == 'array':
        return isinstance(value, list)
    if expected == 'string':
        return isinstance(value, str)
    if expected == 'boolean':
        return isinstance(value, bool)
    if expected == 'integer':
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == 'number':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def content_errors(value, schema: dict, path: str = 'content') -> list[str]:
    """Return '<path>: <problem>' messages for every mismatch with the schema.

    Problems: 'expected <type>', 'required' (missing key), 'unknown field'.
    """
    expected = schema.get('type')
    if value is None and expected not in ('object', 'array'):
        return []
    if expected and not _type_ok(value, expected):
        return [f'{path}: expected {expected}']
    errors = []
    if expected == 'object':
        properties = schema.get('properties', {})
        for key in schema.get('required', []):
            if key not in value:
                errors.append(f'{path}.{key}: required')
        for key, sub in properties.items():
            if key in value:
                errors += content_errors(value[key], sub, f'{path}.{key}')
        if properties:
            errors += [f'{path}.{key}: unknown field' for key in sorted(k for k in value if k not in properties)]
    elif expected == 'array' and 'items' in schema:
        for i, item in enumerate(value):
            errors += content_errors(item, schema['items'], f'{path}[{i}]')
    return errors


def validate_document_content(kind: str, content) -> list[str]:
    schema = RESUME_CONTENT_SCHEMA if kind == 'resume' else _COVER_LETTER_SCHEMA
    return content_errors(content, schema)
