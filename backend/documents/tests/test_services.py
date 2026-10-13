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
        resume = self._resume(status='pending')
        with self.assertRaises(ValueError):
            parse_resume(resume)
        resume.refresh_from_db()
        self.assertEqual(resume.parse_status, 'failed')

    @patch('documents.services.read_file', return_value=b'%PDF')
    @patch('documents.services.analyze_resume', side_effect=RuntimeError('model said no'))
    def test_parse_failure_marks_resume_failed(self, analyze, read):
        resume = self._resume()
        with self.assertRaises(RuntimeError):
            parse_resume(resume)
        resume.refresh_from_db()
        self.assertEqual(resume.parse_status, 'failed')
        self.assertEqual(resume.parse_error, 'model said no')
        self.assertFalse(ParsedResume.objects.filter(resume=resume).exists())

    @patch('documents.services.read_file', return_value=b'%PDF')
    @patch('documents.services.analyze_resume', return_value=ANALYSIS)
    def test_parse_success_marks_resume_ready(self, analyze, read):
        resume = self._resume()
        resume.parse_status = 'pending'
        resume.parse_error = 'old'
        resume.save()
        parse_resume(resume)
        resume.refresh_from_db()
        self.assertEqual(resume.parse_status, 'ready')
        self.assertEqual(resume.parse_error, '')


    @patch('documents.services.read_file', return_value=b'%PDF')
    @patch('documents.services.analyze_resume', return_value=ANALYSIS)
    def test_parse_does_not_clear_a_newer_default(self, analyze, read):
        a = Resume.objects.create(
            user=self.user, s3_key='a', filename='a.pdf', status='ready', is_default=True,
        )
        stale_a = Resume.objects.get(pk=a.pk)
        b = Resume.objects.create(
            user=self.user, s3_key='b', filename='b.pdf', status='ready', is_default=True,
        )
        parse_resume(stale_a)
        b.refresh_from_db()
        a.refresh_from_db()
        self.assertTrue(b.is_default)
        self.assertFalse(a.is_default)
        self.assertEqual(a.parse_status, 'ready')

    @patch('documents.services.read_file', return_value=b'%PDF')
    @patch('documents.services.analyze_resume')
    def test_parse_reraises_original_error_when_resume_deleted_mid_parse(self, analyze, read):
        resume = self._resume()

        def delete_then_fail(_):
            Resume.objects.filter(pk=resume.pk).delete()
            raise RuntimeError('model said no')

        analyze.side_effect = delete_then_fail
        with self.assertRaises(RuntimeError):
            parse_resume(resume)
