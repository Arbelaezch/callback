"""Resume PDF -> structured content + layout."""

import base64
import logging

from callback.config import LLM_MAX_TOKENS_WRITER, LLM_MODEL_WRITER, LLM_TIMEOUT_SECONDS_LONG

from .client import call_structured
from .prompts import RESUME_ANALYSIS_SYSTEM, RESUME_ANALYSIS_USER
from .schemas import RESUME_ANALYSIS_SCHEMA

logger = logging.getLogger(__name__)


def analyze_resume(pdf_bytes: bytes) -> dict:
    """
    Read a resume PDF with the model's native PDF input.

    Returns {'content': dict, 'layout': dict}; see schemas.RESUME_ANALYSIS_SCHEMA.
    Uses the writer-tier model because accurate layout measurement is a vision
    task a light model does poorly.
    """
    result = call_structured(
        model=LLM_MODEL_WRITER,
        system=RESUME_ANALYSIS_SYSTEM,
        content=[
            {
                'type': 'document',
                'source': {
                    'type': 'base64',
                    'media_type': 'application/pdf',
                    'data': base64.standard_b64encode(pdf_bytes).decode('ascii'),
                },
            },
            {'type': 'text', 'text': RESUME_ANALYSIS_USER},
        ],
        schema=RESUME_ANALYSIS_SCHEMA,
        max_tokens=LLM_MAX_TOKENS_WRITER,
        timeout=LLM_TIMEOUT_SECONDS_LONG,
    )
    logger.info('Analysed resume: %d experience entries', len(result['content'].get('experience', [])))
    return result
