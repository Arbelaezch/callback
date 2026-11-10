"""
Render generated documents to HTML and PDF.

The resume layout spec comes from the model (see RESUME_LAYOUT_SCHEMA), so every
value is validated before it reaches CSS: numbers are clamped, enums checked,
colors matched against a hex pattern and fonts mapped to a fixed stack. Nothing
the model wrote is ever emitted into a stylesheet verbatim.

Markdown for cover letters is rendered with raw HTML disabled, and WeasyPrint
is given a URL fetcher that allows no protocol at all, so a crafted <img src> can
neither read local files nor make network calls.
"""

import re

from django.template.loader import render_to_string
from markdown_it import MarkdownIt
from weasyprint import HTML
from weasyprint.urls import URLFetcher

KNOWN_SECTIONS = ['summary', 'experience', 'projects', 'education', 'skills', 'additional']
DEFAULT_SECTION_ORDER = ['summary', 'experience', 'projects', 'education', 'skills', 'additional']
DEFAULT_SECTION_TITLES = {
    'summary': 'Summary',
    'experience': 'Experience',
    'projects': 'Projects',
    'education': 'Education',
    'skills': 'Skills',
}
_SECTION_TITLE_MAX = 60
NAME_STYLES = ('normal', 'uppercase', 'small_caps')
_FIXED_SECTIONS = ('summary', 'experience', 'projects', 'education', 'skills')

_HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')

_FONT_STACKS = {
    'serif': 'Liberation Serif, Times New Roman, Times, serif',
    'sans': 'Liberation Sans, Arial, Helvetica, sans-serif',
    'mono': 'Liberation Mono, Courier New, monospace',
}
_MONO_HINTS = ('mono', 'courier', 'consolas', 'menlo')
# Checked before the serif hints so "Century Gothic" and "Roboto" stay sans.
_SANS_HINTS = (
    'sans', 'gothic', 'grotesk', 'helvetica', 'arial', 'calibri', 'lato', 'roboto',
    'open sans', 'source sans', 'fira sans', 'raleway',
)
_SERIF_HINTS = (
    'georgia', 'times', 'garamond', 'cambria', 'palatino', 'book', 'serif',
    'computer modern', 'latin modern', 'cmu', 'lmroman', 'charter', 'baskerville', 'caslon',
    'minion', 'libertine', 'crimson', 'merriweather', 'didot', 'bodoni', 'century', 'lora',
    'playfair', 'spectral', 'tinos', 'cochin',
)

_markdown = MarkdownIt('commonmark', {'html': False, 'breaks': True}).enable('table')


def _font_stack(name) -> str:
    lowered = str(name or '').lower()
    if any(hint in lowered for hint in _MONO_HINTS):
        return _FONT_STACKS['mono']
    if 'slab' in lowered:
        return _FONT_STACKS['serif']
    if any(hint in lowered for hint in _SANS_HINTS):
        return _FONT_STACKS['sans']
    if any(hint in lowered for hint in _SERIF_HINTS):
        return _FONT_STACKS['serif']
    return _FONT_STACKS['sans']


def _number(value, default, low, high) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _choice(value, allowed, default):
    return value if value in allowed else default


def resolve_layout(layout: dict | None) -> dict:
    """Turn a model-written layout spec into validated values safe to put in CSS."""
    layout = layout or {}
    margins = layout.get('margins_in') or {}
    return {
        'page_size': _choice(layout.get('page_size'), ('letter', 'a4'), 'letter'),
        'font_stack': _font_stack(layout.get('font_family')),
        'font_size_pt': round(_number(layout.get('base_font_size_pt'), 10.5, 8, 13), 2),
        'line_height': round(_number(layout.get('line_height'), 1.3, 1.0, 1.7), 2),
        'margin_top': round(_number(margins.get('top'), 0.6, 0.3, 1.25), 2),
        'margin_right': round(_number(margins.get('right'), 0.7, 0.3, 1.25), 2),
        'margin_bottom': round(_number(margins.get('bottom'), 0.6, 0.3, 1.25), 2),
        'margin_left': round(_number(margins.get('left'), 0.7, 0.3, 1.25), 2),
        'header_align': _choice(layout.get('header_alignment'), ('left', 'center'), 'left'),
        'name_style': _choice(layout.get('name_style'), NAME_STYLES, 'normal'),
        'title_style': _choice(
            layout.get('section_title_style'), ('uppercase', 'small_caps', 'title_case'), 'uppercase',
        ),
        'section_rule': bool(layout.get('section_rule', True)),
        'bullet_style': _choice(layout.get('bullet_style'), ('disc', 'dash', 'none'), 'disc'),
        'accent_color': layout.get('accent_color') if _HEX_COLOR.match(str(layout.get('accent_color') or '')) else '',
        'section_order': _section_order(layout.get('section_order')),
        'section_titles': _section_titles(layout.get('source_sections')),
    }


