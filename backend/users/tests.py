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

from callback.config import (
    CONTEXT_UPLOAD_MAX_BYTES,
    REFRESH_ROTATION_GRACE_SECONDS,
    RESUME_UPLOAD_MAX_BYTES,
)
from documents.models import ParsedResume
from users.models import Resume
from users.views import PRIMARY_DELETE_ERROR


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


    def test_first_successful_upload_is_default(self):
        with patch('users.views.upload_resume', return_value='resumes/user_1/a.pdf'):
            response = self._post('a.pdf', b'%PDF-1.4 body')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['is_default'])
        self.assertTrue(Resume.objects.get().is_default)

    def test_failed_upload_is_not_default(self):
        with patch('users.views.upload_resume', side_effect=Exception('boom')):
            response = self._post('a.pdf', b'%PDF-1.4 body')
        self.assertEqual(response.status_code, 500)
        resume = Resume.objects.get()
        self.assertEqual(resume.status, 'failed')
        self.assertFalse(resume.is_default)

    def test_upload_becomes_default_when_current_default_failed(self):
        old = Resume.objects.create(
            user=self.user, s3_key='', filename='old.pdf', status='failed', is_default=True,
        )
        with patch('users.views.upload_resume', return_value='resumes/user_1/b.pdf'):
            response = self._post('b.pdf', b'%PDF-1.4 body')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Resume.objects.get(pk=response.data['id']).is_default)
        old.refresh_from_db()
        self.assertFalse(old.is_default)

    def test_upload_does_not_steal_ready_default(self):
        current = Resume.objects.create(
            user=self.user, s3_key='k', filename='cur.pdf', status='ready', is_default=True,
        )
        with patch('users.views.upload_resume', return_value='resumes/user_1/c.pdf'):
            response = self._post('c.pdf', b'%PDF-1.4 body')
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['is_default'])
        current.refresh_from_db()
        self.assertTrue(current.is_default)

    def test_oversize_message_uses_limit(self):
        with patch('users.views.RESUME_UPLOAD_MAX_BYTES', 1024 * 1024), \
                patch('users.views.upload_resume') as upload:
            response = self._post('big.pdf', b'%PDF-' + b'0' * (2 * 1024 * 1024))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], 'Resume must be under 1MB.')
        self.assertFalse(Resume.objects.exists())
        upload.assert_not_called()


class ResumeDetailTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user('ada', password='x')
        self.bob = get_user_model().objects.create_user('bob', password='x')
        self.client.force_authenticate(self.user)

    def _resume(self, user=None, status='ready', s3_key='k', is_default=False, **kw):
        return Resume.objects.create(
            user=user or self.user,
            s3_key=s3_key,
            filename=kw.pop('filename', 'r.pdf'),
            status=status,
            is_default=is_default,
            **kw,
        )

    def _parsed(self, resume):
        return ParsedResume.objects.create(resume=resume, user=resume.user, content={}, layout={})

    def _delete(self, resume):
        return self.client.delete(f'/api/users/resumes/{resume.pk}/')

    def _primary(self, resume):
        return self.client.post(f'/api/users/resumes/{resume.pk}/primary/')

    def test_delete_removes_row_storage_object_and_parsed_resume(self):
        resume = self._resume()
        self._parsed(resume)
        with patch('users.views.delete_resume') as delete:
            response = self._delete(resume)
        self.assertEqual(response.status_code, 204)
        delete.assert_called_once_with('k')
        self.assertFalse(Resume.objects.filter(pk=resume.pk).exists())
        self.assertFalse(ParsedResume.objects.filter(resume_id=resume.pk).exists())

    def test_delete_pending_and_failed_resumes_skips_storage(self):
        for row_status in ('pending', 'failed'):
            resume = self._resume(status=row_status, s3_key='')
            with patch('users.views.delete_resume') as delete:
                response = self._delete(resume)
            self.assertEqual(response.status_code, 204, row_status)
            delete.assert_not_called()
            self.assertFalse(Resume.objects.filter(pk=resume.pk).exists())

    def test_cannot_delete_another_users_resume(self):
        resume = self._resume(user=self.bob)
        with patch('users.views.delete_resume') as delete:
            response = self._delete(resume)
        self.assertEqual(response.status_code, 404)
        delete.assert_not_called()
        self.assertTrue(Resume.objects.filter(pk=resume.pk).exists())

    def test_cannot_delete_another_users_primary(self):
        resume = self._resume(user=self.bob, is_default=True)
        with patch('users.views.delete_resume') as delete:
            response = self._delete(resume)
        self.assertEqual(response.status_code, 404)
        delete.assert_not_called()

    def test_storage_failure_keeps_row(self):
        resume = self._resume()
        with patch('users.views.delete_resume', side_effect=Exception('s3 down')):
            response = self._delete(resume)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data['detail'], 'Could not delete the file. Please try again.')
        self.assertTrue(Resume.objects.filter(pk=resume.pk).exists())

    def test_cannot_delete_primary_resume(self):
        primary = self._resume(is_default=True)
        self._parsed(primary)
        other = self._resume()
        with patch('users.views.delete_resume') as delete:
            response = self._delete(primary)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['detail'], PRIMARY_DELETE_ERROR)
        delete.assert_not_called()
        self.assertTrue(Resume.objects.filter(pk=primary.pk).exists())
        self.assertTrue(ParsedResume.objects.filter(resume_id=primary.pk).exists())
        other.refresh_from_db()
        self.assertFalse(other.is_default)

    def test_cannot_delete_only_resume_when_it_is_primary(self):
        primary = self._resume(is_default=True)
        with patch('users.views.delete_resume') as delete:
            response = self._delete(primary)
        self.assertEqual(response.status_code, 409)
        delete.assert_not_called()
        self.assertTrue(Resume.objects.filter(pk=primary.pk).exists())

    def test_primary_can_be_deleted_after_moving_primary(self):
        old = self._resume(is_default=True)
        new = self._resume()
        self.assertEqual(self._primary(new).status_code, 200)
        with patch('users.views.delete_resume'):
            response = self._delete(old)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Resume.objects.filter(pk=old.pk).exists())
        new.refresh_from_db()
        self.assertTrue(new.is_default)

    def test_legacy_failed_default_can_be_deleted(self):
        legacy = self._resume(status='failed', s3_key='', is_default=True)
        other = self._resume()
        with patch('users.views.delete_resume') as delete:
            response = self._delete(legacy)
        self.assertEqual(response.status_code, 204)
        delete.assert_not_called()
        self.assertFalse(Resume.objects.filter(pk=legacy.pk).exists())
        self.assertFalse(Resume.objects.filter(user=self.user, is_default=True).exists())
        other.refresh_from_db()
        self.assertFalse(other.is_default)

    def test_deleting_non_default_keeps_default(self):
        primary = self._resume(is_default=True)
        other = self._resume()
        with patch('users.views.delete_resume'):
            response = self._delete(other)
        self.assertEqual(response.status_code, 204)
        primary.refresh_from_db()
        self.assertTrue(primary.is_default)

    def test_set_primary_moves_default(self):
        old = self._resume(is_default=True)
        new = self._resume()
        response = self._primary(new)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_default'])
        self.assertEqual(response.data['id'], new.pk)
        old.refresh_from_db()
        self.assertFalse(old.is_default)

    def test_set_primary_rejects_non_ready(self):
        for row_status in ('pending', 'failed'):
            resume = self._resume(status=row_status, s3_key='')
            response = self._primary(resume)
            self.assertEqual(response.status_code, 400, row_status)
            self.assertEqual(response.data['detail'], 'Only an uploaded resume can be primary.')
            resume.refresh_from_db()
            self.assertFalse(resume.is_default)

    def test_set_primary_other_user_404(self):
        resume = self._resume(user=self.bob)
        response = self._primary(resume)
        self.assertEqual(response.status_code, 404)
        resume.refresh_from_db()
        self.assertFalse(resume.is_default)

    def test_upload_limits_returns_config_values(self):
        response = self.client.get('/api/users/upload-limits/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            'resume_max_bytes': RESUME_UPLOAD_MAX_BYTES,
            'source_max_bytes': CONTEXT_UPLOAD_MAX_BYTES,
        })

    def test_upload_limits_requires_auth(self):
        self.client.force_authenticate(None)
        response = self.client.get('/api/users/upload-limits/')
        self.assertEqual(response.status_code, 401)

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
