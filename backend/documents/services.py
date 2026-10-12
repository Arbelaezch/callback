import logging

from pipeline.llm import analyze_resume
from pipeline.storage import read_file

from .models import ParsedResume

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
