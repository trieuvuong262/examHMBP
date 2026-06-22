import io
import json
import zipfile
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from assessment.decorators import module_perm_required
from audit.services.rustdesk_enroll import enroll_secret_ok, script_config, upsert_rustdesk_host
from hrm.module_permissions import MODULE_AUDIT

_SCRIPT_TOKENS = (
    '__PORTAL_URL__',
    '__RUSTDESK_HOST__',
    '__PUBLIC_KEY__',
    '__CLIENT_PASSWORD__',
    '__ENROLL_SECRET__',
    '__INSTALLER_URL_WIN__',
    '__INSTALLER_URL_LINUX__',
    '__RUSTDESK_APPROVE_MODE__',
)


def _is_windows_request(request) -> bool:
    ua = (request.META.get('HTTP_USER_AGENT') or '').lower()
    return 'windows' in ua


def _apply_script_tokens(body: str, cfg: dict) -> str:
    replacements = {
        '__PORTAL_URL__': cfg['portal_url'],
        '__RUSTDESK_HOST__': cfg['rustdesk_host'],
        '__PUBLIC_KEY__': cfg['public_key'],
        '__CLIENT_PASSWORD__': cfg['client_password'],
        '__ENROLL_SECRET__': cfg['enroll_secret'],
        '__INSTALLER_URL_WIN__': cfg['installer_url_win'],
        '__INSTALLER_URL_LINUX__': cfg['installer_url_linux'],
        '__RUSTDESK_APPROVE_MODE__': cfg['approve_mode'],
    }
    for token in _SCRIPT_TOKENS:
        body = body.replace(token, replacements.get(token) or '')
    return body


def _to_crlf(text: str) -> str:
    return text.replace('\r\n', '\n').replace('\n', '\r\n')


@module_perm_required(MODULE_AUDIT, 'view')
@require_GET
def rustdesk_install_page(request):
    cfg = script_config()
    platform = request.GET.get('os', '').lower()
    if platform not in ('win', 'linux'):
        platform = 'win' if _is_windows_request(request) else 'linux'
    return render(request, 'audit/rustdesk_install.html', {
        'config': cfg,
        'platform': platform,
        'rustdesk_public_host': cfg['rustdesk_host'],
    })


@module_perm_required(MODULE_AUDIT, 'view')
@require_GET
def rustdesk_download_setup(request):
    cfg = script_config()
    platform = request.GET.get('os', '').lower()
    if platform not in ('win', 'linux', 'it'):
        platform = 'win' if _is_windows_request(request) else 'linux'

    if platform == 'it':
        if not cfg['public_key']:
            return HttpResponse('Thiếu RUSTDESK_PUBLIC_KEY trong cấu hình Portal.', status=503, content_type='text/plain')
        base = Path(settings.BASE_DIR) / 'scripts'
        cmd_path = base / 'JustPlay-RustDesk-IT-Setup.cmd'
        ps1_path = base / 'JustPlay-RustDesk-IT-Setup.ps1'
        if not cmd_path.is_file() or not ps1_path.is_file():
            return HttpResponse('Không tìm thấy script IT.', status=404, content_type='text/plain')
        cmd_body = _to_crlf(_apply_script_tokens(cmd_path.read_text(encoding='utf-8'), cfg))
        ps1_body = _apply_script_tokens(ps1_path.read_text(encoding='utf-8'), cfg)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('JustPlay-RustDesk-IT-Setup.cmd', cmd_body)
            archive.writestr('JustPlay-RustDesk-IT-Setup.ps1', ps1_body)
        response = HttpResponse(buf.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="JustPlay-RustDesk-IT-Setup.zip"'
        return response

    if not cfg['enroll_secret'] or not cfg['public_key']:
        return HttpResponse(
            'Thiếu RUSTDESK_ENROLL_SECRET hoặc RUSTDESK_PUBLIC_KEY trong cấu hình Portal.',
            status=503,
            content_type='text/plain; charset=utf-8',
        )

    base = Path(settings.BASE_DIR) / 'scripts'
    if platform == 'linux':
        template_path = base / 'JustPlay-RustDesk-Setup.sh'
        if not template_path.is_file():
            return HttpResponse('Không tìm thấy file cài đặt.', status=404, content_type='text/plain')
        body = _apply_script_tokens(template_path.read_text(encoding='utf-8'), cfg)
        body = body.replace('\r\n', '\n')
        response = HttpResponse(body, content_type='application/x-sh; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="JustPlay-RustDesk-Setup.sh"'
        return response

    cmd_path = base / 'JustPlay-RustDesk-Setup.cmd'
    ps1_path = base / 'JustPlay-RustDesk-Setup.ps1'
    if not cmd_path.is_file() or not ps1_path.is_file():
        return HttpResponse('Không tìm thấy file cài đặt Windows.', status=404, content_type='text/plain')

    cmd_body = _to_crlf(_apply_script_tokens(cmd_path.read_text(encoding='utf-8'), cfg))
    ps1_body = _apply_script_tokens(ps1_path.read_text(encoding='utf-8'), cfg)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('JustPlay-RustDesk-Setup.cmd', cmd_body)
        archive.writestr('JustPlay-RustDesk-Setup.ps1', ps1_body)
    response = HttpResponse(buf.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="JustPlay-RustDesk-Setup-win.zip"'
    return response


@csrf_exempt
@require_http_methods(['POST'])
def rustdesk_enroll_api(request):
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'error', 'message': 'JSON không hợp lệ'}, status=400)

    secret = (data.get('enroll_secret') or data.get('api_secret') or '').strip()
    if not enroll_secret_ok(secret):
        return JsonResponse({'status': 'error', 'message': 'Sai enroll secret'}, status=403)

    try:
        host, created = upsert_rustdesk_host(data=data)
    except ValueError as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=500)

    return JsonResponse({
        'status': 'success',
        'created': created,
        'host_id': host.pk,
        'rustdesk_id': host.rustdesk_id,
        'name': host.name,
    })
