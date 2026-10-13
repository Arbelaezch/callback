import logging

from celery import shared_task
from django.utils import timezone

from users.models import Resume

from .services import parse_resume

logger = logging.getLogger(__name__)


@shared_task
def parse_resume_task(resume_id: int) -> int:
    """Parse a Resume in the background. Returns the ParsedResume id."""
    return parse_resume(Resume.objects.get(pk=resume_id)).pk


@shared_task
def generate_documents_task(resume_doc_id: int, letter_doc_id: int) -> None:
    """Fill the pending resume and cover letter rows for a posted job."""
    from users.models import CoverLetterSample

    from .generation import generate_documents
    from .models import GeneratedDocument, ParsedResume

    docs = GeneratedDocument.objects.select_related('job_posting').in_bulk([resume_doc_id, letter_doc_id])
    resume_doc = docs.get(resume_doc_id)
    letter_doc = docs.get(letter_doc_id)
    if resume_doc is None or letter_doc is None:
        logger.warning('Generation documents %s/%s no longer exist', resume_doc_id, letter_doc_id)
        return

    if resume_doc.status != 'pending' or letter_doc.status != 'pending':
        logger.info('Skipping generation for %s/%s: no longer pending', resume_doc_id, letter_doc_id)
        return

    user = resume_doc.job_posting.user
    parsed = ParsedResume.objects.filter(resume_id=resume_doc.resume_id, user=user).first()
    if parsed is None:
        GeneratedDocument.objects.filter(pk__in=[resume_doc.pk, letter_doc.pk]).update(
            status='failed',
            error='The resume for this job is no longer available. Please generate again.',
            updated_at=timezone.now(),
        )
        return
    sample = (
        CoverLetterSample.objects.filter(user=user)
        .order_by('-is_default', '-created_at')
        .first()
    )
    generate_documents(resume_doc, letter_doc, parsed, sample.body if sample else '')
