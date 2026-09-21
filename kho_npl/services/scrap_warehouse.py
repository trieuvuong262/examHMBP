from kho_npl.choices import WAREHOUSE_SCRAP_CODE
from kho_npl.models import WarehouseLocation
from kho_npl.stock_domain import (
    STOCK_DOMAIN_ALL,
    STOCK_DOMAIN_NPL,
    domain_from_current_request,
)

SCRAP_WAREHOUSE_NAME = 'Kho hủy'
SCRAP_WAREHOUSE_NAME_VAT_TU = 'Kho hủy vật tư'


class ScrapWarehouseError(Exception):
    pass


def is_scrap_location(location) -> bool:
    return bool(location) and getattr(location, 'code', None) == WAREHOUSE_SCRAP_CODE


def get_scrap_location(domain: str | None = None) -> WarehouseLocation:
    """Kho hủy là vị trí hệ thống — luôn lấy theo mã + domain, kể cả khi bị ngừng dùng."""
    domain = domain or domain_from_current_request()
    location = WarehouseLocation.objects.filter(
        code=WAREHOUSE_SCRAP_CODE,
        stock_domain=domain,
    ).first()
    scrap_name = SCRAP_WAREHOUSE_NAME_VAT_TU if domain != STOCK_DOMAIN_NPL else SCRAP_WAREHOUSE_NAME
    if not location:
        return WarehouseLocation.objects.create(
            code=WAREHOUSE_SCRAP_CODE,
            name=scrap_name,
            is_active=True,
            location_kind=WarehouseLocation.KIND_SCRAP,
            stock_domain=domain,
        )

    update_fields = []
    if not location.is_active:
        location.is_active = True
        update_fields.append('is_active')
    if location.location_kind != WarehouseLocation.KIND_SCRAP:
        location.location_kind = WarehouseLocation.KIND_SCRAP
        update_fields.append('location_kind')
    if not (location.name or '').strip():
        location.name = scrap_name
        update_fields.append('name')
    if getattr(location, 'stock_domain', None) != domain:
        location.stock_domain = domain
        update_fields.append('stock_domain')
    if update_fields:
        location.save(update_fields=update_fields)
    return location


def source_locations_qs(domain: str | None = None):
    """Kho/vị trí chứa hàng dùng được — không gồm kho hủy.

    ``domain=None`` → theo request hiện tại (NPL hoặc vật tư).
    ``domain=STOCK_DOMAIN_ALL`` → cả hai kho (phiếu chuyển liên module).
    """
    qs = WarehouseLocation.objects.filter(is_active=True).exclude(code=WAREHOUSE_SCRAP_CODE)
    if domain == STOCK_DOMAIN_ALL:
        return qs
    if domain is None:
        domain = domain_from_current_request()
    return qs.filter(stock_domain=domain)


def storage_location_filter():
    """Q filter loại kho hủy khỏi queryset có FK location."""
    return {'location__code': WAREHOUSE_SCRAP_CODE}


def exclude_scrap_locations(qs):
    """Loại bản ghi thuộc kho hủy khỏi queryset có FK location."""
    return qs.exclude(**storage_location_filter())


def filter_storage_location_ids(location_ids: list[int] | None) -> list[int]:
    """Giữ lại id vị trí chứa hàng (bỏ kho hủy nếu có trong URL)."""
    if not location_ids:
        return []
    storage_ids = set(source_locations_qs().filter(pk__in=location_ids).values_list('pk', flat=True))
    return [loc_id for loc_id in location_ids if loc_id in storage_ids]


def fallback_stock_location(domain: str | None = None) -> WarehouseLocation | None:
    """Kho gợi ý khi NPL chưa gán vị trí mặc định — ưu tiên MAIN của domain."""
    qs = source_locations_qs(domain)
    return qs.filter(code='MAIN').first() or qs.order_by('code').first()


def is_usable_storage_location(location: WarehouseLocation | None) -> bool:
    if location is None or not location.is_active:
        return False
    return location.code != WAREHOUSE_SCRAP_CODE


def material_default_location(material) -> WarehouseLocation | None:
    """Vị trí mặc định trên danh mục; fallback MAIN nếu chưa gán."""
    loc = getattr(material, 'primary_location', None) if material is not None else None
    domain = getattr(material, 'stock_domain', None) if material is not None else None
    if loc is None and material is not None:
        loc_id = getattr(material, 'primary_location_id', None)
        if loc_id:
            loc = source_locations_qs(domain).filter(pk=loc_id).first()
    if is_usable_storage_location(loc):
        return loc
    return fallback_stock_location(domain)
