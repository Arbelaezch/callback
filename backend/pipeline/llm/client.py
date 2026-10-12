"""
Anthropic API wrapper.

All LLM calls in the application go through this module.
Callers must never import the Anthropic SDK directly.

Functions
---------
score_job(job, profile)         → { score: int, reason: str }
personalize_cover_letter(template, job) → str
"""

import json
import logging
import os

import anthropic

from callback.config import LLM_MODEL, LLM_MAX_TOKENS, LLM_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


def _get_client(timeout: int = LLM_TIMEOUT_SECONDS) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=os.environ['ANTHROPIC_API_KEY'],
        timeout=timeout,
    )


def _strict_schema(schema):
    """
    Return a copy of `schema` closed for structured outputs: every object gets
    additionalProperties: false and all of its properties required. The API caps
    optional fields per schema, so absent values are sent as empty strings or
    arrays instead of being omitted.
    """
    if isinstance(schema, dict):
        out = {k: _strict_schema(v) for k, v in schema.items()}
        if out.get('type') == 'object':
            out['additionalProperties'] = False
            out['required'] = list(out.get('properties', {}))
        return out
    if isinstance(schema, list):
        return [_strict_schema(v) for v in schema]
    return schema


def call_structured(
    *,
    model: str,
    system: str,
    content: list,
    schema: dict,
    max_tokens: int,
    timeout: int = LLM_TIMEOUT_SECONDS,
) -> dict:
    """
    Call the model and return JSON that conforms to `schema`.

    Uses the API's structured outputs (output_config.format), which constrains
    the response to the schema. Forced tool_choice is not used because newer
    models reject it.

    Raises
    ------
    ValueError   if the response was cut off, refused, or has no text.
    anthropic.*  re-raised on any Anthropic API error.
    """
    message = _get_client(timeout).messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        output_config={'format': {'type': 'json_schema', 'schema': _strict_schema(schema)}},
        messages=[{'role': 'user', 'content': content}],
    )
    if message.stop_reason == 'refusal':
        raise ValueError('Model declined the request')
    if message.stop_reason == 'max_tokens':
        raise ValueError('Model output was cut off; raise max_tokens')
    for block in message.content:
        if block.type == 'text':
            return json.loads(block.text)
    raise ValueError('Model returned no text')


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_SCORE_SYSTEM = (
    'You are a job fit evaluator. '
    'Return only JSON with no preamble, no markdown, no code fences.'
)

_SCORE_USER_TEMPLATE = """\
Job:
  Title: {title}
  Company: {company}
  Description: {description}

Profile:
  Target roles: {target_roles}
  Seniority levels: {seniority_levels}
  Years of experience: {years_experience}
  Location preference: {location_types}
  Skills / experience summary: {experience_summary}

Return a JSON object with exactly these keys:
  "score"  — integer 1–10 representing fit (10 = perfect match)
  "reason" — one sentence explaining the score
"""


def score_job(job: dict, profile: dict) -> dict:
    """
    Score a job against a user profile.

    Parameters
    ----------
    job:
        Normalised job dict from the JSearch client.
        Expected keys: title, company, description.
    profile:
        User / JobSearch profile dict.
        Expected keys: target_roles, seniority_levels, years_experience,
        location_types, experience_summary.

    Returns
    -------
    dict with keys:
        score  (int 1–10)
        reason (str)

    Raises
    ------
    ValueError   if the LLM response cannot be parsed as valid JSON.
    anthropic.*  re-raised on any Anthropic API error.
    """
    prompt = _SCORE_USER_TEMPLATE.format(
        title=job.get('title', ''),
        company=job.get('company', ''),
        description=(job.get('description') or '')[:3000],  # cap to avoid token blowout
        target_roles=', '.join(profile.get('target_roles', [])),
        seniority_levels=', '.join(profile.get('seniority_levels', [])),
        years_experience=profile.get('years_experience', 'not specified'),
        location_types=', '.join(profile.get('location_types', [])),
        experience_summary=profile.get('experience_summary', ''),
    )

    logger.debug('Scoring job %s at %s', job.get('title'), job.get('company'))

    client = _get_client()
    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        system=_SCORE_SYSTEM,
        messages=[{'role': 'user', 'content': prompt}],
    )

    raw = message.content[0].text.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error('LLM scoring returned non-JSON for job %s: %s', job.get('job_id'), raw)
        raise ValueError(f'LLM score response was not valid JSON: {raw!r}') from exc

    score = int(result.get('score', 0))
    reason = str(result.get('reason', ''))

    logger.info(
        'Scored job %s at %s: %d/10 — %s',
        job.get('title'), job.get('company'), score, reason,
    )

    return {'score': score, 'reason': reason}


# ---------------------------------------------------------------------------
# Cover letter personalisation
# ---------------------------------------------------------------------------

_COVER_LETTER_SYSTEM = (
    'You are a cover letter editor. '
    'Modify only: the company name, the role title, and the opening sentence. '
    'Do not change anything else. '
    'Return only the full cover letter text with no preamble.'
)

_COVER_LETTER_USER_TEMPLATE = """\
Template:
{cover_letter_text}

Job:
  Company: {company}
  Role title: {role_title}
  Brief description: {brief_description}
"""


def personalize_cover_letter(template: str, job: dict) -> str:
    """
    Personalise a cover letter template for a specific job.

    Parameters
    ----------
    template:
        Raw cover letter template text.
    job:
        Normalised job dict.
        Expected keys: company, title, description.

    Returns
    -------
    str — full personalised cover letter text.

    Raises
    ------
    anthropic.*  re-raised on any Anthropic API error.
    """
    prompt = _COVER_LETTER_USER_TEMPLATE.format(
        cover_letter_text=template,
        company=job.get('company', ''),
        role_title=job.get('title', ''),
        brief_description=(job.get('description') or '')[:500],
    )

    logger.debug(
        'Personalising cover letter for %s at %s',
        job.get('title'), job.get('company'),
    )

    client = _get_client()
    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        system=_COVER_LETTER_SYSTEM,
        messages=[{'role': 'user', 'content': prompt}],
    )

    text = message.content[0].text.strip()
    logger.info('Cover letter personalised for %s at %s', job.get('title'), job.get('company'))
    return text