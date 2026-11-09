from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from documents.models import ContextSource, ParsedResume
from documents.services import (
    PARSE_FAILED_ERROR, SOURCE_FAILED_ERROR, SOURCE_NO_TEXT_ERROR, SOURCE_NOT_UTF8_ERROR,
    index_upload_source, ingest_cover_letter_sample, parse_resume,
)
from users.models import CoverLetterSample, Resume

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
        with self.assertRaises(ValueError), self.assertLogs('documents.services', level='ERROR'):
            parse_resume(resume)
        resume.refresh_from_db()
        self.assertEqual(resume.parse_status, 'failed')

    def test_parse_not_ready_stores_friendly_error(self):
        resume = self._resume(status='pending')
        with self.assertRaises(ValueError), self.assertLogs('documents.services', level='ERROR'):
            parse_resume(resume)
        resume.refresh_from_db()
        self.assertEqual(resume.parse_error, PARSE_FAILED_ERROR)
        self.assertNotIn('not ready', resume.parse_error)

    @patch('documents.services.read_file', return_value=b'%PDF')
    @patch('documents.services.analyze_resume', side_effect=RuntimeError('model said no'))
    def test_parse_failure_marks_resume_failed(self, analyze, read):
        resume = self._resume()
        with self.assertRaises(RuntimeError), self.assertLogs('documents.services', level='ERROR'):
            parse_resume(resume)
        resume.refresh_from_db()
        self.assertEqual(resume.parse_status, 'failed')
        self.assertEqual(resume.parse_error, PARSE_FAILED_ERROR)
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


class CoverLetterIngestTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('ada', password='x')
        self.other = get_user_model().objects.create_user('bob', password='x')
        self.previous = CoverLetterSample.objects.create(
            user=self.user, body='old letter', is_default=True,
        )
        self.foreign = CoverLetterSample.objects.create(
            user=self.other, body='bob letter', is_default=True,
        )

    def _sample(self, filename='letter.txt'):
        return CoverLetterSample.objects.create(
            user=self.user, s3_key='k', filename=filename, status='pending',
        )

    def _assert_untouched(self):
        self.previous.refresh_from_db()
        self.foreign.refresh_from_db()
        self.assertTrue(self.previous.is_default)
        self.assertEqual(self.previous.body, 'old letter')
        self.assertTrue(self.foreign.is_default)
        self.assertEqual(self.foreign.body, 'bob letter')

    def _assert_failed(self, sample, error):
        sample.refresh_from_db()
        self.assertEqual(sample.status, 'failed')
        self.assertEqual(sample.error, error)
        self.assertFalse(sample.is_default)
        self.assertEqual(sample.body, '')
        self._assert_untouched()

    @patch('documents.services.extract_pdf_text')
    @patch('documents.services.read_file', return_value=b'  Dear team,\n\nHello.  \n')
    def test_txt_sample_becomes_ready_default(self, read, extract):
        sample = ingest_cover_letter_sample(self._sample())
        read.assert_called_once_with('k')
        extract.assert_not_called()
        sample.refresh_from_db()
        self.assertEqual(sample.body, 'Dear team,\n\nHello.')
        self.assertEqual(sample.status, 'ready')
        self.assertEqual(sample.error, '')
        self.assertTrue(sample.is_default)
        self.previous.refresh_from_db()
        self.assertFalse(self.previous.is_default)
        self.foreign.refresh_from_db()
        self.assertTrue(self.foreign.is_default)

    @patch('documents.services.extract_pdf_text', return_value='  From the PDF.  ')
    @patch('documents.services.read_file', return_value=b'%PDF-1.7')
    def test_pdf_sample_uses_extracted_text(self, read, extract):
        sample = ingest_cover_letter_sample(self._sample('Letter.PDF'))
        extract.assert_called_once_with(b'%PDF-1.7')
        sample.refresh_from_db()
        self.assertEqual(sample.body, 'From the PDF.')
        self.assertEqual(sample.status, 'ready')
        self.assertTrue(sample.is_default)
        self.foreign.refresh_from_db()
        self.assertTrue(self.foreign.is_default)

    @patch('documents.services.read_file', return_value=b'  \n\t ')
    def test_empty_text_fails(self, read):
        sample = self._sample()
        with self.assertRaises(ValueError):
            ingest_cover_letter_sample(sample)
        self._assert_failed(sample, 'Document has no text')

    @patch('documents.services.read_file', return_value=b'x' * 15001)
    def test_too_long_text_fails(self, read):
        sample = self._sample()
        with self.assertRaises(ValueError):
            ingest_cover_letter_sample(sample)
        self._assert_failed(
            sample,
            'Cover letter is too long (over 15000 characters). Upload a single letter.',
        )

    @patch('documents.services.read_file', return_value=b'\xff\xfe\x00bad')
    def test_non_utf8_text_fails(self, read):
        sample = self._sample()
        with self.assertRaises(ValueError):
            ingest_cover_letter_sample(sample)
        self._assert_failed(sample, 'Text file must be UTF-8.')

    @patch('documents.services.extract_pdf_text', side_effect=RuntimeError('api down'))
    @patch('documents.services.read_file', return_value=b'%PDF-1.7')
    def test_pdf_extraction_failure_fails(self, read, extract):
        sample = self._sample('letter.pdf')
        with self.assertRaises(ValueError):
            ingest_cover_letter_sample(sample)
        self._assert_failed(sample, 'Could not read text from this PDF. Try a .txt file instead.')

    @patch('documents.services.read_file', side_effect=OSError('gone'))
    def test_storage_read_failure_fails_with_empty_error_and_reraises(self, read):
        sample = self._sample()
        with self.assertRaises(OSError):
            ingest_cover_letter_sample(sample)
        self._assert_failed(sample, '')


class IndexUploadSourceTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user('ada', password='x')
        self.source = ContextSource.objects.create(
            user=user, kind='upload', label='notes.md', s3_key='k',
        )

    def _error(self):
        self.source.refresh_from_db()
        self.assertEqual(self.source.status, 'failed')
        return self.source.error

    def test_read_failure_stores_friendly_error_and_logs(self):
        with patch('documents.services.read_file', side_effect=OSError('bucket secret detail')):
            with self.assertRaises(OSError), self.assertLogs('documents.services', level='ERROR'):
                index_upload_source(self.source)
        error = self._error()
        self.assertEqual(error, SOURCE_FAILED_ERROR)
        self.assertNotIn('bucket', error)

    @patch('documents.services.read_file', return_value=b'\xff\xfe\x00bad')
    def test_non_utf8_stores_utf8_message(self, read):
        with self.assertRaises(ValueError):
            index_upload_source(self.source)
        self.assertEqual(self._error(), SOURCE_NOT_UTF8_ERROR)

    @patch('documents.services.read_file', return_value=b'   ')
    def test_empty_document_stores_no_text_message(self, read):
        with self.assertRaises(ValueError):
            index_upload_source(self.source)
        self.assertEqual(self._error(), SOURCE_NO_TEXT_ERROR)

    @patch('documents.services.read_file', return_value=b'hello')
    def test_unexpected_value_error_is_not_shown(self, read):
        with patch('documents.services.split_sections', side_effect=ValueError('internal detail')):
            with self.assertRaises(ValueError), self.assertLogs('documents.services', level='ERROR'):
                index_upload_source(self.source)
        self.assertEqual(self._error(), SOURCE_FAILED_ERROR)
