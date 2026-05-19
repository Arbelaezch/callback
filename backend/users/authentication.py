from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


class CookieJWTAuthentication(JWTAuthentication):
    """
    Reads the JWT access token from an httpOnly cookie instead of
    the Authorization header. Falls back to header if cookie is absent
    so the DRF browsable API and direct API calls still work.
    """

    def authenticate(self, request):
        access_token = request.COOKIES.get('access_token')

        if access_token:
            try:
                validated_token = self.get_validated_token(access_token)
                return self.get_user(validated_token), validated_token
            except InvalidToken:
                return None

        # Fallback to Authorization header
        return super().authenticate(request)