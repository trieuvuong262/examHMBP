"""Prefill phiếu xuất/chuyển từ màn tồn kho."""

from django.urls import reverse

from kho_npl.filter_utils import parse_int_ids
from kho_npl.models import Material, WarehouseLocation


def parse_doc_material_id(request) -> int | None:
    for key in ('material', 'material_id'):
        raw = (request.GET.get(key) or '').strip()
        if raw.isdigit():
            return int(raw)
    return None


def parse_doc_location_id(request, *keys: str) -> int | None:
    for key in keys:
        raw = (request.GET.get(key) or '').strip()
        if raw.isdigit():
            return int(raw)
    return None


def active_material_pk(material_id: int | None) -> int | None:
    if not material_id:
        return None
    if Material.objects.filter(pk=material_id, is_active=True).exists():
        return material_id
    return None


def active_location_pk(location_id: int | None) -> int | None:
    if not location_id:
        return None
    if WarehouseLocation.objects.filter(pk=location_id, is_active=True).exists():
        return location_id
    return None


def issue_line_prefill_initial(
    material_id: int | None,
    location_id: int | None = None,
) -> list[dict]:
    pk = active_material_pk(material_id)
    if not pk:
        return []
    line: dict = {'material': pk}
    loc_pk = active_location_pk(location_id)
    if loc_pk:
        line['location'] = loc_pk
    return [line]


def transfer_form_prefill_initial(from_location_id: int | None = None) -> dict:
    loc_pk = active_location_pk(from_location_id)
    return {'from_location': loc_pk} if loc_pk else {}


def transfer_line_prefill_initial(material_id: int | None) -> list[dict]:
    pk = active_material_pk(material_id)
    return [{'material': pk}] if pk else []


def stock_doc_prefill_location(request, row) -> int | None:
    location_ids = parse_int_ids(request, 'location')
    if len(location_ids) == 1:
        return active_location_pk(location_ids[0])
    balances = row.get('location_balances') or []
    if balances:
        top = max(balances, key=lambda item: item['quantity'])
        return top['location'].pk
    return None


def stock_doc_action_urls(material_pk: int, location_id: int | None = None) -> tuple[str, str]:
    loc_pk = active_location_pk(location_id)
    issue_params = [f'material={material_pk}']
    if loc_pk:
        issue_params.append(f'location={loc_pk}')
    issue_url = reverse('kho_npl:issue_create') + '?' + '&'.join(issue_params)

    transfer_params = ['tab=nhap', f'material={material_pk}']
    if loc_pk:
        transfer_params.append(f'from_location={loc_pk}')
    transfer_url = reverse('kho_npl:transfer_hub') + '?' + '&'.join(transfer_params)
    return issue_url, transfer_url
