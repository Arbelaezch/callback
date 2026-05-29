from django.db import models
from django.conf import settings
from django.contrib.postgres.fields import ArrayField

from users.models import Resume, Portfolio, CoverLetterSample


class Agent(models.Model):
    """
    Singleton per user. The central overseer — owns the master on/off switch.
    All Searches belong to an Agent.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent',
    )
    name = models.CharField(max_length=100, blank=True, default='My Agent')
    active = models.BooleanField(
        default=True,
        help_text='Master kill switch. When false, no Searches run regardless of their own active state.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} — {self.name}'


class Search(models.Model):
    """
    A single job search configuration owned by an Agent.
    Users can have multiple Searches running simultaneously
    (gated by subscription tier).
    """
    SENIORITY_CHOICES = [
        ('intern', 'Intern')
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

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='searches')
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
        related_name='searches',
    )
    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='searches',
    )
    cover_letter_sample = models.ForeignKey(
        CoverLetterSample,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='searches',
    )

    # controls
    daily_target = models.IntegerField(
        default=5,
        help_text='How many applications to aim for per day. Enforced against plan limits in business logic.',
    )
    active = models.BooleanField(default=True)
    schedule_enabled = models.BooleanField(
        default=False,
        help_text='When enabled, this search runs automatically on the daily schedule.',
    )

    job_cooldown = models.IntegerField(
        default=180,
        help_text='Days before a previously applied to job is eligible to be applied to again.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.agent.user.username} — {self.label or "Search"}'


class JobSeen(models.Model):
    """
    Pipeline dedup table. Records every job the user's agent has fetched
    and processed, regardless of outcome (scored, skipped, or applied).

    Scoped to the user — not the search — so the same job listing is never
    re-fetched and re-scored across multiple Searches.

    This is separate from Application, which tracks actual submissions.
    JobSeen answers "have we processed this job before?"
    Application answers "have we applied to this job?"

    Rows are never deleted. Re-eligibility for re-processing is controlled
    by Search.job_cooldown — the pipeline filters on seen_at >= now - cooldown.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='jobs_seen',
    )
    job_id = models.CharField(max_length=255)
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'job_id')
        ordering = ['-seen_at']

    def __str__(self):
        return f'{self.user.username} — {self.job_id}'


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
        ('deleted', 'Deleted'),
        ('skipped', 'Skipped'),
    ]

    REMOTE_TYPE_CHOICES = [
        ('remote', 'Remote'),
        ('hybrid', 'Hybrid'),
        ('onsite', 'On-site'),
        ('unknown', 'Unknown'),
    ]

    search = models.ForeignKey(Search, on_delete=models.CASCADE, related_name='applications')
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
        unique_together = ('search', 'job_id')

    def __str__(self):
        return f'{self.search.agent.user.username} → {self.company} — {self.role_title} ({self.status})'


class RunLog(models.Model):
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('partial', 'Partial'),
        ('failed', 'Failed'),
    ]

    search = models.ForeignKey(Search, on_delete=models.CASCADE, related_name='run_logs')
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
        return f'{self.search.agent.user.username} — {self.run_at.date()} ({self.status})'