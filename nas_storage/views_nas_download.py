"""Trang NAS — tải bộ cài kết nối WebDAV (Windows)."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from audit.services.rustdesk_enroll import downloader_script_fields as rustdesk_downloader_fields
from audit.services.rustdesk_enroll import script_config as rustdesk_script_config
from audit.views_rustdesk_setup import _apply_script_tokens as apply_rustdesk_script_tokens
from equipment.services.inventory_scan import downloader_script_fields as equipment_downloader_fields
from equipment.services.inventory_scan import script_config as equipment_script_config
from equipment.views_inventory_scan import _apply_script_tokens as apply_equipment_script_tokens
from nas_storage.download_shares import WEBDAV_SHARE_ALIASES, nas_webdav_shares_for_user, resolve_webdav_share_name
from nas_storage.nas_download_access import user_can_nas_download
from nas_storage.nas_paths import user_department_folder_code
from nas_storage.views import nas_module_nav_context


def nas_shares_for_user(user) -> list[str]:
    return nas_webdav_shares_for_user(user)


def nas_download_config() -> dict:
    fallback = getattr(settings, 'NAS_RDRIVE_FALLBACK_SERVER', '').strip()
    if not fallback:
        fallback = getattr(settings, 'NAS_SSH_HOST', '').strip()
    webdav_port = int(getattr(settings, 'NAS_WEBDAV_PORT', 5678) or 5678)
    smb_port = int(getattr(settings, 'NAS_SMB_PORT', 445) or 445)
    if smb_port == 5678:
        smb_port = 445
    return {
        'server': getattr(settings, 'NAS_RDRIVE_SERVER', 'justplay.synology.me').strip(),
        'webdav_port': webdav_port,
        'smb_port': smb_port,
        'port': webdav_port,
        'ldap_domain': getattr(settings, 'NAS_LDAP_DOMAIN', 'ldap.justplay.local').strip(),
        'fallback_server': fallback,
    }


def _download_forbidden(request):
    messages.error(request, 'Bạn không có quyền tải bộ cài NAS.')
    return redirect('nas_storage:browse')


def _dept_webdav_share_for_user(user) -> str | None:
    """Map mã phòng ban (SX, MKT…) sang tên share DSM (07_SAN_XUAT…)."""
    from nas_storage.dept_nas_config import DEPT_NAS_SPECS

    dept_code = (user_department_folder_code(user) or '').strip()
    if not dept_code:
        return None
    dept_upper = dept_code.upper()
    for spec in DEPT_NAS_SPECS:
        if spec.nas_group.upper() == dept_upper and spec.share_name:
            return resolve_webdav_share_name(spec.share_name)
    return resolve_webdav_share_name(dept_code)


def _order_shares_for_webdav_mount(shares: list[str], user) -> list[str]:
    """
    Gắn share phòng ban lên Z: trước (vd. KD-MKT → 05_MARKETING, SX → 07_SAN_XUAT).
    Tránh user map share chung lên Z: rồi lỗi unavailable.
    """
    if not shares:
        return []
    dept_share = _dept_webdav_share_for_user(user)
    if not dept_share or dept_share not in shares:
        return list(shares)
    return [dept_share] + [name for name in shares if name != dept_share]


@login_required
@require_GET
def nas_download_page(request):
    if not user_can_nas_download(request.user):
        return _download_forbidden(request)
    cfg = nas_download_config()
    shares = nas_shares_for_user(request.user)
    drive_preview = [
        {'letter': chr(ord('Z') - i), 'share': name}
        for i, name in enumerate(shares)
    ]
    return render(request, 'nas_storage/nas_download.html', {
        **nas_module_nav_context(request, 'nas_download'),
        'config': cfg,
        'user_shares': shares,
        'drive_preview': drive_preview,
    })


def _prepare_ps1(body: str) -> bytes:
    if not body.startswith('\ufeff'):
        body = '\ufeff' + body
    body = body.replace('\r\n', '\n').replace('\n', '\r\n')
    return body.encode('utf-8')


def _prepare_bat(body: str) -> bytes:
    return body.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')


def _nas_script_version() -> str:
    ps1 = Path(settings.BASE_DIR) / 'scripts' / 'JustPlay-NAS-RaiDrive-Setup.ps1'
    if not ps1.is_file():
        return ''
    match = re.search(r"\$NasScriptVersion = '([^']+)'", ps1.read_text(encoding='utf-8-sig'))
    return match.group(1) if match else ''


def nas_user_bundle_config(request, user, cfg: dict) -> dict:
    portal_base = request.build_absolute_uri('/').rstrip('/')
    shares = _order_shares_for_webdav_mount(nas_shares_for_user(user), user)
    primary = shares[0] if shares else ''
    rustdesk_cfg = {**rustdesk_script_config(), **rustdesk_downloader_fields(user)}
    equipment_cfg = {**equipment_script_config(), **equipment_downloader_fields(user)}
    return {
        'bundle_version': 4,
        'script_version': _nas_script_version(),
        'server': cfg['server'],
        'webdav_port': cfg['webdav_port'],
        'smb_port': cfg.get('smb_port', 445),
        'port': cfg['webdav_port'],
        'fallback_server': cfg.get('fallback_server', ''),
        'ldap_domain': cfg['ldap_domain'],
        'portal_password_url': f'{portal_base}/accounts/password/change/',
        'portal_username': user.username,
        'shares': shares,
        'primary_share': primary,
        'webdav_share_aliases': dict(WEBDAV_SHARE_ALIASES),
        'dept_folder_code': user_department_folder_code(user) or '',
        'drive_letter': 'Z',
        'has_rustdesk': bool(rustdesk_cfg.get('enroll_secret') and rustdesk_cfg.get('public_key')),
        'has_equipment_scan': bool(equipment_cfg.get('scan_secret')),
    }


def _build_rustdesk_ps1(user) -> bytes | None:
    cfg = {**rustdesk_script_config(), **rustdesk_downloader_fields(user)}
    if not cfg.get('enroll_secret') or not cfg.get('public_key'):
        return None
    ps1_path = Path(settings.BASE_DIR) / 'scripts' / 'JustPlay-RustDesk-Setup.ps1'
    if not ps1_path.is_file():
        return None
    body = apply_rustdesk_script_tokens(ps1_path.read_text(encoding='utf-8-sig'), cfg)
    return _prepare_ps1(body)


def _build_equipment_scan_ps1(user) -> bytes | None:
    cfg = {**equipment_script_config(), **equipment_downloader_fields(user)}
    if not cfg.get('scan_secret'):
        return None
    ps1_path = Path(settings.BASE_DIR) / 'scripts' / 'JustPlay-Equipment-Scan.ps1'
    if not ps1_path.is_file():
        return None
    body = apply_equipment_script_tokens(ps1_path.read_text(encoding='utf-8-sig'), cfg)
    return _prepare_ps1(body)


def _personalize_ps1(body: str, bundle: dict) -> str:
    replacements = {
        '__NAS_SERVER__': str(bundle['server']),
        '__NAS_PORT__': str(bundle['webdav_port']),
        '__NAS_WEBDAV_PORT__': str(bundle['webdav_port']),
        '__NAS_SMB_PORT__': str(bundle.get('smb_port', 445)),
        '__NAS_FALLBACK_SERVER__': str(bundle.get('fallback_server', '')),
        '__NAS_LDAP_DOMAIN__': str(bundle['ldap_domain']),
        '__PORTAL_PASSWORD_URL__': str(bundle['portal_password_url']),
        '__PORTAL_USERNAME__': str(bundle['portal_username']),
        '__NAS_SHARES__': ','.join(bundle['shares']),
        '__NAS_PRIMARY_SHARE__': str(bundle.get('primary_share', '') or (bundle['shares'][0] if bundle['shares'] else '')),
        '__NAS_DEPT_CODE__': str(bundle['dept_folder_code']),
        '__NAS_DRIVE_LETTER__': str(bundle['drive_letter']),
    }
    for key, value in replacements.items():
        body = body.replace(key, value)
    return body


@login_required
@require_GET
def nas_download_setup(request):
    if not user_can_nas_download(request.user):
        return _download_forbidden(request)

    base = Path(settings.BASE_DIR) / 'scripts'
    ps1_path = base / 'JustPlay-NAS-RaiDrive-Setup.ps1'
    prep_path = base / 'Prepare-JustPlay-WebClient.ps1'
    exe_path = base / 'Ket-Noi-NAS-JustPlay.exe'
    mo_ps1_path = base / 'Mo-Ket-Noi-NAS.ps1'
    mo_bat_path = base / 'Chay-Ket-Noi-NAS.bat'
    if (
        not ps1_path.is_file()
        or not prep_path.is_file()
        or not exe_path.is_file()
        or not mo_ps1_path.is_file()
        or not mo_bat_path.is_file()
    ):
        return HttpResponse(
            'Không tìm thấy script cài NAS trên server.',
            status=404,
            content_type='text/plain; charset=utf-8',
        )

    cfg = nas_download_config()
    bundle = nas_user_bundle_config(request, request.user, cfg)
    ps1_body = _personalize_ps1(ps1_path.read_text(encoding='utf-8-sig'), bundle)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            'Ket-Noi-NAS-JustPlay.exe',
            exe_path.read_bytes(),
        )
        archive.writestr(
            'JustPlay-NAS-RaiDrive-Setup.ps1',
            _prepare_ps1(ps1_body),
        )
        archive.writestr(
            'Prepare-JustPlay-WebClient.ps1',
            _prepare_ps1(prep_path.read_text(encoding='utf-8-sig')),
        )
        archive.writestr(
            'JustPlay-NAS-Config.json',
            json.dumps(bundle, ensure_ascii=False, indent=2).encode('utf-8'),
        )
        archive.writestr(
            'Mo-Ket-Noi-NAS.ps1',
            _prepare_ps1(mo_ps1_path.read_text(encoding='utf-8-sig')),
        )
        archive.writestr(
            'Chay-Ket-Noi-NAS.bat',
            _prepare_bat(mo_bat_path.read_text(encoding='utf-8-sig')),
        )
        rustdesk_ps1 = _build_rustdesk_ps1(request.user)
        if rustdesk_ps1:
            archive.writestr('JustPlay-RustDesk-Setup.ps1', rustdesk_ps1)
        equipment_ps1 = _build_equipment_scan_ps1(request.user)
        if equipment_ps1:
            archive.writestr('JustPlay-Equipment-Scan.ps1', equipment_ps1)

    response = HttpResponse(buf.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="JustPlay-NAS-RaiDrive-Setup.zip"'
    return response
