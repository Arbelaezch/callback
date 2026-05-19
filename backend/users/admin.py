from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, Resume, CoverLetterTemplate


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'is_active', 'is_staff', 'created_at')
    list_filter = ('is_active', 'is_staff')
    ordering = ('-created_at',)


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('filename', 'user', 'is_default', 'uploaded_at')
    list_filter = ('is_default',)
    ordering = ('-uploaded_at',)
    readonly_fields = ('uploaded_at',)


@admin.register(CoverLetterTemplate)
class CoverLetterTemplateAdmin(admin.ModelAdmin):
    list_display = ('label', 'user', 'is_default', 'created_at')
    list_filter = ('is_default',)
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)