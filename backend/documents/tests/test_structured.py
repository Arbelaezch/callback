from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from pipeline.llm import client
from pipeline.llm.schemas import (
    GENERATION_SCHEMA,
    PDF_TEXT_SCHEMA,
    RESUME_CONTENT_ANALYSIS_SCHEMA,
    RESUME_CONTENT_SCHEMA,
    RESUME_LAYOUT_SCHEMA,
    SOURCE_SECTIONS_SCHEMA,
    VERIFICATION_SCHEMA,
    VOICE_PROFILE_SCHEMA,
)


def message(text='{"a": 1}', stop_reason='end_turn'):
    return NS(stop_reason=stop_reason, content=[NS(type='text', text=text)])


class CallStructuredTests(SimpleTestCase):
    def _call(self, response):
        fake = MagicMock()
        fake.messages.create.return_value = response
        with patch.object(client, '_get_client', return_value=fake):
            result = client.call_structured(
                model='m', system='s', content=[], schema={'type': 'object'}, max_tokens=10,
            )
        return result, fake.messages.create.call_args.kwargs

    def test_parses_json_and_sends_schema_without_forced_tool_choice(self):
        result, kwargs = self._call(message())
        self.assertEqual(result, {'a': 1})
        self.assertNotIn('tool_choice', kwargs)
        fmt = kwargs['output_config']['format']
        self.assertEqual(fmt['type'], 'json_schema')
        self.assertFalse(fmt['schema']['additionalProperties'])

    def test_truncated_output_raises(self):
        with self.assertRaises(ValueError):
            self._call(message(text='{"a"', stop_reason='max_tokens'))

    def test_refusal_raises(self):
        with self.assertRaises(ValueError):
            self._call(message(stop_reason='refusal'))


class StrictSchemaTests(SimpleTestCase):
    def test_every_nested_object_is_closed_and_input_is_untouched(self):
        strict = client._strict_schema(RESUME_CONTENT_ANALYSIS_SCHEMA)
        self.assertNotIn('additionalProperties', RESUME_CONTENT_ANALYSIS_SCHEMA)

        def objects(node):
            if isinstance(node, dict):
                if node.get('type') == 'object':
                    yield node
                for v in node.values():
                    yield from objects(v)
            elif isinstance(node, list):
                for v in node:
                    yield from objects(v)

        found = list(objects(strict))
        self.assertGreater(len(found), 5)
        self.assertTrue(all(o['additionalProperties'] is False for o in found))
        self.assertTrue(all(o['required'] == list(o['properties']) for o in found))

    def test_content_analysis_schema_strict_includes_new_fields(self):
        strict = client._strict_schema(RESUME_CONTENT_ANALYSIS_SCHEMA)
        self.assertEqual(strict['required'], ['content', 'source_sections'])
        content = strict['properties']['content']
        self.assertIn('additional_sections', content['required'])
        section = content['properties']['additional_sections']['items']
        entry = section['properties']['entries']['items']
        source = strict['properties']['source_sections']['items']
        for node in (strict, content, section, entry, source):
            self.assertIs(node['additionalProperties'], False)
        self.assertEqual(entry['required'], ['heading', 'detail', 'dates', 'bullets'])
        self.assertIn('additional', source['properties']['placed_in']['enum'])
        # The non-strict schema keeps additional_sections optional for stored content.
        self.assertNotIn('additional_sections', RESUME_CONTENT_SCHEMA['required'])

    def test_layout_schema_strict_keeps_margins_without_source_sections(self):
        strict = client._strict_schema(RESUME_LAYOUT_SCHEMA)
        self.assertIs(strict['additionalProperties'], False)
        self.assertIn('margins_in', strict['required'])
        self.assertIs(strict['properties']['margins_in']['additionalProperties'], False)
        self.assertNotIn('source_sections', strict['properties'])
        self.assertIn('additional', strict['properties']['section_order']['items']['enum'])


def _grammar_weight(schema):
    """Rough size of the grammar the API compiles: typed nodes plus enum values, after strict closing."""
    def walk(node):
        if isinstance(node, dict):
            own = (1 if 'type' in node else 0) + (len(node['enum']) if isinstance(node.get('enum'), list) else 0)
            return own + sum(walk(v) for v in node.values())
        if isinstance(node, list):
            return sum(walk(v) for v in node)
        return 0
    return walk(client._strict_schema(schema))


# The structured-output API rejects schemas whose compiled grammar is too large
# (400 "The compiled grammar is too large"). Verified against the real API on
# 2026-11-03: RESUME_CONTENT_ANALYSIS_SCHEMA (weight 60) compiled; the old combined
# content+layout analysis schema (weight 96) was rejected. Cap = largest passing schema.
MAX_SCHEMA_WEIGHT = 60


class SchemaSizeTests(SimpleTestCase):
    # Every schema sent through call_structured (git grep "schema=" backend/pipeline/llm).
    SENT = {
        'RESUME_CONTENT_ANALYSIS_SCHEMA': RESUME_CONTENT_ANALYSIS_SCHEMA,
        'RESUME_LAYOUT_SCHEMA': RESUME_LAYOUT_SCHEMA,
        'GENERATION_SCHEMA': GENERATION_SCHEMA,
        'VERIFICATION_SCHEMA': VERIFICATION_SCHEMA,
        'VOICE_PROFILE_SCHEMA': VOICE_PROFILE_SCHEMA,
        'PDF_TEXT_SCHEMA': PDF_TEXT_SCHEMA,
    }

    def test_sent_schemas_under_cap(self):
        for name, schema in self.SENT.items():
            with self.subTest(schema=name):
                self.assertLessEqual(_grammar_weight(schema), MAX_SCHEMA_WEIGHT)

    def test_combined_analysis_schema_over_cap(self):
        combined = {
            'type': 'object',
            'properties': {
                'content': RESUME_CONTENT_SCHEMA,
                'layout': {
                    **RESUME_LAYOUT_SCHEMA,
                    'properties': {**RESUME_LAYOUT_SCHEMA['properties'], 'source_sections': SOURCE_SECTIONS_SCHEMA},
                },
            },
            'required': ['content', 'layout'],
        }
        self.assertGreater(_grammar_weight(combined), MAX_SCHEMA_WEIGHT)
