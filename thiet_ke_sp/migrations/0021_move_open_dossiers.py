from django.db import migrations


def move_open_dossiers(apps, schema_editor):
    from thiet_ke_sp.models import DesignVersion, ProductDevelopment, Status, Task
    from thiet_ke_sp.services import workflow as wf

    for dossier in ProductDevelopment.objects.filter(status=Status.BRIEF_PENDING).select_related('proposer'):
        if not dossier.design_versions.exists():
            DesignVersion.objects.create(
                dossier=dossier, version_no=1, option_no=1, created_by=dossier.proposer,
            )
        wf._transition(
            dossier, Status.DESIGNING, dossier.proposer, 'brief_skipped',
            'Bỏ bước duyệt đề bài — chuyển sang thiết kế.',
        )
    for dossier in ProductDevelopment.objects.filter(status=Status.MASTER_PENDING).select_related('approver', 'proposer'):
        wf._transition(
            dossier, Status.SAMPLE_EVAL_PENDING, dossier.approver or dossier.proposer, 'step_merged',
            'Gộp duyệt mẫu chuẩn vào bước Duyệt thiết kế.',
        )
    Task.objects.filter(step=Status.HANDED_OVER, state=Task.STATE_OPEN).update(
        state=Task.STATE_CANCELLED, completed_at=wf.timezone.now(),
    )


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('thiet_ke_sp', '0020_workflow_five_steps'),
    ]

    operations = [
        migrations.RunPython(move_open_dossiers, noop),
    ]
