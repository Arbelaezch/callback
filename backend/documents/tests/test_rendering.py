from unittest.mock import patch

from django.test import SimpleTestCase

from documents.rendering import (
    html_to_pdf,
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
        self.assertEqual(order[:2], ['skills', 'experience'])
        self.assertEqual(sorted(order), sorted(['summary', 'experience', 'projects', 'education', 'skills']))

    def test_empty_layout_gets_defaults(self):
        layout = resolve_layout(None)
        self.assertEqual(layout['page_size'], 'letter')
        self.assertEqual(len(layout['section_order']), 5)


class RenderResumeTests(SimpleTestCase):
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
