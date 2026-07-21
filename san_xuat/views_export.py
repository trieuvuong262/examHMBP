"""Views xuất Excel danh sách Sản xuất."""

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_SAN_XUAT
from san_xuat.list_exports import LIST_EXPORT_REGISTRY, run_list_export


@module_perm_required(MODULE_SAN_XUAT, 'export')
def list_export(request, export_key: str):
    from django.contrib import messages
    from django.shortcuts import redirect

    if export_key not in LIST_EXPORT_REGISTRY:
        messages.error(request, 'Không tìm thấy mẫu xuất Excel.')
        return redirect('san_xuat:overview')
    return run_list_export(request, export_key)
