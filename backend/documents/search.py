"""
Full-text search over a user's context sources.

`search_sections` is the single retrieval entry point. The context scout calls
only this, so a different backend (embeddings) can replace it without touching
the agents.
"""

import re
from functools import reduce
from operator import or_

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import F

from .models import SourceDocumentSection

SEARCH_CONFIG = 'english'
_WORD = re.compile(r"[A-Za-z0-9+#.]{2,}")


def index_sections(source_id: int) -> None:
    """Fill search_vector for a source's sections (heading weighs more than body)."""
    SourceDocumentSection.objects.filter(source_id=source_id).update(
        search_vector=(
            SearchVector('heading', weight='A', config=SEARCH_CONFIG)
            + SearchVector('text', weight='B', config=SEARCH_CONFIG)
        )
    )


def search_sections(user, query: str, source_id: int | None = None, limit: int = 8):
    """
    Return the user's best-matching sections, most relevant first.

    Words are OR-ed so a multi-word query still returns partial matches; rank
    puts sections that match more words first. Only sections from sources in
    'ready' state are searched.
    """
    words = _WORD.findall(query)
    if not words:
        return SourceDocumentSection.objects.none()

    search_query = reduce(or_, (SearchQuery(w, config=SEARCH_CONFIG) for w in words))
    sections = SourceDocumentSection.objects.filter(
        source__user=user, source__status='ready', search_vector=search_query,
    )
    if source_id is not None:
        sections = sections.filter(source_id=source_id)
    return (
        sections.annotate(rank=SearchRank(F('search_vector'), search_query))
        .order_by('-rank', 'id')
        .select_related('source')[:limit]
    )
