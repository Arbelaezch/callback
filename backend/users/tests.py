from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import Resume


class ResumeUploadTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('ada', password='x')
        self.client.force_authenticate(self.user)

    def _post(self, name, content):
        return self.client.post(
            '/api/users/resumes/',
            {'resume': SimpleUploadedFile(name, content)},
            format='multipart',
        )

    def test_uppercase_pdf_extension_uploads_and_file_is_rewound(self):
        seen = {}

        def fake_upload(file, user_id):
            seen['head'] = file.read(5)
            return 'resumes/user_1/x.pdf'

        with patch('users.views.upload_resume', side_effect=fake_upload):
            response = self._post('RESUME.PDF', b'%PDF-1.4 body')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(seen['head'], b'%PDF-')

    def test_non_pdf_content_renamed_pdf_is_rejected(self):
        with patch('users.views.upload_resume') as upload:
            response = self._post('notes.pdf', b'hello world')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], 'Resume must be a PDF.')
        self.assertFalse(Resume.objects.exists())
        upload.assert_not_called()

    def test_wrong_extension_is_rejected(self):
        response = self._post('resume.txt', b'%PDF-1.4')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Resume.objects.exists())


class AuthCookieTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('grace', password='x')

    def _assert_cleared(self, response):
        self.assertEqual(response.cookies['access_token'].value, '')
        self.assertEqual(response.cookies['refresh_token'].value, '')

    def test_failed_refresh_clears_cookies(self):
        self.client.cookies['refresh_token'] = 'garbage'
        response = self.client.post('/api/auth/token/refresh/')
        self.assertEqual(response.status_code, 401)
        self._assert_cleared(response)

    def test_missing_refresh_clears_cookies(self):
        response = self.client.post('/api/auth/token/refresh/')
        self.assertEqual(response.status_code, 401)
        self._assert_cleared(response)

    def test_logout_with_expired_access_token_succeeds(self):
        self.client.cookies['access_token'] = 'expired'
        response = self.client.post('/api/auth/logout/')
        self.assertEqual(response.status_code, 200)
        self._assert_cleared(response)

    def test_logout_blacklists_refresh_token(self):
        token = str(RefreshToken.for_user(self.user))
        self.client.cookies['refresh_token'] = token
        response = self.client.post('/api/auth/logout/')
        self.assertEqual(response.status_code, 200)
        self._assert_cleared(response)
        with self.assertRaises(TokenError):
            RefreshToken(token)

    def test_valid_refresh_sets_access_cookie(self):
        self.client.cookies['refresh_token'] = str(RefreshToken.for_user(self.user))
        response = self.client.post('/api/auth/token/refresh/')
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.cookies['access_token'].value, '')
