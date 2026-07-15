"""Đồng bộ danh mục nhóm NPL một cấp."""

from kho_npl.category_tree import ensure_material_category_tree
from kho_npl.models import Material, MaterialCategory


def sync_material_category_catalog(*, backfill: bool = True) -> dict[str, int]:
    """Đồng bộ các nhóm phẳng mặc định; giữ API kết quả tương thích lệnh cũ."""
    ensure_material_category_tree()
    active_groups = MaterialCategory.objects.filter(is_active=True).count()
    active_materials = Material.objects.filter(is_active=True).count()
    return {
        'roots': active_groups,
        'leaves': active_groups,
        'assigned': 0,
        'skipped': 0,
        'deactivated_legacy': 0,
        'materials_with_parent': 0,
        'materials_active': active_materials,
    }
