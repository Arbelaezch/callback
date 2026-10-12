"""Split a markdown or plain-text document into heading-level sections."""

import re

from callback.config import CONTEXT_SECTION_MAX_CHARS

_HEADING = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')
_FENCE = re.compile(r'^\s*(```|~~~)')


def split_sections(text: str) -> list[tuple[str, str]]:
    """
    Return [(heading, body)] for a document.

    Splits on markdown headings (ignoring '#' lines inside code fences).
    Text before the first heading gets an empty heading. Bodies longer than
    CONTEXT_SECTION_MAX_CHARS are split on blank lines so every section stays
    small enough to read and cite. Empty sections are dropped.
    """
    sections: list[tuple[str, list[str]]] = [('', [])]
    in_fence = False

    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match:
            sections.append((match.group(2), []))
        else:
            sections[-1][1].append(line)

    result: list[tuple[str, str]] = []
    for heading, lines in sections:
        body = '\n'.join(lines).strip()
        if not body:
            continue
        for piece in _split_long(body):
            result.append((heading, piece))
    return result


def _split_long(body: str) -> list[str]:
    if len(body) <= CONTEXT_SECTION_MAX_CHARS:
        return [body]

    pieces: list[str] = []
    current = ''
    for paragraph in re.split(r'\n\s*\n', body):
        if current and len(current) + len(paragraph) + 2 > CONTEXT_SECTION_MAX_CHARS:
            pieces.append(current)
            current = paragraph
        else:
            current = f'{current}\n\n{paragraph}' if current else paragraph
    if current:
        pieces.append(current)
    return pieces
