"""Prompt text for the document generation stages."""

RESUME_ANALYSIS_SYSTEM = (
    'You analyse resumes. Given a resume PDF, extract (1) its content as '
    'structured data and (2) its visual layout as a formatting spec. '
    'Copy every fact exactly as written: do not summarise, correct, add or '
    'drop anything. Use empty strings for fields the resume does not have. '
    'For the layout, measure what you see (fonts, margins, spacing, section '
    'order and styling) so the same design can be re-rendered with new content.'
)

RESUME_ANALYSIS_USER = 'Extract the content and layout of this resume.'
