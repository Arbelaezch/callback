from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models


class ParsedResume(models.Model):
    """
    Structured form of an uploaded Resume, produced once by the resume
    analysis step. `content` holds the facts (header, experience, projects,
    education, skills); `layout` holds the user's formatting (fonts, margins,
    spacing, section order, bullet style). Tailoring changes `content` only,
    so the user's layout survives every generated version.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='parsed_resumes')
    resume = models.OneToOneField('users.Resume', on_delete=models.CASCADE, related_name='parsed')
    content = models.JSONField(default=dict)
    layout = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — parsed {self.resume.filename}'


class ContextSource(models.Model):
    """
    One place the user's background lives: a git repo, an Obsidian vault URL,
    or an uploaded supporting document. A user may add any subset. The context
    scout only searches sources that exist here.
    """
    KIND_CHOICES = [
        ('git', 'Git repository'),
        ('obsidian', 'Obsidian vault URL'),
        ('upload', 'Uploaded document'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='context_sources')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    label = models.CharField(max_length=100, blank=True)
    url = models.URLField(blank=True, help_text='Repository or vault URL. Empty for uploads.')
    s3_key = models.CharField(max_length=500, blank=True, help_text='Stored file for uploads.')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    error = models.TextField(blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — {self.label or self.get_kind_display()}'


class SourceDocumentSection(models.Model):
    """
    One heading-level slice of a document from a ContextSource. This is the
    unit the context scout searches, reads and cites.
    """
    source = models.ForeignKey(ContextSource, on_delete=models.CASCADE, related_name='sections')
    path = models.CharField(max_length=500)
    heading = models.CharField(max_length=300, blank=True)
    text = models.TextField()
    search_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        ordering = ['source', 'path', 'id']
        indexes = [GinIndex(fields=['search_vector'])]

    def __str__(self):
        return f'{self.path} — {self.heading or "(top)"}'


class VoiceProfile(models.Model):
    """
    The user's writing voice, derived from their context sources and cover
    letter sample. Depends only on those inputs, so it is cached per user and
    rebuilt when `built_from_hash` no longer matches.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='voice_profile')
    notes = models.TextField(help_text='Tone, sentence length, vocabulary habits, typical openers.')
    excerpts = models.JSONField(default=list, help_text='Verbatim excerpts that show the voice.')
    built_from_hash = models.CharField(max_length=64)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} — voice profile'


class JobPosting(models.Model):
    """A job description the user pasted in."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='job_postings')
    title = models.CharField(max_length=200)
    company = models.CharField(max_length=200)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} at {self.company}'


class GeneratedDocument(models.Model):
    """
    A tailored resume or cover letter for a JobPosting. Resume content is
    JSON in the same shape as ParsedResume.content; a cover letter keeps its
    letterhead in `content['header']` and its text in `markdown`. `unsupported_claims` holds the verifier's flags for the editor.
    """
    KIND_CHOICES = [
        ('resume', 'Resume'),
        ('cover_letter', 'Cover letter'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='documents')
    kind = models.CharField(max_length=15, choices=KIND_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    content = models.JSONField(default=dict, blank=True)
    layout = models.JSONField(
        default=dict, blank=True,
        help_text='Snapshot of the resume layout at generation time, used for PDF export.',
    )
    markdown = models.TextField(blank=True)
    unsupported_claims = models.JSONField(default=list, blank=True)
    version = models.PositiveIntegerField(default=1)
    edited = models.BooleanField(default=False)
    pdf_s3_key = models.CharField(max_length=500, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_kind_display()} v{self.version} — {self.job_posting}'
