from django.test import SimpleTestCase

from reports.link_utils import extract_urls_from_text, normalize_links_text, parse_link_lines
from reports.weekly_preview import link_preview_rows


class LinkUtilsTests(SimpleTestCase):
    def test_extract_url_from_sentence(self):
        line = 'Dạ em gửi báo cáo ạ: https://canva.link/dtkvcv0qvoe8u9q'
        self.assertEqual(
            extract_urls_from_text(line),
            ['https://canva.link/dtkvcv0qvoe8u9q'],
        )

    def test_parse_link_lines_strips_trailing_punctuation(self):
        line = 'Xem tại https://example.com/a).'
        self.assertEqual(parse_link_lines(line), ['https://example.com/a'])

    def test_normalize_links_text_one_per_line(self):
        raw = 'Dạ em gửi báo cáo ạ: https://canva.link/dtkvcv0qvoe8u9q'
        self.assertEqual(
            normalize_links_text(raw),
            'https://canva.link/dtkvcv0qvoe8u9q',
        )

    def test_link_preview_rows_uses_extracted_href(self):
        rows = link_preview_rows(
            'Dạ em gửi báo cáo ạ: https://canva.link/dtkvcv0qvoe8u9q'
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['url'], 'https://canva.link/dtkvcv0qvoe8u9q')
        self.assertEqual(rows[0]['domain'], 'canva.link')
        self.assertIn('báo cáo', rows[0]['note'])

    def test_multiple_urls_in_one_line(self):
        line = 'A: https://a.com/x B: https://b.com/y'
        self.assertEqual(
            parse_link_lines(line),
            ['https://a.com/x', 'https://b.com/y'],
        )
