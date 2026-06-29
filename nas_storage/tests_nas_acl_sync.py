from django.test import TestCase

from nas_storage.nas_acl_apply import (
    build_share_acl_sync_commands,
    is_fq_ldap_principal,
    parse_synoshare_list_acl,
    principal_group_key,
    principal_should_upgrade,
)


class ShareAclSyncTests(TestCase):
    SAMPLE = """
SYNOSHARE ACL Perm List:
 Name ............[04_KINH_DOANH_CSKH]
 ACL RO List .....[@TGD@ldap.justplay.local]
 ACL RW List .....[@HCNS@ldap.justplay.local,@TGD,@IT@ldap.justplay.local,@administrators]
 ACL NA List .....[]
"""

    def test_parse_synoshare_list_acl(self):
        parsed = parse_synoshare_list_acl(self.SAMPLE)
        self.assertIn('@IT@ldap.justplay.local', parsed['RW'])
        self.assertIn('@TGD@ldap.justplay.local', parsed['RO'])

    def test_principal_group_key(self):
        self.assertEqual(principal_group_key('@IT@ldap.justplay.local'), 'it')
        self.assertEqual(principal_group_key('@TGD'), 'tgd')

    def test_build_share_acl_sync_removes_stale_it(self):
        current = parse_synoshare_list_acl(self.SAMPLE)
        desired = {
            'RW': set(),
            'RO': {'@TGD@ldap.justplay.local'},
            'NA': set(),
        }
        cmds = build_share_acl_sync_commands(
            share='04_KINH_DOANH_CSKH',
            desired=desired,
            current=current,
        )
        joined = '\n'.join(cmds)
        self.assertIn('IT@ldap.justplay.local', joined)
        self.assertIn(' - ', joined)
        self.assertNotIn('@administrators', joined)
    def test_principal_should_upgrade_short_ldap_group(self):
        self.assertTrue(principal_should_upgrade("@IT", "@IT@ldap.justplay.local"))
        self.assertFalse(principal_should_upgrade("@IT@ldap.justplay.local", "@IT@ldap.justplay.local"))
        self.assertTrue(is_fq_ldap_principal("@HCNS@ldap.justplay.local"))
        self.assertFalse(is_fq_ldap_principal("@HCNS"))

    def test_build_share_acl_sync_upgrades_short_it_principal(self):
        current = {"RW": {"@IT", "@administrators"}, "RO": set(), "NA": set()}
        desired = {"RW": {"@IT@ldap.justplay.local"}, "RO": set(), "NA": set()}
        cmds = build_share_acl_sync_commands(
            share="10_HE_THONG_CNTT", desired=desired, current=current,
        )
        joined = "\n".join(cmds)
        self.assertIn(' - "@IT"', joined)
        self.assertIn("+ @IT@ldap.justplay.local", joined)
