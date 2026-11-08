from django.conf import settings
from django.test import SimpleTestCase

from callback import config


class CeleryResultExpiryTests(SimpleTestCase):
    def test_settings_use_config_value(self):
        self.assertEqual(settings.CELERY_RESULT_EXPIRES, config.CELERY_RESULT_EXPIRES)
        self.assertEqual(settings.CELERY_RESULT_EXPIRES, 3600)

    def test_celery_app_picks_up_expiry(self):
        from callback.celery import app

        self.assertEqual(app.conf.result_expires, config.CELERY_RESULT_EXPIRES)
