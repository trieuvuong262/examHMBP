import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from assessment.decorators import module_perm_required
from audit.services.nas_monitor import collect_nas_metrics
from hrm.module_permissions import MODULE_AUDIT


@module_perm_required(MODULE_AUDIT, 'view')
@require_GET
def nas_monitor_page(request):
    try:
        metrics = collect_nas_metrics()
    except Exception as exc:
        metrics = {
            'hostname': None,
            'rclone_available': False,
            'mount_available': False,
            'dsm_available': False,
            'error': str(exc),
            'ram': {},
            'cpu': {'percent': None},
            'disk': None,
            'volumes': [],
            'shares': [],
            'backup': {},
            'processes': [],
        }
    return render(request, 'audit/nas_monitor.html', {
        'metrics': metrics,
        'metrics_json': json.dumps(metrics, ensure_ascii=False),
    })


@module_perm_required(MODULE_AUDIT, 'view')
@require_GET
def nas_monitor_metrics_api(request):
    try:
        metrics = collect_nas_metrics()
    except Exception as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=500)
    return JsonResponse({'status': 'success', 'metrics': metrics})
