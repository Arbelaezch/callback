from django.contrib import admin
from django.urls import path, include

from users.views import (
    RegisterView,
    LoginView,
    LogoutView,
    MeView,
    OnboardingView,
    RefreshView,
    # SOCIAL AUTH SCAFFOLD:
    # SocialAuthView,  # future: /api/auth/social/ — handles Google, GitHub, etc.
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth
    path('api/auth/register/', RegisterView.as_view(), name='register'),
    path('api/auth/login/', LoginView.as_view(), name='login'),
    path('api/auth/logout/', LogoutView.as_view(), name='logout'),
    path('api/auth/token/refresh/', RefreshView.as_view(), name='token_refresh'),
    path('api/auth/me/', MeView.as_view(), name='me'),

    # Onboarding
    path('api/onboarding/', OnboardingView.as_view(), name='onboarding'),

    # SOCIAL AUTH SCAFFOLD:
    # path('api/auth/social/', SocialAuthView.as_view(), name='social_auth'),
    # path('api/auth/social/callback/', SocialAuthCallbackView.as_view(), name='social_auth_callback'),

    # PASSWORD RESET SCAFFOLD:
    # path('api/auth/password/reset/', PasswordResetView.as_view(), name='password_reset'),
    # path('api/auth/password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    # EMAIL VERIFICATION SCAFFOLD:
    # path('api/auth/email/verify/', EmailVerifyView.as_view(), name='email_verify'),
    # path('api/auth/email/verify/confirm/', EmailVerifyConfirmView.as_view(), name='email_verify_confirm'),

    # Apps
    path('api/jobs/', include('jobs.urls')),
    path('api/users/', include('users.urls')),

    # Health
    path('api/health/', include('callback.health')),
]