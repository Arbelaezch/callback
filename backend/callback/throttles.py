import logging
import math

from redis.exceptions import RedisError
from rest_framework.exceptions import Throttled
from rest_framework.throttling import ScopedRateThrottle

logger = logging.getLogger(__name__)


class PostScopedRateThrottle(ScopedRateThrottle):
    """Scoped throttle that only counts POST requests, so polling GETs are free.

    Fails open: if the throttle cache (Redis in prod) raises, the request is
    allowed and a warning is logged, so a cache outage cannot block login.
    The DB-counted daily caps still bound parse and generate.
    """

    def allow_request(self, request, view):
        if request.method != 'POST':
            return True
        try:
            return super().allow_request(request, view)
        except (RedisError, OSError):
            logger.warning(
                'Throttle cache unavailable for scope %s; allowing request',
                getattr(view, 'throttle_scope', None),
                exc_info=True,
            )
            return True


class IPScopedRateThrottle(PostScopedRateThrottle):
    """Scoped POST throttle keyed on the client IP, even for authenticated users."""

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }


class ReadableThrottleMixin:
    """View mixin: throttled responses carry a human-readable minutes message."""

    def throttled(self, request, wait):
        minutes = max(1, math.ceil((wait or 60) / 60))
        exc = Throttled(
            detail=f'Too many requests. Please try again in {minutes} minute{"" if minutes == 1 else "s"}.'
        )
        exc.wait = math.ceil(wait) if wait else None
        raise exc
