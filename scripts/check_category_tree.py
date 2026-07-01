"""In cây nhóm NPL — chạy: python manage.py shell < scripts/check_category_tree.py hoặc exec trên container."""
from kho_npl.category_tree import active_category_roots
from kho_npl.models import MaterialCategory

roots = list(active_category_roots())
print("=== CATEGORY TREE ===")
print("roots:", len(roots))
for r in roots:
    kids = list(r.children.all())
    print(f"  [{r.code}] {r.name} children={len(kids)} -> {[c.code for c in kids]}")
print(
    "parent-null:",
    MaterialCategory.objects.filter(is_active=True, parent__isnull=True).count(),
    "| with parent:",
    MaterialCategory.objects.filter(is_active=True, parent__isnull=False).count(),
)
