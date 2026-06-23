from django.test import SimpleTestCase

from reports.weekly_preview import embed_url_for_link, link_preview_rows


class WeeklyPreviewTests(SimpleTestCase):
    def test_google_drive_embed(self):
        url = 'https://drive.google.com/file/d/abc123XYZ/view?usp=sharing'
        self.assertEqual(
            embed_url_for_link(url),
            'https://drive.google.com/file/d/abc123XYZ/preview',
        )

    def test_google_docs_embed(self):
        url = 'https://docs.google.com/document/d/doc123/edit'
        self.assertEqual(
            embed_url_for_link(url),
            'https://docs.google.com/document/d/doc123/preview',
        )

    def test_youtube_embed(self):
        self.assertEqual(
            embed_url_for_link('https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
            'https://www.youtube.com/embed/dQw4w9WgXcQ',
        )

    def test_plain_link_no_embed(self):
        self.assertIsNone(embed_url_for_link('https://portal.justplay.vn/reports/'))

    def test_link_preview_rows(self):
        rows = link_preview_rows('https://example.com/a\n\nhttps://docs.google.com/spreadsheets/d/sheet1/edit')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['domain'], 'example.com')
        self.assertEqual(rows[0]['label'], 'example.com')
        self.assertIsNone(rows[0]['embed_url'])
        self.assertTrue(rows[1]['embed_url'].endswith('/preview'))
