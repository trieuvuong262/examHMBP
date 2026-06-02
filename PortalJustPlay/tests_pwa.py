import json

from django.test import TestCase


class SiteManifestTests(TestCase):
    def test_manifest_json_and_icons(self):
        response = self.client.get('/manifest.webmanifest')
        self.assertEqual(response.status_code, 200)
        self.assertIn('manifest+json', response['Content-Type'])

        data = json.loads(response.content)
        self.assertEqual(data['short_name'], 'JustPlay')
        self.assertEqual(data['theme_color'], '#dc2626')
        self.assertGreaterEqual(len(data['icons']), 2)
        srcs = ' '.join(icon['src'] for icon in data['icons'])
        self.assertIn('icon-192.png', srcs)
        self.assertIn('icon-512.png', srcs)
