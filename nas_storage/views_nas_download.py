"""Trang Tải bộ cài — Công cụ IT (RustDesk + quét thiết bị + RaiDrive)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from audit.services.rustdesk_enroll import downloader_script_fields as rustdesk_downloader_fields
from audit.services.rustdesk_enroll import script_config as rustdesk_script_config
from audit.views_rustdesk_setup import _apply_script_tokens as apply_rustdesk_script_tokens
from equipment.services.inventory_scan import downloader_script_fields as equipment_downloader_fields
from equipment.services.inventory_scan import script_config as equipment_script_config
from equipment.views_inventory_scan import _apply_script_tokens as apply_equipment_script_tokens
from nas_storage.download_shares import WEBDAV_SHARE_ALIASES, nas_webdav_shares_for_user, resolve_webdav_share_name
from nas_storage.nas_download_access import raidrive_installer_context, user_can_nas_download
from nas_storage.nas_paths import NasPathError, user_department_folder_code
from nas_storage.share_access import get_active_share, resolve_path_for_request
from hrm.menu_permissions import menu_perm_context
from hrm.module_permissions import MODULE_DOCUMENTS


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
    messages.error(request, 'Bạn không có quyền tải bộ cài.')
    return redirect('documents:browse')


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
    """Giữ helper cũ cho code/test gọi lại (ZIP hiện không mount NAS)."""
    if not shares:
        return []
    dept_share = _dept_webdav_share_for_user(user)
    if not dept_share or dept_share not in shares:
        return list(shares)
    return [dept_share] + [name for name in shares if name != dept_share]


def _raidrive_installer_context(request) -> dict:
    return raidrive_installer_context(request)


def _escape_bash_single_quoted(value: str) -> str:
    return (value or '').replace("'", "'\"'\"'")


def _apply_raidrive_linux_tokens(body: str) -> str:
    url = getattr(settings, 'NAS_RAIDRIVE_INSTALLER_URL_LINUX', '').strip()
    return body.replace('__RAIDRIVE_INSTALLER_URL_LINUX__', _escape_bash_single_quoted(url))


def _build_raidrive_ubuntu_sh() -> bytes | None:
    sh_path = Path(settings.BASE_DIR) / 'scripts' / 'JustPlay-RaiDrive-Setup.sh'
    if not sh_path.is_file():
        return None
    body = _apply_raidrive_linux_tokens(sh_path.read_text(encoding='utf-8'))
    body = body.replace('\r\n', '\n')
    if not body.endswith('\n'):
        body += '\n'
    return body.encode('utf-8')


@login_required
@require_GET
def nas_raidrive_download(request):
    """Tải installer RaiDrive — Windows (.exe từ NAS) hoặc Ubuntu (.sh)."""
    if not user_can_nas_download(request.user):
        return _download_forbidden(request)

    platform = (request.GET.get('os') or 'win').lower()
    if platform in ('linux', 'ubuntu'):
        data = _build_raidrive_ubuntu_sh()
        if not data:
            messages.error(request, 'Không tìm thấy script cài RaiDrive Ubuntu.')
            return redirect('documents:nas_download')
        response = HttpResponse(data, content_type='application/x-sh; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="JustPlay-RaiDrive-Setup.sh"'
        return response

    token = getattr(settings, 'NAS_RAIDRIVE_INSTALLER_SHARE_TOKEN', '').strip()
    if not token:
        messages.error(request, 'Chưa cấu hình installer RaiDrive trên server.')
        return redirect('documents:nas_download')

    share = get_active_share(token)
    if share:
        try:
            path = resolve_path_for_request(request.user, share.rel_path, share=share)
        except NasPathError as exc:
            messages.error(request, str(exc))
            path = None
        if path and path.is_file():
            filename = share.item_name or 'RaiDrive_x64.exe'
            response = HttpResponse(path.read_bytes(), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

    exe_path = Path(settings.BASE_DIR) / 'scripts' / 'installers' / 'RaiDrive_x64.exe'
    if exe_path.is_file():
        response = HttpResponse(exe_path.read_bytes(), content_type='application/octet-stream')
        response['Content-Disposition'] = 'attachment; filename="RaiDrive_x64.exe"'
        return response

    messages.error(request, 'Không tìm thấy file cài RaiDrive. Liên hệ IT.')
    return redirect('documents:nas_download')


@login_required
@require_GET
def nas_download_page(request):
    if not user_can_nas_download(request.user):
        return _download_forbidden(request)
    bundle = nas_user_bundle_config(request, request.user, nas_download_config())
    rd_ctx = _raidrive_installer_context(request)
    return render(request, 'nas_storage/nas_download.html', {
        **menu_perm_context(request.user, MODULE_DOCUMENTS, 'nas_download'),
        **rd_ctx,
        'bundle': bundle,
        'has_it_tools': bundle.get('has_rustdesk') or bundle.get('has_equipment_scan'),
        'raidrive_linux_url': request.build_absolute_uri(
            reverse('documents:raidrive_download') + '?os=linux'
        ),
    })


def _prepare_ps1(body: str) -> bytes:
    if not body.startswith('\ufeff'):
        body = '\ufeff' + body
    body = body.replace('\r\n', '\n').replace('\n', '\r\n')
    return body.encode('utf-8')


def _prepare_bat(body: str) -> bytes:
    return body.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')


def nas_user_bundle_config(request, user, cfg: dict) -> dict:
    portal_base = request.build_absolute_uri('/').rstrip('/')
    rustdesk_cfg = {**rustdesk_script_config(), **rustdesk_downloader_fields(user)}
    equipment_cfg = {**equipment_script_config(), **equipment_downloader_fields(user)}
    rd_ctx = raidrive_installer_context(request)
    raidrive_win_url = rd_ctx.get('raidrive_share_url') or ''
    try:
        raidrive_linux_url = request.build_absolute_uri(
            reverse('documents:raidrive_download') + '?os=linux'
        )
    except Exception:
        raidrive_linux_url = ''
    return {
        'bundle_version': 6,
        'bundle_kind': 'it_tools',
        'portal_password_url': f'{portal_base}/accounts/password/change/',
        'portal_username': user.username,
        'dept_folder_code': user_department_folder_code(user) or '',
        'has_rustdesk': bool(rustdesk_cfg.get('enroll_secret') and rustdesk_cfg.get('public_key')),
        'has_equipment_scan': bool(equipment_cfg.get('scan_secret')),
        'has_raidrive': bool(raidrive_win_url) or bool(_build_raidrive_ubuntu_sh()),
        'raidrive_download_url': raidrive_win_url,
        'raidrive_linux_download_url': raidrive_linux_url,
        'raidrive_linux_page': getattr(
            settings,
            'NAS_RAIDRIVE_LINUX_DOWNLOAD_PAGE',
            'https://www.raidrive.com/download/linux',
        ),
        'server': cfg.get('server', ''),
        'webdav_port': cfg.get('webdav_port', 5678),
        'smb_port': cfg.get('smb_port', 445),
        'port': cfg.get('webdav_port', 5678),
        'fallback_server': cfg.get('fallback_server', ''),
        'ldap_domain': cfg.get('ldap_domain', ''),
        'shares': [],
        'primary_share': '',
        'webdav_share_aliases': dict(WEBDAV_SHARE_ALIASES),
        'drive_letter': 'Z',
        'script_version': '',
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


def _build_rustdesk_ubuntu_sh(user) -> bytes | None:
    """Script cài Ubuntu 26.04 — token bash; không đụng file Windows .ps1."""
    cfg = {**rustdesk_script_config(), **rustdesk_downloader_fields(user)}
    if not cfg.get('enroll_secret') or not cfg.get('public_key'):
        return None
    sh_path = Path(settings.BASE_DIR) / 'scripts' / 'JustPlay-RustDesk-Setup.sh'
    if not sh_path.is_file():
        return None
    body = apply_rustdesk_script_tokens(
        sh_path.read_text(encoding='utf-8'),
        cfg,
        bash=True,
    )
    body = body.replace('\r\n', '\n')
    if not body.endswith('\n'):
        body += '\n'
    return body.encode('utf-8')


def _build_equipment_scan_ps1(user) -> bytes | None:
    cfg = {**equipment_script_config(), **equipment_downloader_fields(user)}
    if not cfg.get('scan_secret'):
        return None
    ps1_path = Path(settings.BASE_DIR) / 'scripts' / 'JustPlay-Equipment-Scan.ps1'
    if not ps1_path.is_file():
        return None
    body = apply_equipment_script_tokens(ps1_path.read_text(encoding='utf-8-sig'), cfg)
    return _prepare_ps1(body)


def _build_equipment_scan_ubuntu_sh(user) -> bytes | None:
    """Script quét cấu hình máy Ubuntu — không đụng file Windows .ps1."""
    cfg = {**equipment_script_config(), **equipment_downloader_fields(user)}
    if not cfg.get('scan_secret'):
        return None
    sh_path = Path(settings.BASE_DIR) / 'scripts' / 'JustPlay-Equipment-Scan.sh'
    if not sh_path.is_file():
        return None
    body = apply_equipment_script_tokens(
        sh_path.read_text(encoding='utf-8'),
        cfg,
        bash=True,
    )
    body = body.replace('\r\n', '\n')
    if not body.endswith('\n'):
        body += '\n'
    return body.encode('utf-8')


def _personalize_ps1(body: str, bundle: dict) -> str:
    """Giữ API cũ cho test/import; ZIP IT tools không dùng nữa."""
    replacements = {
        '__NAS_SERVER__': str(bundle.get('server', '')),
        '__NAS_PORT__': str(bundle.get('webdav_port', '')),
        '__NAS_WEBDAV_PORT__': str(bundle.get('webdav_port', '')),
        '__NAS_SMB_PORT__': str(bundle.get('smb_port', 445)),
        '__NAS_FALLBACK_SERVER__': str(bundle.get('fallback_server', '')),
        '__NAS_LDAP_DOMAIN__': str(bundle.get('ldap_domain', '')),
        '__PORTAL_PASSWORD_URL__': str(bundle.get('portal_password_url', '')),
        '__PORTAL_USERNAME__': str(bundle.get('portal_username', '')),
        '__NAS_SHARES__': ','.join(bundle.get('shares') or []),
        '__NAS_PRIMARY_SHARE__': str(bundle.get('primary_share', '')),
        '__NAS_DEPT_CODE__': str(bundle.get('dept_folder_code', '')),
        '__NAS_DRIVE_LETTER__': str(bundle.get('drive_letter', 'Z')),
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
    exe_path = base / 'Ket-Noi-NAS-JustPlay.exe'
    mo_ps1_path = base / 'Mo-Ket-Noi-NAS.ps1'
    mo_bat_path = base / 'Chay-Ket-Noi-NAS.bat'
    ket_noi_bat_path = base / 'KET-NOI-NAS.bat'
    if (
        not exe_path.is_file()
        or not mo_ps1_path.is_file()
        or not mo_bat_path.is_file()
        or not ket_noi_bat_path.is_file()
    ):
        return HttpResponse(
            'Không tìm thấy launcher Công cụ IT trên server.',
            status=404,
            content_type='text/plain; charset=utf-8',
        )

    cfg = nas_download_config()
    bundle = nas_user_bundle_config(request, request.user, cfg)
    rustdesk_ps1 = _build_rustdesk_ps1(request.user)
    rustdesk_ubuntu_sh = _build_rustdesk_ubuntu_sh(request.user)
    equipment_ps1 = _build_equipment_scan_ps1(request.user)
    equipment_ubuntu_sh = _build_equipment_scan_ubuntu_sh(request.user)
    raidrive_ubuntu_sh = _build_raidrive_ubuntu_sh()
    if (
        not rustdesk_ps1
        and not rustdesk_ubuntu_sh
        and not equipment_ps1
        and not equipment_ubuntu_sh
        and not raidrive_ubuntu_sh
    ):
        return HttpResponse(
            'Chưa cấu hình RustDesk / quét thiết bị / RaiDrive trên Portal. Liên hệ IT.',
            status=404,
            content_type='text/plain; charset=utf-8',
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('Ket-Noi-NAS-JustPlay.exe', exe_path.read_bytes())
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
        archive.writestr(
            'KET-NOI-NAS.bat',
            _prepare_bat(ket_noi_bat_path.read_text(encoding='utf-8-sig')),
        )
        if rustdesk_ps1:
            archive.writestr('JustPlay-RustDesk-Setup.ps1', rustdesk_ps1)
        if rustdesk_ubuntu_sh:
            archive.writestr('JustPlay-RustDesk-Setup.sh', rustdesk_ubuntu_sh)
        if equipment_ps1:
            archive.writestr('JustPlay-Equipment-Scan.ps1', equipment_ps1)
        if equipment_ubuntu_sh:
            archive.writestr('JustPlay-Equipment-Scan.sh', equipment_ubuntu_sh)
        if raidrive_ubuntu_sh:
            archive.writestr('JustPlay-RaiDrive-Setup.sh', raidrive_ubuntu_sh)

    response = HttpResponse(buf.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="JustPlay-Cong-Cu-IT.zip"'
    return response
