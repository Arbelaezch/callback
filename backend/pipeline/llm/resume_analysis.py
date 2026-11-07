"""Resume PDF -> structured content + layout."""

import base64
import logging

from callback.config import (
    LLM_MAX_TOKENS_RESUME_LAYOUT,
    LLM_MAX_TOKENS_WRITER,
    LLM_MODEL_WRITER,
    LLM_TIMEOUT_SECONDS_LONG,
)

from .client import call_structured
from .prompts import RESUME_CONTENT_SYSTEM, RESUME_CONTENT_USER, RESUME_LAYOUT_SYSTEM, RESUME_LAYOUT_USER
from .schemas import RESUME_CONTENT_ANALYSIS_SCHEMA, RESUME_LAYOUT_SCHEMA

logger = logging.getLogger(__name__)


def _pdf_block(pdf_bytes: bytes) -> dict:
    return {
        'type': 'document',
        'source': {
            'type': 'base64',
            'media_type': 'application/pdf',
            'data': base64.standard_b64encode(pdf_bytes).decode('ascii'),
        },
    }


def analyze_resume(pdf_bytes: bytes) -> dict:
    """
    Read a resume PDF with the model's native PDF input.

    Two sequential calls on the same PDF, because one combined strict schema is
    too large for the structured-output grammar: a content call
    (schemas.RESUME_CONTENT_ANALYSIS_SCHEMA, content plus source_sections) and a
    layout call (schemas.RESUME_LAYOUT_SCHEMA). source_sections comes from the
    content call so placed_in matches where the content was actually put.

    Returns {'content': dict, 'layout': dict}, with source_sections inside layout.
    Errors from either call propagate. Uses the writer-tier model because
    accurate layout measurement is a vision task a light model does poorly.
    """
    block = _pdf_block(pdf_bytes)
    extracted = call_structured(
        model=LLM_MODEL_WRITER,
        system=RESUME_CONTENT_SYSTEM,
        content=[block, {'type': 'text', 'text': RESUME_CONTENT_USER}],
        schema=RESUME_CONTENT_ANALYSIS_SCHEMA,
        max_tokens=LLM_MAX_TOKENS_WRITER,
        timeout=LLM_TIMEOUT_SECONDS_LONG,
    )
    layout = call_structured(
        model=LLM_MODEL_WRITER,
        system=RESUME_LAYOUT_SYSTEM,
        content=[block, {'type': 'text', 'text': RESUME_LAYOUT_USER}],
        schema=RESUME_LAYOUT_SCHEMA,
        max_tokens=LLM_MAX_TOKENS_RESUME_LAYOUT,
        timeout=LLM_TIMEOUT_SECONDS_LONG,
    )
    content = extracted['content']
    source_sections = extracted.get('source_sections') or []
    logger.info(
        'Analysed resume in two calls: %d experience entries, %d source headings',
        len(content.get('experience', [])), len(source_sections),
    )
    return {'content': content, 'layout': {**layout, 'source_sections': source_sections}}
