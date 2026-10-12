"""
Generate a tailored resume and cover letter for a JobPosting.

Stages: context scout (light model) -> writer (strong model) -> verifier
(light model). Only sources the user has added and that are ready are
searchable; with none, the scout is skipped and the writer works from the
resume and cover letter sample alone.
"""

import hashlib
import json
import logging

from django.db.models.functions import Length

from pipeline.llm import build_voice_profile, run_scout, verify_documents, write_documents

from .models import ContextSource, GeneratedDocument, SourceDocumentSection, VoiceProfile
from .search import search_sections

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 300
VOICE_SECTIONS = 10


def _sources_summary(sources) -> str:
    return '\n'.join(
        f'- id {s.pk}: {s.label or s.get_kind_display()} ({s.get_kind_display()})' for s in sources
    )


def _make_handlers(user, source_ids: set[int]) -> dict:
    def search(query: str, source_id: int | None = None) -> str:
        if source_id is not None and source_id not in source_ids:
            return 'Unknown source_id.'
        sections = search_sections(user, query, source_id=source_id)
        rows = [
            {
                'section_id': s.pk,
                'source': s.source.label or s.source.get_kind_display(),
                'path': s.path,
                'heading': s.heading,
                'snippet': s.text[:SNIPPET_CHARS],
            }
            for s in sections
        ]
        return json.dumps(rows) if rows else 'No matches. Try different keywords.'

    def read(section_id: int) -> str:
        section = SourceDocumentSection.objects.filter(
            pk=section_id, source__user=user, source__status='ready',
        ).select_related('source').first()
        if section is None:
            return 'No such section.'
        return json.dumps({
            'source': section.source.label or section.source.get_kind_display(),
            'path': section.path,
            'heading': section.heading,
            'text': section.text,
        })

    return {'search_sections': search, 'read_section': read}


def get_voice_profile(user, sources, cover_letter_sample: str) -> dict:
    """Return the user's voice profile, rebuilding only if the inputs changed."""
    fingerprint = hashlib.sha256(json.dumps(
        [cover_letter_sample, sorted((s.pk, str(s.last_synced_at)) for s in sources)],
    ).encode()).hexdigest()

    existing = VoiceProfile.objects.filter(user=user).first()
    if existing and existing.built_from_hash == fingerprint:
        return {'notes': existing.notes, 'excerpts': existing.excerpts}

    longest = SourceDocumentSection.objects.filter(
        source__in=sources,
    ).annotate(size=Length('text')).order_by('-size')[:VOICE_SECTIONS]
    samples = [cover_letter_sample] + [s.text for s in longest]
    voice = build_voice_profile(samples)

    VoiceProfile.objects.update_or_create(
        user=user,
        defaults={
            'notes': voice['notes'],
            'excerpts': voice['excerpts'],
            'built_from_hash': fingerprint,
        },
    )
    return voice


def generate_documents(job_posting, parsed_resume, cover_letter_sample: str = '') -> tuple:
    """
    Run all stages and store the results as two GeneratedDocuments.
    Returns (resume_doc, cover_letter_doc). If any stage fails, both documents
    are marked failed with the error and the exception is re-raised.
    """
    user = job_posting.user
    next_version = (
        GeneratedDocument.objects.filter(job_posting=job_posting, kind='resume').count() + 1
    )
    resume_doc = GeneratedDocument.objects.create(
        job_posting=job_posting, kind='resume', version=next_version,
    )
    letter_doc = GeneratedDocument.objects.create(
        job_posting=job_posting, kind='cover_letter', version=next_version,
    )

    try:
        job = {
            'title': job_posting.title,
            'company': job_posting.company,
            'description': job_posting.description,
        }
        sources = list(ContextSource.objects.filter(user=user, status='ready'))

        brief = run_scout(
            job,
            _sources_summary(sources),
            _make_handlers(user, {s.pk for s in sources}) if sources else {},
        )
        voice = get_voice_profile(user, sources, cover_letter_sample)
        written = write_documents(job, parsed_resume.content, brief, voice, cover_letter_sample)
        claims = verify_documents(
            job,
            parsed_resume.content, brief, written['resume'], written['cover_letter_markdown'],
        )
    except Exception as exc:
        for doc in (resume_doc, letter_doc):
            doc.status = 'failed'
            doc.error = str(exc)
            doc.save(update_fields=['status', 'error'])
        logger.exception('Document generation failed for job posting %s', job_posting.pk)
        raise

    resume_doc.content = written['resume']
    resume_doc.unsupported_claims = [c for c in claims if c['document'] == 'resume']
    resume_doc.status = 'ready'
    resume_doc.save(update_fields=['content', 'unsupported_claims', 'status'])

    letter_doc.markdown = written['cover_letter_markdown']
    letter_doc.unsupported_claims = [c for c in claims if c['document'] == 'cover_letter']
    letter_doc.status = 'ready'
    letter_doc.save(update_fields=['markdown', 'unsupported_claims', 'status'])

    logger.info('Generated documents for job posting %s (%d flagged claims)', job_posting.pk, len(claims))
    return resume_doc, letter_doc
