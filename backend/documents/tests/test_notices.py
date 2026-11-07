from django.test import SimpleTestCase

from documents.notices import layout_notices


def src(title, placed_in):
    return {'title': title, 'placed_in': placed_in}


class LayoutNoticesTests(SimpleTestCase):
    def test_two_columns_notice(self):
        notices = layout_notices({}, {'columns': 2})
        self.assertEqual([n['code'] for n in notices], ['columns_simplified'])
        self.assertEqual(notices[0]['sections'], [])

    def test_clean_layout_gives_nothing(self):
        self.assertEqual(layout_notices({'experience': [{}]}, {'columns': 1}), [])

    def test_placed_in_non_empty_section_not_reported(self):
        layout = {'source_sections': [src('Work Experience', 'experience')]}
        self.assertEqual(layout_notices({'experience': [{'heading': 'x'}]}, layout), [])

    def test_placed_in_empty_section_reported(self):
        layout = {'source_sections': [src('Projects', 'projects')]}
        notices = layout_notices({'projects': []}, layout)
        self.assertEqual(notices[0]['code'], 'sections_unplaced')
        self.assertEqual(notices[0]['sections'], ['Projects'])
        self.assertIn('Projects', notices[0]['message'])

    def test_additional_match_is_case_and_space_insensitive(self):
        layout = {'source_sections': [src('Certifications', 'additional')]}
        content = {'additional_sections': [{'title': '  CERTIFICATIONS ', 'entries': []}]}
        self.assertEqual(layout_notices(content, layout), [])

    def test_additional_without_match_reported(self):
        layout = {'source_sections': [src('Awards', 'additional')]}
        content = {'additional_sections': [{'title': 'Languages', 'entries': []}]}
        self.assertEqual(layout_notices(content, layout)[0]['sections'], ['Awards'])

    def test_header_never_reported(self):
        layout = {'source_sections': [src('Contact', 'header')]}
        self.assertEqual(layout_notices({}, layout), [])

    def test_unknown_placed_in_reported(self):
        layout = {'source_sections': [src('Odd', 'nowhere')]}
        self.assertEqual(layout_notices({}, layout)[0]['sections'], ['Odd'])

    def test_malformed_input_does_not_raise(self):
        self.assertEqual(layout_notices(None, None), [])
        self.assertEqual(layout_notices({}, {'source_sections': 'x'}), [])
        self.assertEqual(layout_notices({'additional_sections': 'x'}, {'source_sections': ['a', None, 3, src('', 'skills'), src(5, 'skills')]}), [])
        self.assertIsInstance(layout_notices('x', {'source_sections': [src('A', 'additional')], 'columns': 2}), list)

    def test_duplicate_titles_reported_once(self):
        layout = {'source_sections': [src('Awards', 'additional'), src('Awards', 'additional')]}
        self.assertEqual(layout_notices({}, layout)[0]['sections'], ['Awards'])
