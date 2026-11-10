"""
Compare a parsed resume with its tailored version (issue #35).

Reports whole sections the writer dropped, links it removed, additional-section
titles it invented, and where a summary lands in the rendered block order. Pure
Python (no database, no model calls); it backs the `check_tailoring` command.
"""

from documents.rendering import _norm_title, resolve_layout, resume_blocks

_FIXED_KEYS = ('summary', 'experience', 'projects', 'education', 'skills')


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _filled(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return bool(value)


def _additional(content: dict) -> list[dict]:
    return [s for s in _list(content.get('additional_sections')) if isinstance(s, dict)]


def _titled(sections: list[dict]) -> dict:
    """Map normalized title -> section, for sections with a string title."""
    return {
        _norm_title(s['title']): s for s in sections if isinstance(s.get('title'), str)
    }


def _norm_link(link) -> str:
    return str(link).strip().casefold().rstrip('/')


def compare_tailoring(source_content: dict, tailored_content: dict, layout: dict | None) -> dict:
    source = _dict(source_content)
    tailored = _dict(tailored_content)
    layout_dict = _dict(layout)

    source_has_summary = _filled(source.get('summary'))
    tailored_has_summary = _filled(tailored.get('summary'))

    summary_block_index = None
    if tailored_has_summary:
        blocks = resume_blocks(
            resolve_layout(layout_dict)['section_order'],
            layout_dict.get('source_sections'),
            tailored.get('additional_sections'),
        )
        for index, block in enumerate(blocks):
            if block.get('key') == 'summary':
                summary_block_index = index
                break

    sections_dropped = [
        key for key in _FIXED_KEYS if _filled(source.get(key)) and not _filled(tailored.get(key))
    ]
    tailored_titles = _titled(_additional(tailored))
    for section in _additional(source):
        title = section.get('title')
        if not isinstance(title, str) or not _filled(section.get('entries')):
            continue
        match = tailored_titles.get(_norm_title(title))
        if match is None or not _filled(match.get('entries')):
            sections_dropped.append(f'additional:{title}')

    source_titles = _titled(_additional(source))
    additional_titles_added = [
        s['title'] for s in _additional(tailored)
        if isinstance(s.get('title'), str) and _norm_title(s['title']) not in source_titles
    ]

    tailored_links = {_norm_link(x) for x in _list(_dict(tailored.get('header')).get('links'))}
    links_dropped = [
        link for link in _list(_dict(source.get('header')).get('links'))
        if _norm_link(link) not in tailored_links
    ]

    return {
        'source_has_summary': source_has_summary,
        'tailored_has_summary': tailored_has_summary,
        'summary_added': not source_has_summary and tailored_has_summary,
        'summary_block_index': summary_block_index,
        'summary_first': None if summary_block_index is None else summary_block_index == 0,
        'sections_dropped': sections_dropped,
        'additional_titles_added': additional_titles_added,
        'links_dropped': links_dropped,
        'ok': not (sections_dropped or links_dropped or additional_titles_added),
    }
