from django.test import SimpleTestCase

from documents.validation import validate_document_content

RESUME = {
    'header': {'name': 'Ada', 'links': ['a.dev']},
    'summary': 'Engineer',
    'experience': [{
        'company': 'Acme', 'title': 'Dev', 'location': 'NYC',
        'start': '2020', 'end': '2022', 'bullets': ['Built things'],
    }],
    'projects': [],
    'education': [],
    'skills': [],
}


class ValidateDocumentContentTests(SimpleTestCase):
    def test_valid_resume_has_no_errors(self):
        self.assertEqual(validate_document_content('resume', RESUME), [])

    def test_wrong_nested_type_reports_path(self):
        content = {**RESUME, 'experience': [{'company': 'A', 'title': 'B', 'bullets': 'x'}]}
        self.assertEqual(
            validate_document_content('resume', content),
            ['content.experience[0].bullets: expected array'],
        )

    def test_wrong_array_item_type_reports_index(self):
        content = {**RESUME, 'experience': [{'company': 'A', 'title': 'B', 'bullets': ['ok', 2]}]}
        self.assertEqual(
            validate_document_content('resume', content),
            ['content.experience[0].bullets[1]: expected string'],
        )

    def test_entry_with_empty_required_values_is_accepted(self):
        content = {**RESUME, 'experience': [{'company': '', 'title': '', 'bullets': []}]}
        self.assertEqual(validate_document_content('resume', content), [])

    def test_none_scalar_is_accepted(self):
        self.assertEqual(validate_document_content('resume', {**RESUME, 'summary': None}), [])

    def test_missing_top_level_required_key_is_reported(self):
        content = {k: v for k, v in RESUME.items() if k != 'skills'}
        self.assertEqual(validate_document_content('resume', content), ['content.skills: required'])

    def test_missing_required_key_in_array_item_reports_path(self):
        content = {**RESUME, 'experience': [{'company': 'Acme', 'title': 'Dev'}]}
        self.assertEqual(
            validate_document_content('resume', content),
            ['content.experience[0].bullets: required'],
        )

    def test_unknown_top_level_key_is_rejected(self):
        self.assertEqual(
            validate_document_content('resume', {**RESUME, 'foo': 1}),
            ['content.foo: unknown field'],
        )

    def test_unknown_nested_key_is_rejected(self):
        content = {**RESUME, 'header': {'name': 'Ada', 'nickname': 'A'}}
        self.assertEqual(
            validate_document_content('resume', content),
            ['content.header.nickname: unknown field'],
        )

    def test_valid_cover_letter_content_has_no_errors(self):
        self.assertEqual(validate_document_content('cover_letter', {'header': {'name': 'Ada'}}), [])

    def test_cover_letter_requires_header_and_rejects_unknown_keys(self):
        self.assertEqual(validate_document_content('cover_letter', {}), ['content.header: required'])
        self.assertEqual(
            validate_document_content('cover_letter', {'header': {'name': 'Ada'}, 'body': 'x'}),
            ['content.body: unknown field'],
        )

    def test_cover_letter_header_requires_name(self):
        self.assertEqual(
            validate_document_content('cover_letter', {'header': {'email': 'a@b.c'}}),
            ['content.header.name: required'],
        )

    def test_non_object_is_rejected(self):
        self.assertEqual(validate_document_content('resume', 'a string'), ['content: expected object'])

    def test_cover_letter_header_must_be_object(self):
        self.assertEqual(
            validate_document_content('cover_letter', {'header': 'x'}),
            ['content.header: expected object'],
        )
