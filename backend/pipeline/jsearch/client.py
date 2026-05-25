"""
JSearch API client (RapidAPI).

Query strategies
----------------
All public callers go through ``fetch_jobs()``, which accepts a ``strategy``
argument.  The strategy controls how role titles / cities are combined into
API requests before results are merged and de-duplicated.

Available strategies
~~~~~~~~~~~~~~~~~~~~
``combined``  (default)
    Single API call per JobSearch.  Joins all role titles with " OR " and all
    cities with " OR " into one query string.  Fast, cheap, good enough for
    pure-API application flows.

Future strategies to add here
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``fan_out``
    One API call per (role_title × city) pair.  Better coverage; use when
    browser-automation flows need more signal per posting.

``batched(n)``
    Groups role titles into batches of ``n`` before calling.  Middle ground
    between combined and fan_out.

To add a new strategy:
  1. Define a function ``_build_<name>_queries(role_titles, cities,
     location_types) -> list[dict]`` that returns a list of JSearch param
     dicts.
  2. Add it to ``_STRATEGIES``.
  3. Pass ``strategy='<name>'`` to ``fetch_jobs()``.
"""

import logging
import os

import httpx

from callback.config import JSEARCH_HOST, JSEARCH_TIMEOUT_SECONDS, JSEARCH_PAGE_SIZE

logger = logging.getLogger(__name__)

_JSEARCH_BASE_URL = f'https://{JSEARCH_HOST}/search'


# ---------------------------------------------------------------------------
# Response normalisation
# ---------------------------------------------------------------------------

def _normalise_job(raw: dict) -> dict:
    """
    Map a raw JSearch result dict to the internal job shape used everywhere
    in the application.  Add new fields here; callers should never access the
    raw JSearch payload directly.
    """
    return {
        'job_id': raw.get('job_id', ''),
        'title': raw.get('job_title', ''),
        'company': raw.get('employer_name', ''),
        'description': raw.get('job_description', ''),
        'job_url': raw.get('job_apply_link') or raw.get('job_url', ''),
        'location': _build_location_string(raw),
        'remote_type': _map_remote_type(raw),
        'salary_range': _build_salary_string(raw),
        # Preserve raw apply link separately for ATS detection downstream.
        'apply_link': raw.get('job_apply_link', ''),
    }


def _build_location_string(raw: dict) -> str:
    parts = [
        raw.get('job_city', ''),
        raw.get('job_state', ''),
        raw.get('job_country', ''),
    ]
    return ', '.join(p for p in parts if p)


def _map_remote_type(raw: dict) -> str:
    if raw.get('job_is_remote'):
        return 'remote'
    offer = (raw.get('job_offer_expiration_datetime_utc') or '').lower()
    description = (raw.get('job_description') or '').lower()
    if 'hybrid' in description:
        return 'hybrid'
    return 'onsite'


def _build_salary_string(raw: dict) -> str | None:
    min_sal = raw.get('job_min_salary')
    max_sal = raw.get('job_max_salary')
    period = raw.get('job_salary_period', '')
    if min_sal and max_sal:
        return f'{min_sal}–{max_sal} {period}'.strip()
    if min_sal:
        return f'{min_sal}+ {period}'.strip()
    if max_sal:
        return f'up to {max_sal} {period}'.strip()
    return None


# ---------------------------------------------------------------------------
# Query builders (one per strategy)
# ---------------------------------------------------------------------------

def _build_combined_queries(
    role_titles: list[str],
    cities: list[str],
    location_types: list[str],
) -> list[dict]:
    """
    Single query: join role titles with OR, join cities with OR.
    Returns a one-element list so the fetch loop is uniform across strategies.
    """
    query_parts = [' OR '.join(role_titles)] if role_titles else []
    if cities:
        query_parts.append(' OR '.join(cities))

    query = ' '.join(query_parts) or 'software engineer'

    params = {
        'query': query,
        'num_pages': 1,
        'page': 1,
    }

    if location_types:
        if location_types == ['remote']:
            params['remote_jobs_only'] = 'true'
        elif 'remote' in location_types:
            params['employment_types'] = 'FULLTIME'  # broadest filter available

    return [params]


# Registry: strategy name → query builder function.
_STRATEGIES: dict[str, callable] = {
    'combined': _build_combined_queries,
    # 'fan_out': _build_fan_out_queries,    # add when needed
    # 'batched': _build_batched_queries,    # add when needed
}


# ---------------------------------------------------------------------------
# HTTP call
# ---------------------------------------------------------------------------

def _call_jsearch(params: dict) -> list[dict]:
    """Execute a single JSearch API call and return raw result dicts."""
    api_key = os.environ['JSEARCH_API_KEY']
    headers = {
        'x-rapidapi-host': JSEARCH_HOST,
        'x-rapidapi-key': api_key,
    }

    logger.debug('JSearch request: %s', params)

    with httpx.Client(timeout=JSEARCH_TIMEOUT_SECONDS) as client:
        response = client.get(_JSEARCH_BASE_URL, headers=headers, params=params)

    response.raise_for_status()
    payload = response.json()

    data = payload.get('data', [])
    logger.debug('JSearch returned %d results for query: %s', len(data), params.get('query'))
    return data


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def fetch_jobs(
    role_titles: list[str],
    cities: list[str],
    location_types: list[str],
    strategy: str = 'combined',
) -> list[dict]:
    """
    Fetch and normalise jobs from JSearch.

    Parameters
    ----------
    role_titles:
        List of job titles to search for (e.g. ['Senior Django Developer']).
    cities:
        List of city names (e.g. ['Toronto', 'Vancouver']).
    location_types:
        List of location preferences from JobSearch.LOCATION_TYPE_CHOICES
        (e.g. ['remote', 'hybrid']).
    strategy:
        Query strategy to use.  Currently only 'combined' is implemented.
        See module docstring for how to add new strategies.

    Returns
    -------
    list[dict]
        Normalised job dicts, de-duplicated by job_id across all queries.
        Returns an empty list (never raises) on API error — the caller
        (scan_jobs task) is responsible for deciding what to do with an
        empty result set.
    """
    if strategy not in _STRATEGIES:
        raise ValueError(
            f'Unknown JSearch strategy {strategy!r}. '
            f'Valid options: {list(_STRATEGIES)}'
        )

    build_queries = _STRATEGIES[strategy]
    queries = build_queries(role_titles, cities, location_types)

    seen_ids: set[str] = set()
    results: list[dict] = []

    for params in queries:
        try:
            raw_jobs = _call_jsearch(params)
        except httpx.HTTPStatusError as exc:
            logger.error(
                'JSearch HTTP error %s for params %s: %s',
                exc.response.status_code,
                params,
                exc,
            )
            continue
        except httpx.TimeoutException:
            logger.error('JSearch request timed out for params %s', params)
            continue
        except Exception:
            logger.exception('Unexpected error calling JSearch for params %s', params)
            continue

        for raw in raw_jobs:
            job = _normalise_job(raw)
            if job['job_id'] and job['job_id'] not in seen_ids:
                seen_ids.add(job['job_id'])
                results.append(job)

    logger.info('fetch_jobs returning %d unique jobs (strategy=%s)', len(results), strategy)
    return results