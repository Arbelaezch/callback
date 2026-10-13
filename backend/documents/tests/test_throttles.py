from unittest.mock import patch

from users.models import Resume

from .test_api import ApiTestCase
from documents.models import JobPosting, ParsedResume


class ScopedThrottleTests(ApiTestCase):
    @patch('documents.views.parse_resume_task.delay')
    def test_parse_post_throttled_after_ten(self, delay):
        resumes = [self._resume() for _ in range(11)]
        for r in resumes[:10]:
            self.assertEqual(self.client.post(f'/api/documents/resumes/{r.pk}/parse/').status_code, 202)
        response = self.client.post(f'/api/documents/resumes/{resumes[10].pk}/parse/')
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.data['detail'].startswith('Too many requests.'))
        self.assertIn('Retry-After', response)

    @patch('documents.views.parse_resume_task.delay')
    def test_parse_get_never_throttled(self, delay):
        resumes = [self._resume() for _ in range(11)]
        for r in resumes:
            self.client.post(f'/api/documents/resumes/{r.pk}/parse/')
        response = self.client.get(f'/api/documents/resumes/{resumes[0].pk}/parse/')
        self.assertIn(response.status_code, (200, 404))

    @patch('documents.views.parse_resume_task.delay')
    def test_other_user_unaffected(self, delay):
        resumes = [self._resume() for _ in range(11)]
        for r in resumes:
            self.client.post(f'/api/documents/resumes/{r.pk}/parse/')
        self.client.force_authenticate(self.other)
        theirs = self._resume(user=self.other)
        self.assertEqual(self.client.post(f'/api/documents/resumes/{theirs.pk}/parse/').status_code, 202)

    @patch('documents.views.generate_documents_task.delay')
    def test_generate_post_throttled_after_ten(self, delay):
        resume = self._resume()
        ParsedResume.objects.create(resume=resume, user=self.user, content={}, layout={})
        jobs = [
            JobPosting.objects.create(user=self.user, title=f'J{i}', company='C', description='d')
            for i in range(11)
        ]
        for j in jobs[:10]:
            response = self.client.post(f'/api/documents/jobs/{j.pk}/generate/', {'resume_id': resume.pk})
            self.assertEqual(response.status_code, 202, response.data)
        response = self.client.post(f'/api/documents/jobs/{jobs[10].pk}/generate/', {'resume_id': resume.pk})
        self.assertEqual(response.status_code, 429)
