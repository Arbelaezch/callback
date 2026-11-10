import sys
from unittest.mock import patch

from django.contrib.auth import get_user_model
from botocore.exceptions import ClientError
from django.test import TestCase, override_settings
from django.urls import reverse

from callback.config import (
    APPLY_FAILURE_AGENT, APPLY_FAILURE_DISPATCH, APPLY_FAILURE_PREPARE,
)
from jobs.models import Agent, Application, RunLog, Search
from jobs.serializers import ApplicationSerializer
from pipeline.tasks.apply_job import _apply_one
from users.models import Resume
from pipeline.tasks.daily_run import RUN_FAILED_ERROR, _run_one_search, daily_run

SECRET_MESSAGE = 'connect to postgres://admin:s3cret@db.internal:5432 failed; SELECT * FROM secrets'

# `pipeline.tasks` re-exports the `daily_run` task under the same name as the
# module, so look the module up directly to patch its globals.
DAILY_RUN_MODULE = sys.modules['pipeline.tasks.daily_run']
APPLY_JOB_MODULE = sys.modules['pipeline.tasks.apply_job']


class DailyRunFailureTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username='runner', email='runner@example.com', password='pw-12345-abc',
        )
        agent = Agent.objects.create(user=user)
        self.search = Search.objects.create(agent=agent)

    def _assert_safe(self, log):
        self.assertEqual(log.status, 'failed')
        self.assertEqual(log.error, RUN_FAILED_ERROR)
        for marker in ('s3cret', 'postgres://', 'SELECT'):
            self.assertNotIn(marker, log.error)

    def test_failed_run_stores_safe_message_not_exception_text(self):
        with patch.object(DAILY_RUN_MODULE, 'scan_jobs', side_effect=RuntimeError(SECRET_MESSAGE)):
            with self.assertLogs('pipeline.tasks.daily_run', level='ERROR') as cm:
                _run_one_search(self.search)
        self._assert_safe(RunLog.objects.get(search=self.search))
        self.assertIn('s3cret', '\n'.join(cm.output))
        self.assertIsNotNone(cm.records[0].exc_info)

    def test_failed_run_via_daily_run_task_stores_safe_message(self):
        with patch.object(DAILY_RUN_MODULE, 'scan_jobs', side_effect=RuntimeError(SECRET_MESSAGE)):
            with self.assertLogs('pipeline.tasks.daily_run', level='ERROR'):
                daily_run.run(search_id=self.search.pk)
        self._assert_safe(RunLog.objects.get(search=self.search))


class ApplyJobFailureTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username='applier', email='applier@example.com', password='pw-12345-abc',
        )
        agent = Agent.objects.create(user=user)
        self.search = Search.objects.create(agent=agent)
        self.resume = Resume.objects.create(
            user=user, s3_key='resumes/test.pdf', filename='test.pdf', status='ready',
        )
        self.job = {
            'job_id': 'job-1',
            'job_url': 'https://example.com/jobs/1',
            'company': 'Acme',
            'title': 'Engineer',
        }

    def _assert_safe(self, expected):
        app = Application.objects.get(search=self.search, job_id='job-1')
        self.assertEqual(app.status, 'failed')
        self.assertEqual(app.failure_reason, expected)
        serialized = str(ApplicationSerializer(app).data)
        for marker in ('s3cret', 'postgres://', 'SELECT'):
            self.assertNotIn(marker, app.failure_reason)
            self.assertNotIn(marker, serialized)

    def _payload_patch(self):
        return patch.object(
            APPLY_JOB_MODULE, '_build_lambda_payload', return_value={'application_id': 1},
        )

    def test_payload_build_failure(self):
        with patch.object(
            APPLY_JOB_MODULE, '_build_lambda_payload', side_effect=RuntimeError(SECRET_MESSAGE),
        ):
            with self.assertLogs('pipeline.tasks.apply_job', level='ERROR') as cm:
                result = _apply_one(self.search, self.job, self.resume)
        self.assertFalse(result)
        self._assert_safe(APPLY_FAILURE_PREPARE)
        self.assertIn('s3cret', '\n'.join(cm.output))
        self.assertTrue(any(r.exc_info for r in cm.records))

    @override_settings(USE_LAMBDA=True)
    def test_lambda_client_error(self):
        error = ClientError({'Error': {'Code': 'AccessDenied', 'Message': SECRET_MESSAGE}}, 'Invoke')
        with self._payload_patch(), patch.object(APPLY_JOB_MODULE, '_invoke_lambda', side_effect=error):
            with self.assertLogs('pipeline.tasks.apply_job', level='ERROR') as cm:
                result = _apply_one(self.search, self.job, self.resume)
        self.assertFalse(result)
        self._assert_safe(APPLY_FAILURE_DISPATCH)
        self.assertIn('s3cret', '\n'.join(cm.output))
        self.assertTrue(any(r.exc_info for r in cm.records))

    @override_settings(USE_LAMBDA=True)
    def test_lambda_runtime_error(self):
        with self._payload_patch(), patch.object(
            APPLY_JOB_MODULE, '_invoke_lambda', side_effect=RuntimeError(SECRET_MESSAGE),
        ):
            with self.assertLogs('pipeline.tasks.apply_job', level='ERROR') as cm:
                result = _apply_one(self.search, self.job, self.resume)
        self.assertFalse(result)
        self._assert_safe(APPLY_FAILURE_DISPATCH)
        self.assertTrue(any(r.exc_info for r in cm.records))

    @override_settings(USE_LAMBDA=False)
    def test_local_handler_returned_failure(self):
        with self._payload_patch(), patch.object(
            APPLY_JOB_MODULE, '_run_local', return_value=(False, SECRET_MESSAGE),
        ):
            with self.assertLogs('pipeline.tasks.apply_job', level='WARNING') as cm:
                result = _apply_one(self.search, self.job, self.resume)
        self.assertFalse(result)
        self._assert_safe(APPLY_FAILURE_AGENT)
        self.assertIn('s3cret', '\n'.join(cm.output))

    @override_settings(USE_LAMBDA=False)
    def test_local_import_error(self):
        with self._payload_patch(), patch.object(
            APPLY_JOB_MODULE, '_run_local', side_effect=ImportError(SECRET_MESSAGE),
        ):
            with self.assertLogs('pipeline.tasks.apply_job', level='ERROR') as cm:
                result = _apply_one(self.search, self.job, self.resume)
        self.assertFalse(result)
        self._assert_safe(APPLY_FAILURE_DISPATCH)
        self.assertTrue(any(r.exc_info for r in cm.records))

    @override_settings(USE_LAMBDA=False)
    def test_local_other_exception(self):
        with self._payload_patch(), patch.object(
            APPLY_JOB_MODULE, '_run_local', side_effect=ValueError(SECRET_MESSAGE),
        ):
            with self.assertLogs('pipeline.tasks.apply_job', level='ERROR'):
                result = _apply_one(self.search, self.job, self.resume)
        self.assertFalse(result)
        self._assert_safe(APPLY_FAILURE_DISPATCH)


