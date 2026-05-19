import os
import urllib.parse


def get_database_config(debug: bool) -> dict:
    if debug:
        return {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': os.environ.get('POSTGRES_DB', 'callback'),
                'USER': os.environ.get('POSTGRES_USER', 'callback'),
                'PASSWORD': os.environ['POSTGRES_PASSWORD'],
                'HOST': os.environ.get('DB_HOST', 'db'),
                'PORT': os.environ.get('DB_PORT', '5432'),
            }
        }

    url = urllib.parse.urlparse(os.environ['DATABASE_URL'])
    return {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': url.path.lstrip('/'),
            'USER': url.username,
            'PASSWORD': url.password,
            'HOST': url.hostname,
            'PORT': url.port or '5432',
            'OPTIONS': {'sslmode': 'require'},
        }
    }