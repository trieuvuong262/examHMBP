from kho_npl.stock_domain import (
    NS_KHO_NPL,
    NS_KHO_VAT_TU,
    STOCK_DOMAIN_NPL,
    STOCK_DOMAIN_VAT_TU,
    domain_from_request,
    domain_label,
    item_label,
    item_label_short,
    kind_label,
    module_key_from_request,
    namespace_from_request,
)


def stock_module(request):
    domain = domain_from_request(request)
    return {
        'stock_domain': domain,
        'stock_ns': namespace_from_request(request),
        'stock_module_key': module_key_from_request(request),
        'stock_module_label': domain_label(domain),
        'stock_item_label': item_label(domain),
        'stock_item_label_short': item_label_short(domain),
        'stock_kind_label': kind_label(domain),
        'is_kho_vat_tu': domain == STOCK_DOMAIN_VAT_TU,
        'NS_KHO_NPL': NS_KHO_NPL,
        'NS_KHO_VAT_TU': NS_KHO_VAT_TU,
        'STOCK_DOMAIN_NPL': STOCK_DOMAIN_NPL,
        'STOCK_DOMAIN_VAT_TU': STOCK_DOMAIN_VAT_TU,
    }
