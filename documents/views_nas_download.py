"""Trang Thư viện — tải bộ cài RaiDrive / NAS (Windows)."""

from __future__ import annotations

import io
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


def nas_download_config() -> dict:
    return {
        'server': getattr(settings, 'NAS_RDRIVE_SERVER', 'justplay.synology.me').strip(),
        'port': int(getattr(settings, 'NAS_RDRIVE_PORT', 5678) or 5678),
        'ldap_domain': getattr(settings, 'NAS_LDAP_DOMAIN', 'ldap.justplay.local').strip(),
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
    return render(request, 'documents/nas_download_config.html', {'config': cfg})


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

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('JustPlay-NAS-RaiDrive-Setup.bat', bat_path.read_bytes())
        archive.writestr(
            'JustPlay-NAS-RaiDrive-Setup.ps1',
            ps1_path.read_text(encoding='utf-8').replace('\r\n', '\n').encode('utf-8'),
        )
        archive.writestr(
            'HUONG-DAN.txt',
            (
                'JustPlay NAS — RaiDrive\r\n'
                '1. Giai nen zip\r\n'
                '2. Chay JustPlay-NAS-RaiDrive-Setup.bat\r\n'
                '3. Nhap tai khoan / mat khau Portal khi duoc hoi\r\n'
                f'4. Server: {nas_download_config()["server"]}  Port: {nas_download_config()["port"]}\r\n'
            ).encode('utf-8'),
        )

    response = HttpResponse(buf.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="JustPlay-NAS-RaiDrive-Setup.zip"'
    return response