@override_settings(CALLBACK_SECRET='test-callback-secret')
class ApplicationCallbackFailureTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username='cbuser', email='cb@example.com', password='pw-12345-abc',
        )
        agent = Agent.objects.create(user=user)
        search = Search.objects.create(agent=agent)
        self.app = Application.objects.create(
            search=search, job_id='job-cb', job_url='https://example.com/j',
            company='Acme', role_title='Eng', status='submitted',
        )
        self.url = reverse('application-callback', args=[self.app.pk])

    def _post(self, data, secret='test-callback-secret'):
        return self.client.post(
            self.url, data, content_type='application/json',
            HTTP_X_CALLBACK_SECRET=secret,
        )

    def test_failed_stores_fixed_message_and_logs_text(self):
        with self.assertLogs('pipeline.views', level='WARNING') as logs:
            response = self._post({'status': 'failed', 'failure_reason': SECRET_MESSAGE})
        self.assertEqual(response.status_code, 200)
        self.app.refresh_from_db()
        self.assertEqual(self.app.failure_reason, APPLY_FAILURE_AGENT)
        serialized = str(ApplicationSerializer(self.app).data)
        for marker in ('s3cret', 'postgres://', 'SELECT'):
            self.assertNotIn(marker, self.app.failure_reason)
            self.assertNotIn(marker, serialized)
        self.assertIn('s3cret', '\n'.join(logs.output))

    def test_failed_without_reason(self):
        response = self._post({'status': 'failed', 'failure_reason': None})
        self.assertEqual(response.status_code, 200)
        self.app.refresh_from_db()
        self.assertEqual(self.app.failure_reason, APPLY_FAILURE_AGENT)

    def test_failed_with_non_string_reason(self):
        response = self._post({'status': 'failed', 'failure_reason': {'detail': SECRET_MESSAGE}})
        self.assertEqual(response.status_code, 200)
        self.app.refresh_from_db()
        self.assertEqual(self.app.failure_reason, APPLY_FAILURE_AGENT)

    def test_submitted_does_not_write_failure_reason(self):
        response = self._post({'status': 'submitted', 'failure_reason': SECRET_MESSAGE})
        self.assertEqual(response.status_code, 200)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, 'submitted')
        self.assertIsNone(self.app.failure_reason)

    def test_wrong_secret_rejected(self):
        response = self._post({'status': 'failed', 'failure_reason': 'x'}, secret='nope')
        self.assertEqual(response.status_code, 401)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, 'submitted')
        self.assertIsNone(self.app.failure_reason)
