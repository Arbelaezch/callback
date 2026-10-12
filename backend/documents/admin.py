from django.contrib import admin

from .models import (
    ContextSource,
    GeneratedDocument,
    JobPosting,
    ParsedResume,
    SourceDocumentSection,
    VoiceProfile,
)


@admin.register(ParsedResume)
class ParsedResumeAdmin(admin.ModelAdmin):
    list_display = ('resume', 'user', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ContextSource)
class ContextSourceAdmin(admin.ModelAdmin):
    list_display = ('label', 'kind', 'user', 'status', 'last_synced_at')
    list_filter = ('kind', 'status')


@admin.register(SourceDocumentSection)
class SourceDocumentSectionAdmin(admin.ModelAdmin):
    list_display = ('path', 'heading', 'source')
    search_fields = ('path', 'heading', 'text')


@admin.register(VoiceProfile)
class VoiceProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'updated_at')
    readonly_fields = ('updated_at',)


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'user', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(admin.ModelAdmin):
    list_display = ('job_posting', 'kind', 'version', 'status', 'edited', 'created_at')
    list_filter = ('kind', 'status', 'edited')
    readonly_fields = ('created_at', 'updated_at')
