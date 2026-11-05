from django.db import migrations


MAY_152A_STAGE = "MAY (152A VĨNH LỘC)"
DEFAULT_WORK_CENTER_CODE = "NL-2026-0011"


def set_default_work_center(apps, schema_editor):
    SxOperationGroup = apps.get_model("san_xuat", "SxOperationGroup")
    SxWorkCenter = apps.get_model("san_xuat", "SxWorkCenter")
    center = SxWorkCenter.objects.filter(
        code=DEFAULT_WORK_CENTER_CODE, is_demo=False, is_active=True,
    ).first()
    if center is None:
        return
    SxOperationGroup.objects.filter(
        process_stage_label=MAY_152A_STAGE, is_active=True,
    ).update(default_work_center_id=center.pk)


def unset_default_work_center(apps, schema_editor):
    SxOperationGroup = apps.get_model("san_xuat", "SxOperationGroup")
    SxOperationGroup.objects.filter(
        process_stage_label=MAY_152A_STAGE,
        default_work_center__code=DEFAULT_WORK_CENTER_CODE,
    ).update(default_work_center_id=None)


class Migration(migrations.Migration):
    dependencies = [("san_xuat", "0159_sxsubcontractmaterialline_confirm_note_and_more")]
    operations = [migrations.RunPython(set_default_work_center, unset_default_work_center)]
