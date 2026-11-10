"""
Guards that tidy parsed resume content.

These functions only remove text that is already stored in full in another
field of the same entry (a location in `location`, a degree and its dates in
`degree`/`start`/`end`). They never add or reword anything. No Django, no LLM.
"""

import copy
import re

_PREFIX_STRIP = ' ,;|-–—·\t'
_SEPARATORS = ',;|-–—·'
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
    if stats is not None:
        stats.update(companies_stripped=companies, details_dropped=details)
    return cleaned
