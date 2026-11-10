from unittest.mock import patch

from django.test import SimpleTestCase

from documents.rendering import (
    html_to_pdf,
    resume_blocks,
    render_cover_letter_html,
    render_resume_html,
    resolve_layout,
)

CONTENT = {
    'header': {'name': 'Ada Lovelace', 'headline': 'Engineer', 'email': 'ada@example.com',
               'phone': '', 'location': 'London', 'links': ['github.com/ada']},
    'summary': 'Builds engines.',
    'experience': [{
        'company': 'Analytical Co', 'title': 'Programmer', 'location': '',
        'start': '1842', 'end': '1843', 'bullets': ['Wrote the first program', 'Reviewed notes'],
    }],
    'projects': [],
    'education': [{'school': 'Home', 'degree': '', 'start': '', 'end': '1835', 'details': []}],
    'skills': [{'category': 'Math', 'items': ['Algebra', 'Calculus']}],
}
LAYOUT = {
    'page_size': 'a4', 'font_family': 'Georgia', 'base_font_size_pt': 11,
    'margins_in': {'top': 0.5, 'right': 0.5, 'bottom': 0.5, 'left': 0.5},
    'section_order': ['skills', 'experience'], 'accent_color': '#1f3a5f', 'bullet_style': 'dash',
}


class ResolveLayoutTests(SimpleTestCase):
    def test_hostile_values_never_reach_css(self):
        layout = resolve_layout({
            'font_family': 'x; } body { background: url(http://evil)',
            'accent_color': 'red; background:url(x)',
            'page_size': 'letter; evil',
            'base_font_size_pt': 'huge',
            'margins_in': {'top': 999, 'left': -5},
            'line_height': '1e9',
        })
        self.assertEqual(layout['accent_color'], '')
        self.assertEqual(layout['page_size'], 'letter')
        self.assertEqual(layout['font_size_pt'], 10.5)
        self.assertEqual(layout['margin_top'], 1.25)
        self.assertEqual(layout['margin_left'], 0.3)
        self.assertEqual(layout['line_height'], 1.7)
        self.assertNotIn('evil', layout['font_stack'])

    def test_font_mapping(self):
        self.assertIn('Liberation Serif', resolve_layout({'font_family': 'Georgia'})['font_stack'])
        self.assertIn('Liberation Mono', resolve_layout({'font_family': 'Courier New'})['font_stack'])
        self.assertIn('Liberation Sans', resolve_layout({'font_family': 'Open Sans'})['font_stack'])

    def test_section_order_keeps_every_section(self):
        order = resolve_layout({'section_order': ['skills', 'bogus', 'skills', 'experience']})['section_order']
        self.assertEqual(order[1:3], ['skills', 'experience'])
        self.assertEqual(
            sorted(order), sorted(['summary', 'experience', 'projects', 'education', 'skills', 'additional']),
        )

    def test_empty_layout_gets_defaults(self):
        layout = resolve_layout(None)
        self.assertEqual(layout['page_size'], 'letter')
        self.assertEqual(len(layout['section_order']), 6)
        self.assertEqual(layout['section_titles']['experience'], 'Experience')

    def test_additional_appended_when_missing(self):
        order = resolve_layout({'section_order': ['experience', 'skills']})['section_order']
        self.assertEqual(order[-1], 'additional')
        order = resolve_layout({'section_order': ['additional', 'experience']})['section_order']
        self.assertEqual(order[1], 'additional')
        self.assertEqual(order.count('additional'), 1)

    def test_summary_missing_from_order_goes_first(self):
        order = resolve_layout({'section_order': ['experience', 'education']})['section_order']
        self.assertEqual(order[0], 'summary')
        order = resolve_layout({'section_order': ['experience', 'summary']})['section_order']
        self.assertEqual(order[:2], ['experience', 'summary'])

    def test_section_titles_from_source_sections(self):
        titles = resolve_layout({'source_sections': [
            {'title': 'Contact', 'placed_in': 'header'},
            {'title': 'Work  Experience ', 'placed_in': 'experience'},
            {'title': 'Other Experience', 'placed_in': 'experience'},
        ]})['section_titles']
        self.assertEqual(titles['experience'], 'Work Experience')
        self.assertNotIn('header', titles)

    def test_section_titles_default_and_truncated(self):
        titles = resolve_layout({'source_sections': [
            'Skills',
            None,
            {'title': 42, 'placed_in': 'summary'},
            {'title': '   ', 'placed_in': 'projects'},
            {'title': 'E' * 200, 'placed_in': 'education'},
        ]})['section_titles']
        self.assertEqual(titles['skills'], 'Skills')
        self.assertEqual(titles['summary'], 'Summary')
        self.assertEqual(titles['projects'], 'Projects')
        self.assertEqual(titles['education'], 'E' * 60)
        self.assertEqual(resolve_layout({'source_sections': 'bogus'})['section_titles']['skills'], 'Skills')

    def test_font_hints(self):
        def stack(name):
            return resolve_layout({'font_family': name})['font_stack']

        for name in ('Computer Modern', 'CMU Serif', 'Charter', 'Roboto Slab'):
            self.assertIn('Liberation Serif', stack(name), name)
        for name in ('Century Gothic', 'Lato', 'Calibri', 'Source Sans Pro'):
            self.assertIn('Liberation Sans', stack(name), name)
        self.assertIn('Liberation Mono', stack('Fira Mono'))


