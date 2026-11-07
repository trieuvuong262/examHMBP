from django.db import migrations


EXCLUDED_DIVISION_NAMES = ("QA",)


def _excluded_division_ids(apps):
    Division = apps.get_model("hrm", "Division")
    ids = set()
    for name in EXCLUDED_DIVISION_NAMES:
        ids.update(Division.objects.filter(name__iexact=name).values_list("pk", flat=True))
    return ids


def _set_active(apps, active):
    SxWorkCenter = apps.get_model("san_xuat", "SxWorkCenter")
    SxTeamDivisionMap = apps.get_model("san_xuat", "SxTeamDivisionMap")
    ids = _excluded_division_ids(apps)
    if not ids:
        return
    SxWorkCenter.objects.filter(
        code__in=[f"HRD-{pk}" for pk in ids], is_demo=False,
    ).update(is_active=active)
    SxTeamDivisionMap.objects.filter(division_id__in=ids, is_demo=False).update(is_active=active)


def hide_qa(apps, schema_editor):
    _set_active(apps, False)


def show_qa(apps, schema_editor):
    _set_active(apps, True)


class Migration(migrations.Migration):
    dependencies = [("san_xuat", "0160_may_152a_default_subcontract_center")]
    operations = [migrations.RunPython(hide_qa, show_qa)]
