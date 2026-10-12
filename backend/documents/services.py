import logging

from django.db import transaction
from django.utils import timezone

from pipeline.llm import analyze_resume
from pipeline.storage import read_file

from .models import ParsedResume, SourceDocumentSection
from .search import index_sections
from .sectioning import split_sections

logger = logging.getLogger(__name__)


def parse_resume(resume) -> ParsedResume:
    """
    Analyse a ready Resume and store its structured content and layout.
    Re-running replaces the previous parse.

    Raises ValueError if the resume has no stored file yet.
    """
    if resume.status != 'ready':
        raise ValueError(f'Resume {resume.pk} is {resume.status}, not ready')

    result = analyze_resume(read_file(resume.s3_key))
    parsed, _ = ParsedResume.objects.update_or_create(
        resume=resume,
        defaults={
            'user': resume.user,
            'content': result['content'],
            'layout': result['layout'],
        },
    )
    logger.info('Parsed resume %s for user %s', resume.pk, resume.user_id)
    return parsed


def index_upload_source(source) -> int:
    """
    Read an uploaded ContextSource, replace its sections and mark it ready.
    Returns the number of sections. On failure the source is marked failed
    with the error recorded, and the exception is re-raised.
    """
    try:
        text = read_file(source.s3_key).decode('utf-8')
        sections = split_sections(text)
        if not sections:
            raise ValueError('Document has no text')

        with transaction.atomic():
            source.sections.all().delete()
            SourceDocumentSection.objects.bulk_create(
                SourceDocumentSection(
                    source=source, path=source.label or 'document', heading=heading, text=body,
                )
                for heading, body in sections
            )
            index_sections(source.pk)
            source.status = 'ready'
            source.error = ''
            source.last_synced_at = timezone.now()
            source.save(update_fields=['status', 'error', 'last_synced_at'])
    except Exception as exc:
        source.status = 'failed'
        source.error = str(exc)
        source.save(update_fields=['status', 'error'])
        raise

    logger.info('Indexed source %s: %d sections', source.pk, len(sections))
    return len(sections)
