from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from documents.models import ContextSource, GeneratedDocument, JobPosting, ParsedResume
from users.models import Resume


class ApiTestCase(APITestCase):
    def setUp(self):
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
        delay.assert_called_once_with(job.pk, resume.pk)

    def test_cannot_generate_for_foreign_job(self):
        job = self._job(self.other)
        self.assertEqual(self.client.post(f'/api/documents/jobs/{job.pk}/generate/', {}).status_code, 404)

    def test_patch_saves_edits_and_marks_edited(self):
        doc = GeneratedDocument.objects.create(job_posting=self._job(), kind='cover_letter', markdown='old')
        response = self.client.patch(f'/api/documents/documents/{doc.pk}/', {'markdown': 'new'})
        self.assertEqual(response.status_code, 200)
        doc.refresh_from_db()
        self.assertEqual((doc.markdown, doc.edited), ('new', True))

    def test_patch_cannot_change_read_only_fields(self):
        doc = GeneratedDocument.objects.create(job_posting=self._job(), kind='resume')
        self.client.patch(f'/api/documents/documents/{doc.pk}/', {'status': 'ready', 'kind': 'cover_letter'})
        doc.refresh_from_db()
        self.assertEqual((doc.status, doc.kind), ('pending', 'resume'))

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

    def test_cover_letter_sample_roundtrip(self):
        url = '/api/documents/cover-letter-sample/'
        self.assertEqual(self.client.get(url).data, {'body': ''})
        self.assertEqual(self.client.put(url, {'body': 'Hello there'}, format='json').status_code, 200)
        self.assertEqual(self.client.put(url, {'body': 'Updated'}, format='json').status_code, 200)
        self.assertEqual(self.client.get(url).data, {'body': 'Updated'})
        from users.models import CoverLetterSample
        self.assertEqual(CoverLetterSample.objects.filter(user=self.user).count(), 1)

    def test_cover_letter_sample_edits_the_existing_onboarding_sample(self):
        from users.models import CoverLetterSample
        CoverLetterSample.objects.create(user=self.user, body='old', is_default=True)
        self.client.put('/api/documents/cover-letter-sample/', {'body': 'new'}, format='json')
        self.assertEqual(list(CoverLetterSample.objects.filter(user=self.user).values_list('body', flat=True)), ['new'])

    def test_cover_letter_sample_rejects_empty_body_and_other_users_samples_are_untouched(self):
        from users.models import CoverLetterSample
        theirs = CoverLetterSample.objects.create(user=self.other, body='theirs', is_default=True)
        self.assertEqual(self.client.put('/api/documents/cover-letter-sample/', {'body': '  '}, format='json').status_code, 400)
        self.client.put('/api/documents/cover-letter-sample/', {'body': 'mine'}, format='json')
        theirs.refresh_from_db()
        self.assertEqual(theirs.body, 'theirs')
