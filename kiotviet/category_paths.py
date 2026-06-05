"""Đường dẫn nhóm hàng đầy đủ từ cây kv_category (tối đa 3 cấp KiotViet)."""

from __future__ import annotations

from .models import KvCategory

PATH_SEP = ' › '


class CategoryPathResolver:
    """Resolve categoryId → chuỗi nhóm hàng từ gốc đến lá."""

    def __init__(self, retailer: str):
        self.retailer = retailer
        self._by_id: dict[int, KvCategory] = {
            row.kiotviet_id: row
            for row in KvCategory.objects.filter(retailer=retailer, is_deleted=False)
        }

    def resolve(
        self,
        category_id: int | None,
        *,
        fallback_name: str = '',
    ) -> dict:
        parts = self._path_parts(category_id)
        if not parts and fallback_name:
            parts = [fallback_name.strip()]
        leaf = parts[-1] if parts else (fallback_name.strip() or '—')
        path = PATH_SEP.join(parts) if parts else (fallback_name.strip() or '—')
        return {
            'category_id': category_id,
            'category_name': leaf,
            'category_path': path,
            'category_path_parts': parts,
        }

    def _path_parts(self, category_id: int | None) -> list[str]:
        if not category_id:
            return []
        parts: list[str] = []
        visited: set[int] = set()
        current_id: int | None = category_id
        while current_id and current_id not in visited:
            visited.add(current_id)
            row = self._by_id.get(current_id)
            if row is None:
                break
            name = (row.category_name or '').strip()
            if name:
                parts.append(name)
            current_id = row.parent_kiotviet_id
        parts.reverse()
        return parts
