"""
Type-only validation of user-edited document content.

Walks the same JSON schema the writer uses (RESUME_CONTENT_SCHEMA) so the two
stay in sync. `required` is deliberately not enforced: the editor saves partly
filled entries and autosave must not start failing.
"""
from pipeline.llm.schemas import RESUME_CONTENT_SCHEMA

_COVER_LETTER_SCHEMA = {
    'type': 'object',
    'properties': {'header': RESUME_CONTENT_SCHEMA['properties']['header']},
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
    """Return 'path: expected type' messages for every mismatch with the schema."""
    expected = schema.get('type')
    if value is None and expected not in ('object', 'array'):
        return []
    if expected and not _type_ok(value, expected):
        return [f'{path}: expected {expected}']
    errors = []
    if expected == 'object':
        for key, sub in schema.get('properties', {}).items():
            if key in value:
                errors += content_errors(value[key], sub, f'{path}.{key}')
    elif expected == 'array' and 'items' in schema:
        for i, item in enumerate(value):
            errors += content_errors(item, schema['items'], f'{path}[{i}]')
    return errors


def validate_document_content(kind: str, content) -> list[str]:
    schema = RESUME_CONTENT_SCHEMA if kind == 'resume' else _COVER_LETTER_SCHEMA
    return content_errors(content, schema)
