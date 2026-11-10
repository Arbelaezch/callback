import copy

from django.test import SimpleTestCase

from pipeline.llm.resume_cleanup import clean_resume_content


def _job(company, location):
    return {'experience': [{'company': company, 'location': location}]}


def _edu(degree, details, start='', end='May 2025'):
    return {'education': [{'degree': degree, 'start': start, 'end': end, 'details': details}]}


class CompanyLocationTests(SimpleTestCase):
    def _company(self, company, location):
        return clean_resume_content(_job(company, location))['experience'][0]['company']

    def test_suffix_stripped(self):
        self.assertEqual(self._company('Dunamu Inc., Seoul, S.Korea', 'Seoul, S.Korea'), 'Dunamu Inc.')
        self.assertEqual(self._company('Acme - Berlin', 'Berlin'), 'Acme')
        self.assertEqual(self._company('Acme, BERLIN', 'berlin'), 'Acme')

    def test_company_kept(self):
        self.assertEqual(self._company('Acme, Berlin', ''), 'Acme, Berlin')
        self.assertEqual(self._company('Acme, Berlin', 'Paris'), 'Acme, Berlin')
        self.assertEqual(self._company('Berlin', 'Berlin'), 'Berlin')

    def test_real_names_ending_with_location_kept(self):
        for company, location in (('University of Toronto', 'Toronto'), ('City of Boston', 'Boston'),
                                  ('Royal Bank of Canada', 'Canada'), ('Ubisoft Montreal', 'Montreal'),
                                  ('Acme, S.Korea', 'Korea')):
            self.assertEqual(self._company(company, location), company)


class DegreeDetailsTests(SimpleTestCase):
    DEGREE = 'Bachelor of Science in Biology'

    def _details(self, details, degree=None, **kw):
        degree = self.DEGREE if degree is None else degree
        return clean_resume_content(_edu(degree, details, **kw))['education'][0]['details']

    def test_repeat_dropped(self):
        self.assertEqual(self._details(['Bachelor of Science in Biology, Expected May 2025', 'Honors']), ['Honors'])
        self.assertEqual(self._details(['bachelor of science in biology.']), [])

    def test_extra_facts_kept(self):
        for detail in ('Bachelor of Science in Biology, Minor in Chemistry', 'GPA 3.9',
                       'Bachelor of Science in Biology, June 2024',
                       'Bachelor of Science in Biology, 우등 졸업'):
            self.assertEqual(self._details([detail]), [detail])

    def test_empty_degree_drops_nothing(self):
        self.assertEqual(self._details(['Expected May 2025'], degree=''), ['Expected May 2025'])


class RobustnessTests(SimpleTestCase):
    def test_not_mutated_and_unknown_keys_kept(self):
        content = {**_job('Acme, Berlin', 'Berlin'), 'additional_sections': [{'title': 'A'}], 'projects': []}
        before = copy.deepcopy(content)
        out = clean_resume_content(content)
        self.assertEqual(content, before)
        self.assertEqual(out['additional_sections'], before['additional_sections'])
        self.assertEqual(out['projects'], [])
        self.assertIsNot(out, content)

    def test_junk(self):
        self.assertIsNone(clean_resume_content(None))
        clean_resume_content({'experience': 'x', 'education': 'y'})
        clean_resume_content({'experience': [None, 3], 'education': [None, {'degree': 'x', 'details': 'z'}]})


def _skills(*items):
    return {'skills': [{'category': 'Tech', 'items': list(items)}]}


class RatingGuardTests(SimpleTestCase):
    def test_rating_values_dropped_from_skills(self):
        stats = {}
        out = clean_resume_content(_skills('Python', '80%', '4/5', '3', '4.5', '●●●○○'), stats)
        self.assertEqual(out['skills'][0]['items'], ['Python'])
        self.assertEqual(stats['skill_ratings_dropped'], 5)

    def test_trailing_glyphs_stripped(self):
        out = clean_resume_content(_skills('Python ●●●●○', 'Go ★★★'))
        self.assertEqual(out['skills'][0]['items'], ['Python', 'Go'])

    def test_real_skills_kept(self):
        items = ['C++', '8051', '5G', '3D', 'Go']
        stats = {}
        out = clean_resume_content(_skills(*items), stats)
        self.assertEqual(out['skills'][0]['items'], items)
        self.assertEqual(stats['skill_ratings_dropped'], 0)

    def test_category_of_only_ratings_removed(self):
        out = clean_resume_content(_skills('80%', '90%'))
        self.assertEqual(out['skills'], [])

    def test_empty_category_kept(self):
        out = clean_resume_content(_skills())
        self.assertEqual(len(out['skills']), 1)

    def test_chart_section_removed(self):
        content = {'additional_sections': [{'title': 'A Day', 'entries': [
            {'heading': '30'}, {'heading': '20', 'bullets': ['15%']},
        ]}]}
        stats = {}
        out = clean_resume_content(content, stats)
        self.assertEqual(out['additional_sections'], [])
        self.assertEqual(stats['chart_values_dropped'], 3)

    def test_real_entry_keeps_and_loses_numeric_bullet(self):
        entry = {'heading': 'Spanish', 'detail': 'Native', 'bullets': ['90%']}
        out = clean_resume_content({'additional_sections': [{'title': 'Languages', 'entries': [entry]}]})
        kept = out['additional_sections'][0]['entries'][0]
        self.assertEqual(kept['heading'], 'Spanish')
        self.assertEqual(kept['bullets'], [])

    def test_plain_empty_entry_not_dropped(self):
        content = {'additional_sections': [{'title': 'X', 'entries': [{'heading': ''}]}]}
        stats = {}
        out = clean_resume_content(content, stats)
        self.assertEqual(len(out['additional_sections'][0]['entries']), 1)
        self.assertEqual(stats['chart_values_dropped'], 0)

    def test_malformed_input_does_not_raise(self):
        clean_resume_content({'skills': 'x', 'additional_sections': [None, {'entries': 'y'}]})
        clean_resume_content({'skills': [None, {'items': 'z'}, {'items': [3, None]}]})
