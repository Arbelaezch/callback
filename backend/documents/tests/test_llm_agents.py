import base64
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from callback.config import (
    LLM_MODEL_TEXT_EXTRACTION,
    LLM_MODEL_WRITER,
    LLM_TIMEOUT_SECONDS_EXTRACTION,
)
from pipeline.llm import scout
from pipeline.llm.prompts import WRITER_SYSTEM
from pipeline.llm.resume_analysis import analyze_resume
from pipeline.llm.schemas import PDF_TEXT_SCHEMA, RESUME_ANALYSIS_SCHEMA
from pipeline.llm.text_extraction import extract_pdf_text


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


class PdfTextExtractionTests(SimpleTestCase):
    @patch('pipeline.llm.text_extraction.call_structured')
    def test_sends_pdf_as_document_block_and_returns_stripped_text(self, mock_call):
        mock_call.return_value = {'text': '  Dear team,\n\nHello.  '}
        result = extract_pdf_text(b'%PDF-1.4 data')
        self.assertEqual(result, 'Dear team,\n\nHello.')
        kwargs = mock_call.call_args.kwargs
        self.assertEqual(kwargs['model'], LLM_MODEL_TEXT_EXTRACTION)
        self.assertIs(kwargs['schema'], PDF_TEXT_SCHEMA)
        self.assertEqual(kwargs['timeout'], LLM_TIMEOUT_SECONDS_EXTRACTION)
        self.assertEqual(kwargs['max_retries'], 0)
        block = kwargs['content'][0]
        self.assertEqual(block['type'], 'document')
        self.assertEqual(block['source']['data'], base64.standard_b64encode(b'%PDF-1.4 data').decode('ascii'))

    @patch('pipeline.llm.text_extraction.call_structured', side_effect=ValueError('bad'))
    def test_propagates_structured_output_errors(self, _mock):
        with self.assertRaises(ValueError):
            extract_pdf_text(b'%PDF-')


class AnalyzeResumeTests(SimpleTestCase):
    @patch('pipeline.llm.resume_analysis.call_structured')
    def test_sends_pdf_with_analysis_schema_and_section_rules(self, mock_call):
        mock_call.return_value = {'content': {'experience': []}, 'layout': {}}
        result = analyze_resume(b'%PDF-1.4 resume')
        self.assertEqual(result, mock_call.return_value)
        kwargs = mock_call.call_args.kwargs
        self.assertEqual(kwargs['model'], LLM_MODEL_WRITER)
        self.assertIs(kwargs['schema'], RESUME_ANALYSIS_SCHEMA)
        block = kwargs['content'][0]
        self.assertEqual(block['type'], 'document')
        self.assertEqual(block['source']['type'], 'base64')
        self.assertEqual(block['source']['data'], base64.standard_b64encode(b'%PDF-1.4 resume').decode('ascii'))
        for phrase in ('additional_sections', 'source_sections', 'columns', 'Copy every fact exactly'):
            self.assertIn(phrase, kwargs['system'])


class WriterPromptTests(SimpleTestCase):
    def test_keeps_no_invented_facts_rules_and_additional_sections_rule(self):
        self.assertIn('Never invent employers, titles, dates, degrees, metrics', WRITER_SYSTEM)
        self.assertIn('No invented facts.', WRITER_SYSTEM)
        self.assertIn('Keep additional_sections and their titles', WRITER_SYSTEM)
        self.assertIn('never invent new ones', WRITER_SYSTEM)
