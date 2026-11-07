from django.db import migrations


GH_SLUG = "gh"
GH_CODE = "GH"
GH_QC_GROUP = "QC-GH"
GH_DEFAULT_COLOR = "#f0cfe0"


def _set_active(apps, active):
    SxQcCriteria = apps.get_model("san_xuat", "SxQcCriteria")
    SxQcCriteriaGroup = apps.get_model("san_xuat", "SxQcCriteriaGroup")
    SxProcessStage = apps.get_model("san_xuat", "SxProcessStage")
    SxOperationGroup = apps.get_model("san_xuat", "SxOperationGroup")
    SxWorkCenter = apps.get_model("san_xuat", "SxWorkCenter")
    SxTeamDivisionMap = apps.get_model("san_xuat", "SxTeamDivisionMap")

    SxQcCriteria.objects.filter(team_slug=GH_SLUG).update(is_active=active)
    SxQcCriteriaGroup.objects.filter(code=GH_QC_GROUP).update(is_active=active)
    SxProcessStage.objects.filter(code=GH_CODE).update(is_active=active)
    SxOperationGroup.objects.filter(code=GH_CODE).update(is_active=active)
    SxWorkCenter.objects.filter(code=GH_CODE).update(is_active=active)
    SxTeamDivisionMap.objects.filter(team_slug=GH_SLUG).update(is_active=active)


def retire_gh(apps, schema_editor):
    _set_active(apps, False)
    apps.get_model("san_xuat", "SxTeamStageColor").objects.filter(team_slug=GH_SLUG).delete()


def restore_gh(apps, schema_editor):
    _set_active(apps, True)
    apps.get_model("san_xuat", "SxTeamStageColor").objects.get_or_create(
        team_slug=GH_SLUG, defaults={"color": GH_DEFAULT_COLOR},
    )


class Migration(migrations.Migration):
    dependencies = [("san_xuat", "0162_remove_gh_team_slug_choice")]
    operations = [migrations.RunPython(retire_gh, restore_gh)]
