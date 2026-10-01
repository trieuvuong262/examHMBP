from unittest import mock

from django.test import SimpleTestCase, override_settings

from audit.services import remote_access
from audit.services.vps_monitor import VpsMonitorError


@override_settings(NAS_LAN_HOST='192.168.40.252')
class RemoteAccessSiteToSiteTests(SimpleTestCase):
    @override_settings(NAS_DSM_URL='https://192.168.40.252:5556')
    def test_dsm_on_lan(self):
        with mock.patch.object(remote_access, '_tcp_ok', return_value=True):
            self.assertTrue(remote_access.remote_access_status()['dsm_on_lan'])

    @override_settings(NAS_DSM_URL='https://100.90.91.74:5556')
    def test_dsm_not_on_lan(self):
        with mock.patch.object(remote_access, '_tcp_ok', return_value=True):
            self.assertFalse(remote_access.remote_access_status()['dsm_on_lan'])

    def test_apply_requires_lan(self):
        with mock.patch.object(remote_access, '_tcp_ok', return_value=False):
            with self.assertRaises(VpsMonitorError):
                remote_access.apply_site_to_site()