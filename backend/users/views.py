from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenBackendError, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from django.conf import settings

from callback.throttles import IPScopedRateThrottle, ReadableThrottleMixin
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    OnboardingSerializer,
    ResumeSerializer,
)
from .models import CoverLetterSample, Portfolio, Resume
from jobs.models import Agent, Search
from callback.config import REFRESH_ROTATION_GRACE_SECONDS, RESUME_UPLOAD_MAX_BYTES
from pipeline.storage import upload_resume
from documents.staleness import fail_stale_parses

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
        secure=not settings.DEBUG,
        samesite='Lax',
    )


def clear_auth_cookies(response):
    """Clear JWT cookies on logout."""
    response.delete_cookie('access_token', samesite='Lax')
    response.delete_cookie('refresh_token', samesite='Lax')


def _recently_rotated(raw_token):
    """True if the token is validly signed, unexpired and was blacklisted
    within the rotation grace window (i.e. another tab just rotated it)."""
    try:
        payload = token_backend.decode(raw_token, verify=True)
    except TokenBackendError:
        return False
    jti = payload.get(api_settings.JTI_CLAIM)
    if not jti:
        return False
    cutoff = timezone.now() - timedelta(seconds=REFRESH_ROTATION_GRACE_SECONDS)
    return BlacklistedToken.objects.filter(
        token__jti=jti, blacklisted_at__gte=cutoff
    ).exists()


class RegisterView(ReadableThrottleMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = 'register'

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


class LoginView(ReadableThrottleMixin, APIView):
    permission_classes = [AllowAny]
    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        # print('LOGIN DATA:', request.data)
        username = request.data.get('username')
        password = request.data.get('password')

        # SOCIAL AUTH SCAFFOLD:
        # provider = request.data.get('provider')
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
    # Must work with an expired or stale access cookie, so it never authenticates.
    authentication_classes = []
    permission_classes = [AllowAny]

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


class OnboardingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Free tier: one resume only — proxy for onboarding completion
        if Resume.objects.filter(user=request.user).exists():
            return Response(
                {'detail': 'You have already completed onboarding. Upgrade your plan to add more.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = OnboardingSerializer(data={
            **request.data,
            'resume': request.FILES.get('resume'),
        })
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        with transaction.atomic():
            resume = Resume.objects.create(
                user=request.user,
                s3_key='',
                filename=data['resume'].name,
                is_default=True,
                status='pending',
            )

            portfolio = Portfolio.objects.create(
                user=request.user,
                label=data.get('portfolio_label', 'My Portfolio'),
                body=data.get('portfolio_body', ''),
                is_default=True,
            )

            cover_letter_sample = CoverLetterSample.objects.create(
                user=request.user,
                label=data['cover_letter_label'],
                body=data['cover_letter_body'],
                is_default=True,
            )

            # Create Agent (singleton) then the first Search
            # TODO: Free tier: one search only.
            agent, _ = Agent.objects.get_or_create(user=request.user)

            Search.objects.create(
                agent=agent,
                label=data.get('label', ''),
                role_titles=data['role_titles'],
                cities=data.get('cities', []),
                location_types=data.get('location_types', []),
                seniority_levels=data.get('seniority_levels', []),
                years_experience=data.get('years_experience'),
                salary_min=data.get('salary_min'),
                excluded_companies=data.get('excluded_companies', []),
                resume=resume,
                portfolio=portfolio,
                cover_letter_sample=cover_letter_sample,
                daily_target=5,
                active=True,
            )

        # Upload outside transaction — record exists, status tracks progress
        try:
            s3_key = upload_resume(data['resume'], request.user.id)
            resume.s3_key = s3_key
            resume.status = 'ready'
            resume.save(update_fields=['s3_key', 'status'])
        except Exception:
            resume.status = 'failed'
            resume.save(update_fields=['status'])
            return Response(
                {'detail': 'Resume upload failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({'detail': 'Onboarding complete.'}, status=status.HTTP_201_CREATED)


class RefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        raw = request.COOKIES.get('refresh_token')
        if not raw:
            return self._unauthorized('No refresh token.')

        # The serializer blacklists the presented token and issues a new one
        # (ROTATE_REFRESH_TOKENS / BLACKLIST_AFTER_ROTATION).
        serializer = TokenRefreshSerializer(data={'refresh': raw})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            if _recently_rotated(raw):
                # Another tab rotated this token moments ago and its new
                # cookies are already in the jar: keep them, issue nothing.
                return Response(
                    {'detail': 'Refresh token already rotated.', 'code': 'token_rotated'},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            return self._unauthorized('Invalid refresh token.')
        except (AuthenticationFailed, ObjectDoesNotExist, ValidationError):
            # Inactive or deleted user.
            return self._unauthorized('Invalid refresh token.')

        data = serializer.validated_data
        response = Response({'detail': 'Refreshed.'})
        set_auth_cookies(response, data['access'], data['refresh'])
        return response

    @staticmethod
    def _unauthorized(detail):
        # Clear stale cookies so the user is not stuck behind the /login redirect.
        response = Response({'detail': detail}, status=status.HTTP_401_UNAUTHORIZED)
        clear_auth_cookies(response)
        return response


class ResumeUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all resumes for the user."""
        fail_stale_parses(request.user)
        resumes = Resume.objects.filter(user=request.user)
        return Response(ResumeSerializer(resumes, many=True).data)

    def post(self, request):
        """Upload a new resume PDF."""
        file = request.FILES.get('resume')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)
        if not file.name.lower().endswith('.pdf'):
            return Response({'detail': 'Resume must be a PDF.'}, status=status.HTTP_400_BAD_REQUEST)
        if file.size > RESUME_UPLOAD_MAX_BYTES:
            return Response({'detail': 'Resume must be under 5MB.'}, status=status.HTTP_400_BAD_REQUEST)
        header = file.read(5)
        file.seek(0)
        if header != b'%PDF-':
            return Response({'detail': 'Resume must be a PDF.'}, status=status.HTTP_400_BAD_REQUEST)

        label = request.data.get('label', '')

        resume = Resume.objects.create(
            user=request.user,
            s3_key='',
            filename=file.name,
            label=label,
            is_default=not Resume.objects.filter(user=request.user).exists(),
            status='pending',
        )

        try:
            s3_key = upload_resume(file, request.user.id)
            resume.s3_key = s3_key
            resume.status = 'ready'
            resume.save(update_fields=['s3_key', 'status'])
        except Exception:
            resume.status = 'failed'
            resume.save(update_fields=['status'])
            return Response({'detail': 'Upload failed. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(ResumeSerializer(resume).data, status=status.HTTP_201_CREATED)