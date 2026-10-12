from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from documents.generation import generate_documents
from documents.models import ContextSource, JobPosting, ParsedResume, VoiceProfile
from users.models import Resume

RESUME = {'header': {'name': 'Ada'}, 'experience': [], 'education': [], 'skills': []}
WRITTEN = {'resume': {**RESUME, 'summary': 'Tailored'}, 'cover_letter_markdown': 'Dear Acme'}
CLAIMS = [{'document': 'cover_letter', 'claim': 'Led 50 people', 'reason': 'not in sources'}]


class GenerateDocumentsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('ada', password='x')
        resume = Resume.objects.create(user=self.user, s3_key='k', filename='a.pdf', status='ready')
        self.parsed = ParsedResume.objects.create(user=self.user, resume=resume, content=RESUME)
        self.job = JobPosting.objects.create(
            user=self.user, title='Backend Engineer', company='Acme', description='Django',
        )

    def _run(self, scout=None, claims=CLAIMS):
        with patch('documents.generation.run_scout', return_value=scout or {'facts': []}) as run_scout, \
             patch('documents.generation.build_voice_profile',
                   return_value={'notes': 'warm', 'excerpts': ['hi']}) as voice, \
             patch('documents.generation.write_documents', return_value=WRITTEN) as write, \
             patch('documents.generation.verify_documents', return_value=claims):
            docs = generate_documents(self.job, self.parsed, 'old letter')
        return docs, run_scout, voice, write

    def test_stores_both_documents_with_flagged_claims(self):
        (resume_doc, letter_doc), *_ = self._run()
        self.assertEqual(resume_doc.status, 'ready')
        self.assertEqual(resume_doc.content['summary'], 'Tailored')
        self.assertEqual(resume_doc.unsupported_claims, [])
        self.assertEqual(letter_doc.markdown, 'Dear Acme')
        self.assertEqual(letter_doc.unsupported_claims, CLAIMS)

    def test_documents_snapshot_layout_and_letterhead(self):
        self.parsed.layout = {'font_family': 'Georgia'}
        self.parsed.content = {**RESUME, 'header': {'name': 'Ada'}}
        self.parsed.save()
        (resume_doc, letter_doc), *_ = self._run()
        self.assertEqual(resume_doc.layout, {'font_family': 'Georgia'})
        self.assertEqual(letter_doc.layout, {'font_family': 'Georgia'})
        self.assertEqual(letter_doc.content, {'header': {'name': 'Ada'}})

    def test_scout_gets_no_handlers_without_sources(self):
        _, run_scout, *_ = self._run()
        self.assertEqual(run_scout.call_args.args[2], {})

    def test_scout_gets_handlers_only_for_ready_sources(self):
        ContextSource.objects.create(user=self.user, kind='upload', label='ok', status='ready')
        ContextSource.objects.create(user=self.user, kind='git', label='pending', status='pending')
        _, run_scout, *_ = self._run()
        summary, handlers = run_scout.call_args.args[1:]
        self.assertIn('ok', summary)
        self.assertNotIn('pending', summary)
        self.assertEqual(set(handlers), {'search_sections', 'read_section'})

    def test_voice_profile_is_cached_until_inputs_change(self):
        _, _, voice, _ = self._run()
        self.assertEqual(voice.call_count, 1)
        _, _, voice, _ = self._run()
        voice.assert_not_called()
        self.assertEqual(VoiceProfile.objects.get(user=self.user).notes, 'warm')

    def test_versions_increment_per_run(self):
        self._run()
        (resume_doc, _), *_ = self._run()
        self.assertEqual(resume_doc.version, 2)

    def test_stage_failure_marks_documents_failed(self):
        with patch('documents.generation.run_scout', side_effect=RuntimeError('api down')):
            with self.assertRaises(RuntimeError):
                generate_documents(self.job, self.parsed)
        statuses = set(self.job.documents.values_list('status', flat=True))
        self.assertEqual(statuses, {'failed'})
        self.assertEqual(self.job.documents.first().error, 'api down')
