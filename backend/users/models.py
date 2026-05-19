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
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
        ('deleted', 'Deleted'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resumes')
    s3_key = models.CharField(max_length=500)
    filename = models.CharField(max_length=255)
    is_default = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.user.username} — {self.filename}'

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                self.__class__.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
            super().save(*args, **kwargs)


class CoverLetterTemplate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cover_letter_templates')
    label = models.CharField(max_length=100)
    body = models.TextField()
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — {self.label}'

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                self.__class__.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
            super().save(*args, **kwargs)

