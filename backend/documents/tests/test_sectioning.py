from unittest.mock import patch

from django.test import SimpleTestCase

from documents.sectioning import split_sections


class SplitSectionsTests(SimpleTestCase):
    def test_splits_on_headings_and_keeps_preamble(self):
        text = 'Intro line\n\n# Project A\nBuilt a thing\n\n## Details\nUsed Django'
        self.assertEqual(split_sections(text), [
            ('', 'Intro line'),
            ('Project A', 'Built a thing'),
            ('Details', 'Used Django'),
        ])

    def test_ignores_hash_lines_inside_code_fences(self):
        text = '# Setup\n```\n# not a heading\nrun it\n```'
        sections = split_sections(text)
        self.assertEqual(len(sections), 1)
        self.assertIn('# not a heading', sections[0][1])

    def test_plain_text_is_one_section(self):
        self.assertEqual(split_sections('just some notes'), [('', 'just some notes')])

    def test_empty_sections_are_dropped(self):
        self.assertEqual(split_sections('# Empty\n\n# Full\nhello'), [('Full', 'hello')])

    def test_long_sections_split_on_paragraphs(self):
        with patch('documents.sectioning.CONTEXT_SECTION_MAX_CHARS', 30):
            sections = split_sections('# H\n' + 'a' * 20 + '\n\n' + 'b' * 20)
        self.assertEqual([heading for heading, _ in sections], ['H', 'H'])
