import sys
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from jobs.models import Agent, RunLog, Search
from pipeline.tasks.daily_run import RUN_FAILED_ERROR, _run_one_search, daily_run

SECRET_MESSAGE = 'connect to postgres://admin:s3cret@db.internal:5432 failed; SELECT * FROM secrets'

# `pipeline.tasks` re-exports the `daily_run` task under the same name as the
# module, so look the module up directly to patch its globals.
DAILY_RUN_MODULE = sys.modules['pipeline.tasks.daily_run']


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
