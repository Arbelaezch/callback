from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CoverLetterSample, CustomUser, Portfolio, Resume


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'is_active', 'is_staff', 'created_at')
    list_filter = ('is_active', 'is_staff')
    ordering = ('-created_at',)


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('filename', 'label', 'user', 'is_default', 'status', 'uploaded_at')
    list_filter = ('is_default', 'status')
    ordering = ('-uploaded_at',)
    readonly_fields = ('uploaded_at', 'updated_at')


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ('label', 'user', 'is_default', 'created_at')
    list_filter = ('is_default',)
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CoverLetterSample)
class CoverLetterSampleAdmin(admin.ModelAdmin):
    list_display = ('label', 'user', 'is_default', 'created_at')
    list_filter = ('is_default',)
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')