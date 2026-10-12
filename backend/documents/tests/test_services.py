from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from documents.models import ParsedResume
from documents.services import parse_resume
from users.models import Resume

ANALYSIS = {
    'content': {'header': {'name': 'Ada'}, 'experience': [], 'education': [], 'skills': []},
    'layout': {'page_size': 'letter', 'font_family': 'Georgia', 'base_font_size_pt': 10,
               'section_order': ['experience']},
}


class ParseResumeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('ada', password='x')

    def _resume(self, status='ready'):
        return Resume.objects.create(
            user=self.user, s3_key='resumes/user_1/a.pdf', filename='a.pdf', status=status,
        )

    @patch('documents.services.read_file', return_value=b'%PDF')
    @patch('documents.services.analyze_resume', return_value=ANALYSIS)
    def test_stores_content_and_layout(self, analyze, read):
        resume = self._resume()
        parsed = parse_resume(resume)
        read.assert_called_once_with('resumes/user_1/a.pdf')
        analyze.assert_called_once_with(b'%PDF')
        self.assertEqual(parsed.content['header']['name'], 'Ada')
        self.assertEqual(parsed.layout['font_family'], 'Georgia')

    @patch('documents.services.read_file', return_value=b'%PDF')
    @patch('documents.services.analyze_resume', return_value=ANALYSIS)
    def test_reparse_replaces_previous(self, analyze, read):
        resume = self._resume()
        parse_resume(resume)
        parse_resume(resume)
        self.assertEqual(ParsedResume.objects.filter(resume=resume).count(), 1)

    def test_rejects_resume_that_is_not_ready(self):
        with self.assertRaises(ValueError):
            parse_resume(self._resume(status='pending'))
