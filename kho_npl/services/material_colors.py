from django.db.models import Q

from kho_npl.models import MaterialColor


def resolve_material_color(name: str) -> MaterialColor | None:
    text = (name or '').strip()
    if not text:
        return None
    return MaterialColor.objects.filter(is_active=True).filter(
        Q(name__iexact=text) | Q(code__iexact=text),
    ).first()
