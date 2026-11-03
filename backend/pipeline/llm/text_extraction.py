"""PDF -> plain text, for uploaded cover letter samples."""

import base64

from callback.config import LLM_MAX_TOKENS_EXTRACTION, LLM_MODEL_TEXT_EXTRACTION, LLM_TIMEOUT_SECONDS_EXTRACTION

from .client import call_structured
from .prompts import PDF_TEXT_EXTRACTION_SYSTEM, PDF_TEXT_EXTRACTION_USER
from .schemas import PDF_TEXT_SCHEMA


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Transcribe a PDF's text with the model's native PDF input. Returns stripped text ('' if none)."""
    result = call_structured(
        model=LLM_MODEL_TEXT_EXTRACTION,
        system=PDF_TEXT_EXTRACTION_SYSTEM,
        content=[
            {
                'type': 'document',
                'source': {
                    'type': 'base64',
                    'media_type': 'application/pdf',
                    'data': base64.standard_b64encode(pdf_bytes).decode('ascii'),
                },
            },
            {'type': 'text', 'text': PDF_TEXT_EXTRACTION_USER},
        ],
        schema=PDF_TEXT_SCHEMA,
        max_tokens=LLM_MAX_TOKENS_EXTRACTION,
        timeout=LLM_TIMEOUT_SECONDS_EXTRACTION,
        max_retries=0,
    )
    return result['text'].strip()
