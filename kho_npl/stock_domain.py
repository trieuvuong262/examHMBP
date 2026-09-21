"""Phân tách Kho NPL (phục vụ SX) và Kho vật tư (không phục vụ SX)."""

from __future__ import annotations

import contextvars

from django.db.models import Q

STOCK_DOMAIN_NPL = 'npl'
STOCK_DOMAIN_VAT_TU = 'vat_tu'
STOCK_DOMAIN_ALL = '*'

STOCK_DOMAIN_CHOICES = [
    (STOCK_DOMAIN_NPL, 'Kho nguyên phụ liệu'),
    (STOCK_DOMAIN_VAT_TU, 'Kho vật tư'),
]

NS_KHO_NPL = 'kho_npl'
NS_KHO_VAT_TU = 'kho_vat_tu'

MODULE_KHO_VAT_TU = 'kho_vat_tu'

_request_var: contextvars.ContextVar = contextvars.ContextVar('kho_stock_request', default=None)

DOMAIN_LABELS = {
    STOCK_DOMAIN_NPL: 'Kho NPL',
    STOCK_DOMAIN_VAT_TU: 'Kho vật tư',
}

ITEM_LABELS = {
    STOCK_DOMAIN_NPL: 'Nguyên phụ liệu',
    STOCK_DOMAIN_VAT_TU: 'Vật tư',
}

ITEM_LABELS_SHORT = {
    STOCK_DOMAIN_NPL: 'NPL',
    STOCK_DOMAIN_VAT_TU: 'VT',
}

VAT_TU_PATH_PREFIX = '/kho-vat-tu/'


def bind_request(request):
    return _request_var.set(request)


def reset_request(token) -> None:
    _request_var.reset(token)


def current_request():
    return _request_var.get()


def domain_from_path(path: str | None) -> str:
    normalized = path or ''
    if normalized.startswith(VAT_TU_PATH_PREFIX) or normalized == '/kho-vat-tu':
        return STOCK_DOMAIN_VAT_TU
    return STOCK_DOMAIN_NPL


def domain_from_request(request=None) -> str:
    req = request if request is not None else current_request()
    if req is None:
        return STOCK_DOMAIN_NPL
    cached = getattr(req, 'stock_domain', None)
    if cached in (STOCK_DOMAIN_NPL, STOCK_DOMAIN_VAT_TU):
        return cached
    return domain_from_path(getattr(req, 'path', '') or '')


def domain_from_current_request() -> str:
    return domain_from_request(None)


def is_vat_tu_domain(domain: str | None = None) -> bool:
    return (domain or domain_from_current_request()) == STOCK_DOMAIN_VAT_TU


def namespace_for_domain(domain: str) -> str:
    return NS_KHO_VAT_TU if domain == STOCK_DOMAIN_VAT_TU else NS_KHO_NPL


def namespace_from_request(request=None) -> str:
    req = request if request is not None else current_request()
    match = getattr(req, 'resolver_match', None) if req is not None else None
    ns = getattr(match, 'namespace', None) if match else None
    if ns in (NS_KHO_NPL, NS_KHO_VAT_TU):
        return ns
    return namespace_for_domain(domain_from_request(req))


def namespace_from_current_request() -> str:
    return namespace_from_request(None)


def module_key_for_domain(domain: str) -> str:
    from hrm.module_permissions import MODULE_KHO_NPL

    return MODULE_KHO_VAT_TU if domain == STOCK_DOMAIN_VAT_TU else MODULE_KHO_NPL


def module_key_from_request(request=None) -> str:
    return module_key_for_domain(domain_from_request(request))


def domain_label(domain: str | None = None) -> str:
    return DOMAIN_LABELS.get(domain or domain_from_current_request(), DOMAIN_LABELS[STOCK_DOMAIN_NPL])


def item_label(domain: str | None = None) -> str:
    return ITEM_LABELS.get(domain or domain_from_current_request(), ITEM_LABELS[STOCK_DOMAIN_NPL])


def item_label_short(domain: str | None = None) -> str:
    return ITEM_LABELS_SHORT.get(domain or domain_from_current_request(), ITEM_LABELS_SHORT[STOCK_DOMAIN_NPL])


def kind_label(domain: str | None = None) -> str:
    """Hậu tố menu/tiêu đề trang: NPL hoặc vật tư."""
    return 'vật tư' if (domain or domain_from_current_request()) == STOCK_DOMAIN_VAT_TU else 'NPL'


def location_domain_prefix(domain: str) -> str:
    return 'Vật tư' if domain == STOCK_DOMAIN_VAT_TU else 'NPL'


def materials_catalog_q(domain: str | None = None) -> Q:
    return Q(stock_domain=domain or domain_from_current_request())


def materials_visible_q(domain: str | None = None) -> Q:
    """Danh mục của kho + mã đang có tồn tại vị trí kho này (hàng chuyển sang)."""
    domain = domain or domain_from_current_request()
    return Q(stock_domain=domain) | Q(
        balances__location__stock_domain=domain,
        balances__quantity__gt=0,
    )


def docs_for_domain(qs, domain: str | None = None):
    domain = domain or domain_from_current_request()
    return qs.filter(stock_domain=domain)


def transfers_for_domain(qs, domain: str | None = None):
    domain = domain or domain_from_current_request()
    return qs.filter(
        Q(from_location__stock_domain=domain) | Q(to_location__stock_domain=domain)
    ).distinct()


def transfer_visible_in_domain(transfer, domain: str | None = None) -> bool:
    domain = domain or domain_from_current_request()
    from_domain = getattr(getattr(transfer, 'from_location', None), 'stock_domain', None)
    to_domain = getattr(getattr(transfer, 'to_location', None), 'stock_domain', None)
    return domain in (from_domain, to_domain)


def apply_stock_domain_on_create(instance) -> None:
    """Gán domain kho vật tư khi tạo từ request /kho-vat-tu/; không ghi đè seed."""
    if getattr(instance, 'pk', None):
        return
    if domain_from_current_request() == STOCK_DOMAIN_VAT_TU:
        instance.stock_domain = STOCK_DOMAIN_VAT_TU