ADDITIONAL = [
    {'title': 'Certifications', 'entries': [{
        'heading': 'Certified Engine Operator', 'detail': 'Babbage Institute', 'dates': '1840',
        'bullets': ['Passed with distinction'],
    }]},
    {'title': 'Awards', 'entries': [{'heading': 'Royal Medal', 'detail': '', 'dates': '', 'bullets': []}]},
]


class RenderResumeTests(SimpleTestCase):
    def test_default_section_titles_without_source_sections(self):
        html = render_resume_html(CONTENT, LAYOUT)
        for title in ('Experience', 'Education', 'Skills'):
            self.assertIn(f'<h2>{title}</h2>', html)

    def test_additional_sections_render(self):
        content = {**CONTENT, 'additional_sections': ADDITIONAL}
        layout = {**LAYOUT, 'section_order': ['skills', 'additional', 'experience']}
        html = render_resume_html(content, layout)
        for text in ('<h2>Certifications</h2>', '<h2>Awards</h2>', 'Certified Engine Operator',
                     'Babbage Institute', '<span class="dates">1840</span>', 'Passed with distinction',
                     'Royal Medal'):
            self.assertIn(text, html)
        self.assertLess(html.index('<h2>Skills</h2>'), html.index('<h2>Certifications</h2>'))
        self.assertLess(html.index('<h2>Certifications</h2>'), html.index('<h2>Awards</h2>'))
        self.assertLess(html.index('<h2>Awards</h2>'), html.index('<h2>Experience</h2>'))

    def test_additional_title_escaped(self):
        content = {**CONTENT, 'additional_sections': [
            {'title': '<script>x</script>', 'entries': [{'heading': 'H'}]},
        ]}
        html = render_resume_html(content, LAYOUT)
        self.assertNotIn('<script>x', html)
        self.assertIn('&lt;script&gt;x&lt;/script&gt;', html)

    def test_custom_section_title_rendered(self):
        layout = {**LAYOUT, 'source_sections': [
            {'title': 'Work Experience', 'placed_in': 'experience'},
            {'title': '<b>Tools</b>', 'placed_in': 'skills'},
        ]}
        html = render_resume_html(CONTENT, layout)
        self.assertIn('<h2>Work Experience</h2>', html)
        self.assertNotIn('<h2>Experience</h2>', html)
        self.assertIn('<h2>&lt;b&gt;Tools&lt;/b&gt;</h2>', html)

    def test_empty_additional_section_skipped(self):
        content = {**CONTENT, 'additional_sections': [
            {'title': 'Languages', 'entries': []},
            ADDITIONAL[1],
        ]}
        html = render_resume_html(content, LAYOUT)
        self.assertNotIn('Languages', html)
        self.assertIn('<h2>Awards</h2>', html)

    def test_renders_content_in_requested_order_and_skips_empty_sections(self):
        html = render_resume_html(CONTENT, LAYOUT)
        self.assertIn('Ada Lovelace', html)
        self.assertLess(html.index('Skills'), html.index('Experience'))
        self.assertNotIn('<h2>Projects</h2>', html)
        self.assertIn('size: a4', html)
        self.assertIn('color: #1f3a5f', html)
        self.assertIn('1842 – 1843', html)

    def test_content_is_escaped(self):
        content = {**CONTENT, 'summary': '<script>alert(1)</script>'}
        html = render_resume_html(content, LAYOUT)
        self.assertNotIn('<script>alert', html)
        self.assertIn('&lt;script&gt;', html)

    def test_pdf_is_generated_with_page_count(self):
        pdf, pages = html_to_pdf(render_resume_html(CONTENT, LAYOUT))
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertEqual(pages, 1)

    def test_overflowing_resume_reports_extra_pages(self):
        long = {**CONTENT, 'experience': [{
            'company': 'Co', 'title': 'T', 'bullets': [f'Did thing number {i}' for i in range(150)],
        }]}
        _, pages = html_to_pdf(render_resume_html(long, LAYOUT))
        self.assertGreater(pages, 1)


def _leadership(title='Leadership Experience'):
    return {'title': title, 'entries': [{'heading': 'Club president'}]}


def _src(*pairs):
    return [{'title': t, 'placed_in': p} for t, p in pairs]


