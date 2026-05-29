from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.conf import settings


class CustomUser(AbstractUser):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username


class Resume(models.Model):
    """
    A user's resume as an uploaded file artifact.
    Stored in S3; submitted directly to job applications.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
        ('deleted', 'Deleted'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resumes')
    label = models.CharField(max_length=100, blank=True)
    s3_key = models.CharField(max_length=500)
    filename = models.CharField(max_length=255)
    is_default = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.user.username} — {self.label or self.filename}'

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                self.__class__.objects.filter(
                    user=self.user, is_default=True
                ).exclude(pk=self.pk).update(is_default=False)
            super().save(*args, **kwargs)


class Portfolio(models.Model):
    """
    A free-text repository of the user's accomplishments, skills, projects,
    and career history. The LLM draws from this when tailoring resumes and
    cover letters to specific job postings.

    Stored as unstructured prose for now. Future refactor will add
    PortfolioEntry children (typed, discrete entries) and drop the body field.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='portfolios')
    label = models.CharField(max_length=100, blank=True)
    body = models.TextField(
        help_text='Paste accomplishments, skills, projects, and career history here. '
                  'More detail gives the agent better material to work with.'
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — {self.label or "Portfolio"}'

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                self.__class__.objects.filter(
                    user=self.user, is_default=True
                ).exclude(pk=self.pk).update(is_default=False)
            super().save(*args, **kwargs)


class CoverLetterSample(models.Model):
    """
    A sample cover letter written in the user's own voice.
    The LLM uses this to match tone and style when generating
    job-specific cover letters — not submitted directly.

    Users can upload an existing cover letter here; the name 'sample'
    signals that this is source material, not the final output.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cover_letter_samples')
    label = models.CharField(max_length=100, blank=True)
    body = models.TextField(
        help_text='Paste a cover letter you have written. '
                  'The agent will use this to match your tone and voice.'
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — {self.label or "Cover Letter Sample"}'

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                self.__class__.objects.filter(
                    user=self.user, is_default=True
                ).exclude(pk=self.pk).update(is_default=False)
            super().save(*args, **kwargs)