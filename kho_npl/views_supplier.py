import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL

from kho_npl.forms import SupplierQuickCreateForm
from kho_npl.supplier_search import search_suppliers, supplier_select_label


@module_perm_required(MODULE_KHO_NPL, 'view')
def supplier_search(request):
    q = (request.GET.get('q') or '').strip()
    return JsonResponse({'results': search_suppliers(q)})


@module_perm_required_methods(MODULE_KHO_NPL, post='create')
@require_POST
def supplier_quick_create(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        payload = request.POST

    form = SupplierQuickCreateForm(payload)
    if not form.is_valid():
        return JsonResponse({'ok': False, 'errors': form.errors}, status=400)

    supplier = form.save()
    return JsonResponse({
        'ok': True,
        'supplier': {
            'id': supplier.pk,
            'text': supplier_select_label(supplier),
            'name': supplier.name,
            'code': supplier.code,
            'phone': supplier.phone or '',
        },
    })
