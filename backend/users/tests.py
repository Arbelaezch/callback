from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from callback.config import REFRESH_ROTATION_GRACE_SECONDS
from users.models import Resume


class ResumeUploadTests(APITestCase):
    def setUp(self):
        cache.clear()
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
        cache.clear()
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

    def _refresh_with(self, token):
        self.client.cookies['refresh_token'] = token
        return self.client.post('/api/auth/token/refresh/')

    def test_refresh_rotates_refresh_token(self):
        old = str(RefreshToken.for_user(self.user))
        response = self._refresh_with(old)
        self.assertEqual(response.status_code, 200)
        new = response.cookies['refresh_token'].value
        self.assertNotEqual(new, '')
        self.assertNotEqual(new, old)
        with self.assertRaises(TokenError):
            RefreshToken(old)
        RefreshToken(new)

    def test_reused_token_within_grace_keeps_cookies(self):
        old = str(RefreshToken.for_user(self.user))
        self.assertEqual(self._refresh_with(old).status_code, 200)
        response = self._refresh_with(old)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data['code'], 'token_rotated')
        self.assertNotIn('refresh_token', response.cookies)
        self.assertNotIn('access_token', response.cookies)

    def test_reused_token_after_grace_clears_cookies(self):
        old = str(RefreshToken.for_user(self.user))
        self.assertEqual(self._refresh_with(old).status_code, 200)
        BlacklistedToken.objects.filter(
            token__jti=RefreshToken(old, verify=False)['jti']
        ).update(
            blacklisted_at=timezone.now()
            - timedelta(seconds=REFRESH_ROTATION_GRACE_SECONDS + 1)
        )
        response = self._refresh_with(old)
        self.assertEqual(response.status_code, 401)
        self._assert_cleared(response)
        self.assertNotIn('code', response.data)

    def test_tampered_token_with_just_blacklisted_jti_clears_cookies(self):
        old = str(RefreshToken.for_user(self.user))
        self.assertEqual(self._refresh_with(old).status_code, 200)
        header, payload, signature = old.split('.')
        flipped = 'A' if signature[0] != 'A' else 'B'
        response = self._refresh_with(f'{header}.{payload}.{flipped}{signature[1:]}')
        self.assertEqual(response.status_code, 401)
        self._assert_cleared(response)
        self.assertNotIn('code', response.data)

    def test_expired_token_with_just_blacklisted_jti_clears_cookies(self):
        old = str(RefreshToken.for_user(self.user))
        self.assertEqual(self._refresh_with(old).status_code, 200)
        expired = RefreshToken(old, verify=False)
        expired.set_exp(from_time=timezone.now() - timedelta(days=60))
        response = self._refresh_with(str(expired))
        self.assertEqual(response.status_code, 401)
        self._assert_cleared(response)
        self.assertNotIn('code', response.data)

    def test_refresh_for_inactive_user_clears_cookies(self):
        token = str(RefreshToken.for_user(self.user))
        self.user.is_active = False
        self.user.save()
        response = self._refresh_with(token)
        self.assertEqual(response.status_code, 401)
        self._assert_cleared(response)

    def test_refresh_for_deleted_user_clears_cookies(self):
        token = str(RefreshToken.for_user(self.user))
        self.user.delete()
        response = self._refresh_with(token)
        self.assertEqual(response.status_code, 401)
        self._assert_cleared(response)


NO_PROXY = {**settings.REST_FRAMEWORK, 'NUM_PROXIES': 0}
ONE_PROXY = {**settings.REST_FRAMEWORK, 'NUM_PROXIES': 1}


@override_settings(REST_FRAMEWORK=NO_PROXY)
class AuthThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        get_user_model().objects.create_user('linus', password='right')

    def _login(self, password='wrong', **extra):
        return self.client.post(
            '/api/auth/login/', {'username': 'linus', 'password': password}, **extra
        )

    def test_login_throttled_after_ten_attempts(self):
        for _ in range(10):
            self.assertEqual(self._login().status_code, 401)
        response = self._login('right')
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.data['detail'].startswith('Too many requests.'))

    def test_other_ip_not_throttled(self):
        for _ in range(11):
            self._login()
        self.assertEqual(self._login('right', REMOTE_ADDR='10.0.0.2').status_code, 200)

    def test_spoofed_forwarded_for_does_not_bypass(self):
        for i in range(10):
            self._login(HTTP_X_FORWARDED_FOR=f'1.2.3.{i}')
        response = self._login('right', HTTP_X_FORWARDED_FOR='9.9.9.9')
        self.assertEqual(response.status_code, 429)

    @override_settings(REST_FRAMEWORK=ONE_PROXY)
    def test_one_proxy_keys_on_last_forwarded_hop(self):
        for _ in range(10):
            self._login(HTTP_X_FORWARDED_FOR='6.6.6.6, 1.1.1.1')
        # Same trusted hop, spoofed leading entry: still throttled.
        self.assertEqual(
            self._login('right', HTTP_X_FORWARDED_FOR='7.7.7.7, 1.1.1.1').status_code, 429
        )
        # A different client behind the proxy has its own bucket.
        self.assertEqual(
            self._login('right', HTTP_X_FORWARDED_FOR='7.7.7.7, 2.2.2.2').status_code, 200
        )

    def test_register_throttled_after_five(self):
        for i in range(5):
            response = self.client.post(
                '/api/auth/register/',
                {'username': f'new{i}', 'email': f'new{i}@example.com', 'password': 'Str0ngPass!word'},
            )
            self.assertEqual(response.status_code, 201, response.data)
        response = self.client.post(
            '/api/auth/register/',
            {'username': 'new6', 'email': 'new6@example.com', 'password': 'Str0ngPass!word'},
        )
        self.assertEqual(response.status_code, 429)

    def test_refresh_never_throttled(self):
        for _ in range(15):
            self.assertEqual(self.client.post('/api/auth/token/refresh/').status_code, 401)
