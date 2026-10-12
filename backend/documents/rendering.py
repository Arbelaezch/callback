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

KNOWN_SECTIONS = ['summary', 'experience', 'projects', 'education', 'skills']
DEFAULT_SECTION_ORDER = ['summary', 'experience', 'projects', 'education', 'skills']

_HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')

_FONT_STACKS = {
    'serif': 'Liberation Serif, Times New Roman, Times, serif',
    'sans': 'Liberation Sans, Arial, Helvetica, sans-serif',
    'mono': 'Liberation Mono, Courier New, monospace',
}
_MONO_HINTS = ('mono', 'courier', 'consolas', 'menlo')
_SERIF_HINTS = ('georgia', 'times', 'garamond', 'cambria', 'palatino', 'book', 'serif')

_markdown = MarkdownIt('commonmark', {'html': False, 'breaks': True}).enable('table')


def _font_stack(name) -> str:
    lowered = str(name or '').lower()
    if any(hint in lowered for hint in _MONO_HINTS):
        return _FONT_STACKS['mono']
    if 'sans' not in lowered and any(hint in lowered for hint in _SERIF_HINTS):
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
        'title_style': _choice(
            layout.get('section_title_style'), ('uppercase', 'small_caps', 'title_case'), 'uppercase',
        ),
        'section_rule': bool(layout.get('section_rule', True)),
        'bullet_style': _choice(layout.get('bullet_style'), ('disc', 'dash', 'none'), 'disc'),
        'accent_color': layout.get('accent_color') if _HEX_COLOR.match(str(layout.get('accent_color') or '')) else '',
        'section_order': _section_order(layout.get('section_order')),
    }


def _section_order(requested) -> list[str]:
    """Requested order first, then any known section it left out, so none is dropped."""
    order = [s for s in (requested or []) if s in KNOWN_SECTIONS]
    order = list(dict.fromkeys(order))
    return order + [s for s in DEFAULT_SECTION_ORDER if s not in order]


def render_resume_html(content: dict, layout: dict | None) -> str:
    resolved = resolve_layout(layout)
    return render_to_string('documents/resume.html', {
        'content': content or {},
        'header': (content or {}).get('header') or {},
        'layout': resolved,
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
