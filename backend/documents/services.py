import logging
import os

from django.db import transaction
from django.utils import timezone

from callback.config import COVER_LETTER_SAMPLE_MAX_CHARS
from pipeline.llm import analyze_resume, extract_pdf_text
from pipeline.storage import read_file
from users.models import Resume

from .models import ParsedResume, SourceDocumentSection
from .search import index_sections
from .sectioning import split_sections

logger = logging.getLogger(__name__)


def _set_parse_status(resume, parse_status, parse_error):
    # A queryset update, not resume.save(): the instance may be stale, and
    # Resume.save would clear a default the user chose in the meantime.
    resume.parse_status = parse_status
    resume.parse_error = parse_error
    Resume.objects.filter(pk=resume.pk).update(
        parse_status=parse_status, parse_error=parse_error, updated_at=timezone.now(),
    )


def parse_resume(resume) -> ParsedResume:
    """
    Analyse a ready Resume and store its structured content and layout.
    Re-running replaces the previous parse.

    Sets resume.parse_status to 'ready' on success. On any failure (including
    a resume with no stored file yet) it is set to 'failed' with the error
    recorded, and the exception is re-raised.
    """
    try:
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
        _set_parse_status(resume, 'ready', '')
    except Exception as exc:
        _set_parse_status(resume, 'failed', str(exc) or exc.__class__.__name__)
        raise
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


def _extract_sample_text(sample) -> str:
    data = read_file(sample.s3_key)
    ext = os.path.splitext(sample.filename)[1].lower()
    if ext == '.pdf':
        try:
            return extract_pdf_text(data)
        except Exception:
            logger.exception('PDF text extraction failed for cover letter sample %s', sample.pk)
            raise ValueError('Could not read text from this PDF. Try a .txt file instead.')
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError('Text file must be UTF-8.')


def ingest_cover_letter_sample(sample):
    """
    Extract the text of an uploaded CoverLetterSample into its body and make
    it the user's ready default sample.

    On an extraction problem (no text, too long, not UTF-8, unreadable PDF)
    the sample is marked failed with the error recorded and the ValueError is
    re-raised. On any other failure (such as a storage read) it is marked
    failed with an empty error and the exception is re-raised. A failed
    sample never becomes the default, so the previous default stays in place.
    """
    try:
        text = _extract_sample_text(sample).strip()
        if not text:
            raise ValueError('Document has no text')
        if len(text) > COVER_LETTER_SAMPLE_MAX_CHARS:
            raise ValueError(
                f'Cover letter is too long (over {COVER_LETTER_SAMPLE_MAX_CHARS} characters). '
                'Upload a single letter.'
            )
    except ValueError as exc:
        _fail_sample(sample, str(exc))
        raise
    except Exception:
        _fail_sample(sample, '')
        raise

    sample.body = text
    sample.status = 'ready'
    sample.error = ''
    sample.is_default = True
    # Full save: CoverLetterSample.save clears the user's other defaults.
    sample.save()
    logger.info('Ingested cover letter sample %s for user %s', sample.pk, sample.user_id)
    return sample


def _fail_sample(sample, error):
    sample.status = 'failed'
    sample.error = error
    sample.save(update_fields=['status', 'error', 'updated_at'])
