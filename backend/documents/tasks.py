from celery import shared_task

from users.models import Resume

from .services import parse_resume


@shared_task
def parse_resume_task(resume_id: int) -> int:
    """Parse a Resume in the background. Returns the ParsedResume id."""
    return parse_resume(Resume.objects.get(pk=resume_id)).pk


@shared_task
def generate_documents_task(job_posting_id: int, resume_id: int) -> None:
    """Generate the tailored resume and cover letter for a posted job."""
    from users.models import CoverLetterSample

    from .generation import generate_documents
    from .models import JobPosting, ParsedResume

    job_posting = JobPosting.objects.get(pk=job_posting_id)
    parsed = ParsedResume.objects.get(resume_id=resume_id, user=job_posting.user)
    sample = (
        CoverLetterSample.objects.filter(user=job_posting.user)
        .order_by('-is_default', '-created_at')
        .first()
    )
    generate_documents(job_posting, parsed, sample.body if sample else '')
