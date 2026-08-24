from kho_npl.choices import WAREHOUSE_SCRAP_CODE
from kho_npl.models import WarehouseLocation


class ScrapWarehouseError(Exception):
    pass


def get_scrap_location() -> WarehouseLocation:
    location = WarehouseLocation.objects.filter(code=WAREHOUSE_SCRAP_CODE, is_active=True).first()
    if not location:
        raise ScrapWarehouseError(f'Chưa cấu hình kho hủy (mã {WAREHOUSE_SCRAP_CODE}).')
    return location


def source_locations_qs():
    """Kho/vị trí chứa hàng dùng được — không gồm kho hủy."""
    return WarehouseLocation.objects.filter(is_active=True).exclude(code=WAREHOUSE_SCRAP_CODE)


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


def fallback_stock_location() -> WarehouseLocation | None:
    """Kho gợi ý khi NPL chưa gán vị trí mặc định — ưu tiên MAIN."""
    return (
        source_locations_qs().filter(code='MAIN').first()
        or source_locations_qs().order_by('code').first()
    )


def is_usable_storage_location(location: WarehouseLocation | None) -> bool:
    if location is None or not location.is_active:
        return False
    return location.code != WAREHOUSE_SCRAP_CODE


def material_default_location(material) -> WarehouseLocation | None:
    """Vị trí mặc định trên danh mục NPL; fallback MAIN nếu chưa gán."""
    loc = getattr(material, 'primary_location', None) if material is not None else None
    if loc is None and material is not None:
        loc_id = getattr(material, 'primary_location_id', None)
        if loc_id:
            loc = source_locations_qs().filter(pk=loc_id).first()
    if is_usable_storage_location(loc):
        return loc
    return fallback_stock_location()
