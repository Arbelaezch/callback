from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from callback.config import APPLY_FAILURE_DISPATCH, APPLY_FAILURE_GENERIC
from jobs.models import Agent, Application, Search

LEGACY_RAW = 'connect to postgres://admin:s3cret@db.internal:5432 failed'


class ApplicationListFailureReasonTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='lister', email='lister@example.com', password='pw-12345-abc',
        )
        agent = Agent.objects.create(user=self.user)
        self.search = Search.objects.create(agent=agent)

    def _make(self, job_id, failure_reason):
        return Application.objects.create(
            search=self.search, job_id=job_id, job_url='https://example.com/j',
            company='Acme', role_title='Eng', status='failed',
            failure_reason=failure_reason,
        )

    def test_list_masks_legacy_raw_failure_reason(self):
        legacy = self._make('legacy', LEGACY_RAW)
        safe = self._make('safe', APPLY_FAILURE_DISPATCH)
        none = self._make('none', None)
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get('/api/jobs/applications/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        rows = data['results'] if isinstance(data, dict) else data
        by_id = {row['id']: row for row in rows}
        self.assertEqual(by_id[legacy.pk]['failure_reason'], APPLY_FAILURE_GENERIC)
        self.assertEqual(by_id[safe.pk]['failure_reason'], APPLY_FAILURE_DISPATCH)
        self.assertIsNone(by_id[none.pk]['failure_reason'])
        self.assertNotIn('s3cret', response.content.decode())
