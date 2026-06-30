from django.db.models import Q

from kho_npl.models import MaterialSpecification


def resolve_material_specification(name: str) -> MaterialSpecification | None:
    text = (name or '').strip()
    if not text:
        return None
    return MaterialSpecification.objects.filter(is_active=True).filter(
        Q(name__iexact=text) | Q(code__iexact=text),
    ).first()
