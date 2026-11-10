from django.test import SimpleTestCase

from callback.config import DECORATIVE_ELEMENT_KINDS
from documents.notices import DECORATIVE_LABELS, layout_notices


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


class DecorativeNoticeTests(SimpleTestCase):
    def test_decorative_notice(self):
        notices = layout_notices({}, {'decorative_elements': ['icons', 'charts']})
        self.assertEqual([n['code'] for n in notices], ['decorative_dropped'])
        self.assertEqual(notices[0]['sections'], [])
        self.assertIn('icons, charts', notices[0]['message'])

    def test_labels_follow_config_order(self):
        notices = layout_notices({}, {'decorative_elements': ['skill_pills', 'icons']})
        self.assertIn('icons, skill pills', notices[0]['message'])

    def test_unknown_and_malformed_values_give_no_notice(self):
        for value in (['<b>x</b>', 5, None], 'icons', {'icons': True}, [], None):
            self.assertEqual(layout_notices({}, {'decorative_elements': value}), [], value)

    def test_unknown_values_never_reach_message(self):
        notices = layout_notices({}, {'decorative_elements': ['icons', '<script>']})
        self.assertNotIn('script', notices[0]['message'])

    def test_notice_order(self):
        layout = {
            'columns': 2,
            'decorative_elements': ['icons'],
            'source_sections': [src('Awards', 'additional')],
        }
        codes = [n['code'] for n in layout_notices({}, layout)]
        self.assertEqual(codes, ['columns_simplified', 'decorative_dropped', 'sections_unplaced'])

    def test_every_kind_has_a_label(self):
        self.assertEqual(set(DECORATIVE_LABELS), set(DECORATIVE_ELEMENT_KINDS))
