from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from callback.config import DAILY_GENERATION_LIMIT, DAILY_PARSE_LIMIT
from documents.limits import (
    DAILY_GENERATION_LIMIT_ERROR,
    DAILY_PARSE_LIMIT_ERROR,
    GENERATION_IN_FLIGHT_ERROR,
    PARSE_IN_FLIGHT_ERROR,
)
from documents.models import GeneratedDocument, JobPosting, ParsedResume, ParseRequest
from documents.staleness import STALE_GENERATION_ERROR

from .test_api import ApiTestCase


def _ago(**kwargs):
    return timezone.now() - timedelta(**kwargs)


@patch('documents.views.generate_documents_task.delay')
class GenerateLimitTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.resume = self._resume()
        ParsedResume.objects.create(user=self.user, resume=self.resume)
        self.job = self._job()

    def _job(self, user=None):
        return JobPosting.objects.create(
            user=user or self.user, title='Engineer', company='Acme', description='Django',
        )

    def _docs(self, job, status='pending', created_at=None, version=1):
        docs = [
            GeneratedDocument.objects.create(job_posting=job, kind=kind, status=status, version=version)
            for kind in ('resume', 'cover_letter')
        ]
        if created_at is not None:
            GeneratedDocument.objects.filter(pk__in=[d.pk for d in docs]).update(created_at=created_at)
        return docs

    def _generate(self, job=None):
        job = job or self.job
        return self.client.post(f'/api/documents/jobs/{job.pk}/generate/', {'resume_id': self.resume.pk})

    def test_fresh_pending_docs_return_409(self, delay):
        self._docs(self.job, created_at=_ago(minutes=1))
        response = self._generate()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['detail'], GENERATION_IN_FLIGHT_ERROR)
        self.assertEqual(GeneratedDocument.objects.filter(job_posting=self.job).count(), 2)
        delay.assert_not_called()

    def test_pending_docs_older_than_window_allow_retry(self, delay):
        self._docs(self.job, created_at=_ago(minutes=6))
        response = self._generate()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            GeneratedDocument.objects.filter(job_posting=self.job, version=2).count(), 2,
        )
        delay.assert_called_once()

    def test_stale_pending_docs_are_failed_before_guard(self, delay):
        old = self._docs(self.job, created_at=_ago(minutes=21))
        self.assertEqual(self._generate().status_code, 202)
        for doc in old:
            doc.refresh_from_db()
            self.assertEqual(doc.status, 'failed')
            self.assertEqual(doc.error, STALE_GENERATION_ERROR)

    def test_pending_docs_on_another_job_do_not_block(self, delay):
        self._docs(self._job(), created_at=_ago(minutes=1))
        self.assertEqual(self._generate().status_code, 202)

    def _fill_cap(self, user, created_at):
        for _ in range(DAILY_GENERATION_LIMIT):
            self._docs(self._job(user), status='ready', created_at=created_at)

    def test_daily_cap_returns_429(self, delay):
        self._fill_cap(self.user, _ago(hours=23))
        before = GeneratedDocument.objects.count()
        response = self._generate()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data['detail'], DAILY_GENERATION_LIMIT_ERROR)
        self.assertEqual(GeneratedDocument.objects.count(), before)
        delay.assert_not_called()

    def test_daily_cap_rolls_over_after_24_hours(self, delay):
        self._fill_cap(self.user, _ago(hours=25))
        self.assertEqual(self._generate().status_code, 202)

    def test_other_users_generations_do_not_count(self, delay):
        self._fill_cap(self.other, _ago(hours=1))
        self.assertEqual(self._generate().status_code, 202)


@patch('documents.views.parse_resume_task.delay')
class ParseLimitTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.resume = self._resume()

    def _parse(self, resume=None):
        return self.client.post(f'/api/documents/resumes/{(resume or self.resume).pk}/parse/')

    def _set_pending(self, requested_at):
        self.resume.parse_status = 'pending'
        self.resume.parse_requested_at = requested_at
        self.resume.save()

    def test_fresh_pending_parse_returns_409(self, delay):
        requested_at = _ago(minutes=1)
        self._set_pending(requested_at)
        response = self._parse()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['detail'], PARSE_IN_FLIGHT_ERROR)
        delay.assert_not_called()
        self.resume.refresh_from_db()
        self.assertEqual(self.resume.parse_requested_at, requested_at)
        self.assertFalse(ParseRequest.objects.exists())

    def test_pending_parse_older_than_window_allows_retry(self, delay):
        self._set_pending(_ago(minutes=4))
        self.assertEqual(self._parse().status_code, 202)
        delay.assert_called_once_with(self.resume.pk)

    def test_stale_pending_parse_allows_retry(self, delay):
        self._set_pending(_ago(minutes=11))
        self.assertEqual(self._parse().status_code, 202)
        self.resume.refresh_from_db()
        self.assertEqual(self.resume.parse_status, 'pending')

    def test_successful_parse_records_one_request(self, delay):
        self.assertEqual(self._parse().status_code, 202)
        requests = ParseRequest.objects.all()
        self.assertEqual(requests.count(), 1)
        self.assertEqual((requests[0].user, requests[0].resume), (self.user, self.resume))

    def test_rejected_parse_records_nothing(self, delay):
        self.assertEqual(self._parse(self._resume(user=self.other)).status_code, 404)
        self.assertEqual(self._parse(self._resume(status='pending')).status_code, 400)
        self.assertFalse(ParseRequest.objects.exists())

    def _fill_cap(self, user, created_at):
        ParseRequest.objects.bulk_create(
            [ParseRequest(user=user, resume=None) for _ in range(DAILY_PARSE_LIMIT)]
        )
        ParseRequest.objects.filter(user=user).update(created_at=created_at)

    def test_daily_cap_returns_429(self, delay):
        self._fill_cap(self.user, _ago(hours=23))
        response = self._parse()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data['detail'], DAILY_PARSE_LIMIT_ERROR)
        self.resume.refresh_from_db()
        self.assertEqual(self.resume.parse_status, 'none')
        delay.assert_not_called()

    def test_daily_cap_rolls_over_after_24_hours(self, delay):
        self._fill_cap(self.user, _ago(hours=25))
        self.assertEqual(self._parse().status_code, 202)

    def test_other_users_parses_do_not_count(self, delay):
        self._fill_cap(self.other, _ago(hours=1))
        self.assertEqual(self._parse().status_code, 202)
