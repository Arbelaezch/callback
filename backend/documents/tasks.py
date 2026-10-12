from celery import shared_task

from users.models import Resume

from .services import parse_resume


@shared_task
def parse_resume_task(resume_id: int) -> int:
    """Parse a Resume in the background. Returns the ParsedResume id."""
    return parse_resume(Resume.objects.get(pk=resume_id)).pk
