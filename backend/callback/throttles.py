import math

from rest_framework.exceptions import Throttled
from rest_framework.throttling import ScopedRateThrottle


class PostScopedRateThrottle(ScopedRateThrottle):
    """Scoped throttle that only counts POST requests, so polling GETs are free."""

    def allow_request(self, request, view):
        if request.method != 'POST':
            return True
        return super().allow_request(request, view)


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
