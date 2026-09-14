"""Test LDAP phải có timeout — ldap3 mặc định không có, NAS rớt là treo request."""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from audit.services import nas_ldap_sync as sync

LDAP_SETTINGS = dict(
    NAS_LDAP_SYNC_ENABLED=True,
    NAS_LDAP_HOST='100.90.91.74',
    NAS_LDAP_PORT=636,
    NAS_LDAP_USE_SSL=True,
    NAS_LDAP_VERIFY_SSL=False,
    NAS_LDAP_BASE_DN='dc=ldap,dc=justplay,dc=local',
    NAS_LDAP_BIND_DN='uid=root,cn=users,dc=ldap,dc=justplay,dc=local',
    NAS_LDAP_BIND_PASSWORD='secret',
)


class LdapTimeoutSettingTests(SimpleTestCase):
    def test_defaults(self):
        self.assertEqual(sync._ldap_connect_timeout(), 5)
        self.assertEqual(sync._ldap_receive_timeout(), 10)

    @override_settings(NAS_LDAP_CONNECT_TIMEOUT=3, NAS_LDAP_RECEIVE_TIMEOUT=25)
    def test_reads_settings(self):
        self.assertEqual(sync._ldap_connect_timeout(), 3)
        self.assertEqual(sync._ldap_receive_timeout(), 25)

    @override_settings(NAS_LDAP_CONNECT_TIMEOUT=-3, NAS_LDAP_RECEIVE_TIMEOUT=9999)
    def test_clamps_out_of_range(self):
        self.assertEqual(sync._ldap_connect_timeout(), 1)
        self.assertEqual(sync._ldap_receive_timeout(), 120)

    @override_settings(NAS_LDAP_CONNECT_TIMEOUT=0, NAS_LDAP_RECEIVE_TIMEOUT=0)
    def test_zero_means_default(self):
        self.assertEqual(sync._ldap_connect_timeout(), 5)
        self.assertEqual(sync._ldap_receive_timeout(), 10)

    @override_settings(NAS_LDAP_CONNECT_TIMEOUT='abc', NAS_LDAP_RECEIVE_TIMEOUT=None)
    def test_falls_back_on_bad_value(self):
        self.assertEqual(sync._ldap_connect_timeout(), 5)
        self.assertEqual(sync._ldap_receive_timeout(), 10)


class LdapConnectionTimeoutTests(SimpleTestCase):
    @override_settings(**LDAP_SETTINGS, NAS_LDAP_CONNECT_TIMEOUT=4, NAS_LDAP_RECEIVE_TIMEOUT=11)
    def test_server_and_connection_receive_timeouts(self):
        """Server phải có connect_timeout, Connection phải có receive_timeout."""
        import ldap3

        captured = {}

        real_server = ldap3.Server

        def fake_server(*args, **kwargs):
            captured['server_kwargs'] = kwargs
            return object()

        def fake_connection(server, **kwargs):
            captured['conn_kwargs'] = kwargs

            class _Conn:
                def unbind(self):
                    pass

            return _Conn()

        with patch.object(ldap3, 'Server', fake_server), \
                patch.object(ldap3, 'Connection', fake_connection):
            with sync._ldap_connection():
                pass

        self.assertEqual(captured['server_kwargs'].get('connect_timeout'), 4)
        self.assertEqual(captured['conn_kwargs'].get('receive_timeout'), 11)
        # Giữ nguyên các tham số cũ
        self.assertEqual(captured['server_kwargs'].get('port'), 636)
        self.assertTrue(captured['server_kwargs'].get('use_ssl'))
        self.assertTrue(captured['conn_kwargs'].get('auto_bind'))
        self.assertTrue(captured['conn_kwargs'].get('raise_exceptions'))
        self.assertIs(real_server, ldap3.Server)  # patch đã được nhả

    @override_settings(**LDAP_SETTINGS)
    def test_connection_error_is_wrapped_not_hanging(self):
        """Lỗi kết nối phải nổi lên dưới dạng exception, không treo."""
        import ldap3

        with patch.object(ldap3, 'Server', lambda *a, **k: object()), \
                patch.object(ldap3, 'Connection', side_effect=OSError('timed out')):
            with self.assertRaises(OSError):
                with sync._ldap_connection():
                    pass
