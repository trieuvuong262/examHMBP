from django.test import SimpleTestCase

from kiotviet.formatters import format_description_html


class ProductDescriptionFormatTests(SimpleTestCase):
    def test_renders_kiotviet_html_description(self):
        raw = (
            '<p>Balo Just Play - CROSS <br>- Chất liệu: vải dù</p>'
            '<p># balo bóng đá</p>'
        )
        html = format_description_html(raw)
        self.assertIn('<p>', html)
        self.assertIn('<br>', html)
        self.assertNotIn('&lt;p&gt;', html)
        self.assertIn('Balo Just Play', html)

    def test_plain_text_gets_line_breaks(self):
        html = format_description_html('Dòng 1\nDòng 2')
        self.assertIn('<br>', html)
        self.assertIn('Dòng 1', html)

    def test_empty_description(self):
        self.assertEqual(format_description_html(''), '')
        self.assertEqual(format_description_html(None), '')

    def test_strips_script_tags(self):
        html = format_description_html('<p>OK</p><script>alert(1)</script>')
        self.assertIn('OK', html)
        self.assertNotIn('script', html.lower())
