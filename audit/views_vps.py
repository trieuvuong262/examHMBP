import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from assessment.decorators import module_perm_required
from audit.services.vps_monitor import (
    VpsMonitorError,
    collect_vps_metrics,
    list_optimize_actions,
    run_optimize_action,
)
from hrm.menu_permissions import user_can_update_menu
from hrm.module_permissions import MODULE_AUDIT


def _can_optimize(user) -> bool:
    return user_can_update_menu(user, MODULE_AUDIT, 'vps_monitor')


@module_perm_required(MODULE_AUDIT, 'view')
@require_GET
def vps_monitor_page(request):
    try:
        metrics = collect_vps_metrics()
    except Exception as exc:
        metrics = {
            'scope': 'unknown',
            'host_monitoring': False,
            'docker_available': False,
            'error': str(exc),
            'ram': {},
            'cpu': {},
            'disk': None,
            'docker': {'containers': [], 'summary': {}},
        }
    return render(request, 'audit/vps_monitor.html', {
        'metrics': metrics,
        'metrics_json': json.dumps(metrics, ensure_ascii=False),
        'can_optimize': _can_optimize(request.user),
        'optimize_actions': list_optimize_actions(),
    })


@module_perm_required(MODULE_AUDIT, 'view')
@require_GET
def vps_monitor_metrics_api(request):
    try:
        metrics = collect_vps_metrics()
    except Exception as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=500)
    return JsonResponse({'status': 'success', 'metrics': metrics})


@module_perm_required(MODULE_AUDIT, 'view')
@require_POST
def vps_monitor_optimize(request):
    if not _can_optimize(request.user):
        messages.error(request, 'Bạn không có quyền chạy tối ưu VPS.')
        return redirect('audit:vps_monitor')

    action_id = (request.POST.get('action') or '').strip()
    try:
        result = run_optimize_action(action_id)
    except VpsMonitorError as exc:
        messages.error(request, str(exc))
        return redirect('audit:vps_monitor')

    messages.success(request, result.get('message', 'Đã chạy tối ưu.'))
    return redirect('audit:vps_monitor')
