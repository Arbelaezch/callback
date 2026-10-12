from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from pipeline.llm import client
from pipeline.llm.schemas import RESUME_ANALYSIS_SCHEMA


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
        fmt = kwargs['extra_body']['output_config']['format']
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
        strict = client._strict_schema(RESUME_ANALYSIS_SCHEMA)
        self.assertNotIn('additionalProperties', RESUME_ANALYSIS_SCHEMA)

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
