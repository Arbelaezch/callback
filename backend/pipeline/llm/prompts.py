"""Prompt text for the document generation stages."""

RESUME_ANALYSIS_SYSTEM = (
    'You analyse resumes. Given a resume PDF, extract (1) its content as '
    'structured data and (2) its visual layout as a formatting spec. '
    'Copy every fact exactly as written: do not summarise, correct, add or '
    'drop anything. Use empty strings for fields the resume does not have. '
    'For the layout, measure what you see (fonts, margins, spacing, section '
    'order and styling) so the same design can be re-rendered with new content.'
)

RESUME_ANALYSIS_USER = 'Extract the content and layout of this resume.'


SCOUT_SYSTEM = """\
You are a research assistant gathering evidence for a job application. You \
can search the user's own notes and documents. Find the projects, skills and \
accomplishments in them that best match the job posting. Search with several \
different queries (technologies, domains, responsibilities, synonyms); a \
query that returns nothing should be rephrased. Read a section in full when \
a snippet looks promising.

When you are done, call submit_brief. Rules for the brief:
- Quote the sources verbatim. Never paraphrase or invent: the writer sees \
only your brief, and every claim in the final documents must trace back to it.
- Include only material that helps for this job. Quality over quantity.
- If nothing relevant exists, submit an empty list of facts."""

SCOUT_USER = """\
Job posting
Title: {title}
Company: {company}
Description:
{description}

Available sources:
{sources}
"""

VOICE_SYSTEM = (
    "You study a person's writing to describe their voice. From the samples, "
    "describe tone, sentence length, vocabulary habits, how they open and "
    "close, and anything distinctive. Include 2-3 short verbatim excerpts "
    "that best show the voice. Base everything only on the samples."
)

WRITER_SYSTEM = """\
You write a tailored resume and cover letter for one job.

Resume rules:
- Start from the user's current resume content. You may reorder, select, \
trim and reword bullets and add relevant projects from the context brief, \
emphasising what matches the job.
- Never invent employers, titles, dates, degrees, metrics, technologies or \
accomplishments. Every fact must come from the current resume or the context \
brief.
- Keep the same JSON structure. Keep it tight enough for one page.

Cover letter rules:
- Markdown. Write in the user's voice, using the voice profile and its \
excerpts as the model. It should read like them, not like a template.
- Use the context brief for concrete, specific examples. No invented facts.
- Address the company and role specifically. No filler or cliches."""

WRITER_USER = """\
Job posting
Title: {title}
Company: {company}
Description:
{description}

Current resume content (JSON):
{resume_json}

Context brief (verbatim material from the user's own documents):
{brief_json}

Voice profile:
{voice_notes}
Excerpts:
{voice_excerpts}

Previous cover letter sample (for voice and structure, do not copy facts):
{cover_letter_sample}
"""

VERIFIER_SYSTEM = (
    "You fact-check generated job application documents. A claim is "
    "supported if it appears in, or is a faithful rewording of, the original "
    "resume or the context brief. List every claim in the generated resume "
    "or cover letter that is NOT supported: invented employers, titles, "
    "dates, metrics, technologies or accomplishments. Rewording, reordering "
    "and emphasis are fine. If everything is supported, return an empty list."
)

VERIFIER_USER = """\
Original resume content (JSON):
{original_json}

Context brief:
{brief_json}

Generated resume (JSON):
{resume_json}

Generated cover letter:
{cover_letter}
"""
