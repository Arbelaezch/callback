"""
Guards that tidy parsed resume content.

These functions only remove text that is already stored in full in another
field of the same entry (a location in `location`, a degree and its dates in
`degree`/`start`/`end`), and bare rating values or chart numbers (`80%`, `4/5`,
`●●●○○`), which are decoration, never facts. They never add or reword anything. No Django, no LLM.
"""

import copy
import re

_PREFIX_STRIP = ' ,;|-–—·\t'
_SEPARATORS = ',;|-–—·'
_RATING_VALUE = re.compile(
    r'^\s*(?:\d{1,3}(?:\.\d+)?\s*(?:%|/\s*\d{1,3})?|[●○◐◑◒◓◉◯★☆✦✧■□▪▫◆◇•]+)\s*$'
)
_TRAILING_GLYPHS = re.compile(r'\s*[●○◐◑◒◓◉◯★☆✦✧■□▪▫◆◇]+\s*$')
_DATE_FILLER = {'expected', 'anticipated', 'graduated', 'graduation', 'grad', 'class', 'of'}


def _tokens(value) -> list[str]:
    return re.findall(r'[^\W_]+', value.casefold()) if isinstance(value, str) else []


def _strip_location_from_company(job: dict) -> bool:
    company, location = job.get('company'), job.get('location')
    if not isinstance(company, str) or not isinstance(location, str):
        return False
    company, location = ' '.join(company.split()), ' '.join(location.split())
    if not company or not location or not company.casefold().endswith(location.casefold()):
        return False
    head = company[:-len(location)].rstrip(' \t')
    if not head or head[-1] not in _SEPARATORS:
        return False
    prefix = head.rstrip(_PREFIX_STRIP)
    if not prefix:
        return False
    job['company'] = prefix
    return True


def _drop_repeated_degree(entry: dict) -> int:
    degree = _tokens(entry.get('degree'))
    details = entry.get('details')
    if not degree or not isinstance(details, list):
        return 0
    allowed = set(_tokens(entry.get('start'))) | set(_tokens(entry.get('end'))) | _DATE_FILLER
    kept = []
    for detail in details:
        tokens = _tokens(detail)
        if tokens[:len(degree)] == degree and set(tokens[len(degree):]) <= allowed:
            continue
        kept.append(detail)
    dropped = len(details) - len(kept)
    if dropped:
        entry['details'] = kept
    return dropped


def _is_rating(value) -> bool:
    return isinstance(value, str) and bool(_RATING_VALUE.match(value))


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _clean_skills(skills: list) -> int:
    """Strip rating glyphs and drop rating-only items in place; return the count dropped."""
    dropped = 0
    for category in list(skills):
        if not isinstance(category, dict) or not isinstance(category.get('items'), list):
            continue
        before = category['items']
        kept = []
        for item in before:
            if not isinstance(item, str):
                kept.append(item)
                continue
            if _is_rating(item):
                dropped += 1
                continue
            stripped = _TRAILING_GLYPHS.sub('', item)
            if stripped != item:
                dropped += 1
            if stripped.strip():
                kept.append(stripped)
        category['items'] = kept
        if before and not kept:
            skills.remove(category)
    return dropped


def _clean_additional(sections: list) -> int:
    """Drop rating-like bullets, entries and sections in place; return the count dropped."""
    dropped = 0
    for section in list(sections):
        if not isinstance(section, dict) or not isinstance(section.get('entries'), list):
            continue
        before = section['entries']
        kept_entries = []
        for entry in before:
            if not isinstance(entry, dict):
                kept_entries.append(entry)
                continue
            bullets = entry.get('bullets')
            found = 0
            if isinstance(bullets, list):
                kept_bullets = [b for b in bullets if not _is_rating(b)]
                found += len(bullets) - len(kept_bullets)
                entry['bullets'] = kept_bullets
                bullets = kept_bullets
            heading, detail = entry.get('heading'), entry.get('detail')
            heading_rating, detail_rating = _is_rating(heading), _is_rating(detail)
            found += heading_rating + detail_rating
            entry_gone = (
                (heading_rating or _blank(heading))
                and (detail_rating or _blank(detail))
                and (not isinstance(bullets, list) or not bullets)
            )
            dropped += found
            if found and entry_gone:
                continue
            kept_entries.append(entry)
        section['entries'] = kept_entries
        if before and not kept_entries:
            sections.remove(section)
    return dropped


def clean_resume_content(content: dict, stats: dict | None = None) -> dict:
    """Return a cleaned copy of parsed resume content. `stats` (optional) receives counts."""
    if not isinstance(content, dict):
        return content
    cleaned = copy.deepcopy(content)
    companies = details = 0
    experience = cleaned.get('experience')
    if isinstance(experience, list):
        for job in experience:
            if isinstance(job, dict):
                companies += _strip_location_from_company(job)
    education = cleaned.get('education')
    if isinstance(education, list):
        for entry in education:
            if isinstance(entry, dict):
                details += _drop_repeated_degree(entry)
    skill_ratings = chart_values = 0
    if isinstance(cleaned.get('skills'), list):
        skill_ratings = _clean_skills(cleaned['skills'])
    if isinstance(cleaned.get('additional_sections'), list):
        chart_values = _clean_additional(cleaned['additional_sections'])
    if stats is not None:
        stats.update(
            companies_stripped=companies, details_dropped=details,
            skill_ratings_dropped=skill_ratings, chart_values_dropped=chart_values,
        )
    return cleaned