class RenderResumeIssue32Tests(SimpleTestCase):
    def test_name_style_resolved_and_defaulted(self):
        self.assertEqual(resolve_layout({})['name_style'], 'normal')
        self.assertEqual(resolve_layout({'name_style': 'small_caps'})['name_style'], 'small_caps')
        self.assertEqual(resolve_layout({'name_style': 'uppercase'})['name_style'], 'uppercase')
        self.assertEqual(resolve_layout({'name_style': 'x; color:red'})['name_style'], 'normal')

    def test_name_style_css(self):
        def h1_rule(html):
            start = html.index('header h1 {')
            return html[start:html.index('}', start)]
        small = render_resume_html(CONTENT, {**LAYOUT, 'name_style': 'small_caps'})
        self.assertIn('font-variant: small-caps', h1_rule(small))
        self.assertNotIn('text-transform: uppercase', h1_rule(render_resume_html(CONTENT, LAYOUT)))

    def test_location_not_joined_to_company(self):
        content = {**CONTENT, 'experience': [{
            'company': 'Dunamu Inc.', 'title': 'Engineer', 'location': 'Seoul, S.Korea',
            'start': '2020', 'end': '2021', 'bullets': [],
        }]}
        html = render_resume_html(content, LAYOUT)
        self.assertIn('<span>Dunamu Inc.</span>', html)
        self.assertIn('<span class="location">Seoul, S.Korea</span>', html)
        self.assertNotIn('Dunamu Inc., Seoul', html)

    def test_additional_section_keeps_source_position(self):
        content = {**CONTENT, 'additional_sections': [_leadership()]}
        layout = {
            'section_order': ['education', 'experience', 'skills', 'additional'],
            'source_sections': _src(
                ('Education', 'education'), ('Experience', 'experience'),
                ('Leadership  experience', 'additional'), ('Skills', 'skills'),
            ),
        }
        html = render_resume_html(content, layout)
        self.assertLess(html.index('<h2>Experience</h2>'), html.index('<h2>Leadership Experience</h2>'))
        self.assertLess(html.index('<h2>Leadership Experience</h2>'), html.index('<h2>Skills</h2>'))

    def test_additional_sections_split_by_anchor(self):
        content = {**CONTENT, 'additional_sections': [
            _leadership(), _leadership('Awards'), _leadership('Certifications'),
        ]}
        layout = {
            'section_order': ['experience', 'skills', 'additional'],
            'source_sections': _src(
                ('Experience', 'experience'), ('Leadership Experience', 'additional'),
                ('Skills', 'skills'), ('Awards', 'additional'),
            ),
        }
        html = render_resume_html(content, layout)
        lead, skills = html.index('<h2>Leadership Experience</h2>'), html.index('<h2>Skills</h2>')
        awards, certs = html.index('<h2>Awards</h2>'), html.index('<h2>Certifications</h2>')
        self.assertLess(lead, skills)
        self.assertLess(skills, awards)
        self.assertLess(awards, certs)

    def test_additional_before_any_fixed_section_goes_first(self):
        content = {**CONTENT, 'additional_sections': [_leadership('Objective')]}
        layout = {
            'section_order': ['experience', 'skills', 'additional'],
            'source_sections': _src(('Objective', 'additional'), ('Experience', 'experience')),
        }
        html = render_resume_html(content, layout)
        self.assertLess(html.index('<h2>Objective</h2>'), html.index('<h2>Experience</h2>'))

    def test_resume_blocks_unit(self):
        order = ['summary', 'experience', 'projects', 'education', 'skills', 'additional']
        for source in ('bogus', [None, 'x'], None):
            blocks = resume_blocks(order, source, None)
            self.assertEqual([b['key'] for b in blocks], order[:-1])
        blocks = resume_blocks(order, [], [{'title': 'Empty', 'entries': []}, _leadership()])
        self.assertEqual(len([b for b in blocks if 'section' in b]), 1)
        self.assertEqual(len([b for b in blocks if b['key'] == 'skills']), 1)

    def test_long_company_name_stays_one_page(self):
        content = {**CONTENT, 'experience': [{
            'company': ('Very Long Organisation ' * 7)[:150], 'title': 'T',
            'start': '2020', 'end': '2021', 'bullets': ['x'],
        }]}
        html = render_resume_html(content, LAYOUT)
        self.assertIn('flex: 1 1 auto; min-width: 0', html)
        _, pages = html_to_pdf(html)
        self.assertEqual(pages, 1)


class RenderCoverLetterTests(SimpleTestCase):
    def test_markdown_rendered_with_letterhead(self):
        html = render_cover_letter_html('Dear team,\n\nI **love** this.', CONTENT['header'], LAYOUT)
        self.assertIn('Ada Lovelace', html)
        self.assertIn('<strong>love</strong>', html)

    def test_single_newlines_stay_line_breaks_so_sign_offs_keep_their_lines(self):
        html = render_cover_letter_html('Thanks for reading,\nJordan', {}, {})
        self.assertIn('Thanks for reading,<br', html)

    def test_raw_html_in_markdown_is_escaped(self):
        html = render_cover_letter_html('<script>alert(1)</script> hi', {}, {})
        self.assertNotIn('<script>alert', html)

    def test_external_resources_are_not_fetched(self):
        markdown = '![x](file:///etc/passwd) ![y](http://127.0.0.1:9/pixel.png)'
        with patch('urllib.request.OpenerDirector.open') as opener:
            pdf, _ = html_to_pdf(render_cover_letter_html(markdown, {}, {}))
        opener.assert_not_called()
        self.assertTrue(pdf.startswith(b'%PDF'))
