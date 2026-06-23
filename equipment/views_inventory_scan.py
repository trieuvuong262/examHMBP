import io
import json
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from equipment.services.inventory_scan import (
    create_device_from_scan,
    device_exists_for_mac,
    downloader_script_fields,
    normalize_mac,
    scan_secret_ok,
    script_config,
)
from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_DOCUMENTS

_SCRIPT_TOKENS = (
    '__PORTAL_URL__',
    '__SCAN_SECRET__',
    '__ASSIGNED_USER_TEXT__',
    '__DEPARTMENT_TEXT__',
)


def _is_windows_request(request) -> bool:
    ua = (request.META.get('HTTP_USER_AGENT') or '').lower()
    return 'windows' in ua


def _escape_ps1_literal(value: str) -> str:
    return (value or '').replace("'", "''")


def _escape_bash_single_quoted(value: str) -> str:
    return (value or '').replace("'", "'\"'\"'")


def _apply_script_tokens(body: str, cfg: dict, *, bash: bool = False) -> str:
    esc = _escape_bash_single_quoted if bash else _escape_ps1_literal
    replacements = {
        '__PORTAL_URL__': cfg['portal_url'],
        '__SCAN_SECRET__': cfg['scan_secret'],
        '__ASSIGNED_USER_TEXT__': esc(cfg.get('assigned_user_text', '')),
        '__DEPARTMENT_TEXT__': esc(cfg.get('department_text', '')),
    }
    for token in _SCRIPT_TOKENS:
        body = body.replace(token, replacements.get(token) or '')
    return body


def _prepare_ps1(body: str) -> str:
    if not body.startswith('\ufeff'):
        body = '\ufeff' + body
    return body.replace('\r\n', '\n').replace('\n', '\r\n')


def _to_crlf(text: str) -> str:
    return text.replace('\r\n', '\n').replace('\n', '\r\n')


@login_required
@require_GET
def equipment_scan_page(request):
    if not user_can_access_menu(request.user, MODULE_DOCUMENTS, 'equipment_scan'):
        return _download_forbidden(request)
    cfg = script_config()
    platform = request.GET.get('os', '').lower()
    if platform not in ('win', 'linux'):
        platform = 'win' if _is_windows_request(request) else 'linux'
    return render(request, 'documents/equipment_scan_config.html', {
        'config': cfg,
        'platform': platform,
    })


def _download_forbidden(request):
    from assessment.decorators import portal_admin_denied_message
    from django.contrib import messages

    messages.error(request, portal_admin_denied_message())
    return redirect('home_portal')


@login_required
@require_GET
def equipment_scan_download(request):
    if not user_can_access_menu(request.user, MODULE_DOCUMENTS, 'equipment_scan'):
        return _download_forbidden(request)

    cfg = {**script_config(), **downloader_script_fields(request.user)}
    if not cfg['scan_secret']:
        return HttpResponse(
            'Thiếu EQUIPMENT_SCAN_SECRET (hoặc RUSTDESK_ENROLL_SECRET) trong cấu hình Portal.',
            status=503,
            content_type='text/plain; charset=utf-8',
        )

    platform = request.GET.get('os', '').lower()
    if platform not in ('win', 'linux'):
        platform = 'win' if _is_windows_request(request) else 'linux'

    base = Path(settings.BASE_DIR) / 'scripts'
    if platform == 'linux':
        template_path = base / 'JustPlay-Equipment-Scan.sh'
        if not template_path.is_file():
            return HttpResponse('Không tìm thấy script Linux.', status=404, content_type='text/plain')
        body = _apply_script_tokens(template_path.read_text(encoding='utf-8'), cfg, bash=True)
        body = body.replace('\r\n', '\n')
        response = HttpResponse(body, content_type='application/x-sh; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="JustPlay-Equipment-Scan.sh"'
        return response

    cmd_path = base / 'JustPlay-Equipment-Scan.cmd'
    ps1_path = base / 'JustPlay-Equipment-Scan.ps1'
    if not cmd_path.is_file() or not ps1_path.is_file():
        return HttpResponse('Không tìm thấy script Windows.', status=404, content_type='text/plain')

    cmd_body = _to_crlf(_apply_script_tokens(cmd_path.read_text(encoding='utf-8'), cfg))
    ps1_body = _prepare_ps1(_apply_script_tokens(ps1_path.read_text(encoding='utf-8'), cfg))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('JustPlay-Equipment-Scan.cmd', cmd_body)
        archive.writestr('JustPlay-Equipment-Scan.ps1', ps1_body)
    response = HttpResponse(buf.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="JustPlay-Equipment-Scan-win.zip"'
    return response


def _parse_json_body(request) -> dict:
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError('JSON không hợp lệ') from exc


@csrf_exempt
@require_http_methods(['POST'])
def equipment_scan_check_api(request):
    try:
        data = _parse_json_body(request)
    except ValueError as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)

    secret = (data.get('scan_secret') or data.get('enroll_secret') or data.get('api_secret') or '').strip()
    if not scan_secret_ok(secret):
        return JsonResponse({'status': 'error', 'message': 'Sai scan secret'}, status=403)

    try:
        mac = normalize_mac(data.get('mac_address') or data.get('mac') or '')
    except ValueError as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)

    from equipment.models import Device

    device = Device.objects.filter(mac_address=mac).first()
    return JsonResponse({
        'status': 'success',
        'exists': bool(device),
        'mac_address': mac,
        'device_code': device.device_code if device else '',
        'device_id': str(device.pk) if device else '',
    })


@csrf_exempt
@require_http_methods(['POST'])
def equipment_scan_submit_api(request):
    try:
        data = _parse_json_body(request)
    except ValueError as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)

    secret = (data.get('scan_secret') or data.get('enroll_secret') or data.get('api_secret') or '').strip()
    if not scan_secret_ok(secret):
        return JsonResponse({'status': 'error', 'message': 'Sai scan secret'}, status=403)

    try:
        mac = normalize_mac(data.get('mac_address') or data.get('mac') or '')
    except ValueError as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)

    if device_exists_for_mac(mac):
        from equipment.models import Device

        device = Device.objects.filter(mac_address=mac).first()
        return JsonResponse({
            'status': 'skipped',
            'message': 'MAC đã có trên Portal',
            'exists': True,
            'mac_address': mac,
            'device_code': device.device_code if device else '',
            'device_id': str(device.pk) if device else '',
        })

    try:
        device, created = create_device_from_scan(data=data)
    except ValueError as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=500)

    return JsonResponse({
        'status': 'success',
        'created': created,
        'mac_address': mac,
        'device_code': device.device_code,
        'device_id': str(device.pk),
        'name': device.name,
    })
