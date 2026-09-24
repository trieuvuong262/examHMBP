"""Unit checks for NAS permission presets — no Django DB."""
from nas_storage.permission_defs import (
    detect_preset_from_flags,
    flags_from_preset,
    synoacl_mask_from_flags,
)


def test_no_delete_allows_move_via_delete_bits():
    flags = flags_from_preset('read_write_no_delete')
    assert detect_preset_from_flags(flags) == 'read_write_no_delete'
    assert synoacl_mask_from_flags(flags) == 'rwxpdDaARWc--:fd--'
    assert flags['perm_create_files'] is True
    assert flags['perm_delete'] is True
    assert flags['perm_delete_children'] is True


def test_read_write_still_includes_delete():
    flags = flags_from_preset('read_write')
    assert detect_preset_from_flags(flags) == 'read_write_no_delete'
    assert synoacl_mask_from_flags(flags) == 'rwxpdDaARWc--:fd--'


def test_full_and_read():
    assert synoacl_mask_from_flags(flags_from_preset('full')) == 'rwxpdDaARWcCo:fd--'
    assert synoacl_mask_from_flags(flags_from_preset('read')) == 'r-x---a-R-c--:fd--'


def test_parse_synoacl_get():
    from nas_storage.nas_acl_apply import parse_synoacl_get

    sample = (
        'ACL version: 1\n'
        '\t [0] group:administrators:allow:rwxpdDaARWc--:fd-- (level:0)\n'
        '\t [1] group:TGD@ldap.justplay.local:allow:rwxpdDaARWc--:fd-- (level:0)\n'
        '\t [6] group::allow:rwxpdDaARWc--:fd-- (level:0)\n'
        '\t [9] group:MKT@ldap.justplay.local:allow:rwxpdDaARWc--:fd-- (level:0)\n'
    )
    rows = parse_synoacl_get(sample)
    assert [r['name'] for r in rows] == [
        'administrators',
        'TGD@ldap.justplay.local',
        '',
        'MKT@ldap.justplay.local',
    ]
    assert rows[1]['kind'] == 'group'
    assert rows[1]['index'] == 1
    assert rows[2]['index'] == 6


def test_parse_synoacl_ace():
    from nas_storage.nas_acl_apply import _parse_synoacl_ace

    parsed = _parse_synoacl_ace('group:HCNS@ldap.justplay.local:allow:rwxp--aARWc--:fd--')
    assert parsed == {
        'kind': 'group',
        'name': 'HCNS@ldap.justplay.local',
        'action': 'allow',
        'perm': 'rwxp--aARWc--',
        'inherit': 'fd--',
    }


if __name__ == '__main__':
    test_no_delete_allows_move_via_delete_bits()
    test_read_write_still_includes_delete()
    test_full_and_read()
    test_parse_synoacl_get()
    test_parse_synoacl_ace()
    print('preset tests ok')
