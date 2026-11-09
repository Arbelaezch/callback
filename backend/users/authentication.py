from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .csrf import check_request_origin


class CookieJWTAuthentication(JWTAuthentication):
    """
    Reads the JWT access token from an httpOnly cookie instead of
    the Authorization header. Falls back to header if cookie is absent
    so the DRF browsable API and direct API calls still work.

    Unsafe (non-GET/HEAD/OPTIONS) requests authenticated by the cookie must
    carry an Origin (or Referer) listed in CORS_ALLOWED_ORIGINS, otherwise
    they get 403 (see users/csrf.py). Header-authenticated requests are exempt.
    """

    def authenticate(self, request):
        access_token = request.COOKIES.get('access_token')

        if access_token:
            try:
                validated_token = self.get_validated_token(access_token)
                user = self.get_user(validated_token)
            except InvalidToken:
                return None
            check_request_origin(request)
            return user, validated_token

        # Fallback to Authorization header
        return super().authenticate(request)
