from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from pipeline.llm import scout


def tool_use(name, input, id='t1'):
    return NS(type='tool_use', name=name, input=input, id=id)


def response(*blocks):
    return NS(content=list(blocks))


class ScoutTests(SimpleTestCase):
    JOB = {'title': 'Backend Engineer', 'company': 'Acme', 'description': 'Django'}

    def _client(self, *responses):
        client = MagicMock()
        client.messages.create.side_effect = list(responses)
        return client

    def test_no_handlers_skips_model_call(self):
        with patch.object(scout, '_get_client') as get_client:
            self.assertEqual(scout.run_scout(self.JOB, '', {}), {'facts': []})
        get_client.assert_not_called()

    def test_searches_then_submits_brief(self):
        brief = {'facts': [{'quote': 'Built Django app', 'source': 'notes.md', 'why_relevant': 'match'}]}
        client = self._client(
            response(tool_use('search_sections', {'query': 'django'})),
            response(tool_use('submit_brief', brief)),
        )
        search = MagicMock(return_value='[{"section_id": 1}]')
        with patch.object(scout, '_get_client', return_value=client):
            result = scout.run_scout(self.JOB, 'src', {'search_sections': search, 'read_section': MagicMock()})
        self.assertEqual(result, brief)
        search.assert_called_once_with(query='django')

        second_call = client.messages.create.call_args_list[1].kwargs['messages']
        tool_result = second_call[-1]['content'][0]
        self.assertEqual(tool_result['type'], 'tool_result')
        self.assertFalse(tool_result['is_error'])

    def test_tool_failure_is_reported_to_model_not_raised(self):
        client = self._client(
            response(tool_use('read_section', {'section_id': 9})),
            response(tool_use('submit_brief', {'facts': []})),
        )
        read = MagicMock(side_effect=RuntimeError('boom'))
        with patch.object(scout, '_get_client', return_value=client):
            scout.run_scout(self.JOB, 'src', {'read_section': read})
        result = client.messages.create.call_args_list[1].kwargs['messages'][-1]['content'][0]
        self.assertTrue(result['is_error'])

    def test_forces_submit_when_steps_run_out(self):
        looping = [response(tool_use('search_sections', {'query': 'x'})) for _ in range(scout.SCOUT_MAX_STEPS)]
        client = self._client(*looping, response(tool_use('submit_brief', {'facts': []})))
        with patch.object(scout, '_get_client', return_value=client):
            result = scout.run_scout(self.JOB, 's', {'search_sections': MagicMock(return_value='[]')})
        self.assertEqual(result, {'facts': []})
        last = client.messages.create.call_args_list[-1].kwargs
        self.assertEqual(last['tool_choice'], {'type': 'tool', 'name': 'submit_brief'})
