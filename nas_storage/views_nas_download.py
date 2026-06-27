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

from nas_storage.download_shares import WEBDAV_SHARE_ALIASES, nas_webdav_shares_for_user
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
    shares = nas_shares_for_user(user)
    primary = shares[0] if shares else ''
    return {
        'bundle_version': 3,
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
    }


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
    launcher_path = base / 'Chay-Ket-Noi-NAS.ps1'
    bat_path = base / 'JustPlay-NAS-RaiDrive-Setup.bat'
    cmd_path = base / 'JustPlay-NAS-RaiDrive-Setup.cmd'
    if (
        not bat_path.is_file()
        or not ps1_path.is_file()
        or not prep_path.is_file()
        or not launcher_path.is_file()
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
            'Chay-Ket-Noi-NAS.ps1',
            _prepare_ps1(launcher_path.read_text(encoding='utf-8-sig')),
        )
        archive.writestr(
            'JustPlay-NAS-RaiDrive-Setup.bat',
            _prepare_bat(bat_path.read_text(encoding='utf-8')),
        )
        if cmd_path.is_file():
            archive.writestr(
                'JustPlay-NAS-RaiDrive-Setup.cmd',
                _prepare_bat(cmd_path.read_text(encoding='utf-8')),
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
        share_line = ', '.join(
            f"{chr(ord('Z') - i)}: {name}"
            for i, name in enumerate(bundle['shares'])
        ) if bundle['shares'] else '(chưa xác định — liên hệ IT)'
        archive.writestr(
            'HUONG-DAN.txt',
            _prepare_bat(
                'JustPlay NAS - Ket noi WebDAV tu dong\r\n'
                '\r\n'
                'NEU WINDOWS CHAN FILE .BAT (SmartScreen / Mark of the Web):\r\n'
                '  Cach 1 (khuyen dung): Chuot phai Chay-Ket-Noi-NAS.ps1 -> Run with PowerShell\r\n'
                '  Cach 2: Chuot phai file ZIP -> Thuoc tinh -> Bo chan (Unblock) -> OK -> giai nen lai\r\n'
                '  Cach 3: Double-click JustPlay-NAS-RaiDrive-Setup.cmd (neu .bat bi chan)\r\n'
                '\r\n'
                'CAC BUOC:\r\n'
                '1. Giai nen file ZIP (giu nguyen tat ca file cung thu muc)\r\n'
                '2. Chuot phai Chay-Ket-Noi-NAS.ps1 -> Run with PowerShell (chap nhan UAC neu duoc hoi)\r\n'
                '   KHONG chon Run as administrator\r\n'
                '3. Nhap ten dang nhap va mat khau Portal\r\n'
                f'4. He thong tu gan moi share mot o dia: {share_line}\r\n'
                f'5. WebDAV: https://{cfg["server"]}:{cfg["webdav_port"]}/<share>\r\n'
                '\r\n'
                'File trong ZIP:\r\n'
                '- Chay-Ket-Noi-NAS.ps1 (chay file nay neu Windows chan .bat)\r\n'
                '- JustPlay-NAS-RaiDrive-Setup.bat\r\n'
                '- JustPlay-NAS-RaiDrive-Setup.cmd\r\n'
                '- JustPlay-NAS-RaiDrive-Setup.ps1\r\n'
                '- Prepare-JustPlay-WebClient.ps1\r\n'
                '- JustPlay-NAS-Config.json\r\n'
                '- HUONG-DAN.txt\r\n'
            ),
        )

    response = HttpResponse(buf.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="JustPlay-NAS-RaiDrive-Setup.zip"'
    return response
