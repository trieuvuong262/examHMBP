from django.test import TestCase, override_settings

from nas_storage.dept_nas_config import is_portal_browse_hidden_share, portal_browse_hidden_shares
from nas_storage.models import NasShareFolder
from nas_storage.portal_access import all_share_portal_roots, sync_browse_all_share_permissions


class PortalBrowseHiddenShareTests(TestCase):
  @override_settings(NAS_PORTAL_BROWSE_HIDDEN_SHARES='docker,netbackup')
  def test_hidden_share_names(self):
    self.assertTrue(is_portal_browse_hidden_share('docker'))
    self.assertTrue(is_portal_browse_hidden_share('DOCKER'))
    self.assertFalse(is_portal_browse_hidden_share('07_SAN_XUAT'))

  def test_all_share_portal_roots_skips_docker(self):
    NasShareFolder.objects.create(share_name='docker', display_name='Docker')
    NasShareFolder.objects.create(share_name='07_SAN_XUAT', display_name='SX')
    names = [e.rel_path for e in all_share_portal_roots()]
    self.assertNotIn('docker', names)
    self.assertIn('07_SAN_XUAT', names)

  def test_sync_browse_all_skips_docker(self):
    from nas_storage.models import NasAccessGroup
    NasAccessGroup.objects.create(name='TGD', portal_browse_all=True)
    NasShareFolder.objects.create(share_name='docker')
    NasShareFolder.objects.create(share_name='01_BAN_GIAM_DOC')
    stats = sync_browse_all_share_permissions()
    self.assertEqual(stats['permissions_created'], 1)
