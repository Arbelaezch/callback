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
