import json

from django.test import TestCase


class SiteManifestTests(TestCase):
    def test_manifest_json_and_icons(self):
        response = self.client.get('/manifest.webmanifest')
        self.assertEqual(response.status_code, 200)
        self.assertIn('manifest+json', response['Content-Type'])

        data = json.loads(response.content)
        self.assertEqual(data['short_name'], 'JustPlay')
        self.assertTrue(data['start_url'].startswith('http'))
        self.assertIn('icon-192.png', ' '.join(i['src'] for i in data['icons']))

    def test_service_worker_at_root(self):
        response = self.client.get('/sw.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('javascript', response['Content-Type'])
        self.assertEqual(response.get('Service-Worker-Allowed'), '/')
        self.assertIn(b'install', response.content)
