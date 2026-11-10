"""Re-run sample resume PDFs through the real tailoring path and check the result.

Usage (calls paid APIs, needs ANTHROPIC_API_KEY, makes no database writes):

    env/bin/python manage.py check_tailoring ../docs/test-resumes/*.pdf \
        --job ../docs/test-resumes/job.txt --out ../docs/test-resumes/out/tailoring

Per PDF it runs analyze_resume -> run_scout (no sources) -> build_voice_profile ->
write_documents -> verify_documents, compares the tailored resume with the source
using documents.tailoring_check (dropped sections and links, summary placement),
renders a PDF and writes `<stem>.tailored.json` / `<stem>.tailored.pdf` plus
`report.json` into --out. Outputs belong under `docs/` (gitignored); an --out inside
the repository but outside `docs/` is refused. Backs issue #35.
"""
import json
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from callback.config import LLM_MODEL_WRITER
from documents.rendering import html_to_pdf, render_resume_html
from documents.tailoring_check import compare_tailoring
from pipeline.llm import (
    analyze_resume,
    build_voice_profile,
    run_scout,
    verify_documents,
    write_documents,
)

logger = logging.getLogger(__name__)


def _read_text(path: str | None) -> str:
    return Path(path).read_text(encoding='utf-8') if path else ''


def _check_out_dir(out: Path) -> None:
    repo_root = Path(settings.BASE_DIR).resolve().parent
    if out.is_relative_to(repo_root) and not out.is_relative_to(repo_root / 'docs'):
        raise CommandError(
            f'--out {out} is inside the repository but outside docs/; '
            'use a path under docs/ (gitignored) so resume output is never tracked'
        )


class Command(BaseCommand):
    help = 'Run sample resume PDFs through the real tailoring path and report dropped sections/links.'

    def add_arguments(self, parser):
        parser.add_argument('pdfs', nargs='+', help='Resume PDF paths')
        parser.add_argument('--job', required=True, help='Text file with the job description')
        parser.add_argument('--out', required=True, help='Output directory (under docs/)')
        parser.add_argument('--cover-letter', default='', help='Text file with a cover letter sample')
        parser.add_argument('--title', default='Software Engineer')
        parser.add_argument('--company', default='Example Co')

    def handle(self, *args, **options):
        out = Path(options['out']).resolve()
        _check_out_dir(out)
        pdfs = [Path(p) for p in options['pdfs']]
        missing = [str(p) for p in pdfs if not p.is_file()]
        if missing:
            raise CommandError('PDF not found: ' + ', '.join(missing))
        job_path = options['job']
        try:
            description = _read_text(job_path)
            sample = _read_text(options['cover_letter'])
        except OSError as exc:
            raise CommandError(f'Cannot read input file: {exc}') from exc

        out.mkdir(parents=True, exist_ok=True)
        job = {'title': options['title'], 'company': options['company'], 'description': description}

        report = {}
        for pdf in pdfs:
            try:
                report[pdf.stem] = self._run_one(pdf, job, sample, out)
            except Exception as exc:
                logger.exception('check_tailoring failed for %s', pdf)
                report[pdf.stem] = {'error': f'{type(exc).__name__}: {exc}'}
            self.stdout.write(self._line(pdf.stem, report[pdf.stem]))

        failed = sum(1 for entry in report.values() if entry.get('error') or not entry.get('ok'))
        report['_meta'] = {
            'model_writer': LLM_MODEL_WRITER,
            'job_file': str(job_path),
            'samples': len(pdfs),
        }
        report_path = out / 'report.json'
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

        if failed:
            raise CommandError(
                f'{failed} of {len(pdfs)} samples failed or lost sections/links; see {report_path}'
            )

    def _run_one(self, pdf: Path, job: dict, sample: str, out: Path) -> dict:
        analysis = analyze_resume(pdf.read_bytes())
        content, layout = analysis['content'], analysis['layout']
        brief = run_scout(job, '', {})
        voice = build_voice_profile([sample])
        written = write_documents(job, content, brief, voice, sample)
        claims = verify_documents(
            job, content, brief, written['resume'], written['cover_letter_markdown'],
        )
        check = compare_tailoring(content, written['resume'], layout)
        pdf_bytes, pages = html_to_pdf(render_resume_html(written['resume'], layout))
        (out / f'{pdf.stem}.tailored.pdf').write_bytes(pdf_bytes)
        (out / f'{pdf.stem}.tailored.json').write_text(
            json.dumps({'analysis': analysis, 'written': written, 'claims': claims}, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )
        return {
            **check,
            'generated_pages': pages,
            'unsupported_claims': len(claims),
            'source_sections': layout.get('source_sections', []),
            'error': None,
        }

    @staticmethod
    def _line(stem: str, entry: dict) -> str:
        if entry.get('error'):
            return f'{stem}: ERROR {entry["error"]}'
        status = 'ok' if entry['ok'] else 'FAIL'
        return (
            f'{stem}: {status} dropped={entry["sections_dropped"]} '
            f'links_dropped={entry["links_dropped"]} '
            f'summary_first={entry["summary_first"]} summary_added={entry["summary_added"]}'
        )
