from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from documents.generation import create_pending_documents, generate_documents
from documents.models import GeneratedDocument
from documents.tasks import generate_documents_task
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
            resume_doc, letter_doc = create_pending_documents(self.job, self.parsed.resume)
            docs = generate_documents(resume_doc, letter_doc, self.parsed, 'old letter')
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
        create_pending_documents(self.job, self.parsed.resume)
        resume_doc, letter_doc = create_pending_documents(self.job, self.parsed.resume)
        self.assertEqual((resume_doc.version, letter_doc.version), (2, 2))
        self.assertEqual(resume_doc.resume_id, self.parsed.resume_id)

    def test_fills_given_rows_without_creating_new_ones(self):
        self._run()
        self.assertEqual(self.job.documents.count(), 2)

    def test_stage_failure_marks_documents_failed(self):
        with patch('documents.generation.run_scout', side_effect=RuntimeError('api down')):
            with self.assertRaises(RuntimeError):
                resume_doc, letter_doc = create_pending_documents(self.job, self.parsed.resume)
                generate_documents(resume_doc, letter_doc, self.parsed)
        statuses = set(self.job.documents.values_list('status', flat=True))
        self.assertEqual(statuses, {'failed'})
        self.assertEqual(self.job.documents.first().error, 'api down')


class GenerateDocumentsTaskTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('ada', password='x')
        self.job = JobPosting.objects.create(
            user=self.user, title='Backend Engineer', company='Acme', description='Django',
        )

    def test_task_fails_both_rows_when_resume_is_gone(self):
        resume_doc, letter_doc = create_pending_documents(self.job, None)
        generate_documents_task(resume_doc.pk, letter_doc.pk)
        for doc in GeneratedDocument.objects.filter(job_posting=self.job):
            self.assertEqual(doc.status, 'failed')
            self.assertIn('no longer available', doc.error)

    def test_task_returns_quietly_when_rows_are_gone(self):
        generate_documents_task(999998, 999999)

    def test_task_skips_rows_that_are_no_longer_pending(self):
        resume_doc, letter_doc = create_pending_documents(self.job, None)
        GeneratedDocument.objects.filter(job_posting=self.job).update(status='failed', error='x')
        with patch('documents.generation.generate_documents') as gen:
            generate_documents_task(resume_doc.pk, letter_doc.pk)
        gen.assert_not_called()
        self.assertEqual(set(GeneratedDocument.objects.values_list('status', flat=True)), {'failed'})

    def test_task_uses_parsed_resume_and_sample_for_the_version(self):
        from users.models import CoverLetterSample

        first = Resume.objects.create(user=self.user, s3_key='a', filename='a.pdf', status='ready')
        second = Resume.objects.create(user=self.user, s3_key='b', filename='b.pdf', status='ready')
        ParsedResume.objects.create(user=self.user, resume=first, content=RESUME)
        parsed_second = ParsedResume.objects.create(user=self.user, resume=second, content=RESUME)
        CoverLetterSample.objects.create(user=self.user, body='my sample', is_default=True)
        resume_doc, letter_doc = create_pending_documents(self.job, second)
        with patch('documents.generation.generate_documents') as gen:
            generate_documents_task(resume_doc.pk, letter_doc.pk)
        args = gen.call_args.args
        self.assertEqual((args[0].pk, args[1].pk), (resume_doc.pk, letter_doc.pk))
        self.assertEqual(args[2], parsed_second)
        self.assertEqual(args[3], 'my sample')
