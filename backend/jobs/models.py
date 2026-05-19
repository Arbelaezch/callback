from django.db import models
from django.conf import settings
from django.contrib.postgres.fields import ArrayField

from users.models import Resume, CoverLetterTemplate


class JobSearch(models.Model):
    """
    A single job search configuration. Users can have multiple
    searches running simultaneously (gated by subscription tier).
    """
    SENIORITY_CHOICES = [
        ('junior', 'Junior'),
        ('mid', 'Mid'),
        ('senior', 'Senior'),
        ('lead', 'Lead'),
        ('executive', 'Executive'),
    ]

    LOCATION_TYPE_CHOICES = [
        ('remote', 'Remote'),
        ('hybrid', 'Hybrid'),
        ('onsite', 'On-site'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='job_searches')
    label = models.CharField(max_length=100, blank=True)  # e.g. 'Senior Django roles'

    # what to search for
    role_titles = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    cities = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    location_types = ArrayField(
        models.CharField(max_length=10, choices=LOCATION_TYPE_CHOICES),
        default=list,
        blank=True,
    )
    seniority_levels = ArrayField(
        models.CharField(max_length=15, choices=SENIORITY_CHOICES),
        default=list,
        blank=True,
    )

    # scoring context for LLM
    years_experience = models.IntegerField(null=True, blank=True)
    salary_min = models.IntegerField(null=True, blank=True)
    excluded_companies = ArrayField(models.CharField(max_length=200), default=list, blank=True)

    # which resume + cover letter to use for this search
    resume = models.ForeignKey(
        Resume,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_searches',
    )
    cover_letter_template = models.ForeignKey(
        CoverLetterTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_searches',
    )

    # controls
    daily_limit = models.IntegerField(default=5)
    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Job Searches'

    def __str__(self):
        return f'{self.user.username} — {self.label or "Job Search"}'


class JobSeen(models.Model):
    job_search = models.ForeignKey(JobSearch, on_delete=models.CASCADE, related_name='jobs_seen')
    job_id = models.CharField(max_length=255)
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # a job can be seen by the same user across different searches,
        # but not twice within the same search
        unique_together = ('job_search', 'job_id')
        ordering = ['-seen_at']

    def __str__(self):
        return f'{self.job_search.user.username} — {self.job_id}'


class Application(models.Model):
    SUBMISSION_METHOD_CHOICES = [
        ('greenhouse_api', 'Greenhouse API'),
        ('lever_api', 'Lever API'),
        ('browser_lambda', 'Browser Lambda'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]

    REMOTE_TYPE_CHOICES = [
        ('remote', 'Remote'),
        ('hybrid', 'Hybrid'),
        ('onsite', 'On-site'),
        ('unknown', 'Unknown'),
    ]

    job_search = models.ForeignKey(JobSearch, on_delete=models.CASCADE, related_name='applications')
    resume = models.ForeignKey(Resume, on_delete=models.SET_NULL, null=True, related_name='applications')

    # job details
    job_id = models.CharField(max_length=255)
    job_url = models.URLField(max_length=1000)
    company = models.CharField(max_length=255)
    role_title = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    remote_type = models.CharField(max_length=10, choices=REMOTE_TYPE_CHOICES, default='unknown')
    salary_range = models.CharField(max_length=100, null=True, blank=True)
    job_description = models.TextField(null=True, blank=True)
    source = models.CharField(max_length=50, default='jsearch')

    # submission
    submission_method = models.CharField(max_length=20, choices=SUBMISSION_METHOD_CHOICES, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    cover_letter_used = models.TextField(null=True, blank=True)
    lambda_invocation_id = models.CharField(max_length=255, null=True, blank=True)
    failure_reason = models.TextField(null=True, blank=True)

    # llm scoring
    llm_score = models.IntegerField(null=True, blank=True)
    llm_score_reason = models.TextField(null=True, blank=True)

    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # prevent applying to same job twice within the same search
        unique_together = ('job_search', 'job_id')

    def __str__(self):
        return f'{self.job_search.user.username} → {self.company} — {self.role_title} ({self.status})'


class DailyRunLog(models.Model):
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('partial', 'Partial'),
        ('failed', 'Failed'),
    ]

    job_search = models.ForeignKey(JobSearch, on_delete=models.CASCADE, related_name='daily_run_logs')
    run_at = models.DateTimeField(auto_now_add=True)
    jobs_fetched = models.IntegerField(default=0)
    jobs_scored = models.IntegerField(default=0)
    jobs_applied = models.IntegerField(default=0)
    jobs_failed = models.IntegerField(default=0)
    jobs_skipped = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    error = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-run_at']

    def __str__(self):
        return f'{self.job_search.user.username} — {self.run_at.date()} ({self.status})'