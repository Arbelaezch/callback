import base64
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from callback.config import (
    LLM_MAX_TOKENS_RESUME_LAYOUT,
    LLM_MAX_TOKENS_WRITER,
    LLM_MODEL_TEXT_EXTRACTION,
    LLM_MODEL_WRITER,
    LLM_TIMEOUT_SECONDS_EXTRACTION,
    LLM_TIMEOUT_SECONDS_LONG,
)
from pipeline.llm import scout
from pipeline.llm.prompts import RESUME_CONTENT_SYSTEM, RESUME_LAYOUT_SYSTEM, WRITER_SYSTEM
from pipeline.llm.resume_analysis import analyze_resume
from pipeline.llm.schemas import PDF_TEXT_SCHEMA, RESUME_CONTENT_ANALYSIS_SCHEMA, RESUME_LAYOUT_SCHEMA
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
    PDF = b'%PDF-1.4 resume'
    CONTENT = {'header': {'name': 'Ada'}, 'experience': [], 'additional_sections': [{'title': 'Awards', 'entries': []}]}
    SOURCE_SECTIONS = [{'title': 'Awards', 'placed_in': 'additional'}]
    LAYOUT = {
        'page_size': 'letter', 'font_family': 'Calibri', 'base_font_size_pt': 10.5,
        'margins_in': {'top': 0.5, 'right': 0.5, 'bottom': 0.5, 'left': 0.5},
        'section_order': ['experience', 'additional'], 'columns': 2,
    }

    def _responses(self):
        return [{'content': self.CONTENT, 'source_sections': self.SOURCE_SECTIONS}, dict(self.LAYOUT)]

    @patch('pipeline.llm.resume_analysis.call_structured')
    def test_makes_two_calls_content_then_layout(self, mock_call):
        mock_call.side_effect = self._responses()
        analyze_resume(self.PDF)
        self.assertEqual(mock_call.call_count, 2)
        first, second = (c.kwargs for c in mock_call.call_args_list)
        self.assertIs(first['schema'], RESUME_CONTENT_ANALYSIS_SCHEMA)
        self.assertIs(second['schema'], RESUME_LAYOUT_SCHEMA)
        self.assertEqual(first['max_tokens'], LLM_MAX_TOKENS_WRITER)
        self.assertEqual(second['max_tokens'], LLM_MAX_TOKENS_RESUME_LAYOUT)
        data = base64.standard_b64encode(self.PDF).decode('ascii')
        for kwargs in (first, second):
            self.assertEqual(kwargs['model'], LLM_MODEL_WRITER)
            self.assertEqual(kwargs['timeout'], LLM_TIMEOUT_SECONDS_LONG)
            block = kwargs['content'][0]
            self.assertEqual(block['type'], 'document')
            self.assertEqual(block['source']['type'], 'base64')
            self.assertEqual(block['source']['data'], data)
        self.assertEqual(first['system'], RESUME_CONTENT_SYSTEM)
        self.assertEqual(second['system'], RESUME_LAYOUT_SYSTEM)

    @patch('pipeline.llm.resume_analysis.call_structured')
    def test_merges_source_sections_into_layout(self, mock_call):
        mock_call.side_effect = self._responses()
        result = analyze_resume(self.PDF)
        self.assertEqual(result, {
            'content': self.CONTENT,
            'layout': {**self.LAYOUT, 'decorative_elements': [], 'source_sections': self.SOURCE_SECTIONS},
        })
        self.assertEqual(result['layout']['columns'], 2)

    @patch('pipeline.llm.resume_analysis.call_structured')
    def test_decorative_elements_filtered_and_ordered(self, mock_call):
        layout = {**self.LAYOUT, 'decorative_elements': ['charts', 'bogus', 'icons']}
        mock_call.side_effect = [{'content': self.CONTENT, 'source_sections': []}, layout]
        self.assertEqual(analyze_resume(self.PDF)['layout']['decorative_elements'], ['icons', 'charts'])

    @patch('pipeline.llm.resume_analysis.call_structured')
    def test_guard_drops_add_decorative_kind(self, mock_call):
        content = {**self.CONTENT, 'skills': [{'category': 'Tech', 'items': ['Python', '80%', '60%']}]}
        mock_call.side_effect = [{'content': content, 'source_sections': []}, dict(self.LAYOUT)]
        result = analyze_resume(self.PDF)
        self.assertEqual(result['layout']['decorative_elements'], ['skill_ratings'])
        self.assertEqual(result['content']['skills'][0]['items'], ['Python'])

    @patch('pipeline.llm.resume_analysis.call_structured')
    def test_single_stray_value_does_not_add_decorative_kind(self, mock_call):
        entry = {'heading': 'Spanish', 'detail': 'Native', 'bullets': ['90%']}
        content = {
            **self.CONTENT,
            'skills': [{'category': 'Tech', 'items': ['Python', 'Go ■']}],
            'additional_sections': [{'title': 'Languages', 'entries': [entry]}],
        }
        mock_call.side_effect = [{'content': content, 'source_sections': []}, dict(self.LAYOUT)]
        self.assertEqual(analyze_resume(self.PDF)['layout']['decorative_elements'], [])

    def test_decorative_prompt_phrases(self):
        self.assertIn('decorative_elements', RESUME_LAYOUT_SYSTEM)
        self.assertIn('Copy every fact exactly', RESUME_CONTENT_SYSTEM)
        self.assertIn('charts', RESUME_CONTENT_SYSTEM.lower())

    @patch('pipeline.llm.resume_analysis.call_structured')
    def test_cleans_extracted_content(self, mock_call):
        content = {**self.CONTENT, 'experience': [{'company': 'Acme, Berlin', 'location': 'Berlin'}]}
        mock_call.side_effect = [{'content': content, 'source_sections': []}, dict(self.LAYOUT)]
        result = analyze_resume(self.PDF)
        self.assertEqual(result['content']['experience'][0]['company'], 'Acme')

    @patch('pipeline.llm.resume_analysis.call_structured')
    def test_missing_source_sections_becomes_empty_list(self, mock_call):
        mock_call.side_effect = [{'content': self.CONTENT}, dict(self.LAYOUT)]
        self.assertEqual(analyze_resume(self.PDF)['layout']['source_sections'], [])

    def test_prompts_split_rules(self):
        for phrase in ('additional_sections', 'source_sections', 'Copy every fact exactly', 'do not summarise'):
            self.assertIn(phrase, RESUME_CONTENT_SYSTEM)
        for phrase in ('columns', 'margin', 'section_order', 'font_family', 'Do not transcribe the content.'):
            self.assertIn(phrase, RESUME_LAYOUT_SYSTEM)

    def test_prompts_cover_issue_32_rules(self):
        for phrase in (
            'forthe', 'location', 'degree', 'Copy every fact exactly',
            'do not summarise, correct, add or drop anything',
        ):
            self.assertIn(phrase, RESUME_CONTENT_SYSTEM)
        self.assertIn('name_style', RESUME_LAYOUT_SYSTEM)

    @patch('pipeline.llm.resume_analysis.call_structured')
    def test_layout_failure_propagates(self, mock_call):
        mock_call.side_effect = [{'content': self.CONTENT, 'source_sections': []}, ValueError('cut off')]
        with self.assertRaises(ValueError):
            analyze_resume(self.PDF)

    @patch('pipeline.llm.resume_analysis.call_structured', side_effect=ValueError('refused'))
    def test_content_failure_propagates_without_layout_call(self, mock_call):
        with self.assertRaises(ValueError):
            analyze_resume(self.PDF)
        self.assertEqual(mock_call.call_count, 1)


class WriterPromptTests(SimpleTestCase):
    def test_keeps_no_invented_facts_rules_and_additional_sections_rule(self):
        self.assertIn('Never invent employers, titles, dates, degrees, metrics', WRITER_SYSTEM)
        self.assertIn('No invented facts.', WRITER_SYSTEM)
        self.assertIn('Keep additional_sections and their titles', WRITER_SYSTEM)
        self.assertIn('never invent new ones', WRITER_SYSTEM)

    def test_keeps_never_drop_section_and_links_rule(self):
        self.assertIn('Never drop a whole section of the current resume', WRITER_SYSTEM)
        self.assertIn('keep every link or profile the user listed', WRITER_SYSTEM)
