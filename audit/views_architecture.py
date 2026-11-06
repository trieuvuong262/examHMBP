"""Read-only code architecture explorer for superusers."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from .architecture_service import build_architecture_map, model_mermaid


def _superuser_only(user):
    return bool(user and user.is_authenticated and user.is_superuser)


@login_required
def architecture_map(request):
    if not _superuser_only(request.user):
        raise PermissionDenied('Chỉ superuser được xem Quản lý code.')

    app_label = request.GET.get('app', '').strip()
    data = build_architecture_map(app_label)
    data['model_mermaid'] = model_mermaid(data['models'])
    data['selected_app'] = app_label
    return render(request, 'audit/architecture_map.html', {'architecture': data})
