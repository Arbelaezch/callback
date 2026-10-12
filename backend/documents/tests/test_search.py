from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from documents.models import ContextSource
from documents.search import search_sections
from documents.services import index_upload_source

NOTES = b"""# Callback
Django and Celery app that automates job applications.

# Garden Planner
Mobile app in React Native for planning vegetable beds.
"""


class SearchSectionsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('ada', password='x')
        self.other = User.objects.create_user('bob', password='x')

    def _source(self, user, data=NOTES, label='notes.md'):
        source = ContextSource.objects.create(user=user, kind='upload', label=label, s3_key='k')
        with patch('documents.services.read_file', return_value=data):
            index_upload_source(source)
        return source

    def test_upload_is_indexed_and_marked_ready(self):
        source = self._source(self.user)
        source.refresh_from_db()
        self.assertEqual(source.status, 'ready')
        self.assertEqual(source.sections.count(), 2)

    def test_finds_relevant_section_first(self):
        self._source(self.user)
        results = list(search_sections(self.user, 'django celery backend'))
        self.assertEqual(results[0].heading, 'Callback')

    def test_partial_word_match_still_returns_results(self):
        self._source(self.user)
        results = list(search_sections(self.user, 'react unrelatedword'))
        self.assertEqual(results[0].heading, 'Garden Planner')

    def test_never_returns_another_users_sections(self):
        self._source(self.other)
        self.assertEqual(list(search_sections(self.user, 'django')), [])

    def test_reindex_replaces_sections(self):
        source = self._source(self.user)
        with patch('documents.services.read_file', return_value=b'# Only\nOne section'):
            index_upload_source(source)
        self.assertEqual(source.sections.count(), 1)

    def test_empty_document_marks_source_failed(self):
        source = ContextSource.objects.create(user=self.user, kind='upload', label='e.md', s3_key='k')
        with patch('documents.services.read_file', return_value=b'   '):
            with self.assertRaises(ValueError):
                index_upload_source(source)
        source.refresh_from_db()
        self.assertEqual(source.status, 'failed')
