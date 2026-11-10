import copy
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

CONTENT = {
    'header': {'name': 'Ada', 'links': ['https://github.com/x']},
    'summary': '',
    'experience': [{'company': 'A', 'title': 'Dev', 'dates': '2020', 'bullets': ['Did it']}],
    'projects': [{'name': 'P', 'bullets': ['Built']}],
    'education': [{'school': 'Home'}],
    'skills': [{'category': 'Math', 'items': ['Algebra']}],
    'additional_sections': [],
}
LAYOUT = {
    'section_order': ['experience', 'projects', 'education', 'skills'],
    'source_sections': [],
}
SAMPLE = 'Dear team, I write plainly.'
CMD = 'documents.management.commands.check_tailoring.'


def _analysis(pdf_bytes):
    return {'content': copy.deepcopy(CONTENT), 'layout': copy.deepcopy(LAYOUT)}


class CheckTailoringCommandTests(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.job = self.tmp / 'job.txt'
        self.job.write_text('Build things.')
        self.letter = self.tmp / 'letter.txt'
        self.letter.write_text(SAMPLE)
        self.out = self.tmp / 'out'

    def _pdf(self, name):
        path = self.tmp / name
        path.write_bytes(b'%PDF-dummy')
        return str(path)

    def _run(self, pdfs, out=None, **mocks):
        defaults = {
            'analyze_resume': _analysis,
            'run_scout': lambda *a, **k: {'brief': 'x'},
            'build_voice_profile': lambda *a, **k: {'voice': 'x'},
            'write_documents': lambda *a, **k: {
                'resume': copy.deepcopy(CONTENT), 'cover_letter_markdown': 'Hi',
            },
            'verify_documents': lambda *a, **k: [],
        }
        defaults.update(mocks)
        patches = [patch(CMD + name, side_effect=fn) if callable(fn) else patch(CMD + name, fn)
                   for name, fn in defaults.items()]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        call_command(
            'check_tailoring', *pdfs, job=str(self.job), out=str(out or self.out),
            cover_letter=str(self.letter), stdout=StringIO(),
        )

    def test_happy_path_writes_report_and_outputs(self):
        self._run([self._pdf('one.pdf')])
        report = json.loads((self.out / 'report.json').read_text())
        self.assertTrue(report['one']['ok'])
        self.assertIsNone(report['one']['error'])
        self.assertEqual(report['_meta']['samples'], 1)
        self.assertTrue((self.out / 'one.tailored.json').is_file())
        self.assertTrue((self.out / 'one.tailored.pdf').read_bytes().startswith(b'%PDF'))

    def test_dropped_projects_reported_and_raises(self):
        dropped = copy.deepcopy(CONTENT)
        dropped['projects'] = []
        with self.assertRaises(CommandError):
            self._run(
                [self._pdf('one.pdf')],
                write_documents=lambda *a, **k: {'resume': dropped, 'cover_letter_markdown': 'Hi'},
            )
        report = json.loads((self.out / 'report.json').read_text())
        self.assertIn('projects', report['one']['sections_dropped'])
        self.assertFalse(report['one']['ok'])

    def test_one_pdf_error_does_not_stop_others(self):
        def analyze(pdf_bytes):
            if pdf_bytes == b'boom':
                raise ValueError('bad pdf')
            return _analysis(pdf_bytes)

        bad = self.tmp / 'bad.pdf'
        bad.write_bytes(b'boom')
        with self.assertRaises(CommandError):
            self._run([str(bad), self._pdf('good.pdf')], analyze_resume=analyze)
        report = json.loads((self.out / 'report.json').read_text())
        self.assertIn('ValueError: bad pdf', report['bad']['error'])
        self.assertTrue(report['good']['ok'])

    def test_out_inside_repo_outside_docs_refused_before_llm(self):
        repo_root = Path(settings.BASE_DIR).resolve().parent
        out = repo_root / 'backend' / 'tmp-out-check-tailoring'
        with patch(CMD + 'analyze_resume') as analyze:
            with self.assertRaises(CommandError):
                call_command(
                    'check_tailoring', self._pdf('one.pdf'), job=str(self.job), out=str(out),
                )
        analyze.assert_not_called()
        self.assertFalse(out.exists())

    def test_scout_and_voice_called_with_no_sources(self):
        with patch(CMD + 'run_scout', return_value={'brief': 'x'}) as scout, \
                patch(CMD + 'build_voice_profile', return_value={'voice': 'x'}) as voice:
            self._run([self._pdf('one.pdf')], run_scout=scout, build_voice_profile=voice)
        job = scout.call_args.args[0]
        self.assertEqual(job['description'], 'Build things.')
        self.assertEqual(scout.call_args.args[1:], ('', {}))
        voice.assert_called_once_with([SAMPLE])
