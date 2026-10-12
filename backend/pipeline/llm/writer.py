"""Writer and verifier stages for tailored application documents."""

import json
import logging

from callback.config import (
    LLM_MAX_TOKENS,
    LLM_MAX_TOKENS_WRITER,
    LLM_MODEL_VERIFIER,
    LLM_MODEL_WRITER,
    LLM_TIMEOUT_SECONDS_LONG,
    VOICE_SAMPLE_MAX_CHARS,
    LLM_MODEL_SCOUT,
)

from .client import call_structured
from .prompts import (
    VERIFIER_SYSTEM,
    VERIFIER_USER,
    VOICE_SYSTEM,
    WRITER_SYSTEM,
    WRITER_USER,
)
from .schemas import GENERATION_SCHEMA, VERIFICATION_SCHEMA, VOICE_PROFILE_SCHEMA

logger = logging.getLogger(__name__)


def build_voice_profile(samples: list[str]) -> dict:
    """Describe the user's writing voice from their own text. Light model."""
    text = '\n\n---\n\n'.join(s for s in samples if s.strip())[:VOICE_SAMPLE_MAX_CHARS]
    if not text:
        return {'notes': '', 'excerpts': []}
    return call_structured(
        model=LLM_MODEL_SCOUT,
        system=VOICE_SYSTEM,
        content=[{'type': 'text', 'text': text}],
        schema=VOICE_PROFILE_SCHEMA,
        max_tokens=LLM_MAX_TOKENS,
    )


def write_documents(
    job: dict,
    resume_content: dict,
    brief: dict,
    voice: dict,
    cover_letter_sample: str,
) -> dict:
    """
    Produce {'resume': content dict, 'cover_letter_markdown': str}.
    The writer sees only what is passed here; it does no searching.
    """
    prompt = WRITER_USER.format(
        title=job.get('title', ''),
        company=job.get('company', ''),
        description=job.get('description', ''),
        resume_json=json.dumps(resume_content, indent=2),
        brief_json=json.dumps(brief, indent=2),
        voice_notes=voice.get('notes') or '(none available)',
        voice_excerpts='\n'.join(f'- {e}' for e in voice.get('excerpts', [])) or '(none)',
        cover_letter_sample=cover_letter_sample or '(none provided)',
    )
    return call_structured(
        model=LLM_MODEL_WRITER,
        system=WRITER_SYSTEM,
        content=[{'type': 'text', 'text': prompt}],
        schema=GENERATION_SCHEMA,
        max_tokens=LLM_MAX_TOKENS_WRITER,
        timeout=LLM_TIMEOUT_SECONDS_LONG,
    )


def verify_documents(
    job: dict,
    original_resume: dict,
    brief: dict,
    resume: dict,
    cover_letter: str,
) -> list[dict]:
    """Return [{document, claim, reason}] for claims the sources do not support."""
    prompt = VERIFIER_USER.format(
        title=job.get('title', ''),
        company=job.get('company', ''),
        description=job.get('description', ''),
        original_json=json.dumps(original_resume, indent=2),
        brief_json=json.dumps(brief, indent=2),
        resume_json=json.dumps(resume, indent=2),
        cover_letter=cover_letter,
    )
    result = call_structured(
        model=LLM_MODEL_VERIFIER,
        system=VERIFIER_SYSTEM,
        content=[{'type': 'text', 'text': prompt}],
        schema=VERIFICATION_SCHEMA,
        max_tokens=LLM_MAX_TOKENS_WRITER,
        timeout=LLM_TIMEOUT_SECONDS_LONG,
    )
    return result['unsupported_claims']
