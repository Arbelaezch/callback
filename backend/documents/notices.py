"""Plain-language notices about how a resume layout differs from the source.

Pure functions, no DB access. Input comes from model output, so every access is
tolerant of missing or malformed data.
"""
from callback.config import DECORATIVE_ELEMENT_KINDS

from .rendering import KNOWN_SECTIONS

FIXED_SECTIONS = [s for s in KNOWN_SECTIONS if s != 'additional']

COLUMNS_MESSAGE = (
    'Your original resume uses two columns or a sidebar. We lay it out in a single column, '
    'so it will look simpler than the original.'
)

DECORATIVE_LABELS = {
    'icons': 'icons',
    'charts': 'charts',
    'skill_ratings': 'skill rating bars or dots',
    'skill_pills': 'skill pills',
}


def _norm(text):
    return text.strip().casefold() if isinstance(text, str) else ''


def _additional_titles(content):
    sections = content.get('additional_sections')
    if not isinstance(sections, list):
        return set()
    return {_norm(s.get('title')) for s in sections if isinstance(s, dict) and _norm(s.get('title'))}


def _is_placed(placed_in, title, content, additional_titles):
    if placed_in == 'header':
        return True
    if placed_in in FIXED_SECTIONS:
        return bool(content.get(placed_in))
    if placed_in == 'additional':
        return _norm(title) in additional_titles
    return False


def layout_notices(content, layout):
    content = content if isinstance(content, dict) else {}
    layout = layout if isinstance(layout, dict) else {}
    notices = []

    if layout.get('columns') == 2:
        notices.append({'code': 'columns_simplified', 'message': COLUMNS_MESSAGE, 'sections': []})

    decorative = layout.get('decorative_elements')
    if isinstance(decorative, list):
        labels = [DECORATIVE_LABELS[k] for k in DECORATIVE_ELEMENT_KINDS if k in decorative]
        if labels:
            notices.append({
                'code': 'decorative_dropped',
                'message': (
                    f'Your original resume has decorative elements ({", ".join(labels)}). '
                    'They are not carried over, so this version will look simpler than the original.'
                ),
                'sections': [],
            })

    source_sections = layout.get('source_sections')
    if not isinstance(source_sections, list):
        return notices

    additional_titles = _additional_titles(content)
    unplaced = []
    for item in source_sections:
        if not isinstance(item, dict):
            continue
        title = item.get('title')
        if not isinstance(title, str) or not title.strip():
            continue
        title = title.strip()
        if _is_placed(item.get('placed_in'), title, content, additional_titles):
            continue
        if title not in unplaced:
            unplaced.append(title)

    if unplaced:
        notices.append({
            'code': 'sections_unplaced',
            'message': (
                'These sections from your original resume are not in this version: '
                f'{", ".join(unplaced)}. Add them in the editor if you need them.'
            ),
            'sections': unplaced,
        })
    return notices
