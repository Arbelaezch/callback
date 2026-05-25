import os
import django
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'callback.settings')
django.setup()

app = Celery('callback')

# Read config from Django settings, namespace CELERY_ prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodiscover tasks in all INSTALLED_APPS.
app.autodiscover_tasks(['pipeline'])