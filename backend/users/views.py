from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.conf import settings

from .serializers import (
    RegisterSerializer,
    UserSerializer,
    OnboardingSerializer,
)
from .models import Resume, CoverLetterTemplate
from jobs.models import JobSearch
from pipeline.storage import upload_resume

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


class OnboardingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Free tier: one resume only
        if Resume.objects.filter(user=request.user).exists():
            return Response(
                {'detail': 'You have already completed onboarding. Upgrade your plan to add more resumes.'},
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
                s3_key='',           # placeholder until upload completes
                filename=data['resume'].name,
                is_default=True,
                status='pending',
            )

            cover_letter = CoverLetterTemplate.objects.create(
                user=request.user,
                label=data['cover_letter_label'],
                body=data['cover_letter_body'],
                is_default=True,
            )

            # Free tier: one search only
            JobSearch.objects.create(
                user=request.user,
                label=data.get('label', ''),
                role_titles=data['role_titles'],
                cities=data.get('cities', []),
                location_types=data.get('location_types', []),
                seniority_levels=data.get('seniority_levels', []),
                years_experience=data.get('years_experience'),
                salary_min=data.get('salary_min'),
                excluded_companies=data.get('excluded_companies', []),
                resume=resume,
                cover_letter_template=cover_letter,
                daily_limit=5,
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
        refresh_token = request.COOKIES.get('refresh_token')
        if not refresh_token:
            return Response({'detail': 'No refresh token.'}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            refresh = RefreshToken(refresh_token)
            response = Response({'detail': 'Refreshed.'})
            set_auth_cookies(response, refresh.access_token, refresh)
            return response
        except TokenError:
            return Response({'detail': 'Invalid refresh token.'}, status=status.HTTP_401_UNAUTHORIZED)