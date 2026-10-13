from datetime import timedelta

from django.utils import timezone

from documents.models import GeneratedDocument, JobPosting
from users.models import Resume
from documents.staleness import STALE_GENERATION_ERROR, STALE_PARSE_ERROR

from .test_api import ApiTestCase


class StaleParseTests(ApiTestCase):
    def _pending(self, minutes_ago, user=None):
        resume = self._resume(user=user)
        resume.parse_status = 'pending'
        resume.parse_requested_at = timezone.now() - timedelta(minutes=minutes_ago)
        resume.save()
        return resume

    def test_stale_pending_parse_is_failed_on_list(self):
        resume = self._pending(11)
        response = self.client.get('/api/users/resumes/')
        resume.refresh_from_db()
        self.assertEqual(resume.parse_status, 'failed')
        self.assertEqual(resume.parse_error, STALE_PARSE_ERROR)
        self.assertEqual(response.data[0]['parse_status'], 'failed')

    def test_recent_pending_parse_is_untouched(self):
        resume = self._pending(1)
        self.client.get('/api/users/resumes/')
        resume.refresh_from_db()
        self.assertEqual(resume.parse_status, 'pending')

    def test_other_users_parses_untouched(self):
        resume = self._pending(11, user=self.other)
        self.client.get('/api/users/resumes/')
        resume.refresh_from_db()
        self.assertEqual(resume.parse_status, 'pending')

    def test_old_ready_and_failed_parses_are_untouched(self):
        ready = self._resume()
        failed = self._resume()
        old = timezone.now() - timedelta(minutes=30)
        Resume.objects.filter(pk=ready.pk).update(
            parse_status='ready', parse_error='', parse_requested_at=old)
        Resume.objects.filter(pk=failed.pk).update(
            parse_status='failed', parse_error='boom', parse_requested_at=old)
        self.client.get('/api/users/resumes/')
        ready.refresh_from_db()
        failed.refresh_from_db()
        self.assertEqual((ready.parse_status, ready.parse_error), ('ready', ''))
        self.assertEqual((failed.parse_status, failed.parse_error), ('failed', 'boom'))


class StaleDocumentTests(ApiTestCase):
    def _job(self, minutes_ago, user=None, status='pending'):
        job = JobPosting.objects.create(user=user or self.user, title='Dev', company='Acme', description='x')
        for kind in ('resume', 'cover_letter'):
            GeneratedDocument.objects.create(job_posting=job, kind=kind, status=status)
        GeneratedDocument.objects.filter(job_posting=job).update(
            created_at=timezone.now() - timedelta(minutes=minutes_ago),
        )
        return job

    def _statuses(self, job):
        return set(GeneratedDocument.objects.filter(job_posting=job).values_list('status', flat=True))

    def test_stale_pending_documents_are_failed_on_job_detail(self):
        job = self._job(21)
        response = self.client.get(f'/api/documents/jobs/{job.pk}/')
        self.assertEqual(response.status_code, 200)
        for doc in response.data['documents']:
            self.assertEqual(doc['status'], 'failed')
            self.assertEqual(doc['error'], STALE_GENERATION_ERROR)
        self.assertEqual(self._statuses(job), {'failed'})
        self.assertEqual(
            set(GeneratedDocument.objects.filter(job_posting=job).values_list('error', flat=True)),
            {STALE_GENERATION_ERROR},
        )

    def test_stale_pending_documents_are_failed_on_job_list(self):
        job = self._job(21)
        response = self.client.get('/api/documents/jobs/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._statuses(job), {'failed'})
        for doc in response.data[0]['documents']:
            self.assertEqual(doc['error'], STALE_GENERATION_ERROR)

    def test_recent_pending_documents_are_untouched(self):
        job = self._job(2)
        self.client.get(f'/api/documents/jobs/{job.pk}/')
        self.assertEqual(self._statuses(job), {'pending'})

    def test_ready_documents_are_untouched(self):
        job = self._job(30, status='ready')
        self.client.get('/api/documents/jobs/')
        self.assertEqual(self._statuses(job), {'ready'})

    def test_other_users_documents_untouched(self):
        job = self._job(30, user=self.other)
        self.client.get('/api/documents/jobs/')
        self.assertEqual(self._statuses(job), {'pending'})
