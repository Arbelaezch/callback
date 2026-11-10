"""
JSON schemas for structured LLM output.

RESUME_CONTENT_SCHEMA is the single shape for resume facts: it is what resume
analysis extracts, what the writer tailors, and what the PDF template renders.
Sections outside the five fixed ones (certifications, awards, languages and so
on) go in the optional `additional_sections` list, so nothing has to be dropped.

RESUME_LAYOUT_SCHEMA describes the formatting. SOURCE_SECTIONS_SCHEMA lists every
heading printed on the source and where its content was put, so section titles
can be re-used and anything left unplaced can be reported.

Resume analysis is two calls against the same PDF: RESUME_CONTENT_ANALYSIS_SCHEMA
(content plus source_sections, so the call that places the content also reports
where each heading went) and RESUME_LAYOUT_SCHEMA. One combined schema is
rejected by the structured-output API ("The compiled grammar is too large"):
the strict-schema grammar has a size limit, so keep each sent schema small.

RESUME_LAYOUT_SCHEMA also reports decorative_elements (a fixed enum of kinds the
source prints, such as icons or charts) so the app can tell the user they are left out.
"""

from callback.config import DECORATIVE_ELEMENT_KINDS

_STR = {'type': 'string'}
_STR_LIST = {'type': 'array', 'items': _STR}

RESUME_CONTENT_SCHEMA = {
    'type': 'object',
    'properties': {
        'header': {
            'type': 'object',
            'properties': {
                'name': _STR,
                'headline': _STR,
                'email': _STR,
                'phone': _STR,
                'location': _STR,
                'links': _STR_LIST,
            },
            'required': ['name'],
        },
        'summary': _STR,
        'experience': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'company': _STR,
                    'title': _STR,
                    'location': _STR,
                    'start': _STR,
                    'end': _STR,
                    'bullets': _STR_LIST,
                },
                'required': ['company', 'title', 'bullets'],
            },
        },
        'projects': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'name': _STR,
                    'link': _STR,
                    'bullets': _STR_LIST,
                },
                'required': ['name', 'bullets'],
            },
        },
        'education': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'school': _STR,
                    'degree': _STR,
                    'start': _STR,
                    'end': _STR,
                    'details': _STR_LIST,
                },
                'required': ['school'],
            },
        },
        'skills': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {'category': _STR, 'items': _STR_LIST},
                'required': ['items'],
            },
        },
        # The strict schema sent to the model requires every property (client._strict_schema),
        # but content stored before this field existed may lack it, so readers must default it.
        'additional_sections': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'title': {
                        'type': 'string',
                        'description': 'Section heading exactly as printed, e.g. Certifications',
                    },
                    'entries': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'heading': _STR,
                                'detail': _STR,
                                'dates': _STR,
                                'bullets': _STR_LIST,
                            },
                            'required': ['heading'],
                        },
                    },
                },
                'required': ['title', 'entries'],
            },
        },
    },
    'required': ['header', 'experience', 'education', 'skills'],
}

RESUME_LAYOUT_SCHEMA = {
    'type': 'object',
    'properties': {
        'page_size': {'type': 'string', 'enum': ['letter', 'a4']},
        'font_family': _STR,
        'base_font_size_pt': {'type': 'number'},
        'margins_in': {
            'type': 'object',
            'properties': {
                'top': {'type': 'number'},
                'right': {'type': 'number'},
                'bottom': {'type': 'number'},
                'left': {'type': 'number'},
            },
        },
        'line_height': {'type': 'number'},
        'header_alignment': {'type': 'string', 'enum': ['left', 'center']},
        'name_style': {'type': 'string', 'enum': ['normal', 'uppercase', 'small_caps']},
        'section_order': {
            'type': 'array',
            'items': {
                'type': 'string',
                'enum': ['summary', 'experience', 'projects', 'education', 'skills', 'additional'],
            },
        },
        'section_title_style': {
            'type': 'string',
            'enum': ['uppercase', 'small_caps', 'title_case'],
        },
        'section_rule': {'type': 'boolean'},
        'bullet_style': {'type': 'string', 'enum': ['disc', 'dash', 'none']},
        'accent_color': {'type': 'string', 'description': 'Hex color, e.g. #1f3a5f, or empty'},
        'columns': {
            'type': 'integer',
            'enum': [1, 2],
            'description': '2 if the resume uses two columns or a sidebar, else 1',
        },
        'decorative_elements': {
            'type': 'array',
            'description': 'Decorative elements printed on the resume (left out when re-rendered); empty if none',
            'items': {'type': 'string', 'enum': list(DECORATIVE_ELEMENT_KINDS)},
        },
    },
    'required': ['page_size', 'font_family', 'base_font_size_pt', 'section_order'],
}

SOURCE_SECTIONS_SCHEMA = {
    'type': 'array',
    'description': (
        'Every section heading printed on the resume, in reading order (main column '
        'first, then sidebar), and the content field its text was put in.'
    ),
    'items': {
        'type': 'object',
        'properties': {
            'title': _STR,
            'placed_in': {
                'type': 'string',
                'enum': [
                    'header', 'summary', 'experience', 'projects', 'education', 'skills', 'additional',
                ],
            },
        },
        'required': ['title', 'placed_in'],
    },
}

RESUME_CONTENT_ANALYSIS_SCHEMA = {
    'type': 'object',
    'properties': {
        'content': RESUME_CONTENT_SCHEMA,
        'source_sections': SOURCE_SECTIONS_SCHEMA,
    },
    'required': ['content', 'source_sections'],
}


# ---------------------------------------------------------------------------
# Generation stages
# ---------------------------------------------------------------------------

CONTEXT_BRIEF_SCHEMA = {
    'type': 'object',
    'properties': {
        'facts': {
            'type': 'array',
            'description': 'Material from the user sources that is relevant to this job.',
            'items': {
                'type': 'object',
                'properties': {
                    'quote': {'type': 'string', 'description': 'Verbatim text from the source.'},
                    'source': {'type': 'string', 'description': 'Source label and path.'},
                    'why_relevant': {'type': 'string'},
                },
                'required': ['quote', 'source', 'why_relevant'],
            },
        },
    },
    'required': ['facts'],
}

VOICE_PROFILE_SCHEMA = {
    'type': 'object',
    'properties': {
        'notes': {
            'type': 'string',
            'description': 'Tone, sentence length, vocabulary habits, typical openers and closers.',
        },
        'excerpts': {
            'type': 'array',
            'description': '2-3 short verbatim excerpts that show the voice.',
            'items': {'type': 'string'},
        },
    },
    'required': ['notes', 'excerpts'],
}

GENERATION_SCHEMA = {
    'type': 'object',
    'properties': {
        'resume': RESUME_CONTENT_SCHEMA,
        'cover_letter_markdown': {'type': 'string'},
    },
    'required': ['resume', 'cover_letter_markdown'],
}

VERIFICATION_SCHEMA = {
    'type': 'object',
    'properties': {
        'unsupported_claims': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'document': {'type': 'string', 'enum': ['resume', 'cover_letter']},
                    'claim': {'type': 'string'},
                    'reason': {'type': 'string'},
                },
                'required': ['document', 'claim', 'reason'],
            },
        },
    },
    'required': ['unsupported_claims'],
}

PDF_TEXT_SCHEMA = {
    'type': 'object',
    'properties': {'text': {'type': 'string'}},
}
