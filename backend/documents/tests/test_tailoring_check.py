import copy

from django.test import SimpleTestCase

from documents.tailoring_check import compare_tailoring

SOURCE = {
    'header': {'name': 'Ada', 'links': ['https://github.com/x/', 'https://linkedin.com/in/ada']},
    'summary': '',
    'experience': [{'company': 'A', 'title': 'Dev', 'bullets': ['Did it']}],
    'projects': [{'name': 'P', 'bullets': ['Built']}],
    'education': [{'school': 'Home'}],
    'skills': [{'category': 'Math', 'items': ['Algebra']}],
    'additional_sections': [{'title': 'Awards', 'entries': ['Won']}],
}
LAYOUT = {
    'section_order': ['experience', 'projects', 'education', 'skills', 'additional'],
    'source_sections': [
        {'title': 'Experience', 'placed_in': 'experience'},
        {'title': 'Awards', 'placed_in': 'additional'},
    ],
}


def tailored(**changes):
    content = copy.deepcopy(SOURCE)
    content.update(changes)
    return content


class CompareTailoringTests(SimpleTestCase):
    def test_identical_is_ok(self):
        result = compare_tailoring(SOURCE, copy.deepcopy(SOURCE), LAYOUT)
        self.assertTrue(result['ok'])
        self.assertEqual(result['sections_dropped'], [])
        self.assertEqual(result['links_dropped'], [])
        self.assertEqual(result['additional_titles_added'], [])

    def test_dropped_projects(self):
        result = compare_tailoring(SOURCE, tailored(projects=[]), LAYOUT)
        self.assertIn('projects', result['sections_dropped'])
        self.assertFalse(result['ok'])

    def test_dropped_additional_section_by_normalized_title(self):
        result = compare_tailoring(SOURCE, tailored(additional_sections=[]), LAYOUT)
        self.assertIn('additional:Awards', result['sections_dropped'])
        renamed = tailored(additional_sections=[{'title': '  AWARDS ', 'entries': ['Won']}])
        self.assertEqual(compare_tailoring(SOURCE, renamed, LAYOUT)['sections_dropped'], [])

    def test_invented_additional_title(self):
        extra = SOURCE['additional_sections'] + [{'title': 'Certifications', 'entries': ['X']}]
        result = compare_tailoring(SOURCE, tailored(additional_sections=extra), LAYOUT)
        self.assertEqual(result['additional_titles_added'], ['Certifications'])
        self.assertFalse(result['ok'])

    def test_links(self):
        header = {'name': 'Ada', 'links': ['https://github.com/x', 'https://linkedin.com/in/ada']}
        self.assertEqual(compare_tailoring(SOURCE, tailored(header=header), LAYOUT)['links_dropped'], [])
        header = {'name': 'Ada', 'links': ['https://github.com/x']}
        result = compare_tailoring(SOURCE, tailored(header=header), LAYOUT)
        self.assertEqual(result['links_dropped'], ['https://linkedin.com/in/ada'])

    def test_writer_added_summary_goes_first(self):
        result = compare_tailoring(SOURCE, tailored(summary='Engineer.'), LAYOUT)
        self.assertTrue(result['summary_added'])
        self.assertTrue(result['summary_first'])
        self.assertEqual(result['summary_block_index'], 0)

    def test_empty_summaries(self):
        result = compare_tailoring(SOURCE, copy.deepcopy(SOURCE), LAYOUT)
        self.assertIsNone(result['summary_block_index'])
        self.assertIsNone(result['summary_first'])
        self.assertNotIn('summary', result['sections_dropped'])

    def test_summary_dropped(self):
        source = tailored(summary='Has one.')
        result = compare_tailoring(source, tailored(summary=''), LAYOUT)
        self.assertIn('summary', result['sections_dropped'])

    def test_non_dict_inputs(self):
        self.assertTrue(compare_tailoring(None, None, None)['ok'])
        self.assertTrue(compare_tailoring('x', ['y'], 'z')['ok'])
