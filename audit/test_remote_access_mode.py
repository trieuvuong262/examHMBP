from django.test import SimpleTestCase, override_settings

from audit.services.remote_access import infer_mode, apply_remote_access_mode, _nas_host_on_tailscale
from audit.services.vps_monitor import VpsMonitorError


class RemoteAccessModeTests(SimpleTestCase):
    def test_infer_prefers_file(self):
        self.assertEqual(infer_mode(file_mode='fortinet', nas_on_tailscale=True), 'fortinet')
        self.assertEqual(infer_mode(file_mode='tailscale', nas_on_tailscale=False), 'tailscale')

    def test_infer_without_file(self):
        self.assertEqual(infer_mode(file_mode='', nas_on_tailscale=True), 'tailscale')
        self.assertEqual(infer_mode(file_mode='', nas_on_tailscale=False), 'fortinet')

    def test_invalid_mode_rejected(self):
        with self.assertRaises(VpsMonitorError):
            apply_remote_access_mode('openvpn')

    @override_settings(NAS_DSM_URL='https://100.90.91.74:5556')
    def test_nas_on_tailscale(self):
        self.assertTrue(_nas_host_on_tailscale())

    @override_settings(NAS_DSM_URL='https://192.168.40.252:5556')
    def test_nas_on_lan(self):
        self.assertFalse(_nas_host_on_tailscale())
