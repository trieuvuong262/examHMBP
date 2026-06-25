"""Cấu hình nhóm NAS ↔ phòng ban Portal — nguồn dữ liệu chung cho LDAP, phân quyền share."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from hrm.department_permission_templates import department_name_to_code

# Portal department code → tên nhóm trên NAS/LDAP (khớp DSM Group tab).
PORTAL_CODE_TO_NAS_GROUP: dict[str, str] = {
    'tgd': 'TGD',
    'dbcl': 'DBCL',
    'hcns': 'HCNS',
    'tckt': 'TCKT',
    'kd-mkt': 'MKT',
    'khsx': 'KHSX',
    'rd': 'RnD',
    'sx': 'SX',
    'it': 'IT',
}

# Alias giữ tương thích với nas_ldap_sync.
PORTAL_CODE_TO_LDAP_GROUP = PORTAL_CODE_TO_NAS_GROUP
DEPARTMENT_NAS_GROUPS = frozenset(PORTAL_CODE_TO_NAS_GROUP.values())

# Mô tả user local trên DSM (cột Description) → nhóm NAS.
NAS_USER_DESCRIPTION_TO_GROUP: dict[str, str] = {
    'SX': 'SX',
    'KD-MKT': 'MKT',
    'HCNS': 'HCNS',
    'TCKT': 'TCKT',
    'RnD': 'RnD',
    'TGD': 'TGD',
    'Admin': 'IT',
}

NAS_LOCAL_SYNC_SKIP_USERS = frozenset({
    'admin',
    'guest',
    'tailscale-justplay',
    'justplay-it',
})


@dataclass(frozen=True)
class DeptNasSpec:
    portal_code: str
    nas_group: str
    share_name: str | None
    label: str
    sort_order: int


# Share phòng ban trên NAS (synoshare) — khớp tmp_nas_fix_all_dept_acl + KD-MKT root remote.
DEPT_NAS_SPECS: tuple[DeptNasSpec, ...] = (
    DeptNasSpec('tgd', 'TGD', '01_BAN_GIAM_DOC', 'Ban giám đốc', 10),
    DeptNasSpec('hcns', 'HCNS', '02_HANH_CHINH_NHAN_SU', 'Hành chính nhân sự', 20),
    DeptNasSpec('tckt', 'TCKT', '03_TAI_CHINH_KE_TOAN', 'Tài chính kế toán', 30),
    DeptNasSpec('dbcl', 'DBCL', None, 'Đảm bảo chất lượng', 35),
    DeptNasSpec('kd-mkt', 'MKT', 'KD-MKT', 'Kinh doanh - Marketing', 40),
    DeptNasSpec('khsx', 'KHSX', None, 'Kế hoạch sản xuất', 45),
    DeptNasSpec('rd', 'RnD', '06_RnD_THIET_KE_SAN_PHAM', 'R&D', 50),
    DeptNasSpec('sx', 'SX', '07_SAN_XUAT', 'Sản xuất', 60),
    DeptNasSpec('it', 'IT', '10_HE_THONG_CNTT', 'Hệ thống CNTT', 70),
)

# Share phụ (cùng nhóm MKT) — nếu tồn tại trên NAS.
EXTRA_SHARE_GROUP_LINKS: tuple[tuple[str, str], ...] = (
    ('05_MARKETING', 'MKT'),
)


def nas_group_for_portal_department(department_name: str | None) -> str | None:
    code = department_name_to_code(department_name or '')
    if not code:
        return None
    return PORTAL_CODE_TO_NAS_GROUP.get(code)


def nas_principal_for_group(group_name: str) -> str:
    domain = getattr(settings, 'NAS_LDAP_DOMAIN', 'ldap.justplay.local')
    return f'@{group_name}@{domain}'


def nas_group_for_user_description(description: str | None) -> str | None:
    key = (description or '').strip()
    if not key:
        return None
    return NAS_USER_DESCRIPTION_TO_GROUP.get(key)
