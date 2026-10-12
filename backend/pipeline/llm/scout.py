"""
Context scout: a light-model agent that searches the user's own documents for
material relevant to one job posting and returns a brief for the writer.

The scout never touches Django models. The caller passes in `handlers`, which
implement the search tools over whatever sources the user has added.
"""

import json
import logging
from typing import Callable

from callback.config import (
    LLM_MAX_TOKENS_SCOUT,
    LLM_MODEL_SCOUT,
    SCOUT_MAX_STEPS,
    SCOUT_TOOL_RESULT_MAX_CHARS,
)

from .client import _get_client
from .prompts import SCOUT_SYSTEM, SCOUT_USER
from .schemas import CONTEXT_BRIEF_SCHEMA

logger = logging.getLogger(__name__)

SUBMIT_TOOL = 'submit_brief'

_SEARCH_TOOL = {
    'name': 'search_sections',
    'description': 'Full-text search the user\'s notes and documents. Returns '
                   'matching sections with an id, source, heading and a snippet.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Keywords to search for.'},
            'source_id': {'type': 'integer', 'description': 'Limit to one source (optional).'},
        },
        'required': ['query'],
    },
}
_READ_TOOL = {
    'name': 'read_section',
    'description': 'Read the full text of one section by id.',
    'input_schema': {
        'type': 'object',
        'properties': {'section_id': {'type': 'integer'}},
        'required': ['section_id'],
    },
}
_SUBMIT_TOOL = {
    'name': SUBMIT_TOOL,
    'description': 'Submit the final context brief. Ends the research.',
    'input_schema': CONTEXT_BRIEF_SCHEMA,
}


def run_scout(job: dict, sources_summary: str, handlers: dict[str, Callable[..., str]]) -> dict:
    """
    Research one job and return {'facts': [...]} (see CONTEXT_BRIEF_SCHEMA).

    `handlers` maps tool names ('search_sections', 'read_section') to callables
    taking the tool input as keyword arguments and returning text. With no
    handlers (the user added no sources) no model call is made.
    """
    if not handlers:
        return {'facts': []}

    client = _get_client()
    tools = [_SEARCH_TOOL, _READ_TOOL, _SUBMIT_TOOL]
    messages = [{
        'role': 'user',
        'content': SCOUT_USER.format(
            title=job.get('title', ''),
            company=job.get('company', ''),
            description=job.get('description', ''),
            sources=sources_summary,
        ),
    }]

    for step in range(SCOUT_MAX_STEPS + 1):
        out_of_steps = step == SCOUT_MAX_STEPS
        response = client.messages.create(
            model=LLM_MODEL_SCOUT,
            max_tokens=LLM_MAX_TOKENS_SCOUT,
            system=SCOUT_SYSTEM,
            tools=tools,
            tool_choice={'type': 'tool', 'name': SUBMIT_TOOL} if out_of_steps else {'type': 'auto'},
            messages=messages,
        )
        calls = [b for b in response.content if b.type == 'tool_use']

        for call in calls:
            if call.name == SUBMIT_TOOL:
                logger.info('Scout finished after %d step(s): %d facts', step + 1, len(call.input.get('facts', [])))
                return call.input

        if not calls:
            # Model answered in prose; push it to submit.
            messages.append({'role': 'assistant', 'content': response.content})
            messages.append({'role': 'user', 'content': f'Call {SUBMIT_TOOL} with your findings.'})
            continue

        messages.append({'role': 'assistant', 'content': response.content})
        messages.append({
            'role': 'user',
            'content': [_tool_result(call, handlers) for call in calls],
        })

    raise ValueError('Scout did not submit a brief')


def _tool_result(call, handlers: dict[str, Callable[..., str]]) -> dict:
    handler = handlers.get(call.name)
    if handler is None:
        text, is_error = f'Unknown tool {call.name}', True
    else:
        try:
            text, is_error = handler(**call.input), False
        except Exception as exc:  # a bad tool call should not abort the run
            logger.warning('Scout tool %s failed: %s', call.name, exc)
            text, is_error = f'Tool error: {exc}', True
    return {
        'type': 'tool_result',
        'tool_use_id': call.id,
        'content': text[:SCOUT_TOOL_RESULT_MAX_CHARS],
        'is_error': is_error,
    }
