"""
Origin/Referer check for unsafe requests that rely on cookies.

Auth uses JWTs in cookies. SameSite=Lax does not stop login CSRF (a foreign
site posting credentials to log the victim in as the attacker), and DRF views
are csrf-exempt, so Django's CsrfViewMiddleware does not help. Unsafe requests
must therefore come from an origin listed in CORS_ALLOWED_ORIGINS.
"""
from urllib.parse import urlsplit

from django.conf import settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS

REJECTED_DETAIL = 'Cross-site request rejected.'


def _allowed_origins():
    # Read at call time so override_settings works.
    return {o.rstrip('/').lower() for o in settings.CORS_ALLOWED_ORIGINS}


def _request_origin(request):
    """The request's origin as `scheme://netloc`, or None if unknown."""
    origin = request.META.get('HTTP_ORIGIN')
    if origin is not None:
        # Origin wins over Referer; the literal 'null' is never allowed.
        return None if origin == 'null' else origin
    referer = request.META.get('HTTP_REFERER')
    if not referer:
        return None
    parts = urlsplit(referer)
    if not parts.scheme or not parts.netloc:
        return None
    return f'{parts.scheme}://{parts.netloc}'


def check_request_origin(request):
    """Raise PermissionDenied (403) for an unsafe request from a disallowed origin."""
    if request.method in SAFE_METHODS:
        return
    origin = _request_origin(request)
    if origin is None or origin.lower() not in _allowed_origins():
        raise PermissionDenied(REJECTED_DETAIL)


class OriginCheckMixin:
    """APIView mixin: check the origin before authentication and throttling."""

    def initial(self, request, *args, **kwargs):
        check_request_origin(request)
        super().initial(request, *args, **kwargs)
