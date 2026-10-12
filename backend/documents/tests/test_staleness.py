from datetime import timedelta

from django.utils import timezone

from documents.staleness import STALE_PARSE_ERROR

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
