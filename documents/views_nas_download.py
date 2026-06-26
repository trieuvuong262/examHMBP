"""Trang Thư viện — tải bộ cài RaiDrive / NAS (Windows)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from assessment.decorators import module_perm_required
from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_DOCUMENTS
from nas_storage.download_shares import nas_mount_shares_for_user
from nas_storage.nas_paths import user_department_folder_code


def nas_shares_for_user(user) -> list[str]:
    return nas_mount_shares_for_user(user)


def nas_download_config() -> dict:
    fallback = getattr(settings, 'NAS_RDRIVE_FALLBACK_SERVER', '').strip()
    if not fallback:
        fallback = getattr(settings, 'NAS_SSH_HOST', '').strip()
    smb_port = int(getattr(settings, 'NAS_SMB_PORT', 445) or 445)
    if smb_port == 5678:
        smb_port = 445
    return {
        'server': getattr(settings, 'NAS_RDRIVE_SERVER', 'justplay.synology.me').strip(),
        'port': smb_port,
        'webdav_port': int(getattr(settings, 'NAS_WEBDAV_PORT', 5678) or 5678),
        'ldap_domain': getattr(settings, 'NAS_LDAP_DOMAIN', 'ldap.justplay.local').strip(),
        'fallback_server': fallback,
    }


def _download_forbidden(request):
    from assessment.decorators import portal_admin_denied_message
    from django.contrib import messages

    messages.error(request, portal_admin_denied_message())
    return redirect('home_portal')


@login_required
@module_perm_required(MODULE_DOCUMENTS, 'view')
@require_GET
def nas_download_page(request):
    if not user_can_access_menu(request.user, MODULE_DOCUMENTS, 'nas_download'):
        return _download_forbidden(request)
    cfg = nas_download_config()
    return render(request, 'documents/nas_download_config.html', {
        'config': cfg,
        'user_shares': nas_shares_for_user(request.user),
    })


def _prepare_ps1(body: str) -> bytes:
    """UTF-8 BOM + CRLF — PowerShell 5.1 tren Windows."""
    if not body.startswith('\ufeff'):
        body = '\ufeff' + body
    body = body.replace('\r\n', '\n').replace('\n', '\r\n')
    return body.encode('utf-8')


def _prepare_bat(body: str) -> bytes:
    return body.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')


def nas_user_bundle_config(request, user, cfg: dict) -> dict:
    portal_base = request.build_absolute_uri('/').rstrip('/')
    return {
        'bundle_version': 1,
        'server': cfg['server'],
        'port': cfg['port'],
        'webdav_port': cfg.get('webdav_port', 5678),
        'fallback_server': cfg.get('fallback_server', ''),
        'ldap_domain': cfg['ldap_domain'],
        'portal_password_url': f'{portal_base}/accounts/password/change/',
        'portal_username': user.username,
        'shares': nas_shares_for_user(user),
        'dept_folder_code': user_department_folder_code(user) or '',
        'drive_letter': 'Z',
    }


def _personalize_ps1(body: str, bundle: dict) -> str:
    replacements = {
        '__NAS_SERVER__': str(bundle['server']),
        '__NAS_PORT__': str(bundle['port']),
        '__NAS_FALLBACK_SERVER__': str(bundle.get('fallback_server', '')),
        '__NAS_LDAP_DOMAIN__': str(bundle['ldap_domain']),
        '__PORTAL_PASSWORD_URL__': str(bundle['portal_password_url']),
        '__PORTAL_USERNAME__': str(bundle['portal_username']),
        '__NAS_SHARES__': ','.join(bundle['shares']),
        '__NAS_DEPT_CODE__': str(bundle['dept_folder_code']),
        '__NAS_DRIVE_LETTER__': str(bundle['drive_letter']),
    }
    for key, value in replacements.items():
        body = body.replace(key, value)
    return body


@login_required
@require_GET
def nas_download_setup(request):
    if not user_can_access_menu(request.user, MODULE_DOCUMENTS, 'nas_download'):
        return _download_forbidden(request)

    base = Path(settings.BASE_DIR) / 'scripts'
    bat_path = base / 'JustPlay-NAS-RaiDrive-Setup.bat'
    ps1_path = base / 'JustPlay-NAS-RaiDrive-Setup.ps1'
    if not bat_path.is_file() or not ps1_path.is_file():
        return HttpResponse(
            'Không tìm thấy script cài NAS trên server.',
            status=404,
            content_type='text/plain; charset=utf-8',
        )

    cfg = nas_download_config()
    bundle = nas_user_bundle_config(request, request.user, cfg)
    ps1_body = _personalize_ps1(ps1_path.read_text(encoding='utf-8'), bundle)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            'JustPlay-NAS-RaiDrive-Setup.bat',
            _prepare_bat(bat_path.read_text(encoding='utf-8')),
        )
        archive.writestr(
            'JustPlay-NAS-RaiDrive-Setup.ps1',
            _prepare_ps1(ps1_body),
        )
        archive.writestr(
            'JustPlay-NAS-Config.json',
            json.dumps(bundle, ensure_ascii=False, indent=2).encode('utf-8'),
        )
        share_line = bundle['shares'][0] if bundle['shares'] else '(chua xac dinh phong ban)'
        archive.writestr(
            'HUONG-DAN.txt',
            _prepare_bat(
                'JustPlay NAS - ket noi SMB tu dong\r\n'
                '1. Giai nen zip\r\n'
                '2. Chay JustPlay-NAS-RaiDrive-Setup.bat\r\n'
                '3. Nhap ten dang nhap va mat khau Portal\r\n'
                f'4. He thong tu gan o Z: (share {share_line}) - khong can RaiDrive\r\n'
                f'5. SMB cong {cfg["port"]} (5678 la WebDAV, khong dung cho map o)\r\n'
                + (
                    f'6. Server du phong: {cfg.get("fallback_server")}\r\n'
                    if cfg.get('fallback_server') else ''
                )
            ),
        )

    response = HttpResponse(buf.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="JustPlay-NAS-RaiDrive-Setup.zip"'
    return response
