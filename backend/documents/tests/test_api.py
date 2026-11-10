from unittest.mock import patch

from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from documents.views import (
    NO_PRIMARY_RESUME_ERROR, PRIMARY_NOT_PARSED_ERROR, RESUME_NOT_PARSED_ERROR,
)
from documents.models import ContextSource, GeneratedDocument, JobPosting, ParsedResume
from users.models import Resume


class ApiTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.user = User.objects.create_user('ada', password='x')
        self.other = User.objects.create_user('bob', password='x')
        self.client.force_authenticate(self.user)

    def _resume(self, user=None, status='ready'):
        return Resume.objects.create(user=user or self.user, s3_key='k', filename='a.pdf', status=status)


class AuthTests(APITestCase):
    def test_endpoints_require_authentication(self):
        for url in ('/api/documents/sources/', '/api/documents/jobs/'):
            self.assertEqual(self.client.get(url).status_code, 401)


class ResumeParseTests(ApiTestCase):
    @patch('documents.views.parse_resume_task.delay')
    def test_post_queues_parse(self, delay):
        resume = self._resume()
        response = self.client.post(f'/api/documents/resumes/{resume.pk}/parse/')
        self.assertEqual(response.status_code, 202)
        delay.assert_called_once_with(resume.pk)

    @patch('documents.views.parse_resume_task.delay')
    def test_cannot_parse_pending_or_foreign_resume(self, delay):
        pending = self._resume(status='pending')
        foreign = self._resume(user=self.other)
        self.assertEqual(self.client.post(f'/api/documents/resumes/{pending.pk}/parse/').status_code, 400)
        self.assertEqual(self.client.post(f'/api/documents/resumes/{foreign.pk}/parse/').status_code, 404)
        delay.assert_not_called()

    @patch('documents.views.parse_resume_task.delay')
    def test_post_marks_parse_pending(self, delay):
        resume = self._resume()
        resume.parse_status = 'failed'
        resume.parse_error = 'old error'
        resume.save()
        response = self.client.post(f'/api/documents/resumes/{resume.pk}/parse/')
        self.assertEqual(response.status_code, 202)
        resume.refresh_from_db()
        self.assertEqual(resume.parse_status, 'pending')
        self.assertEqual(resume.parse_error, '')
        self.assertIsNotNone(resume.parse_requested_at)

    @patch('documents.views.parse_resume_task.delay', side_effect=Exception('broker down'))
    def test_post_returns_503_when_queueing_fails(self, delay):
        resume = self._resume()
        response = self.client.post(f'/api/documents/resumes/{resume.pk}/parse/')
        self.assertEqual(response.status_code, 503)
        resume.refresh_from_db()
        self.assertEqual(resume.parse_status, 'failed')

    def test_resume_list_exposes_parse_status(self):
        resume = self._resume()
        resume.parse_status = 'failed'
        resume.parse_error = 'boom'
        resume.save()
        response = self.client.get('/api/users/resumes/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['parse_status'], 'failed')
        self.assertEqual(response.data[0]['parse_error'], 'boom')
        self.assertIn('parse_requested_at', response.data[0])

    def test_get_returns_parsed_content(self):
        resume = self._resume()
        ParsedResume.objects.create(user=self.user, resume=resume, content={'header': {'name': 'Ada'}})
        response = self.client.get(f'/api/documents/resumes/{resume.pk}/parse/')
        self.assertEqual(response.data['content']['header']['name'], 'Ada')
        self.assertEqual(response.data['layout_notices'], [])


class SourceTests(ApiTestCase):
    def _upload(self, name='projects.md', data=b'# Callback\nDjango app', **extra):
        return self.client.post(
            '/api/documents/sources/',
            {'file': SimpleUploadedFile(name, data), **extra},
            format='multipart',
        )

    @patch('documents.services.read_file', return_value=b'# Callback\nDjango app')
    @patch('documents.views.upload_context_document', return_value='context/user_1/x.md')
    def test_upload_indexes_document(self, upload, read):
        response = self._upload()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'ready')
        self.assertEqual(ContextSource.objects.get().sections.count(), 1)

    def test_rejects_unsupported_extension_and_kind(self):
        self.assertEqual(self._upload(name='notes.exe').status_code, 400)
        response = self.client.post('/api/documents/sources/', {'kind': 'git', 'url': 'https://x'})
        self.assertEqual(response.status_code, 400)

    @patch('documents.services.read_file', return_value=b'   ')
    @patch('documents.views.upload_context_document', return_value='context/user_1/x.md')
    def test_empty_document_reports_failure(self, upload, read):
        response = self._upload(data=b'   ')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(ContextSource.objects.get().status, 'failed')

    @patch('documents.views.delete_resume')
    def test_delete_only_own_source(self, delete):
        mine = ContextSource.objects.create(user=self.user, kind='upload', s3_key='k')
        theirs = ContextSource.objects.create(user=self.other, kind='upload', s3_key='k2')
        self.assertEqual(self.client.delete(f'/api/documents/sources/{theirs.pk}/').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/documents/sources/{mine.pk}/').status_code, 204)
        delete.assert_called_once_with('k')


class JobAndGenerationTests(ApiTestCase):
    def _job(self, user=None):
        return JobPosting.objects.create(
            user=user or self.user, title='Engineer', company='Acme', description='Django',
        )

    def test_create_and_list_own_jobs_only(self):
        self._job(self.other)
        response = self.client.post('/api/documents/jobs/', {
            'title': 'Engineer', 'company': 'Acme', 'description': 'Django',
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(self.client.get('/api/documents/jobs/').data), 1)

    @patch('documents.views.generate_documents_task.delay')
    def test_generate_requires_parsed_resume(self, delay):
        job, resume = self._job(), self._resume()
        url = f'/api/documents/jobs/{job.pk}/generate/'
        self.assertEqual(self.client.post(url, {'resume_id': resume.pk}).status_code, 400)
        ParsedResume.objects.create(user=self.user, resume=resume)
        self.assertEqual(self.client.post(url, {'resume_id': resume.pk}).status_code, 202)
        docs = GeneratedDocument.objects.filter(job_posting=job)
        self.assertEqual(docs.count(), 2)
        self.assertEqual(set(docs.values_list('status', flat=True)), {'pending'})
        self.assertEqual(set(docs.values_list('resume_id', flat=True)), {resume.pk})
        self.assertEqual(set(docs.values_list('version', flat=True)), {1})
        resume_doc = docs.get(kind='resume')
        letter_doc = docs.get(kind='cover_letter')
        delay.assert_called_once_with(resume_doc.pk, letter_doc.pk)

    def _primary(self, user=None, status='ready', parsed=True):
        resume = self._resume(user=user, status=status)
        resume.is_default = True
        resume.save()
        if parsed:
            ParsedResume.objects.create(user=resume.user, resume=resume)
        return resume

    @patch('documents.views.generate_documents_task.delay')
    def test_generate_without_resume_id_uses_primary(self, delay):
        job, other_resume = self._job(), self._resume()
        ParsedResume.objects.create(user=self.user, resume=other_resume)
        primary = self._primary()
        response = self.client.post(f'/api/documents/jobs/{job.pk}/generate/', {}, format='json')
        self.assertEqual(response.status_code, 202)
        docs = GeneratedDocument.objects.filter(job_posting=job)
        self.assertEqual(docs.count(), 2)
        self.assertEqual(set(docs.values_list('resume_id', flat=True)), {primary.pk})

    @patch('documents.views.generate_documents_task.delay')
    def test_generate_explicit_resume_id_overrides_primary(self, delay):
        job, other_resume = self._job(), self._resume()
        ParsedResume.objects.create(user=self.user, resume=other_resume)
        self._primary()
        response = self.client.post(
            f'/api/documents/jobs/{job.pk}/generate/', {'resume_id': other_resume.pk}, format='json',
        )
        self.assertEqual(response.status_code, 202)
        docs = GeneratedDocument.objects.filter(job_posting=job)
        self.assertEqual(docs.count(), 2)
        self.assertEqual(set(docs.values_list('resume_id', flat=True)), {other_resume.pk})

    @patch('documents.views.generate_documents_task.delay')
    def test_generate_without_resume_id_requires_primary(self, delay):
        job, resume = self._job(), self._resume()
        ParsedResume.objects.create(user=self.user, resume=resume)
        response = self.client.post(f'/api/documents/jobs/{job.pk}/generate/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], NO_PRIMARY_RESUME_ERROR)
        self.assertFalse(GeneratedDocument.objects.filter(job_posting=job).exists())

    @patch('documents.views.generate_documents_task.delay')
    def test_generate_without_resume_id_ignores_non_ready_primary(self, delay):
        job = self._job()
        self._primary(status='pending')
        response = self.client.post(f'/api/documents/jobs/{job.pk}/generate/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], NO_PRIMARY_RESUME_ERROR)

    @patch('documents.views.generate_documents_task.delay')
    def test_generate_without_resume_id_requires_parsed_primary(self, delay):
        job = self._job()
        self._primary(parsed=False)
        response = self.client.post(f'/api/documents/jobs/{job.pk}/generate/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], PRIMARY_NOT_PARSED_ERROR)

    @patch('documents.views.generate_documents_task.delay')
    def test_generate_primary_is_scoped_to_user(self, delay):
        job = self._job()
        self._primary(user=self.other)
        response = self.client.post(f'/api/documents/jobs/{job.pk}/generate/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], NO_PRIMARY_RESUME_ERROR)

    @patch('documents.views.generate_documents_task.delay')
    def test_generate_rejects_non_ready_resume_id(self, delay):
        job, resume = self._job(), self._resume(status='failed')
        ParsedResume.objects.create(user=self.user, resume=resume)
        response = self.client.post(f'/api/documents/jobs/{job.pk}/generate/', {'resume_id': resume.pk})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], RESUME_NOT_PARSED_ERROR)

    @patch('documents.views.generate_documents_task.delay')
    def test_generate_rejects_non_numeric_resume_id(self, delay):
        job = self._job()
        response = self.client.post(f'/api/documents/jobs/{job.pk}/generate/', {'resume_id': 'abc'})
        self.assertEqual(response.status_code, 400)

    @patch('documents.views.generate_documents_task.delay', side_effect=Exception('broker down'))
    def test_generate_returns_503_and_fails_rows_when_queueing_fails(self, delay):
        job, resume = self._job(), self._resume()
        ParsedResume.objects.create(user=self.user, resume=resume)
        response = self.client.post(f'/api/documents/jobs/{job.pk}/generate/', {'resume_id': resume.pk})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['detail'], 'Could not start generation. Please try again.')
        docs = GeneratedDocument.objects.filter(job_posting=job)
        self.assertEqual(docs.count(), 2)
        self.assertEqual(set(docs.values_list('status', flat=True)), {'failed'})
        self.assertEqual(
            set(docs.values_list('error', flat=True)),
            {'Could not start generation. Please try again.'},
        )

    @patch('documents.views.generate_documents_task.delay')
    def test_generate_again_increments_version(self, delay):
        job, resume = self._job(), self._resume()
        ParsedResume.objects.create(user=self.user, resume=resume)
        url = f'/api/documents/jobs/{job.pk}/generate/'
        self.assertEqual(self.client.post(url, {'resume_id': resume.pk}).status_code, 202)
        GeneratedDocument.objects.filter(job_posting=job).update(status='ready')
        self.assertEqual(self.client.post(url, {'resume_id': resume.pk}).status_code, 202)
        for kind in ('resume', 'cover_letter'):
            versions = set(GeneratedDocument.objects.filter(job_posting=job, kind=kind).values_list('version', flat=True))
            self.assertEqual(versions, {1, 2})

    def test_job_detail_exposes_document_resume(self):
        job, resume = self._job(), self._resume()
        GeneratedDocument.objects.create(job_posting=job, kind='resume', resume=resume)
        response = self.client.get(f'/api/documents/jobs/{job.pk}/')
        self.assertEqual(response.data['documents'][0]['resume'], resume.pk)

    def test_cannot_generate_for_foreign_job(self):
        job = self._job(self.other)
        self.assertEqual(self.client.post(f'/api/documents/jobs/{job.pk}/generate/', {}).status_code, 404)

    def test_patch_saves_edits_and_marks_edited(self):
        doc = GeneratedDocument.objects.create(
            job_posting=self._job(), kind='cover_letter', markdown='old', status='ready',
        )
        response = self.client.patch(f'/api/documents/documents/{doc.pk}/', {'markdown': 'new'})
        self.assertEqual(response.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual((doc.markdown, doc.edited), ('new', True))

    def test_patch_cannot_change_read_only_fields(self):
        doc = GeneratedDocument.objects.create(job_posting=self._job(), kind='resume', status='ready')
        self.client.patch(f'/api/documents/documents/{doc.pk}/', {'status': 'failed', 'kind': 'cover_letter'})
        doc.refresh_from_db()
        self.assertEqual((doc.status, doc.kind), ('ready', 'resume'))

    def test_patch_on_pending_or_failed_document_returns_409(self):
        job = self._job()
        for doc_status in ('pending', 'failed'):
            doc = GeneratedDocument.objects.create(
                job_posting=job, kind='cover_letter', markdown='old', status=doc_status,
            )
            response = self.client.patch(f'/api/documents/documents/{doc.pk}/', {'markdown': 'new'})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.data['detail'], 'Document is not ready.')
            doc.refresh_from_db()
            self.assertEqual((doc.markdown, doc.edited), ('old', False))

    def test_patch_with_malformed_content_returns_400_and_does_not_save(self):
        doc = GeneratedDocument.objects.create(
            job_posting=self._job(), kind='resume', status='ready', content={'summary': 'old'},
        )
        response = self.client.patch(
            f'/api/documents/documents/{doc.pk}/', {'content': ['x']}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['content'], ['content: expected object'])
        doc.refresh_from_db()
        self.assertEqual((doc.content, doc.edited), ({'summary': 'old'}, False))

    def _valid_resume_content(self):
        return {'header': {'name': 'Ada'}, 'summary': 'old', 'experience': [],
                'projects': [], 'education': [], 'skills': []}

    def test_patch_resume_content_with_unknown_or_missing_keys_returns_400_and_does_not_save(self):
        original = self._valid_resume_content()
        doc = GeneratedDocument.objects.create(
            job_posting=self._job(), kind='resume', status='ready', content=original,
        )
        url = f'/api/documents/documents/{doc.pk}/'
        missing_skills = {k: v for k, v in original.items() if k != 'skills'}
        for content, expected in (
            ({**original, 'foo': 1}, ['content.foo: unknown field']),
            (missing_skills, ['content.skills: required']),
        ):
            response = self.client.patch(url, {'content': content}, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data['content'], expected)
            doc.refresh_from_db()
            self.assertEqual((doc.content, doc.edited), (original, False))

    def test_patch_cover_letter_content_is_validated(self):
        doc = GeneratedDocument.objects.create(
            job_posting=self._job(), kind='cover_letter', status='ready',
            content={'header': {'name': 'Ada'}}, markdown='old',
        )
        url = f'/api/documents/documents/{doc.pk}/'
        response = self.client.patch(
            url, {'content': {'header': {'name': 'Ada'}, 'body': 'x'}, 'markdown': 'new'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['content'], ['content.body: unknown field'])
        doc.refresh_from_db()
        self.assertEqual((doc.markdown, doc.edited, doc.content), ('old', False, {'header': {'name': 'Ada'}}))
        response = self.client.patch(url, {'content': {'header': {'name': 'Grace'}}}, format='json')
        self.assertEqual(response.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.content['header']['name'], 'Grace')

    def test_patch_accepts_full_resume_content_from_editor(self):
        doc = GeneratedDocument.objects.create(
            job_posting=self._job(), kind='resume', status='ready', content=self._valid_resume_content(),
        )
        content = {
            'header': {'name': 'Ada', 'headline': 'Eng', 'email': 'a@b.c', 'phone': '1',
                       'location': 'NYC', 'links': []},
            'summary': 'Hello',
            'experience': [{'company': 'Acme', 'title': 'Dev', 'location': '', 'start': '',
                            'end': '', 'bullets': ['x']}],
            'projects': [],
            'education': [{'school': 'MIT', 'degree': '', 'start': '', 'end': '', 'details': []}],
            'skills': [{'category': '', 'items': ['Python']}],
        }
        response = self.client.patch(f'/api/documents/documents/{doc.pk}/', {'content': content}, format='json')
        self.assertEqual(response.status_code, 200)
        doc.refresh_from_db()
        self.assertTrue(doc.edited)

    def test_cannot_read_foreign_document(self):
        doc = GeneratedDocument.objects.create(job_posting=self._job(self.other), kind='resume')
        self.assertEqual(self.client.get(f'/api/documents/documents/{doc.pk}/').status_code, 404)


class RenderEndpointTests(ApiTestCase):
    def _doc(self, user=None, kind='resume', status='ready'):
        job = JobPosting.objects.create(
            user=user or self.user, title='Engineer', company='Acme', description='x',
        )
        return GeneratedDocument.objects.create(
            job_posting=job, kind=kind, status=status,
            content={'header': {'name': 'Ada'}, 'summary': 'Hello', 'experience': [],
                     'education': [], 'skills': []},
            markdown='Dear team',
        )

    def test_export_returns_pdf_with_page_count(self):
        doc = self._doc()
        response = self.client.get(f'/api/documents/documents/{doc.pk}/export/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertEqual(response['X-Page-Count'], '1')
        self.assertIn('resume.pdf', response['Content-Disposition'])

    def test_cover_letter_export_and_preview(self):
        doc = self._doc(kind='cover_letter')
        self.assertIn('cover-letter.pdf', self.client.get(f'/api/documents/documents/{doc.pk}/export/')['Content-Disposition'])
        preview = self.client.get(f'/api/documents/documents/{doc.pk}/preview/')
        self.assertIn('text/html', preview['Content-Type'])
        self.assertIn('Dear team', preview.content.decode())

    def test_not_ready_and_foreign_documents_are_refused(self):
        pending = self._doc(status='pending')
        foreign = self._doc(user=self.other)
        self.assertEqual(self.client.get(f'/api/documents/documents/{pending.pk}/export/').status_code, 409)
        self.assertEqual(self.client.get(f'/api/documents/documents/{foreign.pk}/export/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/documents/documents/{foreign.pk}/preview/').status_code, 404)

    def test_document_detail_includes_layout_notices_for_resume_only(self):
        resume_doc = self._doc()
        resume_doc.layout = {'columns': 2}
        resume_doc.save()
        letter = self._doc(kind='cover_letter')
        letter.layout = {'columns': 2}
        letter.save()
        got = self.client.get(f'/api/documents/documents/{resume_doc.pk}/')
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.data['layout_notices'][0]['code'], 'columns_simplified')
        self.assertEqual(self.client.get(f'/api/documents/documents/{letter.pk}/').data['layout_notices'], [])

    def test_document_detail_includes_decorative_notice(self):
        doc = self._doc()
        doc.layout = {'decorative_elements': ['charts']}
        doc.save()
        got = self.client.get(f'/api/documents/documents/{doc.pk}/')
        self.assertIn('decorative_dropped', [n['code'] for n in got.data['layout_notices']])

    def test_export_reflects_user_edits(self):
        doc = self._doc()
        self.client.patch(f'/api/documents/documents/{doc.pk}/', {
            'content': {'header': {'name': 'Ada'}, 'summary': 'Edited summary', 'experience': [],
                        'education': [], 'skills': []},
        }, format='json')
        preview = self.client.get(f'/api/documents/documents/{doc.pk}/preview/')
        self.assertIn('Edited summary', preview.content.decode())


class ProfileEndpointTests(ApiTestCase):
    def test_parsed_resume_list_is_scoped_and_omits_content(self):
        mine = ParsedResume.objects.create(user=self.user, resume=self._resume(), content={'big': 1})
        ParsedResume.objects.create(user=self.other, resume=self._resume(user=self.other))
        response = self.client.get('/api/documents/resumes/parsed/')
        self.assertEqual([row['id'] for row in response.data], [mine.pk])
        self.assertNotIn('content', response.data[0])
        self.assertEqual(response.data[0]['layout_notices'], [])

    def test_parsed_resume_list_includes_layout_notices(self):
        ParsedResume.objects.create(
            user=self.user, resume=self._resume(), content={}, layout={'columns': 2},
        )
        response = self.client.get('/api/documents/resumes/parsed/')
        self.assertEqual([n['code'] for n in response.data[0]['layout_notices']], ['columns_simplified'])


COVER_LETTER_URL = '/api/documents/cover-letter-sample/'


@patch('documents.services.extract_pdf_text')
@patch('documents.services.read_file')
@patch('documents.views.upload_cover_letter_sample', return_value='k')
class CoverLetterSampleUploadTests(ApiTestCase):
    def _post(self, name='letter.txt', data=b'Dear team,\n\nHello.'):
        return self.client.post(COVER_LETTER_URL, {'file': SimpleUploadedFile(name, data)}, format='multipart')

    def _sample(self, user=None, **kwargs):
        from users.models import CoverLetterSample
        return CoverLetterSample.objects.create(user=user or self.user, **kwargs)

    def _rows(self, user=None):
        from users.models import CoverLetterSample
        return CoverLetterSample.objects.filter(user=user or self.user)

    def test_txt_upload_becomes_the_ready_default_and_get_returns_it(self, upload, read_file, extract):
        read_file.return_value = b'  Dear team,\n\nHello.  '
        old = self._sample(body='old', is_default=True)
        response = self._post()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['body'], 'Dear team,\n\nHello.')
        self.assertEqual(response.data['filename'], 'letter.txt')
        self.assertTrue(response.data['updated_at'])
        sample = self._rows().get(filename='letter.txt')
        self.assertEqual((sample.status, sample.is_default, sample.s3_key), ('ready', True, 'k'))
        old.refresh_from_db()
        self.assertFalse(old.is_default)
        self.assertEqual(self.client.get(COVER_LETTER_URL).data, response.data)
        extract.assert_not_called()

    def test_pdf_upload_uses_extracted_text(self, upload, read_file, extract):
        read_file.return_value = b'%PDF-1.4 bytes'
        extract.return_value = 'From the PDF.'
        response = self._post('letter.pdf', b'%PDF-1.4 bytes')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['body'], 'From the PDF.')
        extract.assert_called_once_with(b'%PDF-1.4 bytes')

    def test_invalid_files_return_400_and_create_no_row(self, upload, read_file, extract):
        cases = [
            (lambda: self.client.post(COVER_LETTER_URL, {}, format='multipart'), 'No file provided.'),
            (lambda: self._post('letter.docx', b'x'), 'File must be one of: .pdf, .txt.'),
            (lambda: self._post('letter.pdf', b'not a pdf'), 'File is not a valid PDF.'),
        ]
        for send, detail in cases:
            response = send()
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data['detail'], detail)
        with patch('documents.views.COVER_LETTER_UPLOAD_MAX_BYTES', 3):
            response = self._post('letter.txt', b'four')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], 'File is too large.')
        self.assertFalse(self._rows().exists())
        upload.assert_not_called()

    def test_empty_text_returns_422_and_keeps_the_previous_sample(self, upload, read_file, extract):
        read_file.return_value = b'   '
        self._sample(body='kept', filename='old.txt', is_default=True)
        response = self._post()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data['detail'], 'Document has no text')
        self.assertEqual(self.client.get(COVER_LETTER_URL).data['body'], 'kept')
        self.assertEqual(self._rows().get(filename='letter.txt').status, 'failed')

    def test_storage_failure_returns_500_and_marks_the_row_failed(self, upload, read_file, extract):
        upload.side_effect = OSError('disk full')
        response = self._post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data['detail'], 'Upload failed. Please try again.')
        sample = self._rows().get()
        self.assertEqual(sample.status, 'failed')
        self.assertFalse(sample.is_default)

    def test_storage_read_failure_returns_500(self, upload, read_file, extract):
        read_file.side_effect = OSError('missing')
        response = self._post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self._rows().get().status, 'failed')

    def test_put_is_not_allowed(self, upload, read_file, extract):
        response = self.client.put(COVER_LETTER_URL, {'body': 'pasted'}, format='json')
        self.assertEqual(response.status_code, 405)
        self.assertFalse(self._rows().exists())

    def test_get_ignores_pending_and_failed_rows(self, upload, read_file, extract):
        empty = {'body': '', 'filename': '', 'updated_at': None}
        self.assertEqual(self.client.get(COVER_LETTER_URL).data, empty)
        self._sample(body='', status='pending')
        self._sample(body='broken', status='failed', error='Document has no text')
        self.assertEqual(self.client.get(COVER_LETTER_URL).data, empty)
        self._sample(body='good', status='ready', is_default=True)
        self._sample(body='', status='pending')
        self.assertEqual(self.client.get(COVER_LETTER_URL).data['body'], 'good')

    def test_other_users_sample_is_never_returned_or_changed(self, upload, read_file, extract):
        theirs = self._sample(user=self.other, body='theirs', is_default=True)
        self.assertEqual(self.client.get(COVER_LETTER_URL).data['body'], '')
        read_file.return_value = b'mine'
        self.assertEqual(self._post().status_code, 201)
        theirs.refresh_from_db()
        self.assertTrue(theirs.is_default)
        self.assertEqual(theirs.body, 'theirs')
        self.assertEqual(self.client.get(COVER_LETTER_URL).data['body'], 'mine')

    def test_requires_authentication(self, upload, read_file, extract):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(COVER_LETTER_URL).status_code, 401)
        self.assertEqual(self._post().status_code, 401)
        self.assertFalse(self._rows().exists())
