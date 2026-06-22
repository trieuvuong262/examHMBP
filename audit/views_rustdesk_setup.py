import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from assessment.decorators import module_perm_required
from audit.services.rustdesk_enroll import enroll_secret_ok, script_config, upsert_rustdesk_host
from hrm.module_permissions import MODULE_AUDIT


def _is_windows_request(request) -> bool:
    ua = (request.META.get('HTTP_USER_AGENT') or '').lower()
    return 'windows' in ua


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
    if not cfg['enroll_secret'] or not cfg['public_key']:
        return HttpResponse(
            'Thiếu RUSTDESK_ENROLL_SECRET hoặc RUSTDESK_PUBLIC_KEY trong cấu hình Portal.',
            status=503,
            content_type='text/plain; charset=utf-8',
        )

    platform = request.GET.get('os', '').lower()
    if platform not in ('win', 'linux'):
        platform = 'win' if _is_windows_request(request) else 'linux'

    from pathlib import Path

    base = Path(settings.BASE_DIR) / 'scripts'
    if platform == 'linux':
        template_path = base / 'JustPlay-RustDesk-Setup.sh'
        filename = 'JustPlay-RustDesk-Setup.sh'
        content_type = 'application/x-sh'
    else:
        template_path = base / 'JustPlay-RustDesk-Setup.cmd'
        filename = 'JustPlay-RustDesk-Setup.cmd'
        content_type = 'application/octet-stream'

    if not template_path.is_file():
        return HttpResponse('Không tìm thấy file cài đặt.', status=404, content_type='text/plain')

    body = template_path.read_text(encoding='utf-8')
    replacements = {
        '__PORTAL_URL__': cfg['portal_url'],
        '__RUSTDESK_HOST__': cfg['rustdesk_host'],
        '__PUBLIC_KEY__': cfg['public_key'],
        '__CLIENT_PASSWORD__': cfg['client_password'],
        '__ENROLL_SECRET__': cfg['enroll_secret'],
        '__INSTALLER_URL_WIN__': cfg['installer_url_win'],
        '__INSTALLER_URL_LINUX__': cfg['installer_url_linux'],
    }
    for token, value in replacements.items():
        body = body.replace(token, value or '')

    response = HttpResponse(body, content_type=f'{content_type}; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
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
