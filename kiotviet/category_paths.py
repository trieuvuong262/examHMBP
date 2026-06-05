"""Đường dẫn nhóm hàng đầy đủ từ cây kv_category (tối đa 3 cấp KiotViet)."""

from __future__ import annotations

from .models import KvCategory, KvProduct

PATH_SEP = ' › '


class CategoryPathResolver:
    """Resolve categoryId → chuỗi nhóm hàng từ gốc đến lá."""

    def __init__(self, retailer: str):
        self.retailer = retailer
        self._by_id: dict[int, KvCategory] = {
            row.kiotviet_id: row
            for row in KvCategory.objects.filter(retailer=retailer, is_deleted=False)
        }
        self._register_product_category_hints()

    def _register_product_category_hints(self) -> None:
        """Bổ sung nhóm có trên SP nhưng chưa có trong kv_category."""
        rows = (
            KvProduct.objects.filter(retailer=self.retailer, is_deleted=False)
            .exclude(category_kiotviet_id=None)
            .values('category_kiotviet_id', 'category_name', 'category_path')
            .distinct()
        )
        for row in rows:
            category_id = int(row['category_kiotviet_id'])
            if category_id in self._by_id:
                continue
            name = (row['category_name'] or '').strip()
            if not name and row['category_path']:
                parts = [
                    part.strip()
                    for part in (row['category_path'] or '').split(PATH_SEP)
                    if part.strip()
                ]
                name = parts[-1] if parts else ''
            if not name:
                continue
            self._by_id[category_id] = KvCategory(
                retailer=self.retailer,
                kiotviet_id=category_id,
                category_name=name,
                parent_kiotviet_id=None,
            )

    def resolve(
        self,
        category_id: int | None,
        *,
        fallback_name: str = '',
        fallback_path: str = '',
    ) -> dict:
        if fallback_path.strip():
            parts = [
                part.strip()
                for part in fallback_path.split(PATH_SEP)
                if part.strip()
            ]
            if parts:
                return {
                    'category_id': category_id,
                    'category_name': parts[-1],
                    'category_path': PATH_SEP.join(parts),
                    'category_path_parts': parts,
                }
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


def category_info_from_product(product: KvProduct, resolver: CategoryPathResolver) -> dict:
    stored_path = (product.category_path or '').strip()
    if stored_path:
        parts = [
            part.strip()
            for part in stored_path.split(PATH_SEP)
            if part.strip()
        ]
        return {
            'category_id': product.category_kiotviet_id,
            'category_name': parts[-1] if parts else (product.category_name or '—'),
            'category_path': stored_path,
            'category_path_parts': parts,
        }
    return resolver.resolve(
        product.category_kiotviet_id,
        fallback_name=product.category_name or '',
    )


def refresh_product_category_path(retailer: str, product_id: int) -> None:
    product = KvProduct.objects.filter(
        retailer=retailer,
        kiotviet_id=product_id,
        is_deleted=False,
    ).first()
    if not product:
        return
    resolver = CategoryPathResolver(retailer)
    info = resolver.resolve(
        product.category_kiotviet_id,
        fallback_name=product.category_name or '',
    )
    path = info['category_path']
    if path != (product.category_path or ''):
        KvProduct.objects.filter(pk=product.pk).update(category_path=path)


def refresh_all_product_category_paths(retailer: str) -> int:
    resolver = CategoryPathResolver(retailer)
    updated = 0
    for product in KvProduct.objects.filter(retailer=retailer, is_deleted=False).iterator():
        info = resolver.resolve(
            product.category_kiotviet_id,
            fallback_name=product.category_name or '',
        )
        path = info['category_path']
        if path != (product.category_path or ''):
            KvProduct.objects.filter(pk=product.pk).update(category_path=path)
            updated += 1
    return updated