def _section_order(requested) -> list[str]:
    """Requested order first, then any known section it left out, so none is dropped.

    A summary the source did not have (the writer may add one) goes first, not last.
    """
    order = [s for s in (requested or []) if s in KNOWN_SECTIONS]
    order = list(dict.fromkeys(order))
    if 'summary' not in order:
        order.insert(0, 'summary')
    return order + [s for s in DEFAULT_SECTION_ORDER if s not in order]


def _section_titles(source_sections) -> dict[str, str]:
    """Headings as printed on the source, falling back to the built-in titles.

    Only plain text survives (whitespace collapsed, capped in length); the
    template autoescapes it.
    """
    titles = dict(DEFAULT_SECTION_TITLES)
    found = set()
    for item in source_sections if isinstance(source_sections, list) else []:
        if not isinstance(item, dict):
            continue
        key, title = item.get('placed_in'), item.get('title')
        if key not in titles or key in found or not isinstance(title, str):
            continue
        title = ' '.join(title.split())[:_SECTION_TITLE_MAX].strip()
        if title:
            titles[key] = title
            found.add(key)
    return titles


def _norm_title(title) -> str:
    return ' '.join(title.split()).casefold()


def resume_blocks(section_order, source_sections, additional_sections) -> list[dict]:
    """Order the resume's blocks, placing each additional section where the source had it.

    An additional section follows the fixed section printed before it in
    source_sections. Ones not found there render at the 'additional' slot.
    """
    sections = [
        s for s in (additional_sections if isinstance(additional_sections, list) else [])
        if isinstance(s, dict) and isinstance(s.get('entries'), list) and s['entries']
    ]
    anchors = {}
    last_fixed = None
    for item in source_sections if isinstance(source_sections, list) else []:
        if not isinstance(item, dict):
            continue
        placed = item.get('placed_in')
        if placed in _FIXED_SECTIONS:
            last_fixed = placed
        elif placed == 'additional' and isinstance(item.get('title'), str):
            anchors.setdefault(_norm_title(item['title']), last_fixed)

    def known(section):
        title = section.get('title')
        return isinstance(title, str) and _norm_title(title) in anchors

    def block(section):
        return {'key': 'additional', 'section': section}

    blocks = [block(s) for s in sections if known(s) and anchors[_norm_title(s['title'])] is None]
    for key in section_order:
        if key == 'additional':
            blocks.extend(block(s) for s in sections if not known(s))
        else:
            blocks.append({'key': key})
            blocks.extend(
                block(s) for s in sections if known(s) and anchors[_norm_title(s['title'])] == key
            )
    return blocks


def render_resume_html(content: dict, layout: dict | None) -> str:
    resolved = resolve_layout(layout)
    return render_to_string('documents/resume.html', {
        'content': content or {},
        'header': (content or {}).get('header') or {},
        'layout': resolved,
        'blocks': resume_blocks(
            resolved['section_order'], (layout or {}).get('source_sections'),
            (content or {}).get('additional_sections'),
        ),
        'css': render_to_string('documents/styles.css', {'layout': resolved}),
    })


def render_cover_letter_html(markdown: str, header: dict | None, layout: dict | None) -> str:
    resolved = resolve_layout(layout)
    return render_to_string('documents/cover_letter.html', {
        'header': header or {},
        'body_html': _markdown.render(markdown or ''),
        'layout': resolved,
        'css': render_to_string('documents/styles.css', {'layout': resolved}),
    })


# No protocol is allowed, so images, stylesheets and fonts referenced by the
# content are skipped instead of fetched (no file:// reads, no network calls).
_NO_FETCH = URLFetcher(allowed_protocols=())


def html_to_pdf(html: str) -> tuple[bytes, int]:
    """Return (pdf_bytes, page_count)."""
    document = HTML(string=html, url_fetcher=_NO_FETCH).render()
    return document.write_pdf(), len(document.pages)
