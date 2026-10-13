from django.test import SimpleTestCase

from documents.validation import validate_document_content

RESUME = {
    'header': {'name': 'Ada', 'links': ['a.dev']},
    'summary': 'Engineer',
    'experience': [{
        'company': 'Acme', 'title': 'Dev', 'location': 'NYC',
        'start': '2020', 'end': '2022', 'bullets': ['Built things'],
    }],
}


class ValidateDocumentContentTests(SimpleTestCase):
    def test_valid_resume_has_no_errors(self):
        self.assertEqual(validate_document_content('resume', RESUME), [])

    def test_non_object_is_rejected(self):
        self.assertEqual(validate_document_content('resume', 'a string'), ['content: expected object'])

    def test_wrong_nested_type_reports_path(self):
        errors = validate_document_content('resume', {'experience': [{'bullets': 'x'}]})
        self.assertEqual(errors, ['content.experience[0].bullets: expected array'])

    def test_wrong_array_item_type_reports_index(self):
        errors = validate_document_content('resume', {'experience': [{'bullets': ['ok', 2]}]})
        self.assertEqual(errors, ['content.experience[0].bullets[1]: expected string'])

    def test_partial_entry_is_accepted(self):
        self.assertEqual(validate_document_content('resume', {'experience': [{'company': 'Acme'}]}), [])

    def test_none_scalar_is_accepted(self):
        self.assertEqual(validate_document_content('resume', {'summary': None}), [])

    def test_cover_letter_header_must_be_object(self):
        self.assertEqual(
            validate_document_content('cover_letter', {'header': 'x'}),
            ['content.header: expected object'],
        )
