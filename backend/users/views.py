from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .serializers import RegisterSerializer, UserSerializer

User = get_user_model()


def set_auth_cookies(response, access_token, refresh_token):
    """Set JWT tokens as httpOnly cookies."""
    response.set_cookie(
        'access_token',
        str(access_token),
        max_age=settings.AUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
    )
    response.set_cookie(
        'refresh_token',
        str(refresh_token),
        max_age=settings.AUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite='Lax',
    )


def clear_auth_cookies(response):
    """Clear JWT cookies on logout."""
    response.delete_cookie('access_token', samesite='Lax')
    response.delete_cookie('refresh_token', samesite='Lax')


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        refresh = RefreshToken.for_user(user)

        response = Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )
        set_auth_cookies(response, refresh.access_token, refresh)

        # EMAIL VERIFICATION SCAFFOLD:
        # send_verification_email(user)

        return response


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        # SOCIAL AUTH SCAFFOLD:
        # provider = request.data.get('provider')  # 'google', 'github', etc.
        # if provider:
        #     return self.social_login(provider, request.data.get('token'))

        user = User.objects.filter(username=username).first()
        if not user or not user.check_password(password) or not user.is_active:
            return Response(
                {'detail': 'Invalid credentials.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        response = Response(UserSerializer(user).data)
        set_auth_cookies(response, refresh.access_token, refresh)
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.COOKIES.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except TokenError:
            pass

        response = Response({'detail': 'Logged out.'})
        clear_auth_cookies(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)