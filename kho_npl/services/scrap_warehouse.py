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
