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
    return WarehouseLocation.objects.filter(is_active=True).exclude(code=WAREHOUSE_SCRAP_CODE)
