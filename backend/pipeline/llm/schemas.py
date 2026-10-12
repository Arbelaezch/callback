"""
JSON schemas for structured LLM output.

RESUME_CONTENT_SCHEMA is the single shape for resume facts: it is what resume
analysis extracts, what the writer tailors, and what the PDF template renders.
"""

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
        'section_order': {
            'type': 'array',
            'items': {
                'type': 'string',
                'enum': ['summary', 'experience', 'projects', 'education', 'skills'],
            },
        },
        'section_title_style': {
            'type': 'string',
            'enum': ['uppercase', 'small_caps', 'title_case'],
        },
        'section_rule': {'type': 'boolean'},
        'bullet_style': {'type': 'string', 'enum': ['disc', 'dash', 'none']},
        'accent_color': {'type': 'string', 'description': 'Hex color, e.g. #1f3a5f, or empty'},
        'columns': {'type': 'integer', 'enum': [1, 2]},
    },
    'required': ['page_size', 'font_family', 'base_font_size_pt', 'section_order'],
}

RESUME_ANALYSIS_SCHEMA = {
    'type': 'object',
    'properties': {
        'content': RESUME_CONTENT_SCHEMA,
        'layout': RESUME_LAYOUT_SCHEMA,
    },
    'required': ['content', 'layout'],
}
